import os, sys, json, time, hashlib, shutil, tempfile, sqlite3
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
import pm4py
from pm4py.objects.ocel.validation import ocel20_rel_validation, xmlocel, jsonocel
from reconstruction.complete import run_complete_toolkit
from reconstruction.export import write, read, to_ocel
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.run_stage8 import toolkit_files, _variants, load_messy, SEEDS, TAGS

# Stage 11: export the complete toolkit's output as OCEL 2.0 (SQLite with the specification's keys, XML, JSON),
# read every file back, and check that nothing measurable changes and that each file is valid:
#   - SQLite: the 24 OCEL 2.0 relational constraints (pm4py's validator) and SQLite's foreign-key check;
#   - XML and JSON: validation against the schema files in evaluation/schemas/ (sources in SOURCES.json).
# The clean log is the control. Seed 42 is the development seed; seeds 7 and 123 are held out.

RESULTS = os.path.join(ROOT, "results")
EXPORTS = os.path.join(RESULTS, "exports")
SCHEMAS = os.path.join(ROOT, "evaluation", "schemas")
FREEZES = [os.path.join(ROOT, "evaluation", f) for f in ("toolkit_freeze.json", "toolkit_freeze_stage9.json",
                                                         "toolkit_freeze_stage10.json", "toolkit_freeze_stage11.json")]
SEED_ROLE = {42: "development", 7: "held-out", 123: "held-out"}


def check_freezes():
    now = toolkit_files()
    for path in FREEZES:
        record = json.load(open(path))
        changed = [f for f, h in record["files"].items() if f not in now or h not in _variants(now[f])]
        assert not changed, f"{os.path.basename(path)}: toolkit files changed since the freeze: {changed}"
        print(f"Freeze verified ({os.path.basename(path)}): {len(record['files'])} files unchanged "
              f"since {record['frozen_at']}")


def load_schemas():
    """Supporting schema files (pm4py's, see SOURCES.json). They are not stored in git (AGPL-3.0): a missing file is
    downloaded from its pinned commit URL, and every file must match its recorded SHA-256 before use."""
    import urllib.request
    sources = json.load(open(os.path.join(SCHEMAS, "SOURCES.json")))
    paths = {}
    for fmt in ("xml", "json"):
        entry = sources[fmt]
        path = os.path.join(SCHEMAS, entry["file"])
        if not os.path.exists(path):
            print(f"Downloading {entry['file']} from {entry['url']}")
            urllib.request.urlretrieve(entry["url"], path)
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert digest == entry["sha256"], f"{entry['file']}: SHA-256 {digest} does not match SOURCES.json"
        paths[fmt] = path
        print(f"Schema ({fmt}, supporting check): {entry['path']} @ {entry['commit'][:12]} "
              f"(SHA-256 {digest[:12]}... verified)")
    return paths


def link_sets(t):
    return (set(zip(t["relations"]["_record_id"], t["relations"]["_item_id"], t["relations"]["_role"])),
            set(zip(t["o2o"]["_item_id"], t["o2o"]["_linked_item_id"], t["o2o"]["_link_type"])))


def check_file(name, fmt, path, original, schemas, scored=None):
    """Read one exported file back and run every check. scored = (messy, truth, clean, in-memory score table)."""
    t0 = time.time()
    back = read(path, fmt)
    row = {"run": name, "format": fmt, "size_mb": round(os.path.getsize(path) / 1e6, 1), "read_s": round(time.time() - t0, 1)}
    row["counts_equal"] = all(len(back[k]) == len(original[k]) for k in ("events", "objects", "relations", "o2o"))
    row["links_equal"] = link_sets(back) == link_sets(original)
    ts = lambda t: pd.to_datetime(t["events"].set_index("_record_id")["_timestamp"], utc=True, format="mixed").sort_index()
    row["timestamps_equal"] = ts(back).equals(ts(original))
    acts = lambda t: t["events"].set_index("_record_id")["_activity"].sort_index()
    row["activities_equal"] = acts(back).equals(acts(original))
    if scored is not None:
        messy, truth, clean, before = scored
        after = score(back, messy, truth, clean, system="re-read", severity=None)
        diff = (before["value"].values - after["value"].values)
        row["scores_equal"] = bool(len(before) == len(after) and abs(diff).max() < 1e-12)
    if fmt == "sqlite":
        ok, bad = ocel20_rel_validation.apply(path)
        con = sqlite3.connect(path)
        row["fk_violations"] = len(con.execute("PRAGMA foreign_key_check").fetchall())
        con.close()
        row["constraints_satisfied"], row["constraints_unsatisfied"] = len(ok), ";".join(bad)
    else:
        row["schema_valid"] = bool((xmlocel if fmt == "xml" else jsonocel).apply(path, schemas[fmt]))
    return row


