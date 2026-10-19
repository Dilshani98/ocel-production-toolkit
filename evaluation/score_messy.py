import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reconstruction.mapping import SchemaMapping, apply_mapping
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score

# Scores the messy data as-is (no repair) at the three severities. This is the "before" picture
# that every later stage is compared with.

DATA = os.path.join(ROOT, "data", "messy")
RESULTS = os.path.join(ROOT, "results")
TAGS = {"sev0_05": 0.05, "sev0_15": 0.15, "sev0_3": 0.30}
MAPPING = SchemaMapping("record_id", "activity_name", "event_time", "item_id",
                        "item_category", "linked_item_id", "link_type", "role")

# Figure: one headline number per area, labelled with what it is
HEADLINE = [("labels", "accuracy", "Labels\n(accuracy)"),
            ("timestamps", "drifted_restored_exactly", "Timestamps\n(drifted restored, share)"),
            ("identity", "f1", "Identity\n(F1)"),
            ("e2o", "f1", "E2O\n(F1)"),
            ("o2o", "f1", "O2O\n(F1)"),
            ("usefulness", "edge_f1", "DF edges\n(F1)")]


def load_messy(tag):
    load = lambda n: pd.read_csv(os.path.join(DATA, f"messy_{n}_{tag}.csv"), low_memory=False)
    return {kind: apply_mapping(load(kind), MAPPING, kind) for kind in ("events", "objects", "relations", "o2o")}


def plot(table, path):
    sevs = list(TAGS.values())
    colours = ["#9ecae1", "#4292c6", "#08519c"]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    width = 0.25
    for i, sev in enumerate(sevs):
        vals = [table[(table.severity == sev) & (table.area == a) & (table.metric == m)]["value"].iloc[0]
                for a, m, _ in HEADLINE]
        bars = ax.bar([x + (i - 1) * width for x in range(len(HEADLINE))], vals, width, label=f"{sev:.0%}", color=colours[i])
        ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=1)          # so zero bars are visible as "0.00"
    ax.set_xticks(range(len(HEADLINE)))
    ax.set_xticklabels([label for _, _, label in HEADLINE], fontsize=9)
    ax.set_ylabel("Score (accuracy, share or F1; 1.0 = perfect)")
    ax.set_ylim(0, 1.1)
    ax.set_title("Messy data as-is, scored against the clean log")
    ax.legend(title="Severity")
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150)


if __name__ == "__main__":
    clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
    tables = []
    for tag, sev in TAGS.items():
        gt = load_ground_truth(os.path.join(DATA, f"ground_truth_{tag}.json"))
        truth = build_truth(clean, gt)
        messy = load_messy(tag)
        tables.append(score(messy, messy, truth, clean, system="messy_as_is", severity=sev))
    table = pd.concat(tables, ignore_index=True)

    os.makedirs(RESULTS, exist_ok=True)
    table.to_csv(os.path.join(RESULTS, "scores_messy_as_is.csv"), index=False)
    plot(table, os.path.join(RESULTS, "figures", "scores_messy_as_is.png"))

    wide = table.pivot_table(index=["area", "metric"], columns="severity", values="value", sort=False)
    with pd.option_context("display.max_rows", 200, "display.max_columns", 10, "display.width", 140,
                           "display.float_format", "{:.4f}".format):
        print(wide)

    get = lambda sev, a, m: table[(table.severity == sev) & (table.area == a) & (table.metric == m)]["value"].iloc[0]
    for sev in TAGS.values():
        assert get(sev, "events", "missing_events") == 0 and get(sev, "events", "extra_events") == 0
        assert get(sev, "identity", "f1") == 0.0 and get(sev, "identity", "false_merges") == 0
        assert get(sev, "timestamps", "drifted_restored_exactly") == 0.0
        assert get(sev, "labels", "distorted_restored") == 0.0 and get(sev, "labels", "valid_wrongly_changed") == 0
        assert get(sev, "e2o", "affected_recall") == 0.0
        # A few swaps land on another row's true target (one source, several "created from" rows), so not exactly 0
        assert get(sev, "o2o", "affected_recall") < 0.01
        assert 0.9 < get(sev, "e2o", "f1") < 1.0 and 0.6 < get(sev, "o2o", "f1") < 1.0
        assert get(sev, "validity", "relations_unknown_object") == 0
    for a, m in [("e2o", "f1"), ("o2o", "f1"), ("labels", "accuracy")]:
        assert get(0.05, a, m) > get(0.15, a, m) > get(0.30, a, m), f"{a} {m} should fall with severity"
    print("\nSaved results/scores_messy_as_is.csv and results/figures/scores_messy_as_is.png")
    print("ALL MESSY-AS-IS CHECKS PASSED")
