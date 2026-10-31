import os, sys, json, hashlib, glob
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.baselines import apply_b1, apply_b2, apply_b3
from reconstruction.pipeline import run_toolkit
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.plots import plot_by_system, TOOLKIT_COLOUR

# Stage 8: scores B0, B1, B2 (pair-only), B3 (closest in time) and the toolkit on seed 42 and on two
# extra seeds (7, 123) that were generated AFTER the toolkit design was frozen. The frozen file hashes
# are checked first, so no rule can have changed after seeing the extra seeds.

RESULTS = os.path.join(ROOT, "results")
FREEZE_FILE = os.path.join(ROOT, "evaluation", "toolkit_freeze.json")     # in git, unlike results/
SEEDS = {42: os.path.join(ROOT, "data", "messy"),
         7: os.path.join(ROOT, "data", "seeds", "seed7"),
         123: os.path.join(ROOT, "data", "seeds", "seed123")}
TAGS = {"sev0_05": 0.05, "sev0_15": 0.15, "sev0_3": 0.30}
MAPPING = SchemaMapping("record_id", "activity_name", "event_time", "item_id",
                        "item_category", "linked_item_id", "link_type", "role")
SYSTEMS = {"B0 (as-is)": lambda t: (t, {}, None),
           "B1 (hygiene)": lambda t: (*apply_b1(t), None),
           "B2 (pair-only)": lambda t: (*apply_b2(t, max_group=2), None),
           "B3 (closest in time)": lambda t: run_toolkit(t, identity_decision="closest"),
           "Toolkit": lambda t: run_toolkit(t)}
FIGURE_SYSTEMS = list(SYSTEMS)
FIGURE_COLOURS = ["#f0f0f0", "#bdbdbd", "#969696", "#525252", TOOLKIT_COLOUR]
KEY = [("labels", "distorted_restored"), ("timestamps", "drifted_restored_exactly"),
       ("identity", "precision"), ("identity", "recall"), ("identity", "f1"), ("identity", "false_merges"),
       ("e2o", "affected_recall"), ("o2o", "affected_recall"), ("usefulness", "edge_f1"),
       ("usefulness", "edge_frequency_difference"), ("usefulness", "object_count_abs_difference"),
       ("usefulness", "object_count_difference[SteelSheet]")]


def _variants(data):
    # Git on Windows (core.autocrlf) can switch a file between LF and CRLF on checkout without changing its
    # content, so a file counts as unchanged if its raw, LF or CRLF form matches the frozen hash.
    lf = data.replace(b"\r\n", b"\n")
    return {hashlib.sha256(v).hexdigest() for v in (data, lf, lf.replace(b"\n", b"\r\n"))}


def toolkit_files():
    files = sorted(glob.glob(os.path.join(ROOT, "reconstruction", "*.py")))
    return {os.path.relpath(f, ROOT).replace("\\", "/"): open(f, "rb").read() for f in files}


def toolkit_hashes():
    """LF-normalised SHA-256 per toolkit file (used for new freeze records)."""
    return {f: hashlib.sha256(d.replace(b"\r\n", b"\n")).hexdigest() for f, d in toolkit_files().items()}


def write_freeze():
    """Record the toolkit design freeze. Refuses to overwrite an existing record."""
    import datetime
    assert not os.path.exists(FREEZE_FILE), f"{FREEZE_FILE} exists; a freeze is never overwritten"
    record = {"frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "note": "Design frozen after unit tests passed, before any real-data run. No rule may change after this.",
              "files": toolkit_hashes()}
    with open(FREEZE_FILE, "w") as f:
        json.dump(record, f, indent=2)
    print(f"Freeze recorded in {FREEZE_FILE}")


def check_freeze():
    frozen = json.load(open(FREEZE_FILE))
    now = toolkit_files()
    changed = [f for f, h in frozen["files"].items() if f not in now or h not in _variants(now[f])]
    assert not changed, f"toolkit files changed since the freeze: {changed}"
    print(f"Design freeze verified: {len(frozen['files'])} toolkit files unchanged since {frozen['frozen_at']}")


def load_messy(folder, tag):
    f = lambda n: pd.read_csv(os.path.join(folder, f"messy_{n}_{tag}.csv"), low_memory=False)
    return {k: apply_mapping(f(k), MAPPING, k) for k in ("events", "objects", "relations", "o2o")}


