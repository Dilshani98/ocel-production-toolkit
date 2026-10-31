import os, sys, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
from reconstruction.baselines import apply_b1, apply_b2
from reconstruction.pipeline import run_toolkit
from reconstruction.toolkit import run_b4
from reconstruction.complete import run_complete_toolkit, run_b5
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.plots import plot_by_system, TOOLKIT_COLOUR
from evaluation.run_stage8 import toolkit_files, _variants, load_messy, SEEDS, TAGS
from evaluation.run_stage9 import wilson

# Stage 10: B0-B5 and the complete toolkit (identity + missing E2O + O2O repair) on three seeds.
# Seed 42 is the DEVELOPMENT seed: the stage 10 rules were explored on it. Seeds 7 and 123 are held out
# and run once on the frozen design.

RESULTS = os.path.join(ROOT, "results")
FREEZES = [os.path.join(ROOT, "evaluation", f) for f in
           ("toolkit_freeze.json", "toolkit_freeze_stage9.json", "toolkit_freeze_stage10.json")]
SEED_ROLE = {42: "development", 7: "held-out", 123: "held-out"}
SYSTEMS = {"B0 (as-is)": lambda t: (t, {}, None),
           "B1 (hygiene)": lambda t: (*apply_b1(t), None),
           "B2 (pair-only)": lambda t: (*apply_b2(t, max_group=2), None),
           "B3 (closest in time)": lambda t: run_toolkit(t, identity_decision="closest"),
           "B4 (B3 + eager links)": run_b4,
           "B5 (toolkit, delete O2O)": run_b5,
           "Toolkit": run_complete_toolkit}
FIGURE_COLOURS = ["#ffffff", "#f0f0f0", "#d9d9d9", "#bdbdbd", "#969696", "#525252", TOOLKIT_COLOUR]
KEY = [("identity", "f1"), ("identity", "false_merges"),
       ("e2o", "precision"), ("e2o", "affected_recall"),
       ("o2o", "precision"), ("o2o", "recall"), ("o2o", "f1"), ("o2o", "affected_recall"),
       ("usefulness", "edge_frequency_difference")]


def check_freezes():
    now = toolkit_files()
    for path in FREEZES:
        record = json.load(open(path))
        changed = [f for f, h in record["files"].items() if f not in now or h not in _variants(now[f])]
        assert not changed, f"{os.path.basename(path)}: toolkit files changed since the freeze: {changed}"
        print(f"Freeze verified ({os.path.basename(path)}): {len(record['files'])} files unchanged "
              f"since {record['frozen_at']}")


def o2o_rows(decisions, truth, system, seed, sev):
    """DIAGNOSTIC (uses ground truth): was each O2O decision right?"""
    if decisions is None or decisions.empty:
        return []
    real = lambda v: truth.true_id.get(v, v)
    right = lambda s, t, q: (real(s), real(t), q) in truth.o2o
    rows = []
    for status, g in decisions.groupby("status"):
        old_right = [right(s, t, q) for s, t, q in zip(g["source"], g["old_target"], g["link_type"])]
        new_right = [right(s, t, q) if t is not None else False
                     for s, t, q in zip(g["source"], g["new_target"], g["link_type"])]
        rows.append({"system": system, "seed": seed, "seed_role": SEED_ROLE[seed], "severity": sev, "status": status,
                     "links": len(g), "old_was_right": sum(old_right),
                     "new_is_right": sum(new_right) if status == "repaired" else 0,
                     "broken": sum(o and not n for o, n in zip(old_right, new_right)) if status == "repaired" else 0,
                     "false_removals": sum(old_right) if status == "removed" else 0})
    return rows


