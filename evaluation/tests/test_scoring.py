import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from evaluation.scoring import build_truth, score

# A tiny log where every right score is known.
# Clean IDs: events c1..c4; objects cA, cB (SteelSheet), cC, cD (SteelCoil).
# Messy IDs (rename table): c1->e_3, c2->e_1, c3->e_4, c4->e_2; cA->o_s_2, cB->o_s_1, cC->o_c_1, cD->o_c_2.
# Injected: clone o_s_3 of o_s_2 takes the e_4 link; link (e_2, o_s_1) removed; O2O target of o_s_1
# swapped from o_c_2 to o_c_1; e_1 drifted +5 s; e_4 relabelled Heat -> Het.

T0 = pd.Timestamp("2024-01-01 08:00:00", tz="UTC")
ts = lambda s: T0 + pd.Timedelta(seconds=s)

CLEAN = {
    "events": pd.DataFrame({"_record_id": ["c1", "c2", "c3", "c4"],
                            "_activity": ["Split", "Form", "Heat", "Split"],
                            "_timestamp": [ts(0), ts(10), ts(20), ts(30)]}),
    "objects": pd.DataFrame({"_item_id": ["cA", "cB", "cC", "cD"],
                             "_item_type": ["SteelSheet", "SteelSheet", "SteelCoil", "SteelCoil"]}),
    "relations": pd.DataFrame({"_record_id": ["c1", "c1", "c2", "c3", "c4"],
                               "_item_id": ["cA", "cC", "cA", "cA", "cB"],
                               "_item_type": ["SteelSheet", "SteelCoil", "SteelSheet", "SteelSheet", "SteelSheet"],
                               "_role": ["output", "on", "input", "on", "output"]}),
    "o2o": pd.DataFrame({"_item_id": ["cA", "cB"], "_linked_item_id": ["cC", "cD"],
                         "_link_type": ["created from", "created from"]}),
}
EV = {"c1": "e_3", "c2": "e_1", "c3": "e_4", "c4": "e_2"}
OB = {"cA": "o_s_2", "cB": "o_s_1", "cC": "o_c_1", "cD": "o_c_2"}
GT = [
    {"pattern": "object_clones", "change_type": "clone_created", "target_id": "o_s_2", "details": {"clone_id": "o_s_3"}},
    {"pattern": "object_clones", "change_type": "relation_reassigned", "target_id": "o_s_2",
     "details": {"clone_id": "o_s_3", "event_id": "e_4"}},
    {"pattern": "missing_e2o", "change_type": "relation_removed", "target_id": "o_s_1",
     "details": {"event_id": "e_2", "activity": "Split", "object_type": "SteelSheet"}},
    {"pattern": "incorrect_o2o", "change_type": "target_swapped", "target_id": "o_s_1",
     "details": {"original_target": "o_c_2", "wrong_target": "o_c_1", "qualifier": "created from"}},
    {"pattern": "timestamp_drift", "change_type": "timestamp_shifted", "target_id": "e_1",
     "details": {"original_timestamp": str(ts(10)), "drift_seconds": 5}},
    {"pattern": "label_distortion", "change_type": "activity_relabelled", "target_id": "e_4",
     "details": {"original_label": "Heat", "distorted_label": "Het"}},
    {"pattern": "pseudonymisation", "change_type": "ids_renamed", "target_id": "all",
     "details": {"objects": OB, "events": EV}},
]

SHEETS, COILS = ["SteelSheet"] * 3, ["SteelCoil"] * 2
MESSY = {
    "events": pd.DataFrame({"_record_id": ["e_3", "e_1", "e_4", "e_2"], "_activity": ["Split", "Form", "Het", "Split"],
                            "_timestamp": [ts(0), ts(15), ts(20), ts(30)]}),
    "objects": pd.DataFrame({"_item_id": ["o_s_1", "o_s_2", "o_s_3", "o_c_1", "o_c_2"], "_item_type": SHEETS + COILS}),
    "relations": pd.DataFrame({"_record_id": ["e_3", "e_3", "e_1", "e_4"], "_item_id": ["o_s_2", "o_c_1", "o_s_2", "o_s_3"],
                               "_item_type": ["SteelSheet", "SteelCoil", "SteelSheet", "SteelSheet"],
                               "_role": ["output", "on", "input", "on"]}),
    "o2o": pd.DataFrame({"_item_id": ["o_s_2", "o_s_1"], "_linked_item_id": ["o_c_1", "o_c_1"],
                         "_link_type": ["created from", "created from"]}),
}