def losses(pairs, truth, system, seed, sev):
    """DIAGNOSTIC (uses ground truth): where each true clone pair ends up."""
    status = {} if pairs is None or not len(pairs) else \
        {frozenset((a, b)): s for a, b, s in zip(pairs["a"], pairs["b"], pairs["status"])}
    counts = {"lost at blocking": 0, "non-match (< 0.5)": 0, "possible-match band (0.5-0.9)": 0,
              "ambiguity rule": 0, "one-to-one conflict": 0, "merged": 0}
    name = {"non_match": "non-match (< 0.5)", "possible": "possible-match band (0.5-0.9)",
            "ambiguous": "ambiguity rule", "conflict": "one-to-one conflict", "merged": "merged"}
    for pair in truth.clone_pairs:
        counts[name[status[pair]] if pair in status else "lost at blocking"] += 1
    return [{"system": system, "seed": seed, "severity": sev, "step": k, "true_pairs": v} for k, v in counts.items()]


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        write_freeze()
        sys.exit(0)
    check_freeze()
    clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
    tables, loss_rows, reports, mu_rows = [], [], [], []
    for seed, folder in SEEDS.items():
        for tag, sev in TAGS.items():
            truth = build_truth(clean, load_ground_truth(os.path.join(folder, f"ground_truth_{tag}.json")))
            messy = load_messy(folder, tag)
            for name, run in SYSTEMS.items():
                recon, report, pairs = run(messy)
                tables.append(score(recon, messy, truth, clean, system=name, severity=sev).assign(seed=seed))
                if name in ("Toolkit", "B3 (closest in time)"):
                    loss_rows += losses(pairs, truth, name, seed, sev)
                if name == "Toolkit":
                    idr = report["identity"]
                    reports.append({"seed": seed, "severity": sev, "fragments": idr["fragments"],
                                    "complementary_pairs": idr["complementary_pairs"],
                                    "candidate_pairs": idr["candidate_pairs"], "hub_cutoff": idr["hub_cutoff"],
                                    "match_share": round(next(iter(idr["match_share"].values()), float("nan")), 4),
                                    "timestamp_repair": report["timestamps"]["status"], **idr["status_counts"]})
                    for typ, rows in idr["m_u_tables"].items():
                        mu_rows += [{"seed": seed, "severity": sev, "type": typ, **r} for r in rows]
            print(f"done: seed {seed}, {tag}")

    # Clean baseline: the toolkit on the undamaged log must change nothing
    clean_out, clean_report, _ = run_toolkit(clean)
    clean_scores = score(clean_out, clean, build_truth(clean, None), clean, system="Toolkit (clean log)", severity=0.0)
    tables.append(clean_scores.assign(seed=0))

    table = pd.concat(tables, ignore_index=True)[["system", "seed", "severity", "area", "metric", "value"]]
    os.makedirs(RESULTS, exist_ok=True)
    table.to_csv(os.path.join(RESULTS, "scores_stage8.csv"), index=False)
    pd.DataFrame(loss_rows).to_csv(os.path.join(RESULTS, "identity_losses.csv"), index=False)
    pd.DataFrame(reports).to_csv(os.path.join(RESULTS, "identity_reports.csv"), index=False)
    pd.DataFrame(mu_rows).to_csv(os.path.join(RESULTS, "identity_m_u_tables.csv"), index=False)
    plot_by_system(table[table.seed == 42], FIGURE_SYSTEMS, FIGURE_COLOURS,
                   os.path.join(RESULTS, "figures", "scores_by_system_stage8.png"),
                   "Seed 42: baselines and toolkit scored against the clean log")

    pd.set_option("display.width", 250), pd.set_option("display.max_columns", 30), pd.set_option("display.max_rows", 200)
    get = lambda t: t.set_index(["system", "seed", "severity", "area", "metric"])["value"]
    v = get(table)
    print("\n=== Seed 42 (key metrics) ===")
    s42 = table[(table.seed == 42)].set_index(["area", "metric", "system", "severity"])["value"].unstack(["system"])
    for a, m in KEY:
        print(f"\n{a} / {m}")
        print(s42.loc[(a, m)][FIGURE_SYSTEMS].to_string(float_format="{:.4f}".format))
    print("\n=== All three seeds: mean [min, max] (seed 42, 7, 123; seeds 7 and 123 run once on the frozen design) ===")
    seeds = table[table.seed.isin(list(SEEDS))]
    agg = seeds.groupby(["area", "metric", "system", "severity"])["value"].agg(["mean", "min", "max"])
    for a, m in KEY:
        print(f"\n{a} / {m}")
        sub = agg.loc[(a, m)]
        print(sub.apply(lambda r: f"{r['mean']:.4f} [{r['min']:.4f}, {r['max']:.4f}]", axis=1)
              .unstack("severity").loc[FIGURE_SYSTEMS].to_string())
    print("\n=== Toolkit internals per run ===")
    print(pd.DataFrame(reports).to_string(index=False))
    print("\n=== DIAGNOSTIC (ground truth): where the true clone pairs end up, Toolkit ===")
    L = pd.DataFrame(loss_rows)
    print(L[L.system == "Toolkit"].pivot_table(index="step", columns=["seed", "severity"], values="true_pairs", sort=False)
          .to_string())
    print("\n=== Clean baseline (toolkit on the undamaged log) ===")
    cb = clean_scores.set_index(["area", "metric"])["value"]
    print(f"merged pairs {clean_report['identity']['merged_pairs']}, fragments {clean_report['identity']['fragments']}, "
          f"labels changed {clean_report['labels_changed']}, timestamp repair: {clean_report['timestamps']['status']}, "
          f"identity false merges {int(cb[('identity', 'false_merges')])}, E2O F1 {cb[('e2o', 'f1')]:.4f}, "
          f"O2O F1 {cb[('o2o', 'f1')]:.4f}, label accuracy {cb[('labels', 'accuracy')]:.4f}")

    assert clean_report["identity"]["merged_pairs"] == 0, "toolkit merged objects in the clean log"
    assert cb[("labels", "accuracy")] == 1.0 and cb[("e2o", "f1")] == 1.0 and cb[("o2o", "f1")] == 1.0
    for seed in SEEDS:
        for sev in TAGS.values():
            for s in SYSTEMS:
                assert v[(s, seed, sev, "validity", "relations_unknown_object")] == 0, f"{s} dangling"
                assert v[(s, seed, sev, "events", "missing_events")] == 0
    print("\nSaved results/scores_stage8.csv, identity_losses.csv, identity_reports.csv, identity_m_u_tables.csv, "
          "figures/scores_by_system_stage8.png")
    print("NOTE: seeds 7 and 123 were generated after the design was frozen and run once; no rule was changed after seeing them.")
    print("ALL STAGE 8 CHECKS PASSED")
