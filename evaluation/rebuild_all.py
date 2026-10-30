"""Rebuild every report asset in one command. Wiring only: it runs the existing scripts in order.

    python evaluation/rebuild_all.py          freeze checks + exact seed 42 reproduction (run_experiments.py),
                                              realism AUCs for the three seeds, then all tables and figures
    python evaluation/rebuild_all.py --full   also re-runs the stage 10 and 11 runners first (about 1.5 hours)

Needs the generated data for seeds 42, 7 and 123 (tests/generate_datasets.py) and, without --full, the saved
stage 10 scores in results/.

The realism check on seed 7 at 5% fails one rule by chance (a clone holds the highest sheet ID number; its AUC is
0.485, no signal). The realism script saves its CSV before it reports the failure, so a non-zero exit there is
accepted only when the CSV has a row (AUC values or a FAILED row) for every seed and severity; the failure is
printed and reported in the realism table. Every other failure stops the rebuild.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd

SEEDS = {42: "data/messy", 7: "data/seeds/seed7", 123: "data/seeds/seed123"}
SEVERITIES = (0.05, 0.15, 0.3)
REALISM = "results/realism_auc.csv"


def commands(full=False):
    """(label, argv, must_succeed) for each step, in order."""
    py = sys.executable
    steps = [("experiments", [py, "evaluation/run_experiments.py"] + (["--full"] if full else []), True)]
    steps += [(f"realism seed {s}", [py, "tests/test_id_realism.py", "--seed", str(s), "--data", d, "--csv", REALISM],
               False) for s, d in SEEDS.items()]
    steps.append(("details", [py, "evaluation/make_report_details.py"], True))
    return steps


def realism_complete(path, seeds=tuple(SEEDS), severities=SEVERITIES):
    """Returns (missing (seed, severity) pairs, failed rows as text). Complete = every pair has AUCs or a FAILED row."""
    if not os.path.exists(path):
        return [(s, v) for s in seeds for v in severities], []
    auc = pd.read_csv(path)
    have = set(zip(auc.seed, auc.severity.round(2)))
    missing = [(s, v) for s in seeds for v in severities if (s, round(v, 2)) not in have]
    failed = [f"seed {r.seed} at {r.severity:.0%}: {r.check}" for r in auc.itertuples()
              if str(r.check).startswith("FAILED")]
    return missing, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rebuild every report asset.")
    parser.add_argument("--full", action="store_true", help="re-run the stage 10 and 11 runners first")
    args = parser.parse_args(argv)
    if os.path.exists(os.path.join(ROOT, REALISM)):
        os.remove(os.path.join(ROOT, REALISM))             # rebuilt from scratch, never mixed with an old run
    for label, cmd, must_succeed in commands(args.full):
        print(f"\n== {label}: {' '.join(cmd[1:])}", flush=True)
        if label == "details":
            missing, failed = realism_complete(os.path.join(ROOT, REALISM))
            if missing:
                raise SystemExit(f"realism results incomplete, missing (seed, severity): {missing}")
            for f in failed:
                print(f"realism check failure (reported in realism_auc): {f}")
        done = subprocess.run(cmd, cwd=ROOT)
        if done.returncode != 0 and must_succeed:
            raise SystemExit(f"{label} failed (exit {done.returncode}); stopped")
    print("\nAll report assets rebuilt in report_assets/.")


if __name__ == "__main__":
    main()
