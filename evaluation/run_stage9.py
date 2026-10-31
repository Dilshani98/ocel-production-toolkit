import os, sys, json, math
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
from reconstruction.baselines import apply_b1, apply_b2
from reconstruction.pipeline import run_toolkit
from reconstruction.toolkit import run_full_toolkit, run_b4
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.plots import plot_by_system, TOOLKIT_COLOUR
from evaluation.run_stage8 import toolkit_files, _variants, load_messy, SEEDS, TAGS

# Stage 9: B0-B4 and the full toolkit (identity + missing E2O recovery) on three seeds.
# Seed 42 is the DEVELOPMENT seed: the stage 9 rules were explored on it. Seeds 7 and 123 are held out:
# no stage 9 rule was looked at on them before the design was frozen, and they are run once here.

RESULTS = os.path.join(ROOT, "results")
FREEZES = [os.path.join(ROOT, "evaluation", "toolkit_freeze.json"),           # stage 8
           os.path.join(ROOT, "evaluation", "toolkit_freeze_stage9.json")]    # stage 9
SEED_ROLE = {42: "development", 7: "held-out", 123: "held-out"}
SYSTEMS = {"B0 (as-is)": lambda t: (t, {}, None),
           "B1 (hygiene)": lambda t: (*apply_b1(t), None),
           "B2 (pair-only)": lambda t: (*apply_b2(t, max_group=2), None),
           "B3 (closest in time)": lambda t: run_toolkit(t, identity_decision="closest"),
           "B4 (B3 + eager links)": run_b4,
           "Toolkit": run_full_toolkit}
FIGURE_COLOURS = ["#f7f7f7", "#d9d9d9", "#bdbdbd", "#969696", "#525252", TOOLKIT_COLOUR]
KEY = [("identity", "f1"), ("identity", "false_merges"),
       ("e2o", "precision"), ("e2o", "recall"), ("e2o", "affected_recall"),
       ("o2o", "affected_recall"), ("usefulness", "edge_frequency_difference"),
       ("usefulness", "object_count_abs_difference")]


def check_freezes():
    now = toolkit_files()
    for path in FREEZES:
        record = json.load(open(path))
        changed = [f for f, h in record["files"].items() if f not in now or h not in _variants(now[f])]
        assert not changed, f"{os.path.basename(path)}: toolkit files changed since the freeze: {changed}"
        print(f"Freeze verified ({os.path.basename(path)}): {len(record['files'])} files unchanged "
              f"since {record['frozen_at']}")


