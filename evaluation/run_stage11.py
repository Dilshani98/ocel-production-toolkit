import os, sys, json, time, shutil, tempfile, sqlite3
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
import pm4py
from pm4py.objects.ocel.validation import ocel20_rel_validation
from reconstruction.complete import run_complete_toolkit
from reconstruction.export import write, read, from_ocel, file_objects
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.run_stage8 import toolkit_files, _variants, load_messy, SEEDS, TAGS

# Stage 11: export the complete toolkit's output as OCEL 2.0 (SQLite with the specification's keys, XML, JSON),
# read every file back, and check that nothing measurable changes and that each file is valid.
#   Validity: the 24 OCEL 2.0 relational constraints (pm4py's validator) and SQLite's foreign-key check.
#   Round trip: counts (through pm4py and directly in the file), links, timestamps, activities, and scores.
#   No schema checks: pm4py's XSD rejects the published sOCEL 2.0 file, and its JSON schema requires string
#   values that the OCEL 2.0 specification does not require (see evaluation/schemas/SOURCES.json).
#   The clusters table (which IDs the toolkit merged) is toolkit metadata, not part of OCEL 2.0; it is carried
#   over to the re-read log only for scoring, where only the identity evaluation reads it.
#   Safety check: the reconstruction scores must equal results/scores_stage10.csv exactly.
# The clean log with all its attributes is the control. Seed 42 is the development seed; 7 and 123 are held out.

RESULTS = os.path.join(ROOT, "results")
EXPORTS = os.path.join(RESULTS, "exports")
FREEZES = [os.path.join(ROOT, "evaluation", f) for f in ("toolkit_freeze.json", "toolkit_freeze_stage9.json",
                                                         "toolkit_freeze_stage10.json", "toolkit_freeze_stage11.json")]
SEED_ROLE = {42: "development", 7: "held-out", 123: "held-out"}
STAGE10 = os.path.join(RESULTS, "scores_stage10.csv")


def check_freezes():
    now = toolkit_files()
    for path in FREEZES:
        record = json.load(open(path))
        files = record["files"]
        for amendment in record.get("amendments", []):
            files = {**files, **amendment["files"]}         # an amendment supersedes the hashes it lists
        changed = [f for f, h in files.items() if f not in now or h not in _variants(now[f])]
        assert not changed, f"{os.path.basename(path)}: toolkit files changed since the freeze: {changed}"
        note = f", amended {record['amendments'][-1]['date']}" if record.get("amendments") else ""
        print(f"Freeze verified ({os.path.basename(path)}): {len(files)} files unchanged since {record['frozen_at']}{note}")


def link_sets(t):
    return (set(zip(t["relations"]["_record_id"], t["relations"]["_item_id"], t["relations"]["_role"])),
            set(zip(t["o2o"]["_item_id"], t["o2o"]["_linked_item_id"], t["o2o"]["_link_type"])))


def check_file(fmt, path, original, scored=None):
    """Read one exported file back and run every check. scored = (messy, truth, clean, in-memory score table)."""
    t0 = time.time()
    back = read(path, fmt)
    row = {"format": fmt, "size_mb": round(os.path.getsize(path) / 1e6, 1), "read_s": round(time.time() - t0, 1)}
    row["counts_equal"] = all(len(back[k]) == len(original[k]) for k in ("events", "objects", "relations", "o2o"))
    row["file_objects_equal"] = len(file_objects(path, fmt)) == original["objects"]["_item_id"].nunique()
    row["links_equal"] = link_sets(back) == link_sets(original)
    ts = lambda t: pd.to_datetime(t["events"].set_index("_record_id")["_timestamp"], utc=True, format="mixed").sort_index()
    row["timestamps_equal"] = ts(back).equals(ts(original))
    acts = lambda t: t["events"].set_index("_record_id")["_activity"].sort_index()
    row["activities_equal"] = acts(back).equals(acts(original))
    if scored is not None:
        messy, truth, clean, before = scored
        back["clusters"] = original.get("clusters")        # toolkit metadata, not part of OCEL 2.0
        after = score(back, messy, truth, clean, system="re-read", severity=None)
        diff = (before["value"].values - after["value"].values)
        row["scores_equal"] = bool(len(before) == len(after) and abs(diff).max() < 1e-12)
    if fmt == "sqlite":
        ok, bad = ocel20_rel_validation.apply(path)
        con = sqlite3.connect(path)
        row["fk_violations"] = len(con.execute("PRAGMA foreign_key_check").fetchall())
        con.close()
        row["constraints_satisfied"], row["constraints_unsatisfied"] = len(ok), ";".join(bad)
    return row