if __name__ == "__main__":
    check_freezes()
    schemas = load_schemas()
    os.makedirs(EXPORTS, exist_ok=True)
    tmp = tempfile.mkdtemp()
    rows = []
    try:
        # Control: the clean log as distributed, written by pm4py, keys added, validated the same way
        clean_ocel = pm4py.read_ocel2_xml(os.path.join(ROOT, "socel2_hinge.xml"))
        clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
        for fmt in ("sqlite", "xml", "json"):
            path = os.path.join(EXPORTS if fmt == "sqlite" else tmp, f"clean_log.{fmt}")
            t0 = time.time()
            write(clean, path, fmt)
            row = check_file("clean log", fmt, path, clean, schemas)
            row.update({"seed": 0, "seed_role": "clean log", "severity": 0.0, "write_s": round(time.time() - t0, 1)})
            rows.append(row)
        control = pd.DataFrame(rows)
        print("clean log (control):")
        print(control[["format", "counts_equal", "links_equal", "timestamps_equal", "activities_equal"] +
                      [c for c in ("schema_valid", "constraints_satisfied", "fk_violations") if c in control]].to_string(index=False))
        schema_ok = bool(control["schema_valid"].dropna().all()) and control["schema_valid"].notna().sum() == 2
        if not schema_ok:
            raise SystemExit("STOP: the clean log (a log known to be valid) fails the supporting schemas, "
                             "so they are not trustworthy here. No toolkit output was validated.")
        if "--control-only" in sys.argv:
            raise SystemExit("Control passed (--control-only: toolkit outputs not run).")

        for seed, folder in SEEDS.items():
            for tag, sev in TAGS.items():
                truth = build_truth(clean, load_ground_truth(os.path.join(folder, f"ground_truth_{tag}.json")))
                messy = load_messy(folder, tag)
                out, report, _ = run_complete_toolkit(messy)
                before = score(out, messy, truth, clean, system="in-memory", severity=None)
                for fmt in ("sqlite", "xml", "json"):
                    path = os.path.join(EXPORTS if fmt == "sqlite" else tmp, f"toolkit_seed{seed}_{tag}.{fmt}")
                    t0 = time.time()
                    write(out, path, fmt)
                    w = round(time.time() - t0, 1)
                    row = check_file(f"seed {seed} {tag}", fmt, path, out, schemas, (messy, truth, clean, before))
                    row.update({"seed": seed, "seed_role": SEED_ROLE[seed], "severity": sev, "write_s": w})
                    rows.append(row)
                    if fmt != "sqlite":
                        os.remove(path)                    # keep only the keyed SQLite files on disk
                print(f"done: seed {seed} ({SEED_ROLE[seed]}), {tag}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    table = pd.DataFrame(rows)
    cols = ["seed", "seed_role", "severity", "format", "size_mb", "write_s", "read_s", "counts_equal", "links_equal",
            "timestamps_equal", "activities_equal", "scores_equal", "schema_valid", "constraints_satisfied",
            "constraints_unsatisfied", "fk_violations"]
    table = table[[c for c in cols if c in table.columns]]
    table.to_csv(os.path.join(RESULTS, "export_validation.csv"), index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 100):
        print(table.to_string(index=False))

    data = table[table.seed != 0]
    checks = ["counts_equal", "links_equal", "timestamps_equal", "activities_equal", "scores_equal"]
    for role in ("development", "held-out"):
        sub = data[data.seed_role == role]
        print(f"\n{role}: {len(sub)} exported files; " + ", ".join(f"{c} {int(sub[c].sum())}/{len(sub)}" for c in checks)
              + f"; SQLite 24/24 constraints {int((sub.constraints_satisfied == 24).sum())}/{int((sub.format == 'sqlite').sum())}"
              + f"; schema-valid XML/JSON {int(sub.schema_valid.fillna(False).sum())}/{int(sub.format.isin(['xml', 'json']).sum())}")
    ctrl = table[table.seed == 0]
    print(f"clean log (control): SQLite constraints {int(ctrl.constraints_satisfied.dropna().iloc[0])}/24; "
          f"schema-valid XML/JSON {int(ctrl.schema_valid.fillna(False).sum())}/2")

    for c in checks:
        assert data[c].all(), f"export check failed: {c}"
    assert ctrl[["counts_equal", "links_equal", "timestamps_equal", "activities_equal"]].all().all()
    sq = table[table.format == "sqlite"]
    assert (sq.constraints_satisfied == 24).all() and (sq.fk_violations == 0).all(), "SQLite constraints failed"
    print("\nSaved results/export_validation.csv and keyed SQLite files in results/exports/")
    print("NOTE: seed 42 is the development seed; seeds 7 and 123 are held out and were exported once on the frozen design.")
    print("ALL STAGE 11 CHECKS PASSED" if table.schema_valid.dropna().all()
          else "STAGE 11: export checks passed; SOME FILES ARE NOT SCHEMA-VALID (see table)")