def perfect():
    """The right answer: clean values with messy IDs, clone merged into o_s_2."""
    return {
        "events": pd.DataFrame({"_record_id": ["e_3", "e_1", "e_4", "e_2"], "_activity": ["Split", "Form", "Heat", "Split"],
                                "_timestamp": [ts(0), ts(10), ts(20), ts(30)]}),
        "objects": pd.DataFrame({"_item_id": ["o_s_1", "o_s_2", "o_c_1", "o_c_2"], "_item_type": SHEETS[:2] + COILS}),
        "relations": pd.DataFrame({"_record_id": ["e_3", "e_3", "e_1", "e_4", "e_2"],
                                   "_item_id": ["o_s_2", "o_c_1", "o_s_2", "o_s_2", "o_s_1"],
                                   "_item_type": ["SteelSheet", "SteelCoil", "SteelSheet", "SteelSheet", "SteelSheet"],
                                   "_role": ["output", "on", "input", "on", "output"]}),
        "o2o": pd.DataFrame({"_item_id": ["o_s_2", "o_s_1"], "_linked_item_id": ["o_c_1", "o_c_2"],
                             "_link_type": ["created from", "created from"]}),
        "clusters": pd.DataFrame({"_item_id": ["o_s_2", "o_s_3"], "_cluster_id": ["o_s_2", "o_s_2"]}),
    }


TRUTH = build_truth(CLEAN, GT)


def run(recon):
    table = score(recon, MESSY, TRUTH, CLEAN, system="test")
    return {(a, m): v for a, m, v in zip(table["area"], table["metric"], table["value"])}


def close(a, b):
    return abs(a - b) < 1e-9


def test_translation_and_truth():
    assert TRUTH.e2o == {("e_3", "o_s_2", "output"), ("e_3", "o_c_1", "on"), ("e_1", "o_s_2", "input"),
                         ("e_4", "o_s_2", "on"), ("e_2", "o_s_1", "output")}
    assert TRUTH.true_id["o_s_3"] == "o_s_2"
    assert TRUTH.damaged_e2o == {("e_4", "o_s_2", "on"), ("e_2", "o_s_1", "output")}
    assert TRUTH.damaged_o2o == {("o_s_1", "o_c_2", "created from")}


def test_perfect_is_one():
    s = run(perfect())
    for area in ("e2o", "o2o", "identity"):
        for m in ("precision", "recall", "f1"):
            assert close(s[(area, m)], 1.0), (area, m, s[(area, m)])
    assert s[("e2o", "affected_recall")] == 1.0 and s[("o2o", "affected_recall")] == 1.0
    assert s[("labels", "accuracy")] == 1.0 and s[("labels", "distorted_restored")] == 1.0
    assert s[("labels", "valid_wrongly_changed")] == 0
    assert s[("timestamps", "drifted_restored_exactly")] == 1.0 and s[("timestamps", "untouched_changed")] == 0
    assert s[("identity", "false_merges")] == 0 and s[("identity", "impure_clusters")] == 0
    assert s[("events", "missing_events")] == 0 and s[("events", "extra_events")] == 0
    assert all(v == 0 for (a, m), v in s.items() if a == "validity"), "perfect output has validity problems"
    assert s[("usefulness", "edge_f1")] == 1.0 and s[("usefulness", "edge_frequency_difference")] == 0.0
    assert s[("usefulness", "object_count_abs_difference")] == 0


def test_empty_is_zero():
    empty = {"events": pd.DataFrame(columns=["_record_id", "_activity", "_timestamp"]),
             "objects": pd.DataFrame(columns=["_item_id", "_item_type"]),
             "relations": pd.DataFrame(columns=["_record_id", "_item_id", "_item_type", "_role"]),
             "o2o": pd.DataFrame(columns=["_item_id", "_linked_item_id", "_link_type"])}
    s = run(empty)
    for area in ("e2o", "o2o", "identity"):
        for m in ("precision", "recall", "f1"):
            assert s[(area, m)] == 0.0, (area, m, s[(area, m)])
    assert s[("events", "missing_events")] == 4 and s[("labels", "accuracy")] == 0.0


def test_one_wrong_e2o_triple():
    r = perfect()
    r["relations"].loc[1, "_item_id"] = "o_c_2"            # (e_3, o_c_1, on) -> wrong coil
    s = run(r)
    assert close(s[("e2o", "precision")], 0.8) and close(s[("e2o", "recall")], 0.8) and close(s[("e2o", "f1")], 0.8)


def test_unmerged_clone_does_not_match():
    r = perfect()
    r["relations"].loc[3, "_item_id"] = "o_s_3"            # clone kept, not merged
    r["clusters"] = None
    s = run(r)
    assert close(s[("e2o", "precision")], 0.8) and close(s[("e2o", "recall")], 0.8)
    assert s[("identity", "recall")] == 0.0 and s[("identity", "missed_merges")] == 1


