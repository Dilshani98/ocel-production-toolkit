import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# One headline number per area, labelled with what it is
HEADLINE = [("labels", "accuracy", "Labels (accuracy)"),
            ("timestamps", "drifted_restored_exactly", "Timestamps (drifted restored, share)"),
            ("identity", "f1", "Identity (F1)"),
            ("e2o", "f1", "E2O (F1)"),
            ("o2o", "f1", "O2O (F1)"),
            ("usefulness", "edge_f1", "DF edges (F1)")]
BASELINE_GREYS = ["#d9d9d9", "#969696", "#525252"]
TOOLKIT_COLOUR = "#2171b5"


def plot_by_system(table, systems, colours, path, title):
    """Six panels (one per area); x = severity, one bar per system, value written on each bar.
    Baselines are greys; the toolkit, when added, gets the one accent colour."""
    severities = sorted(table["severity"].unique())
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharey=True)
    width = 0.8 / len(systems)
    for ax, (area, metric, label) in zip(axes.flat, HEADLINE):
        for i, (system, colour) in enumerate(zip(systems, colours)):
            sel = table[(table.system == system) & (table.area == area) & (table.metric == metric)]
            vals = [sel[sel.severity == s]["value"].iloc[0] for s in severities]
            xs = [x + (i - (len(systems) - 1) / 2) * width for x in range(len(severities))]
            bars = ax.bar(xs, vals, width, color=colour, edgecolor="black", linewidth=0.4, label=system)
            crowded = len(systems) > 3
            ax.bar_label(bars, fmt="%.2f", fontsize=6 if crowded else 6.5, padding=1, rotation=90 if crowded else 0)
        ax.set_title(label, fontsize=10)
        ax.set_xticks(range(len(severities)))
        ax.set_xticklabels([f"{s:.0%}" for s in severities])
        ax.set_ylim(0, 1.2 if len(systems) > 3 else 1.12)
    for ax in axes[:, 0]:
        ax.set_ylabel("Score (1.0 = perfect)")
    for ax in axes[1]:
        ax.set_xlabel("Severity")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(systems), fontsize=9, bbox_to_anchor=(0.5, 0.95))
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
