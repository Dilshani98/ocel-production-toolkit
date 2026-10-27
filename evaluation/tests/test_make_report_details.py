import os, sys, tempfile, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from evaluation.make_report_details import build_details

# Made-up score, diagnostics and realism files where every reported value is known.
# Toolkit false merges at 15%: 0 and 2 on the held-out seeds, 1 on seed 42. Toolkit identity F1 at 5%:
# 0.8 and 0.6 held out, 0.9 on seed 42. One O2O repair batch of 10 links with 9 right new targets (1 wrong),
# and one B5 removal batch that removed 4 right links.

SYSTEMS = ["B0 (as-is)", "B1 (hygiene)", "B2 (pair-only)", "B3 (closest in time)", "B4 (B3 + eager links)",
           "B5 (toolkit, delete O2O)", "Toolkit"]
SEEDS = ((42, "development"), (7, "held-out"), (123, "held-out"))
SEVS = (0.05, 0.15, 0.3)
METRICS = {"identity": ["precision", "recall", "f1", "false_merges", "missed_merges", "n_true", "n_correct",
                        "n_predicted"],
           "e2o": ["precision", "recall", "f1", "affected_recall", "n_affected"],
           "o2o": ["precision", "recall", "f1", "affected_recall", "n_affected"],
           "labels": ["accuracy", "distorted_restored", "valid_wrongly_changed"],
           "timestamps": ["drifted_restored_exactly", "untouched_changed"],
           "usefulness": ["edge_precision", "edge_recall", "edge_f1", "edge_frequency_difference",
                          "object_count_abs_difference"]}


def value(system, seed, sev, area, metric):
    group = {"B4 (B3 + eager links)": "B3 (closest in time)", "B5 (toolkit, delete O2O)": "Toolkit"}
    if area == "identity":
        system = group.get(system, system)               # identity scores equal within these pairs
    if (system, area, metric, sev) == ("Toolkit", "identity", "f1", 0.05):
        return {42: 0.9, 7: 0.8, 123: 0.6}[seed]
    if (system, area, metric, sev) == ("Toolkit", "identity", "false_merges", 0.15):
        return {42: 1, 7: 0, 123: 2}[seed]
    return 0.5


def make_inputs(d, realism_fail=True):
    rows = [(s, seed, role, sev, a, m, value(s, seed, sev, a, m))
            for s in SYSTEMS for seed, role in SEEDS for sev in SEVS for a, ms in METRICS.items() for m in ms]
    exp = os.path.join(d, "experiments")
    os.makedirs(exp)
    pd.DataFrame(rows, columns=["system", "seed", "seed_role", "severity", "area", "metric", "value"]) \
        .to_csv(os.path.join(exp, "scores_all.csv"), index=False)
    links = [("Toolkit", seed, role, sev, "R1", 20, 20, 20, 0) for seed, role in SEEDS for sev in SEVS]
    links += [("B4 (B3 + eager links)", seed, role, sev, "eager", 30, 30, 25, 5) for seed, role in SEEDS for sev in SEVS]
    pd.DataFrame(links, columns=["system", "seed", "seed_role", "severity", "rule", "links", "added", "correct",
                                 "wrong"]).to_csv(os.path.join(exp, "link_diagnostics.csv"), index=False)
    o2o = [("Toolkit", seed, role, sev, "repaired", 10, 0, 9, 0, 0) for seed, role in SEEDS for sev in SEVS]
    o2o += [("B5 (toolkit, delete O2O)", seed, role, sev, "removed", 12, 4, 0, 0, 4) for seed, role in SEEDS
            for sev in SEVS]
    pd.DataFrame(o2o, columns=["system", "seed", "seed_role", "severity", "status", "links", "old_was_right",
                               "new_is_right", "broken", "false_removals"]) \
        .to_csv(os.path.join(exp, "o2o_diagnostics.csv"), index=False)
    auc = [(seed, sev, "X number AUC", 0.5) for seed, _ in SEEDS for sev in SEVS
           if not (realism_fail and (seed, sev) == (7, 0.05))]
    if realism_fail:
        auc.append((7, 0.05, "FAILED: X: clone numbers outside real range", float("nan")))
    pd.DataFrame(auc, columns=["seed", "severity", "check", "auc"]).to_csv(os.path.join(d, "realism_auc.csv"),
                                                                        index=False)


