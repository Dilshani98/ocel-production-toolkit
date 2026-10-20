import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from reconstruction.baselines import apply_b1, apply_b2

# Hand-made tables (internal column names) where the right baseline output is known.


def tables():
    events = pd.DataFrame({
        "_record_id": ["e_1", "e_2", "e_3", "e_4", "e_5", " e_6"],
        "_activity": ["HeatSteelSheet", "HeatSteelSheet", " heat steel_sheet", "HeatSteelShet", "Form", "Form"],
        "_timestamp": ["2024-01-01 08:00:00+00:00"] * 6})
    objects = pd.DataFrame({
        "_item_id": ["a", "b", "c", "d", "e", "f", "g", "h"],
        "_item_type": ["Sheet"] * 6 + ["Coil", "Sheet"],
        "mass": ["1.5", "1.5", "2.0", "2.0", "2.0", None, "1.5", None],
        "material": ["DC01", "DC01", "DC01", "DC01", "DC01", None, "DC01", None]})
    relations = pd.DataFrame({
        "_record_id": ["e_1", "e_2", "e_3", "e_3", "e_1"],
        "_item_id": ["a", "b", "c", "f", "a"],
        "_item_type": ["Sheet", "Sheet", "Sheet", "Sheet", "Sheet"],
        "_role": ["on", "on", "input", "input", "on"]})            # last row duplicates the first
    o2o = pd.DataFrame({"_item_id": ["a", "b"], "_linked_item_id": ["g", "g"], "_link_type": ["created from"] * 2})
    return {"events": events, "objects": objects, "relations": relations, "o2o": o2o}


def test_b1_respells_by_key_but_does_not_fix_typos():
    out, report = apply_b1(tables())
    acts = out["events"]["_activity"].tolist()
    assert acts[2] == "HeatSteelSheet", "same key should take the most frequent spelling"
    assert acts[3] == "HeatSteelShet", "a typo has a different key and must stay"
    assert out["events"]["_record_id"].iloc[5] == "e_6", "IDs should be trimmed"
    assert report["values_respelled_activity"] == 1


def test_b1_drops_only_exact_duplicates():
    out, report = apply_b1(tables())
    assert len(out["relations"]) == 4 and report["duplicates_dropped_relations"] == 1
    assert len(out["events"]) == 6 and len(out["objects"]) == 8


def test_b1_parses_timestamps():
    out, _ = apply_b1(tables())
    assert str(out["events"]["_timestamp"].dt.tz) == "UTC" and out["events"]["_timestamp"].notna().all()


def test_b2_pair_only_merges_unique_pairs():
    out, report = apply_b2(tables(), max_group=2)
    # Sheets with (1.5, DC01): a, b -> a pair, merged. (2.0, DC01): c, d, e -> group of 3, not merged.
    # f and h are all-blank -> never merged. g is a Coil with (1.5, DC01) -> different type, not merged.
    clusters = dict(zip(out["clusters"]["_item_id"], out["clusters"]["_cluster_id"]))
    assert clusters == {"a": "a", "b": "a"}, clusters
    assert report["groups_merged"] == 1 and report["groups_too_large"] == 1
    assert "b" not in set(out["objects"]["_item_id"]) and "a" in set(out["objects"]["_item_id"])
    assert set(out["relations"]["_item_id"]) <= set(out["objects"]["_item_id"]), "dangling object after merge"
    assert set(out["o2o"]["_item_id"]) == {"a"} and len(out["o2o"]) == 1, "merged O2O duplicate not dropped"


def test_b2_larger_limit_and_no_limit():
    out3, _ = apply_b2(tables(), max_group=3)
    c3 = dict(zip(out3["clusters"]["_item_id"], out3["clusters"]["_cluster_id"]))
    assert c3 == {"a": "a", "b": "a", "c": "c", "d": "c", "e": "c"}, c3
    out_all, _ = apply_b2(tables(), max_group=None)
    assert dict(zip(out_all["clusters"]["_item_id"], out_all["clusters"]["_cluster_id"])) == c3
    assert "f" not in set(out_all["clusters"]["_item_id"]) and "h" not in set(out_all["clusters"]["_item_id"])


def test_values_after_a_blank_still_count():
    # Regression: a blank marker containing a NUL character made pandas ignore everything after it,
    # so these two different records were merged.
    t = tables()
    t["objects"] = pd.DataFrame({"_item_id": ["p", "q"], "_item_type": ["Sheet", "Sheet"],
                                 "material": [None, None], "mass": ["1.5", "2.0"]})
    out, _ = apply_b2(t, max_group=None)
    assert len(out["clusters"]) == 0, "records differing after a blank were merged"


def test_inputs_are_not_changed():
    t = tables()
    before = {k: v.copy() for k, v in t.items()}
    apply_b2(t, max_group=None)
    assert all(t[k].equals(before[k]) for k in t), "baseline changed its input tables"


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
    print(f"ALL {len(tests)} BASELINE TESTS PASSED")