def check_against_stage10(before, seed, sev, stage10):
    ref = stage10[(stage10.system == "Toolkit") & (stage10.seed == seed) & (stage10.severity == sev)]
    merged = before.merge(ref[["area", "metric", "value"]], on=["area", "metric"], how="outer",
                          suffixes=("_now", "_stage10"), indicator=True)
    differ = merged[(merged["_merge"] != "both") | (merged["value_now"] != merged["value_stage10"])]
    assert len(ref) and differ.empty, (f"seed {seed} severity {sev}: reconstruction scores differ from stage 10:\n"
                                       f"{differ[['area', 'metric', 'value_now', 'value_stage10']].to_string()}")
    return len(ref)


if __name__ == "__main__":
    check_freezes()
    stage10 = pd.read_csv(STAGE10, float_precision="round_trip")   # pandas' default parser loses the last bit
    os.makedirs(EXPORTS, exist_ok=True)
    tmp = tempfile.mkdtemp()
    rows = []
    try:
        # Control: the clean log as distributed, with all its event and object attributes
        clean_full = from_ocel(pm4py.read_ocel2_xml(os.path.join(ROOT, "socel2_hinge.xml")))
        clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
        for fmt in ("sqlite", "xml", "json"):
            path = os.path.join(EXPORTS if fmt == "sqlite" else tmp, f"clean_log.{fmt}")
            t0 = time.time()
            write(clean_full, path, fmt)
            row = check_file(fmt, path, clean_full)
            row.update({"seed": 0, "seed_role": "clean log", "severity": 0.0, "write_s": round(time.time() - t0, 1),
                        "isolated_objects": int((~clean_full["objects"]["_item_id"].isin(clean_full["relations"]["_item_id"])).sum())})
            rows.append(row)
        print("done: clean log (control)")

        for seed, folder in SEEDS.items():
            for tag, sev in TAGS.items():
                truth = build_truth(clean, load_ground_truth(os.path.join(folder, f"ground_truth_{tag}.json")))
                messy = load_messy(folder, tag)
                out, report, _ = run_complete_toolkit(messy)
                before = score(out, messy, truth, clean, system="in-memory", severity=None)
                n_ref = check_against_stage10(before, seed, sev, stage10)
                isolated = int((~out["objects"]["_item_id"].isin(out["relations"]["_item_id"])).sum())
                for fmt in ("sqlite", "xml", "json"):
                    path = os.path.join(EXPORTS if fmt == "sqlite" else tmp, f"toolkit_seed{seed}_{tag}.{fmt}")
                    t0 = time.time()
                    write(out, path, fmt)
                    w = round(time.time() - t0, 1)
                    row = check_file(fmt, path, out, (messy, truth, clean, before))
                    row.update({"seed": seed, "seed_role": SEED_ROLE[seed], "severity": sev, "write_s": w,
                                "isolated_objects": isolated, "stage10_scores_equal": True})
                    rows.append(row)
                    if fmt != "sqlite":
                        os.remove(path)                    # keep only the keyed SQLite files on disk
                print(f"done: seed {seed} ({SEED_ROLE[seed]}), {tag}: {n_ref} reconstruction scores equal stage 10")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    table = pd.DataFrame(rows)
    cols = ["seed", "seed_role", "severity", "format", "size_mb", "write_s", "read_s", "isolated_objects",
            "counts_equal", "file_objects_equal", "links_equal", "timestamps_equal", "activities_equal", "scores_equal",
            "stage10_scores_equal", "constraints_satisfied", "constraints_unsatisfied", "fk_violations"]
    table = table[[c for c in cols if c in table.columns]]
    table.to_csv(os.path.join(RESULTS, "export_validation.csv"), index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 100):
        print(table.to_string(index=False))

    checks = ["counts_equal", "file_objects_equal", "links_equal", "timestamps_equal", "activities_equal"]
    data, ctrl = table[table.seed != 0], table[table.seed == 0]
    for role in ("development", "held-out"):
        sub = data[data.seed_role == role]
        print(f"\n{role}: {len(sub)} exported files; " + ", ".join(f"{c} {int(sub[c].sum())}/{len(sub)}"
                                                                for c in checks + ["scores_equal"])
              + f"; SQLite 24/24 constraints {int((sub.constraints_satisfied == 24).sum())}/{int((sub.format == 'sqlite').sum())}"
              + f"; isolated objects restored per run {sorted(set(sub.isolated_objects))}")
    print(f"clean log (control): " + ", ".join(f"{c} {int(ctrl[c].sum())}/3" for c in checks)
          + f"; SQLite constraints {int(ctrl.constraints_satisfied.dropna().iloc[0])}/24")

    failed = [c for c in checks + ["scores_equal"] if not data[c].all()] + \
             [f"control {c}" for c in checks if not ctrl[c].all()]
    sq = table[table.format == "sqlite"]
    if not ((sq.constraints_satisfied == 24).all() and (sq.fk_violations == 0).all()):
        failed.append("SQLite constraints")
    print("\nSaved results/export_validation.csv and keyed SQLite files in results/exports/")
    print("NOTE: seed 42 is the development seed; seeds 7 and 123 are held out.")
    assert not failed, f"STAGE 11 CHECKS FAILED: {failed}"
    print("ALL STAGE 11 CHECKS PASSED")
