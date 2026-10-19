import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from reconstruction.cleaning import repair_timestamp_drift

# Small hand-made tables where the right answer is known. No messy data, no ground truth.
# Each group: a "before" event, the culprit C, and an "after" event, all at the same moment.
# Groups are 10 minutes apart. Drift moves C in groups 30..89 (60 events).

OTHERS = ["A", "B", "D", "E"]
SHIFT = 120
BLOCK = range(30, 90)


def make_events(n_groups=120, varied_neighbours=True):
    t0 = pd.Timestamp("2024-01-01", tz="UTC")
    rows = []
    for k in range(n_groups):
        t = t0 + pd.Timedelta(minutes=10 * k)
        before = OTHERS[k % 4] if varied_neighbours else "B"
        after = OTHERS[(k + 2) % 4] if varied_neighbours else "D"
        rows += [(before, t), ("C", t), (after, t)]
    df = pd.DataFrame(rows, columns=["_activity", "_timestamp"])
    df.insert(0, "_record_id", [f"e{i}" for i in range(len(df))])
    return df


def drift(df, seconds):
    df = df.copy()
    drifted = (df["_activity"] == "C") & (df.index // 3).isin(BLOCK)
    df.loc[drifted, "_timestamp"] += pd.Timedelta(seconds=seconds)
    return df, drifted


def check_restored(seconds, direction):
    clean = make_events()
    messy, drifted = drift(clean, seconds)
    repaired, report, log = repair_timestamp_drift(messy)
    print(f"{direction:5s} shift:", report)
    assert report["status"] == "repaired"
    assert report.get("direction") == direction, f"direction {report.get('direction')} != {direction}"
    assert report["culprit_activity"] == "C"
    assert report["shift_seconds"] == SHIFT
    assert report["n_corrected"] == drifted.sum() == len(log)
    assert (repaired["_timestamp"] == clean["_timestamp"]).all(), "not every timestamp restored"
    assert report["backward_after"] == 0


def test_late_shift_restored_exactly():
    check_restored(+SHIFT, "late")


def test_early_shift_restored_exactly():
    check_restored(-SHIFT, "early")


def test_undamaged_table_unchanged():
    clean = make_events()
    repaired, report, log = repair_timestamp_drift(clean)
    print("clean      :", report)
    assert report["status"] == "no systematic drift found"
    assert report["backward_before"] == 0
    assert len(log) == 0
    assert (repaired["_timestamp"] == clean["_timestamp"]).all(), "repair changed an undamaged table"


def test_ambiguous_not_repaired():
    # Neighbours are always the same activity, so both sides of every backward step
    # are dominated by one activity and the direction cannot be told apart.
    clean = make_events(varied_neighbours=False)
    messy, _ = drift(clean, +SHIFT)
    repaired, report, log = repair_timestamp_drift(messy)
    print("ambiguous  :", report)
    assert report["status"] == "ambiguous"
    assert len(log) == 0
    assert (repaired["_timestamp"] == messy["_timestamp"]).all(), "ambiguous case was changed"


if __name__ == "__main__":
    tests = [test_late_shift_restored_exactly, test_early_shift_restored_exactly,
             test_undamaged_table_unchanged, test_ambiguous_not_repaired]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, "-", e)
    assert failed == 0, f"{failed} of {len(tests)} tests failed"
    print("ALL TIMESTAMP UNIT TESTS PASSED")
