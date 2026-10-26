import os, sys, tempfile, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from evaluation.make_report import build

# A made-up score file where every aggregate is known. Two systems, development seed 42, held-out seeds 7 and 123,
# two severities. Toolkit identity F1 at 5%: 0.9 on seed 42 (development), 0.8 and 0.6 on the held-out seeds.

AREAS = [("labels", "accuracy"), ("timestamps", "drifted_restored_exactly"), ("identity", "f1"),
         ("e2o", "f1"), ("o2o", "f1"), ("usefulness", "edge_f1")]


def scores():
    rows = []
    for system in ("Baseline", "Toolkit"):
        for seed, role in ((42, "development"), (7, "held-out"), (123, "held-out")):
            for sev in (0.05, 0.15):
                for area, metric in AREAS:
                    v = 0.5
                    if system == "Toolkit" and (area, metric) == ("identity", "f1") and sev == 0.05:
                        v = {42: 0.9, 7: 0.8, 123: 0.6}[seed]
                    rows.append((system, seed, role, sev, area, metric, v))
    rows.append(("Toolkit (clean log)", 0, "clean log", 0.0, "o2o", "f1", 1.0))
    return pd.DataFrame(rows, columns=["system", "seed", "seed_role", "severity", "area", "metric", "value"])


def build_into(d, df):
    path = os.path.join(d, "scores.csv")
    df.to_csv(path, index=False)
    return build(path, os.path.join(d, "out")), os.path.join(d, "out")


def test_aggregates_are_known_and_roles_are_kept_apart():
    with tempfile.TemporaryDirectory() as d:
        files, out = build_into(d, scores())
        held = pd.read_csv(os.path.join(out, "headline_heldout.csv")).set_index(["area", "metric", "system"])
        dev = pd.read_csv(os.path.join(out, "headline_development.csv")).set_index(["area", "metric", "system"])
        assert held.at[("identity", "f1", "Toolkit"), "5%"] == "0.7000 [0.6000, 0.8000]", held.loc["identity"]
        assert held.at[("identity", "f1", "Toolkit"), "15%"] == "0.5000 [0.5000, 0.5000]"
        assert float(dev.at[("identity", "f1", "Toolkit"), "5%"]) == 0.9
        numbers = open(os.path.join(out, "numbers.md"), encoding="utf-8").read()
        assert "0.7000 [0.6000, 0.8000]" in numbers and "Held-out (2 seeds)" in numbers
        assert "Toolkit (clean log): o2o / f1 = 1.0000" in numbers


def test_expected_files_are_written():
    with tempfile.TemporaryDirectory() as d:
        files, out = build_into(d, scores())
        for f in ("headline_heldout.csv", "headline_heldout.md", "headline_development.csv",
                  "headline_development.md", "f1_vs_severity.png", "scores_by_system_heldout.png", "numbers.md"):
            assert f in files and os.path.getsize(os.path.join(out, f)) > 0, f


def test_second_run_is_byte_identical():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        files, out1 = build_into(d1, scores())
        _, out2 = build_into(d2, scores())
        h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        differ = [f for f in files if h(os.path.join(out1, f)) != h(os.path.join(out2, f))]
        assert not differ, f"not deterministic: {differ}"


def test_missing_column_is_refused():
    with tempfile.TemporaryDirectory() as d:
        try:
            build_into(d, scores().drop(columns=["seed_role"]))
        except ValueError as e:
            print("   caught:", e)
            return
        raise AssertionError("a score file without seed_role was accepted")


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
    print(f"ALL {len(tests)} MAKE_REPORT TESTS PASSED")
