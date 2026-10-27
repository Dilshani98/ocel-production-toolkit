"""Detail tables and figures for the report, on top of make_report.py (frozen at stage 12). Never runs the toolkit.

    python evaluation/make_report_details.py [--results results] [--out report_assets]

First rebuilds the stage 12 assets with make_report.build(), then adds (each as .csv, .md and .png):
    identity_by_system      identity precision, recall, F1 and false merges per system
    links_by_system         E2O and O2O recovery per system, with wrong links added and right links lost
    repairs_by_severity     what the toolkit changed at each severity, right and wrong
    usefulness_by_system    directly-follows edge F1, edge frequency difference, object count difference
    realism_auc             can clones be told apart from real objects by ID number, row position or noise?
and appends the same tables to numbers.md. Held-out seeds are the headline (mean [min, max]); development
seed 42 is shown separately. Inputs: results/experiments/scores_all.csv, link_diagnostics.csv,
o2o_diagnostics.csv (copied there by run_experiments.py) and results/realism_auc.csv (from
tests/test_id_realism.py --csv). Deterministic: a second run gives byte-identical files.
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from evaluation.make_report import build, markdown, _fmt, PNG

SEVERITIES = (0.05, 0.15, 0.30)
ROLES = (("held-out", "held-out"), ("development", "dev (seed 42)"))
TOOLKIT, GREY_LIGHT, GREY_DARK = "#2171b5", "#bdbdbd", "#636363"
B2, B3, B4, B5, TK = ("B2 (pair-only)", "B3 (closest in time)", "B4 (B3 + eager links)",
                      "B5 (toolkit, delete O2O)", "Toolkit")


COUNTS = {"false_merges", "missed_merges", "valid_wrongly_changed", "untouched_changed", "links_added",
          "wrong_links_added", "links_changed", "wrong_changes", "right_links_lost", "object_count_abs_difference"}


def cell(values, role, count=False):
    """Held-out: mean [min, max] over seeds; development: the single value. Blank if there is no value.
    Counts are whole numbers (a mean of two counts may end in .5)."""
    v = pd.Series(values, dtype=float).dropna()
    if v.empty:
        return ""
    f = (lambda x: f"{x:.0f}" if x == int(x) else f"{x:.1f}") if count else _fmt
    if role == "development":
        return f(v.iloc[0])
    return f"{f(v.mean())} [{f(v.min())}, {f(v.max())}]"


def is_count(metric):
    return metric.startswith("n_") or metric in COUNTS


def columns():
    return [f"{label} {s:.0%}" for _, label in ROLES for s in SEVERITIES]


def score_table(scores, metrics, systems):
    """One row per (area, metric, system); one column per seed role and severity."""
    rows = []
    for area, metric in metrics:
        for system in systems:
            sub = scores[(scores.area == area) & (scores.metric == metric) & (scores.system == system)]
            rows.append([area, metric, system] + [cell(sub[(sub.seed_role == role) & (sub.severity == s)].value, role,
                                                       is_count(metric)) for role, _ in ROLES for s in SEVERITIES])
    return pd.DataFrame(rows, columns=["area", "metric", "system"] + columns())


def held(scores, area, metric, system):
    """Held-out mean, min, max and development value per severity (for figures)."""
    sub = scores[(scores.area == area) & (scores.metric == metric) & (scores.system == system)]
    out = []
    for s in SEVERITIES:
        h = sub[(sub.seed_role == "held-out") & (sub.severity == s)].value
        d = sub[(sub.seed_role == "development") & (sub.severity == s)].value
        out.append((h.mean(), h.min(), h.max(), d.iloc[0] if len(d) else float("nan")))
    return pd.DataFrame(out, columns=["mean", "min", "max", "dev"], index=SEVERITIES)


def same_scores(scores, area, a, b):
    """True if systems a and b have identical values for every metric of one area (all seeds, severities)."""
    x = scores[(scores.area == area) & (scores.system == a)].set_index(["seed", "severity", "metric"]).value
    y = scores[(scores.area == area) & (scores.system == b)].set_index(["seed", "severity", "metric"]).value
    return len(x) > 0 and x.sort_index().equals(y.sort_index())


def bars(ax, series, colours, ylabel, title, ylim=None):
    """Grouped bars: held-out mean with a min-max whisker, development seed as a hollow diamond."""
    width = 0.8 / len(series)
    for i, ((label, d), colour) in enumerate(zip(series, colours)):
        x = [k + (i - (len(series) - 1) / 2) * width for k in range(len(SEVERITIES))]
        ax.bar(x, d["mean"], width, color=colour, edgecolor="black", linewidth=0.4, label=label,
               yerr=[d["mean"] - d["min"], d["max"] - d["mean"]], capsize=2, error_kw={"linewidth": 0.8})
        ax.scatter(x, d["dev"], marker="D", s=14, facecolors="white", edgecolors="black", linewidths=0.8, zorder=3)
    ax.set_xticks(range(len(SEVERITIES)))
    ax.set_xticklabels([f"{s:.0%}" for s in SEVERITIES])
    ax.set_xlabel("Severity")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    if ylim:
        ax.set_ylim(*ylim)


def finish(fig, path, note):
    fig.text(0.5, 0.005, note, ha="center", fontsize=7.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, **PNG)
    plt.close(fig)


NOTE = "Bars: held-out seeds 7 and 123 (mean, whisker = min-max). Hollow diamond: development seed 42."


def identity(scores, systems, out_dir):
    table = score_table(scores, [("identity", m) for m in ("precision", "recall", "f1", "false_merges",
                                                           "missed_merges", "n_true")], systems)
    # B4 only adds links to B3, and B5 only changes O2O handling of the toolkit, so their identity scores are
    # the same; the figure shows each distinct identity method once
    assert same_scores(scores, "identity", B3, B4) and same_scores(scores, "identity", TK, B5)
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.6))
    show = [(B2, GREY_LIGHT), (B3, GREY_DARK), (TK, TOOLKIT)]
    for ax, (metric, label) in zip(axes, [("precision", "Precision"), ("recall", "Recall"), ("f1", "F1"),
                                          ("false_merges", "False merges (pairs)")]):
        bars(ax, [(s, held(scores, "identity", metric, s)) for s, _ in show], [c for _, c in show],
             label, f"Identity: {label}", None if metric == "false_merges" else (0, 1.05))
    axes[0].legend(fontsize=7, loc="lower left")
    finish(fig, os.path.join(out_dir, "identity_by_system.png"),
           NOTE + " B4 = B3 and B5 = Toolkit on identity; B0 and B1 merge nothing.")
    return table, "Identity resolution by system", ("Pairs of records of the same real object. n_true = true pairs "
                                                    "(clones). False merges = merged pairs that are not the same object.")


def link_diagnostics(results):
    links = pd.read_csv(os.path.join(results, "link_diagnostics.csv"))
    o2o = pd.read_csv(os.path.join(results, "o2o_diagnostics.csv"))
    added = links[links.added > 0].groupby(["system", "seed", "seed_role", "severity"])[["added", "wrong"]].sum()
    o2o["right_lost"] = o2o.broken + o2o.false_removals
    # a repair is wrong if its new target is wrong; a removal is wrong if the removed link was right
    o2o["wrong"] = (o2o.links - o2o.new_is_right).where(o2o.status == "repaired", o2o.false_removals)
    changed = o2o[o2o.status.isin(["repaired", "removed"])].groupby(
        ["system", "seed", "seed_role", "severity"])[["links", "wrong", "right_lost"]].sum()
    keys = ["system", "seed", "seed_role", "severity"]
    e2o = added.reset_index().melt(keys, var_name="metric").assign(area="e2o")
    o2o = changed.reset_index().melt(keys, var_name="metric").assign(area="o2o")
    e2o["metric"] = e2o.metric.map({"added": "links_added", "wrong": "wrong_links_added"})
    o2o["metric"] = o2o.metric.map({"links": "links_changed", "wrong": "wrong_changes", "right_lost": "right_links_lost"})
    return pd.concat([e2o, o2o], ignore_index=True)


def links(scores, systems, diag, out_dir):
    both = pd.concat([scores, diag], ignore_index=True)
    metrics = [(a, m) for a in ("e2o", "o2o") for m in ("precision", "recall", "f1", "affected_recall",
                                                        "n_affected")]
    metrics += [("e2o", "links_added"), ("e2o", "wrong_links_added"), ("o2o", "links_changed"),
                ("o2o", "wrong_changes"), ("o2o", "right_links_lost")]
    table = score_table(both, metrics, systems)
    zero = lambda d: d.fillna(0)                          # a system with no diagnostics row changed nothing
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.6))
    e2o = [(B3, GREY_LIGHT), (B4, GREY_DARK), (TK, TOOLKIT)]
    o2o = [(B3, GREY_LIGHT), (B5, GREY_DARK), (TK, TOOLKIT)]
    bars(axes[0], [(s, held(both, "e2o", "affected_recall", s)) for s, _ in e2o], [c for _, c in e2o],
         "Affected recall", "E2O: damaged links recovered", (0, 1.05))
    bars(axes[1], [(s, zero(held(both, "e2o", "wrong_links_added", s))) for s, _ in e2o], [c for _, c in e2o],
         "Links", "E2O: wrong links added")
    bars(axes[2], [(s, held(both, "o2o", "affected_recall", s)) for s, _ in o2o], [c for _, c in o2o],
         "Affected recall", "O2O: damaged links recovered", (0, 1.05))
    bars(axes[3], [(s, zero(held(both, "o2o", "right_links_lost", s))) for s, _ in o2o], [c for _, c in o2o],
         "Links", "O2O: right links broken or removed")
    axes[0].legend(fontsize=7, loc="upper right")
    axes[2].legend(fontsize=7, loc="center left")
    finish(fig, os.path.join(out_dir, "links_by_system.png"), NOTE)
    return table, "E2O and O2O recovery by system", (
        "Affected recall = share of damaged links (n_affected) that the output gets right. Links added, wrong links "
        "added, links changed and right links lost come from the diagnostics files; blank = the system makes no such "
        "change.")


def repairs(scores, diag, out_dir):
    both = pd.concat([scores, diag], ignore_index=True)
    spec = [("labels", "distorted_restored", "Labels: share of distorted labels restored"),
            ("labels", "valid_wrongly_changed", "Labels: valid labels changed"),
            ("timestamps", "drifted_restored_exactly", "Timestamps: share of drifted events restored exactly"),
            ("timestamps", "untouched_changed", "Timestamps: untouched events changed"),
            ("identity", "n_predicted", "Identity: pairs merged"),
            ("identity", "false_merges", "Identity: wrong pairs merged"),
            ("identity", "n_true", "Identity: true pairs"),
            ("e2o", "links_added", "E2O: links added"),
            ("e2o", "wrong_links_added", "E2O: wrong links added"),
            ("e2o", "n_affected", "E2O: damaged links"),
            ("o2o", "links_changed", "O2O: links repaired"),
            ("o2o", "wrong_changes", "O2O: repairs with a wrong new target"),
            ("o2o", "right_links_lost", "O2O: right links broken"),
            ("o2o", "n_affected", "O2O: damaged links")]
    tk = both[both.system == TK]
    rows = [[label] + [cell(tk[(tk.area == a) & (tk.metric == m) & (tk.seed_role == role) & (tk.severity == s)]
                            .value, role, is_count(m)) for role, _ in ROLES for s in SEVERITIES] for a, m, label in spec]
    table = pd.DataFrame(rows, columns=["repair"] + columns())
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (area, right, wrong, title) in zip(axes, [("identity", "n_predicted", "false_merges", "Identity merges (pairs)"),
                                                      ("e2o", "links_added", "wrong_links_added", "E2O links added"),
                                                      ("o2o", "links_changed", "wrong_changes", "O2O links repaired")]):
        r, w = held(tk, area, right, TK).fillna(0), held(tk, area, wrong, TK).fillna(0)
        bars(ax, [("changes made", r), ("of which wrong", w)], [TOOLKIT, GREY_DARK], "Count", title)
        top = ax.get_ylim()[1]
        for k, v in enumerate(w["mean"]):                 # wrong counts are too small to see as bars
            ax.text(k + 0.2, top * 0.03, f"{v:g}", ha="center", va="bottom", fontsize=8)
        ax.legend(fontsize=7, loc="upper left")
    finish(fig, os.path.join(out_dir, "repairs_by_severity.png"),
           NOTE + " Labels and timestamps: every damaged value restored, 0 wrong (table).")
    return table, "Toolkit repairs by severity", (
        "What the toolkit changed, and how much of it was wrong. Labels and timestamps are shares of the damaged "
        "values; the rest are counts.")


def usefulness(scores, systems, out_dir):
    table = score_table(scores, [("usefulness", m) for m in ("edge_precision", "edge_recall", "edge_f1",
                                                             "edge_frequency_difference",
                                                             "object_count_abs_difference")], systems)
    show = [("B0 (as-is)", GREY_LIGHT), (B3, GREY_DARK), (TK, TOOLKIT)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (metric, label, ylim) in zip(axes, [("edge_f1", "Edge F1", (0, 1.05)),
                                                ("edge_frequency_difference", "Frequency difference", None),
                                                ("object_count_abs_difference", "Objects (absolute difference)",
                                                 None)]):
        bars(ax, [(s, held(scores, "usefulness", metric, s)) for s, _ in show], [c for _, c in show], label,
             {"edge_f1": "Directly-follows edges: F1", "edge_frequency_difference": "Edge frequency difference",
              "object_count_abs_difference": "Object count difference"}[metric], ylim)
    axes[0].legend(fontsize=7, loc="lower right")
    finish(fig, os.path.join(out_dir, "usefulness_by_system.png"), NOTE + " Lower is better for both differences.")
    return table, "Process-mining usefulness by system", (
        "Directly-follows edges of the output against the clean log (per object type); frequency difference = mean "
        "absolute difference of edge shares; object count difference = objects too many or too few (lower is better).")


def realism(path, out_dir):
    auc = pd.read_csv(path)
    failed = auc[auc.check.str.startswith("FAILED")]
    auc = auc[~auc.check.str.startswith("FAILED")].assign(
        seed_role=lambda d: d.seed.map(lambda s: "development" if s == 42 else "held-out"))
    rows = []
    for check in dict.fromkeys(auc.check):
        sub = auc[auc.check == check]
        rows.append([check] + [cell(sub[(sub.seed_role == role) & (sub.severity.round(2) == s)].auc, role)
                               for role, _ in ROLES for s in SEVERITIES])
    table = pd.DataFrame(rows, columns=["check"] + columns())
    fig, ax = plt.subplots(figsize=(11, 3.8))
    checks = list(dict.fromkeys(auc.check))
    ax.axhspan(0.4, 0.6, color="#f0f0f0", zorder=0)
    ax.axhline(0.5, color="black", linewidth=0.6)
    for role, colour, marker, label in (("held-out", GREY_DARK, "o", "held-out seeds 7, 123"),
                                        ("development", TOOLKIT, "D", "development seed 42")):
        sub = auc[auc.seed_role == role]
        offsets = {s: (i - 1) * 0.12 for i, s in enumerate(SEVERITIES)}
        x = [checks.index(c) + offsets[round(s, 2)] for c, s in zip(sub.check, sub.severity)]
        ax.scatter(x, sub.auc, s=16, color=colour, marker=marker, label=label, zorder=3)
    ax.set_xticks(range(len(checks)))
    ax.set_xticklabels([c.replace(" AUC", "").replace("SteelSheet ", "SteelSheet\n") for c in checks], fontsize=7.5)
    ax.set_ylim(0.3, 0.7)
    ax.set_ylabel("AUC (0.5 = no signal)")
    ax.set_xlabel("Check")
    ax.set_title("Can clones be told apart from real objects? (dots left to right: 5%, 15%, 30%)", fontsize=10)
    ax.legend(fontsize=7, loc="upper right")
    note = "Grey band: pass range 0.4-0.6."
    if len(failed):
        note += " Not shown (check failed before its AUCs): " + "; ".join(
            f"seed {r.seed} at {r.severity:.0%}: {r.check[len('FAILED: '):]}" for r in failed.itertuples()) + "."
    finish(fig, os.path.join(out_dir, "realism_auc.png"), note)
    return table, "Realism check (clone detectability)", (
        "AUC of a simple score (ID number, row position, number of blank attributes, decimal places) for telling "
        "clones from real objects of the same type; 0.5 = no signal. Number and objects-position AUCs are equal "
        "because objects are written sorted by ID. " + note)


def build_details(results, out_dir):
    files = build(os.path.join(results, "experiments", "scores_all.csv"), out_dir)
    scores = pd.read_csv(os.path.join(results, "experiments", "scores_all.csv"), float_precision="round_trip")
    systems = list(dict.fromkeys(scores.loc[scores.seed_role != "clean log", "system"]))
    diag = link_diagnostics(os.path.join(results, "experiments"))
    parts = [("identity_by_system", identity(scores, systems, out_dir)),
             ("links_by_system", links(scores, systems, diag, out_dir)),
             ("repairs_by_severity", repairs(scores, diag, out_dir)),
             ("usefulness_by_system", usefulness(scores, systems, out_dir)),
             ("realism_auc", realism(os.path.join(results, "realism_auc.csv"), out_dir))]
    md = ["", "# Details", "", "Generated by evaluation/make_report_details.py. " + NOTE.replace("Bars: h", "H"), ""]
    for name, (table, title, note) in parts:
        table.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False, lineterminator="\n")
        text = markdown(table, title, note)
        open(os.path.join(out_dir, f"{name}.md"), "w", encoding="utf-8", newline="\n").write(text)
        md.append(text)
        files += [f"{name}.csv", f"{name}.md", f"{name}.png"]
    with open(os.path.join(out_dir, "numbers.md"), "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rebuild all report tables and figures, with the detail tables.")
    parser.add_argument("--results", default=os.path.join(ROOT, "results"))
    parser.add_argument("--out", default=os.path.join(ROOT, "report_assets"))
    args = parser.parse_args(argv)
    for f in build_details(args.results, args.out):
        print("wrote", os.path.join(args.out, f))


if __name__ == "__main__":
    main()
