import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
from reconstruction.baselines import apply_b1, apply_b2
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.score_messy import load_messy, TAGS, DATA, RESULTS
from evaluation.plots import plot_by_system, BASELINE_GREYS

# Scores B0 (messy as-is), B1 (hygiene) and B2 (exact attribute match, several group-size limits)
# at the three severities. Headline systems go in the figure; the B2 variants only in the CSV.

HEADLINE_SYSTEMS = ["B0 (as-is)", "B1 (hygiene)", "B2 (pair-only)"]
SYSTEMS = {
    "B0 (as-is)": lambda t: (t, {}),
    "B1 (hygiene)": apply_b1,
    "B2 (pair-only)": lambda t: apply_b2(t, max_group=2),
    "B2 (max_group=3)": lambda t: apply_b2(t, max_group=3),
    "B2 (max_group=5)": lambda t: apply_b2(t, max_group=5),
    "B2-all": lambda t: apply_b2(t, max_group=None),
}
SUMMARY = [("labels", "accuracy"), ("labels", "distorted_restored"), ("labels", "valid_wrongly_changed"),
           ("timestamps", "drifted_restored_exactly"),
           ("identity", "precision"), ("identity", "recall"), ("identity", "f1"),
           ("identity", "n_predicted"), ("identity", "false_merges"), ("identity", "impure_clusters"),
           ("e2o", "f1"), ("e2o", "affected_recall"), ("o2o", "f1"), ("o2o", "affected_recall"),
           ("usefulness", "edge_f1"), ("usefulness", "object_count_abs_difference"),
           ("events", "missing_events"), ("events", "extra_events")]

if __name__ == "__main__":
    clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
    tables, reports = [], []
    for tag, sev in TAGS.items():
        truth = build_truth(clean, load_ground_truth(os.path.join(DATA, f"ground_truth_{tag}.json")))
        messy = load_messy(tag)
        for name, run in SYSTEMS.items():
            recon, report = run(messy)
            tables.append(score(recon, messy, truth, clean, system=name, severity=sev))
            reports.append({"system": name, "severity": sev, **report})
    table = pd.concat(tables, ignore_index=True)

    os.makedirs(RESULTS, exist_ok=True)
    table.to_csv(os.path.join(RESULTS, "scores_baselines.csv"), index=False)
    pd.DataFrame(reports).to_csv(os.path.join(RESULTS, "baseline_actions.csv"), index=False)
    plot_by_system(table, HEADLINE_SYSTEMS, BASELINE_GREYS,
                   os.path.join(RESULTS, "figures", "scores_by_system.png"),
                   "Baselines scored against the clean log")

    get = lambda sys_, sev, a, m: table[(table.system == sys_) & (table.severity == sev) &
                                        (table.area == a) & (table.metric == m)]["value"].iloc[0]
    rows = {(a, m): {(s, sev): get(s, sev, a, m) for s in SYSTEMS for sev in TAGS.values()} for a, m in SUMMARY}
    wide = pd.DataFrame(rows).T
    with pd.option_context("display.max_rows", 100, "display.max_columns", 30, "display.width", 250,
                           "display.float_format", "{:.4f}".format):
        for sev in TAGS.values():
            print(f"\n=== severity {sev:.0%} ===")
            print(wide.xs(sev, axis=1, level=1))
        print("\n=== what each baseline did (from baseline_actions.csv) ===")
        print(pd.DataFrame(reports).set_index(["severity", "system"]).fillna(0).astype(int).to_string())
    print("\nNOTE: the headline B2 limit (max_group=2) is informed by how this dataset makes clones (each clone "
          "has exactly one original, so a true group is a pair). A real dataset may need a different limit; "
          "max_group=3, 5 and no limit are reported in the CSV for that reason.")

    for sev in TAGS.values():
        for a, m in [("labels", "accuracy"), ("timestamps", "drifted_restored_exactly"), ("e2o", "f1"),
                     ("o2o", "f1"), ("usefulness", "edge_f1"), ("identity", "f1")]:
            assert get("B1 (hygiene)", sev, a, m) == get("B0 (as-is)", sev, a, m), f"B1 differs from B0 on {a} {m}"
        merges = [get(s, sev, "identity", "n_predicted") for s in ["B2 (pair-only)", "B2 (max_group=3)",
                                                                    "B2 (max_group=5)", "B2-all"]]
        assert merges == sorted(merges), "larger group limits must predict at least as many pairs"
        assert get("B2 (pair-only)", sev, "identity", "n_predicted") > 0
        for s in SYSTEMS:
            assert get(s, sev, "validity", "relations_unknown_object") == 0, f"{s}: dangling object"
            assert get(s, sev, "events", "missing_events") == 0
    print("\nSaved results/scores_baselines.csv, results/baseline_actions.csv, results/figures/scores_by_system.png")
    print("ALL BASELINE CHECKS PASSED")