def run(d, **kw):
    make_inputs(d, **kw)
    return build_details(d, os.path.join(d, "out")), os.path.join(d, "out")


def table(out, name):
    return pd.read_csv(os.path.join(out, f"{name}.csv"), dtype=str, keep_default_na=False)


def test_known_values_and_seed_roles():
    with tempfile.TemporaryDirectory() as d:
        _, out = run(d)
        t = table(out, "identity_by_system").set_index(["metric", "system"])
        assert t.at[("f1", "Toolkit"), "held-out 5%"] == "0.7000 [0.6000, 0.8000]", t.loc["f1"]
        assert t.at[("f1", "Toolkit"), "dev (seed 42) 5%"] == "0.9000"
        assert t.at[("false_merges", "Toolkit"), "held-out 15%"] == "1 [0, 2]"     # counts as whole numbers
        assert t.at[("false_merges", "Toolkit"), "dev (seed 42) 15%"] == "1"


def test_wrong_changes_from_diagnostics():
    with tempfile.TemporaryDirectory() as d:
        _, out = run(d)
        t = table(out, "links_by_system").set_index(["area", "metric", "system"])
        assert t.at[("o2o", "wrong_changes", "Toolkit"), "held-out 30%"] == "1 [1, 1]"           # 10 - 9
        assert t.at[("o2o", "right_links_lost", "Toolkit"), "held-out 30%"] == "0 [0, 0]"
        assert t.at[("o2o", "wrong_changes", "B5 (toolkit, delete O2O)"), "held-out 30%"] == "4 [4, 4]"
        assert t.at[("e2o", "wrong_links_added", "B4 (B3 + eager links)"), "held-out 5%"] == "5 [5, 5]"
        assert t.at[("e2o", "links_added", "Toolkit"), "held-out 5%"] == "20 [20, 20]"
        assert t.at[("e2o", "links_added", "B3 (closest in time)"), "held-out 5%"] == ""      # makes no such change
        r = table(out, "repairs_by_severity").set_index("repair")
        assert r.at["O2O: repairs with a wrong new target", "dev (seed 42) 15%"] == "1"


def test_realism_failure_is_reported_not_hidden():
    with tempfile.TemporaryDirectory() as d:
        _, out = run(d)
        r = table(out, "realism_auc").set_index("check")
        assert r.at["X number AUC", "held-out 5%"] == "0.5000 [0.5000, 0.5000]"   # seed 123 only
        md = open(os.path.join(out, "realism_auc.md"), encoding="utf-8").read()
        assert "seed 7 at 5%: X: clone numbers outside real range" in md


def test_numbers_md_has_headline_and_details():
    with tempfile.TemporaryDirectory() as d:
        files, out = run(d)
        md = open(os.path.join(out, "numbers.md"), encoding="utf-8").read()
        assert md.count("# Results") == 1 and md.count("# Details") == 1, "numbers.md not rebuilt cleanly"
        for name in ("identity_by_system", "links_by_system", "repairs_by_severity", "usefulness_by_system",
                     "realism_auc"):
            for ext in ("csv", "md", "png"):
                f = f"{name}.{ext}"
                assert f in files and os.path.getsize(os.path.join(out, f)) > 0, f


def test_second_run_is_byte_identical():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        files, out1 = run(d1)
        _, out2 = run(d2)
        h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        differ = [f for f in files if h(os.path.join(out1, f)) != h(os.path.join(out2, f))]
        assert not differ, f"not deterministic: {differ}"


def test_rebuilding_in_the_same_folder_does_not_duplicate_numbers_md():
    with tempfile.TemporaryDirectory() as d:
        _, out = run(d)
        build_details(d, out)
        md = open(os.path.join(out, "numbers.md"), encoding="utf-8").read()
        assert md.count("# Details") == 1


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print("PASS", test.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", test.__name__, "-", e)
    assert failed == 0, f"{failed} of {len(tests)} tests failed"
    print(f"ALL {len(tests)} MAKE_REPORT_DETAILS TESTS PASSED")