if __name__ == "__main__":
    check_freezes()
    clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
    tables, decisions_table, reports = [], [], []
    for seed, folder in SEEDS.items():
        for tag, sev in TAGS.items():
            truth = build_truth(clean, load_ground_truth(os.path.join(folder, f"ground_truth_{tag}.json")))
            messy = load_messy(folder, tag)
            for name, run in SYSTEMS.items():
                recon, report, extra = run(messy)
                tables.append(score(recon, messy, truth, clean, system=name, severity=sev)
                              .assign(seed=seed, seed_role=SEED_ROLE[seed]))
                if isinstance(extra, dict) and "o2o_decisions" in extra:
                    decisions_table += o2o_rows(extra["o2o_decisions"], truth, name, seed, sev)
                    r = report["o2o"]
                    reports.append({"system": name, "seed": seed, "severity": sev, **{k: r[k] for k in
                                    ("links", "detected", "repaired", "flagged", "removed")},
                                    "verifiable_groups": sum(g["verifiable"] for g in r["groups"]),
                                    "groups": len(r["groups"])})
            print(f"done: seed {seed} ({SEED_ROLE[seed]}), {tag}")

    # Clean baseline: the complete toolkit on the undamaged log must change nothing
    clean_out, clean_report, _ = run_complete_toolkit(clean)
    clean_scores = score(clean_out, clean, build_truth(clean, None), clean, system="Toolkit (clean log)", severity=0.0)
    tables.append(clean_scores.assign(seed=0, seed_role="clean log"))

    table = pd.concat(tables, ignore_index=True)[["system", "seed", "seed_role", "severity", "area", "metric", "value"]]
    dec = pd.DataFrame(decisions_table)
    os.makedirs(RESULTS, exist_ok=True)
    table.to_csv(os.path.join(RESULTS, "scores_stage10.csv"), index=False)
    dec.to_csv(os.path.join(RESULTS, "o2o_diagnostics.csv"), index=False)
    pd.DataFrame(reports).to_csv(os.path.join(RESULTS, "o2o_reports.csv"), index=False)
    plot_by_system(table[table.seed == 42], list(SYSTEMS), FIGURE_COLOURS,
                   os.path.join(RESULTS, "figures", "scores_by_system_stage10.png"),
                   "Seed 42 (development seed): baselines and complete toolkit scored against the clean log")

    pd.set_option("display.width", 250), pd.set_option("display.max_columns", 30), pd.set_option("display.max_rows", 200)
    order = list(SYSTEMS)
    for role, seeds in (("DEVELOPMENT seed 42", [42]), ("HELD-OUT seeds 7 and 123: mean [min, max]", [7, 123])):
        sub = table[table.seed.isin(seeds)]
        agg = sub.groupby(["area", "metric", "system", "severity"])["value"].agg(["mean", "min", "max"])
        print(f"\n=================== {role} ===================")
        for a, m in KEY:
            print(f"\n{a} / {m}")
            fmt = (lambda r: f"{r['mean']:.4f}") if len(seeds) == 1 else \
                  (lambda r: f"{r['mean']:.4f} [{r['min']:.4f}, {r['max']:.4f}]")
            print(agg.loc[(a, m)].apply(fmt, axis=1).unstack("severity").loc[order].to_string())

    print("\n=================== DIAGNOSTIC (ground truth): O2O decisions ===================")
    print(dec.groupby(["system", "status", "seed_role", "severity"])[
        ["links", "old_was_right", "new_is_right", "broken", "false_removals"]].sum().to_string())
    print("\nToolkit repair accuracy (new target right) with sample size and 95% Wilson interval:")
    rep = dec[(dec.system == "Toolkit") & (dec.status == "repaired")]
    for label, sel in (("seed 42 (development)", rep.seed == 42), ("seeds 7 + 123 (held-out)", rep.seed != 42),
                       ("all three seeds", rep.seed.notna())):
        n, c = int(rep[sel].links.sum()), int(rep[sel].new_is_right.sum())
        lo, hi = wilson(c, n)
        print(f"    {label:26s} n = {n:6d}, right = {c:6d}, accuracy = {c / n if n else float('nan'):.4f} "
              f"[{lo:.4f}, {hi:.4f}], links broken = {int(rep[sel].broken.sum())}")
    b5 = dec[(dec.system == "B5 (toolkit, delete O2O)") & (dec.status == "removed")]
    print(f"\nB5 false removals (right links deleted): development {int(b5[b5.seed == 42].false_removals.sum())}, "
          f"held-out {int(b5[b5.seed != 42].false_removals.sum())}")
    print("\nToolkit O2O decisions per run:")
    print(pd.DataFrame(reports).query("system == 'Toolkit'").to_string(index=False))

    cb = clean_scores.set_index(["area", "metric"])["value"]
    co = clean_report["o2o"]
    clean_changes = co["repaired"] + co["removed"]
    print(f"\n=== Clean baseline: O2O links detected {co['detected']}, repaired {co['repaired']}, "
          f"E2O links added {clean_report['relations']['added_R1'] + clean_report['relations']['added_R2']}, "
          f"merged pairs {clean_report['identity']['merged_pairs']}, E2O F1 {cb[('e2o', 'f1')]:.4f}, "
          f"O2O F1 {cb[('o2o', 'f1')]:.4f}")

    assert clean_changes == 0 and co["detected"] == 0, "the toolkit changed O2O links in the clean log"
    assert clean_report["relations"]["added_R1"] + clean_report["relations"]["added_R2"] == 0
    assert clean_report["identity"]["merged_pairs"] == 0
    assert cb[("e2o", "f1")] == 1.0 and cb[("o2o", "f1")] == 1.0
    assert int(rep.broken.sum()) == 0, "the toolkit's O2O repair broke a right link"
    v = table.set_index(["system", "seed", "severity", "area", "metric"])["value"]
    for seed in SEEDS:
        for sev in TAGS.values():
            for s in SYSTEMS:
                assert v[(s, seed, sev, "validity", "o2o_unknown_object")] == 0, f"{s}: dangling O2O object"
                assert v[(s, seed, sev, "validity", "duplicate_o2o_rows")] == 0, f"{s}: duplicate O2O rows"
    print("\nSaved results/scores_stage10.csv, o2o_diagnostics.csv, o2o_reports.csv, "
          "figures/scores_by_system_stage10.png")
    print("NOTE: seed 42 is the development seed (stage 10 rules were explored on it); seeds 7 and 123 are held out "
          "and were run once on the frozen design.")
    print("ALL STAGE 10 CHECKS PASSED")