def wilson(correct, n, z=1.96):
    """95% Wilson interval for a proportion (honest for small n)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = correct / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def link_rows(links, removed, system, seed, sev):
    """DIAGNOSTIC (uses ground truth): is each added link one the injector removed?"""
    if links is None or links.empty:
        return []
    rows = []
    for rule, g in links.groupby("rule"):
        added = rule in ("R1", "R2", "eager")
        correct = sum((e, o) in removed for e, o in zip(g["event"], g["object"])) if added else 0
        rows.append({"system": system, "seed": seed, "seed_role": SEED_ROLE[seed], "severity": sev, "rule": rule,
                     "links": len(g), "added": len(g) if added else 0, "correct": correct,
                     "wrong": (len(g) - correct) if added else 0})
    return rows


if __name__ == "__main__":
    check_freezes()
    clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
    tables, link_table, reports = [], [], []
    for seed, folder in SEEDS.items():
        for tag, sev in TAGS.items():
            gt = load_ground_truth(os.path.join(folder, f"ground_truth_{tag}.json"))
            truth = build_truth(clean, gt)
            removed = {(g["details"]["event_id"], g["target_id"]) for g in gt if g["change_type"] == "relation_removed"}
            messy = load_messy(folder, tag)
            for name, run in SYSTEMS.items():
                recon, report, extra = run(messy)
                tables.append(score(recon, messy, truth, clean, system=name, severity=sev)
                              .assign(seed=seed, seed_role=SEED_ROLE[seed]))
                if isinstance(extra, dict):
                    link_table += link_rows(extra["links"], removed, name, seed, sev)
                    rr = report["relations"]
                    reports.append({"system": name, "seed": seed, "severity": sev, "missing_links": rr["missing_links"],
                                    **{k: rr.get(k, 0) for k in ("added_R1", "added_R2", "added_eager", "possible",
                                                                  "no_candidate")},
                                    "untrusted_activities": sum(not a["trusted"] for a in rr["activities"].values())})
            print(f"done: seed {seed} ({SEED_ROLE[seed]}), {tag}")

    # Clean baseline: the full toolkit on the undamaged log must add nothing and merge nothing
    clean_out, clean_report, _ = run_full_toolkit(clean)
    clean_scores = score(clean_out, clean, build_truth(clean, None), clean, system="Toolkit (clean log)", severity=0.0)
    tables.append(clean_scores.assign(seed=0, seed_role="clean log"))

    table = pd.concat(tables, ignore_index=True)[["system", "seed", "seed_role", "severity", "area", "metric", "value"]]
    links = pd.DataFrame(link_table)
    os.makedirs(RESULTS, exist_ok=True)
    table.to_csv(os.path.join(RESULTS, "scores_stage9.csv"), index=False)
    links.to_csv(os.path.join(RESULTS, "link_diagnostics.csv"), index=False)
    pd.DataFrame(reports).to_csv(os.path.join(RESULTS, "relations_reports.csv"), index=False)
    plot_by_system(table[table.seed == 42], list(SYSTEMS), FIGURE_COLOURS,
                   os.path.join(RESULTS, "figures", "scores_by_system_stage9.png"),
                   "Seed 42 (development seed): baselines and toolkit scored against the clean log")

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

    print("\n=================== DIAGNOSTIC (ground truth): added links that the injector really removed ===================")
    added = links[links.added > 0]
    by = added.groupby(["system", "rule", "seed_role", "severity"])[["added", "correct", "wrong"]].sum()
    print(by.to_string())
    print("\nR2 (part-link rule) accuracy with sample size and 95% Wilson interval:")
    r2 = links[(links.system == "Toolkit") & (links.rule == "R2")]
    for label, sel in (("seed 42 (development)", r2.seed == 42), ("seeds 7 + 123 (held-out)", r2.seed != 42),
                       ("all three seeds", r2.seed.notna())):
        n, c = int(r2[sel].added.sum()), int(r2[sel].correct.sum())
        lo, hi = wilson(c, n)
        print(f"    {label:26s} n = {n:3d}, correct = {c:3d}, accuracy = {c / n if n else float('nan'):.3f} "
              f"[{lo:.3f}, {hi:.3f}]")
    print("\nToolkit link decisions per run:")
    print(pd.DataFrame(reports).query("system == 'Toolkit'").to_string(index=False))

    cb = clean_scores.set_index(["area", "metric"])["value"]
    cr = clean_report["relations"]
    n_added_clean = cr["added_R1"] + cr["added_R2"]
    print(f"\n=== Clean baseline: missing links {cr['missing_links']}, links added {n_added_clean}, "
          f"merged pairs {clean_report['identity']['merged_pairs']}, E2O F1 {cb[('e2o', 'f1')]:.4f}, "
          f"O2O F1 {cb[('o2o', 'f1')]:.4f}")

    assert n_added_clean == 0, "the toolkit added links to the clean log"
    assert clean_report["identity"]["merged_pairs"] == 0, "the toolkit merged objects in the clean log"
    assert cb[("e2o", "f1")] == 1.0 and cb[("o2o", "f1")] == 1.0
    v = table.set_index(["system", "seed", "severity", "area", "metric"])["value"]
    for seed in SEEDS:
        for sev in TAGS.values():
            for s in SYSTEMS:
                assert v[(s, seed, sev, "validity", "relations_unknown_object")] == 0, f"{s}: dangling object"
                assert v[(s, seed, sev, "validity", "duplicate_relation_rows")] == 0, f"{s}: duplicate links"
    print("\nSaved results/scores_stage9.csv, link_diagnostics.csv, relations_reports.csv, "
          "figures/scores_by_system_stage9.png")
    print("NOTE: seed 42 is the development seed (stage 9 rules were explored on it); seeds 7 and 123 are held out "
          "and were run once on the frozen design.")
    print("ALL STAGE 9 CHECKS PASSED")
