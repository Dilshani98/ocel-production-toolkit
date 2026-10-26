"""Rebuild every result table and figure from saved score files. Never runs the toolkit.

    python evaluation/make_report.py [--scores results/experiments/scores_all.csv] [--out report_assets]

Input: a long score table with columns system, seed, seed_role, severity, area, metric, value
(seed_role is "development", "held-out" or "clean log"). Output (deterministic: a second run gives
byte-identical files):
    headline_heldout.csv / .md       held-out seeds: mean [min, max] per system and severity
    headline_development.csv / .md   development seed: value per system and severity
    f1_vs_severity.png               identity F1, E2O F1 and O2O F1 against severity (held-out mean, min-max band)
    scores_by_system_heldout.png     six-panel bars (held-out mean)
    numbers.md                       the headline numbers as text, generated from the same table
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

REQUIRED = ["system", "seed", "seed_role", "severity", "area", "metric", "value"]
KEY = [("labels", "accuracy"), ("timestamps", "drifted_restored_exactly"),
       ("identity", "precision"), ("identity", "recall"), ("identity", "f1"), ("identity", "false_merges"),
       ("e2o", "precision"), ("e2o", "recall"), ("e2o", "f1"), ("e2o", "affected_recall"),
       ("o2o", "precision"), ("o2o", "recall"), ("o2o", "f1"), ("o2o", "affected_recall"),
       ("usefulness", "edge_f1"), ("usefulness", "edge_frequency_difference"),
       ("usefulness", "object_count_abs_difference")]
LINES = [("identity", "f1", "Identity F1"), ("e2o", "f1", "E2O F1"), ("o2o", "f1", "O2O F1")]
MARKERS = ["o", "s", "^", "D", "v", "P", "X"]
STYLES = ["-", "--", ":", "-.", "-", "--", ":"]
PNG = {"metadata": {"Software": None}, "dpi": 150}          # no version stamp, so files are byte-stable


def load(path):
    table = pd.read_csv(path, float_precision="round_trip")
    missing = [c for c in REQUIRED if c not in table.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    return table


def _fmt(v):
    return f"{v:.4f}" if abs(v) < 10 else f"{v:.0f}"


def summary(table, role):
    """Per (area, metric, system, severity): mean, min, max and number of seeds, for one seed role."""
    sub = table[(table.seed_role == role) & table.apply(lambda r: (r.area, r.metric) in KEY, axis=1)]
    g = sub.groupby(["area", "metric", "system", "severity"], sort=False)["value"]
    return g.agg(["mean", "min", "max", "count"]).reset_index()


def wide(summ, systems, with_range):
    cell = (lambda r: f"{_fmt(r['mean'])} [{_fmt(r['min'])}, {_fmt(r['max'])}]") if with_range \
        else (lambda r: _fmt(r["mean"]))
    summ = summ.assign(cell=summ.apply(cell, axis=1))
    out = summ.pivot_table(index=["area", "metric", "system"], columns="severity", values="cell", aggfunc="first")
    order = [(a, m, s) for a, m in KEY for s in systems if (a, m, s) in out.index]
    out = out.loc[order]
    out.columns = [f"{c:.0%}" for c in out.columns]
    return out.reset_index()


def markdown(df, title, note):
    lines = [f"## {title}", "", note, "", "| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines) + "\n"


def plot_lines(summ, systems, colours, path):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, (area, metric, label) in zip(axes, LINES):
        for i, (system, colour) in enumerate(zip(systems, colours)):
            s = summ[(summ.area == area) & (summ.metric == metric) & (summ.system == system)].sort_values("severity")
            if s.empty:
                continue
            # greys repeat, so marker and line style keep every system apart in the legend
            toolkit = system == "Toolkit"
            ax.plot(s.severity, s["mean"], marker=MARKERS[i % len(MARKERS)], color=colour, label=system,
                    linestyle="-" if toolkit else STYLES[i % len(STYLES)], linewidth=2.2 if toolkit else 1.3,
                    markersize=5, zorder=3 if toolkit else 2)
            ax.fill_between(s.severity, s["min"], s["max"], color=colour, alpha=0.15, linewidth=0)
        ax.set_title(label)
        ax.set_xlabel("Severity")
        ax.set_xticks(sorted(summ.severity.unique()))
        ax.set_xticklabels([f"{v:.0%}" for v in sorted(summ.severity.unique())])
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("Score (held-out mean; band = min-max)")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, **PNG)
    plt.close(fig)


def build(scores_path, out_dir, systems=None):
    table = load(scores_path)
    systems = systems or list(dict.fromkeys(table.loc[table.seed_role != "clean log", "system"]))
    os.makedirs(out_dir, exist_ok=True)
    greys = ["#f0f0f0", "#d9d9d9", "#bdbdbd", "#969696", "#737373", "#525252"]
    colours = [("#2171b5" if s == "Toolkit" else greys[i % len(greys)]) for i, s in enumerate(systems)]
    line_colours = [("#2171b5" if s == "Toolkit" else ["#969696", "#525252", "#252525"][i % 3])
                    for i, s in enumerate(systems)]
    files = []
    notes = {"held-out": "Held-out seeds: mean [min, max] over seeds; rules were never tuned on these seeds.",
             "development": "Development seed: the seed the rules were explored on."}
    md = ["# Results", "", "Generated by evaluation/make_report.py from " + os.path.basename(scores_path) + ".", ""]
    for role, name in (("held-out", "heldout"), ("development", "development")):
        summ = summary(table, role)
        if summ.empty:
            continue
        n_seeds = int(table[table.seed_role == role].seed.nunique())
        df = wide(summ, systems, with_range=(role == "held-out"))
        df.to_csv(os.path.join(out_dir, f"headline_{name}.csv"), index=False, lineterminator="\n")
        text = markdown(df, f"{role.capitalize()} ({n_seeds} seed{'s' if n_seeds != 1 else ''})", notes[role])
        open(os.path.join(out_dir, f"headline_{name}.md"), "w", encoding="utf-8", newline="\n").write(text)
        md.append(text)
        files += [f"headline_{name}.csv", f"headline_{name}.md"]
        if role == "held-out":
            plot_lines(summ, systems, line_colours, os.path.join(out_dir, "f1_vs_severity.png"))
            from evaluation import plots
            bars = summ.rename(columns={"mean": "value"})
            plots.plot_by_system(bars, systems, colours, os.path.join(out_dir, "scores_by_system_heldout.png"),
                                 "Held-out seeds (mean): baselines and toolkit scored against the clean log")
            files += ["f1_vs_severity.png", "scores_by_system_heldout.png"]
    clean = table[table.seed_role == "clean log"]
    if len(clean):
        md += ["## Clean log (no damage)", ""] + [f"- {r.system}: {r.area} / {r.metric} = {_fmt(r.value)}"
                                                  for r in clean.itertuples() if (r.area, r.metric) in KEY] + [""]
    open(os.path.join(out_dir, "numbers.md"), "w", encoding="utf-8", newline="\n").write("\n".join(md))
    files.append("numbers.md")
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rebuild result tables and figures from saved scores.")
    parser.add_argument("--scores", default=os.path.join(ROOT, "results", "experiments", "scores_all.csv"))
    parser.add_argument("--out", default=os.path.join(ROOT, "report_assets"))
    args = parser.parse_args(argv)
    for f in build(args.scores, args.out):
        print("wrote", os.path.join(args.out, f))


if __name__ == "__main__":
    main()
