import sys, os, json
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from reconstruction.mapping import SchemaMapping, apply_mapping
from reconstruction.profiling import (profile_activity_labels, profile_unlinked_records,
                                      profile_event_ordering, build_profile_report)

# Part 1: small hand-made tables where every answer is known. Part 2: the messy data at all three
# severities, checked against the ground truth (tests may read it; the profiling code never does).


def events_table(rows):
    df = pd.DataFrame(rows, columns=["_activity", "_timestamp"])
    df.insert(0, "_record_id", [f"e{i}" for i in range(len(df))])
    return df


def test_rare_similar_label_is_a_suspect():
    # 60 + 60 common rows, one typo of "Assemble" (similar) and one rare unrelated label (not similar)
    ev = events_table([("Assemble", "2024-01-01")] * 60 + [("Inspect", "2024-01-01")] * 60
                      + [("Assmble", "2024-01-01"), ("Audit", "2024-01-01")])
    s = profile_activity_labels(ev)
    assert list(s["label"]) == ["Assmble"], s
    row = s.iloc[0]
    assert row["likely_intended"] == "Assemble" and row["count"] == 1
    assert 0.85 <= row["similarity"] < 1.0


def test_common_labels_are_never_suspects():
    # two similar labels, both common: neither is rare, so neither is reported
    ev = events_table([("Assemble", "2024-01-01")] * 50 + [("Assembled", "2024-01-01")] * 50)
    assert profile_activity_labels(ev).empty


def test_similarity_threshold_is_respected():
    ev = events_table([("Assemble", "2024-01-01")] * 99 + [("Assmble", "2024-01-01")])
    assert len(profile_activity_labels(ev, similarity=0.85)) == 1
    assert profile_activity_labels(ev, similarity=0.99).empty


def test_unlinked_records_are_counted_once():
    ev = events_table([("A", "2024-01-01")] * 5)
    rel = pd.DataFrame({"_record_id": ["e0", "e0", "e2"], "_item_id": ["o1", "o2", "o1"]})
    assert profile_unlinked_records(ev, rel) == 3          # e1, e3 and e4; two links on e0 do not count twice


def test_ordering_compares_with_the_previous_row_in_the_whole_file():
    # row 2 (activity B) is earlier than row 1 (activity A): counted, although it is B's first row.
    # Equal times are not backward.
    ev = events_table([("A", "2024-01-01 10:00:00"), ("A", "2024-01-01 10:05:00"),
                       ("B", "2024-01-01 10:03:00"), ("B", "2024-01-01 10:03:00"),
                       ("A", "2024-01-01 10:06:00")])
    r = profile_event_ordering(ev)
    assert r == {"out_of_order_records": 1, "share_out_of_order": 0.2}, r


def test_ordering_on_an_ordered_table_is_zero():
    ev = events_table([("A", f"2024-01-01 10:0{i}:00") for i in range(5)])
    assert profile_event_ordering(ev) == {"out_of_order_records": 0, "share_out_of_order": 0.0}


def test_report_counts():
    ev = events_table([("A", "2024-01-01")] * 3)
    obj = pd.DataFrame({"_item_id": ["o1", "o2"], "_item_type": ["T", "T"]})
    rel = pd.DataFrame({"_record_id": ["e0"], "_item_id": ["o1"]})
    o2o = pd.DataFrame({"_item_id": ["o1", "o1", "o2"], "_linked_item_id": ["o2", "o2", "o1"]})
    r = build_profile_report(ev, obj, rel, o2o)
    assert (r["n_events"], r["n_items"], r["n_links"], r["n_item_to_item_links"]) == (3, 2, 1, 3)
    assert r["duplicate_item_to_item_links"] == 1 and r["unlinked_records"] == 2


DATA_DIR = os.path.join(PROJECT_ROOT, "data", "messy")
MAPPING = SchemaMapping("record_id", "activity_name", "event_time", "item_id",
                        "item_category", "linked_item_id", "link_type", "role")


def test_messy_data_all_severities():
    # every reported suspect is a label the injector distorted, and it points to the original label
    for tag in ("sev0_05", "sev0_15", "sev0_3"):
        if not os.path.exists(os.path.join(DATA_DIR, f"messy_events_{tag}.csv")):
            raise AssertionError(f"missing data for {tag}: run tests/generate_datasets.py first")
        load = lambda n: apply_mapping(pd.read_csv(os.path.join(DATA_DIR, f"messy_{n}_{tag}.csv")), MAPPING, n)
        events = load("events")
        r = build_profile_report(events, load("objects"), load("relations"), load("o2o"))
        truth = json.load(open(os.path.join(DATA_DIR, f"ground_truth_{tag}.json")))
        distorted = {c["details"]["distorted_label"]: c["details"]["original_label"]
                     for c in truth if c["pattern"] == "label_distortion"}
        s = r["label_suspects"]
        assert len(s) > 0 and r["n_events"] == len(events)
        wrong = [(l, i) for l, i in zip(s["label"], s["likely_intended"]) if distorted.get(l) != i]
        assert not wrong, f"{tag}: suspects that are not injected typos (or point to the wrong label): {wrong}"
        assert set(s["label"]) == set(distorted), f"{tag}: typos not reported: {set(distorted) - set(s['label'])}"
        assert r["out_of_order_records"]["out_of_order_records"] > 0     # drift leaves backward steps
        print(f"   {tag}: {len(s)} suspects, all injected typos ({len(distorted)} distorted labels in total); "
              f"{r['out_of_order_records']['out_of_order_records']} backward steps; "
              f"{r['unlinked_records']} unlinked records")


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
    print(f"ALL {len(tests)} PROFILING TESTS PASSED")
