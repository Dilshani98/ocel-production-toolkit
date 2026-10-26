"""One command for the experiments. Wiring only: it reuses the stage runners and the report builder.

    python evaluation/run_experiments.py          freeze checks, reproduce development seed 42 exactly,
                                                  assemble the saved scores, rebuild report_assets/
    python evaluation/run_experiments.py --full   also re-run the stage 10 and stage 11 runners first
                                                  (all seeds; about 1.5 hours)

The saved stage 10 scores (results/scores_stage10.csv) are the reference: seed 42 must reproduce them exactly
(every system, every severity), so the assembled tables are known to come from the frozen toolkit.
"""
import argparse, json, os, shutil, subprocess, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
from evaluation import run_stage11
from evaluation.run_stage8 import load_messy, SEEDS, TAGS
from evaluation.run_stage10 import SYSTEMS
from evaluation.scoring import load_clean_ocel, load_ground_truth, build_truth, score
from evaluation.make_report import build

RESULTS = os.path.join(ROOT, "results")
STAGE10 = os.path.join(RESULTS, "scores_stage10.csv")
OUT = os.path.join(RESULTS, "experiments")
REPORT = os.path.join(ROOT, "report_assets")
STAGE12 = os.path.join(ROOT, "evaluation", "toolkit_freeze_stage12.json")


def check_freezes():
    """Stage 8-11 records (with amendments), then the stage 12 record if it exists (toolkit + evaluation code)."""
    run_stage11.check_freezes()
    if os.path.exists(STAGE12):
        import hashlib
        record = json.load(open(STAGE12))
        changed = []
        for f, h in record["files"].items():
            data = open(os.path.join(ROOT, f), "rb").read() if os.path.exists(os.path.join(ROOT, f)) else None
            lf = data.replace(b"\r\n", b"\n") if data is not None else None
            if data is None or h not in {hashlib.sha256(v).hexdigest() for v in (data, lf, lf.replace(b"\n", b"\r\n"))}:
                changed.append(f)
        assert not changed, f"toolkit_freeze_stage12.json: files changed since the freeze: {changed}"
        print(f"Freeze verified (toolkit_freeze_stage12.json): {len(record['files'])} files unchanged "
              f"since {record['frozen_at']}")


def reproduce_development_seed(stage10):
    """Re-run every system on development seed 42 and require the saved stage 10 scores exactly."""
    clean = load_clean_ocel(os.path.join(ROOT, "socel2_hinge.xml"))
    folder, n = SEEDS[42], 0
    for tag, sev in TAGS.items():
        truth = build_truth(clean, load_ground_truth(os.path.join(folder, f"ground_truth_{tag}.json")))
        messy = load_messy(folder, tag)
        for name, run in SYSTEMS.items():
            now = score(run(messy)[0], messy, truth, clean, system=name, severity=sev)
            ref = stage10[(stage10.system == name) & (stage10.seed == 42) & (stage10.severity == sev)]
            m = now.merge(ref[["area", "metric", "value"]], on=["area", "metric"], how="outer",
                          suffixes=("_now", "_saved"), indicator=True)
            bad = m[(m["_merge"] != "both") | (m["value_now"] != m["value_saved"])]
            assert len(ref) and bad.empty, f"seed 42 {tag} {name}: differs from stage 10:\n{bad.to_string()}"
            n += len(ref)
        print(f"development seed 42, {tag}: all {len(SYSTEMS)} systems reproduce stage 10 exactly")
    return n


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the experiments and rebuild the report assets.")
    parser.add_argument("--full", action="store_true", help="re-run the stage 10 and 11 runners first (all seeds)")
    args = parser.parse_args(argv)
    for folder in SEEDS.values():
        missing = [t for t in TAGS if not os.path.exists(os.path.join(folder, f"messy_events_{t}.csv"))]
        if missing:
            raise SystemExit(f"missing data in {folder} for {missing}: run tests/generate_datasets.py first")
    check_freezes()
    if args.full:
        for runner in ("run_stage10.py", "run_stage11.py"):
            subprocess.run([sys.executable, os.path.join(ROOT, "evaluation", runner)], check=True)
    stage10 = pd.read_csv(STAGE10, float_precision="round_trip")
    n = reproduce_development_seed(stage10)
    os.makedirs(OUT, exist_ok=True)
    shutil.copyfile(STAGE10, os.path.join(OUT, "scores_all.csv"))
    for extra in ("export_validation.csv", "o2o_diagnostics.csv", "link_diagnostics.csv", "identity_losses.csv"):
        if os.path.exists(os.path.join(RESULTS, extra)):
            shutil.copyfile(os.path.join(RESULTS, extra), os.path.join(OUT, extra))
    files = build(os.path.join(OUT, "scores_all.csv"), REPORT)
    print(f"\n{n} development-seed scores reproduced exactly; report assets rebuilt: {', '.join(files)}")


if __name__ == "__main__":
    main()
