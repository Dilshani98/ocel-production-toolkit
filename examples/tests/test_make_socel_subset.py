import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pandas as pd
from make_socel_subset import subset

# The subset rule on a hand-made log of 10 events (file order = time order), window = rows 2..5 (start 0.2, end 0.6).
# Object A has all its events in the window (whole); B has one event outside (not whole); M is a machine on every
# event (never whole, but kept as a shared resource on kept events); C is only linked to event e4 with B.

EVENTS = pd.DataFrame({"record_id": [f"e{i}" for i in range(10)], "activity_name": ["x"] * 10,
                       "event_time": [f"2026-01-01 00:0{i}:00" for i in range(10)]})
REL = pd.DataFrame([("e2", "A"), ("e3", "A"), ("e3", "B"), ("e4", "B"), ("e4", "C"), ("e7", "B")]
                   + [(f"e{i}", "M") for i in range(10)], columns=["record_id", "item_id"])
OBJ = pd.DataFrame({"item_id": ["A", "B", "C", "M", "Z"]})
O2O = pd.DataFrame({"item_id": ["A", "A", "C", "Z"], "linked_item_id": ["B", "Z", "B", "A"],
                    "link_type": ["created from"] * 4})


def run():
    return subset({"events": EVENTS, "objects": OBJ, "relations": REL, "o2o": O2O}, 0.2, 0.6)


def test_whole_objects_choose_the_events():
    s = run()
    # whole objects in rows 2..5: A (e2, e3) and C (e4); B also has e7 outside, M has events outside
    assert sorted(s["events"]["record_id"]) == ["e2", "e3", "e4"], s["events"]


def test_objects_are_everything_on_kept_events():
    s = run()
    assert sorted(s["objects"]["item_id"]) == ["A", "B", "C", "M"]          # Z is on no kept event
    assert len(s["relations"]) == 3 + 2 + 3 and s["relations"]["record_id"].isin(["e2", "e3", "e4"]).all()


def test_o2o_needs_both_ends_and_nothing_dangles():
    s = run()
    assert sorted(zip(s["o2o"]["item_id"], s["o2o"]["linked_item_id"])) == [("A", "B"), ("C", "B")]
    objs = set(s["objects"]["item_id"])
    assert s["relations"]["item_id"].isin(objs).all() and s["relations"]["record_id"].isin(s["events"]["record_id"]).all()


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
    print(f"ALL {len(tests)} SOCEL SUBSET TESTS PASSED")
