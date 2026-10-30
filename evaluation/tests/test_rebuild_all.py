import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from evaluation.rebuild_all import commands, realism_complete

# The rebuild wiring: the order of the steps, which steps may fail, and when the realism results count as complete.


def test_step_order_and_full_flag():
    labels = [label for label, _, _ in commands()]
    assert labels == ["experiments", "realism seed 42", "realism seed 7", "realism seed 123", "details"], labels
    assert "--full" not in commands()[0][1] and commands(full=True)[0][1][-1] == "--full"
    must = {label: m for label, _, m in commands()}
    assert must["experiments"] and must["details"] and not must["realism seed 7"]


def write(d, rows):
    path = os.path.join(d, "auc.csv")
    pd.DataFrame(rows, columns=["seed", "severity", "check", "auc"]).to_csv(path, index=False)
    return path


def test_realism_complete_with_a_failed_row():
    with tempfile.TemporaryDirectory() as d:
        rows = [(s, v, "X AUC", 0.5) for s in (42, 7) for v in (0.05, 0.15, 0.3) if (s, v) != (7, 0.05)]
        rows.append((7, 0.05, "FAILED: range", float("nan")))
        missing, failed = realism_complete(write(d, rows), seeds=(42, 7))
        assert missing == [] and failed == ["seed 7 at 5%: FAILED: range"], (missing, failed)


def test_realism_incomplete_is_named():
    with tempfile.TemporaryDirectory() as d:
        rows = [(42, v, "X AUC", 0.5) for v in (0.05, 0.15, 0.3)] + [(7, 0.15, "X AUC", 0.5)]
        missing, failed = realism_complete(write(d, rows), seeds=(42, 7))
        assert missing == [(7, 0.05), (7, 0.3)] and failed == [], missing
        assert len(realism_complete(os.path.join(d, "none.csv"), seeds=(42, 7))[0]) == 6


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
    print(f"ALL {len(tests)} REBUILD_ALL TESTS PASSED")