def test_clone_only_cluster_named_like_original_gets_no_credit():
    r = perfect()
    r["clusters"] = pd.DataFrame({"_item_id": ["o_s_3"], "_cluster_id": ["o_s_2"]})
    s = run(r)
    # All three A triples use "o_s_2", whose cluster holds only the clone -> unresolved.
    assert close(s[("e2o", "precision")], 0.4) and close(s[("e2o", "recall")], 0.4)


def test_correct_merge_any_name_gets_credit():
    r = perfect()
    r["clusters"] = pd.DataFrame({"_item_id": ["o_s_2", "o_s_3"], "_cluster_id": ["o_s_3", "o_s_3"]})
    r["relations"]["_item_id"] = r["relations"]["_item_id"].replace({"o_s_2": "o_s_3"})
    r["o2o"]["_item_id"] = r["o2o"]["_item_id"].replace({"o_s_2": "o_s_3"})
    r["objects"]["_item_id"] = r["objects"]["_item_id"].replace({"o_s_2": "o_s_3"})
    s = run(r)
    assert s[("e2o", "f1")] == 1.0 and s[("o2o", "f1")] == 1.0 and s[("identity", "f1")] == 1.0


def test_impure_cluster_is_a_false_merge():
    r = perfect()
    r["clusters"] = pd.DataFrame({"_item_id": ["o_s_1", "o_s_2"], "_cluster_id": ["M", "M"]})
    r["relations"]["_item_id"] = r["relations"]["_item_id"].replace({"o_s_1": "M", "o_s_2": "M"})
    r["relations"].loc[3, "_item_id"] = "o_s_3"            # clone left unmerged
    s = run(r)
    assert close(s[("e2o", "precision")], 0.2) and close(s[("e2o", "recall")], 0.2)
    assert s[("identity", "false_merges")] == 1 and s[("identity", "impure_clusters")] == 1
    assert s[("identity", "precision")] == 0.0 and s[("identity", "recall")] == 0.0


def test_valid_label_wrongly_changed():
    r = perfect()
    r["events"].loc[0, "_activity"] = "Form"               # e_3 was correct (Split)
    s = run(r)
    assert s[("labels", "valid_wrongly_changed")] == 1 and close(s[("labels", "accuracy")], 0.75)


def test_unrepaired_drift():
    r = perfect()
    r["events"].loc[1, "_timestamp"] = ts(15)              # e_1 left at its drifted time
    s = run(r)
    assert s[("timestamps", "drifted_restored_exactly")] == 0.0
    assert s[("timestamps", "drifted_mean_abs_error_s")] == 5.0 and s[("timestamps", "untouched_changed")] == 0


def test_messy_as_is():
    s = run({**MESSY})
    assert close(s[("e2o", "precision")], 0.75) and close(s[("e2o", "recall")], 0.6)
    assert s[("e2o", "affected_recall")] == 0.0
    assert close(s[("o2o", "precision")], 0.5) and s[("o2o", "affected_recall")] == 0.0
    assert close(s[("labels", "accuracy")], 0.75) and s[("timestamps", "drifted_restored_exactly")] == 0.0


def test_dangling_relation_is_counted():
    r = perfect()
    r["relations"] = pd.concat([r["relations"], pd.DataFrame(
        {"_record_id": ["e_9"], "_item_id": ["o_s_1"], "_item_type": ["SteelSheet"], "_role": ["on"]})], ignore_index=True)
    s = run(r)
    assert s[("validity", "relations_unknown_event")] == 1


def test_usefulness_ties_broken_by_file_row():
    r = perfect()
    r["events"]["_timestamp"] = ts(0)                      # all events at the same moment
    first = run(r)[("usefulness", "edge_f1")]
    assert all(run(r)[("usefulness", "edge_f1")] == first for _ in range(3))
    assert first == 1.0, "with equal timestamps, file order should give the clean order back"


def test_broken_rename_table_is_rejected():
    broken = [dict(g) for g in GT]
    broken[-1] = {**GT[-1], "details": {"objects": {k: v for k, v in OB.items() if k != "cD"}, "events": EV}}
    try:
        build_truth(CLEAN, broken)
    except ValueError as e:
        print("   caught:", e)
        return
    raise AssertionError("missing rename was not caught")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, "-", e)
    assert failed == 0, f"{failed} of {len(tests)} tests failed"
    print(f"ALL {len(tests)} SCORING TESTS PASSED")
