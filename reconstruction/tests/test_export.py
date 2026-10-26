import os, sys, sqlite3, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from pm4py.objects.ocel.validation import ocel20_rel_validation
from reconstruction.export import write, read, add_keys, file_objects, FORMATS

# A tiny log: 3 events, 4 objects of 2 types, 6 event-object links, 2 object-object links, one attribute each.

T0 = pd.Timestamp("2024-01-01 06:00:00", tz="UTC")


def tables():
    return {"events": pd.DataFrame({"_record_id": ["e1", "e2", "e3"], "_activity": ["Cut", "Join", "Cut"],
                                    "_timestamp": [T0, T0 + pd.Timedelta(seconds=90), T0 + pd.Timedelta(seconds=150)],
                                    "duration": [1.5, 2.0, 1.25]}),
            "objects": pd.DataFrame({"_item_id": ["a", "b", "h", "m"], "_item_type": ["Part", "Part", "Hinge", "Machine"],
                                     "mass": [0.5, 0.75, None, None]}),
            "relations": pd.DataFrame({"_record_id": ["e1", "e1", "e2", "e2", "e2", "e3"],
                                       "_item_id": ["a", "m", "a", "b", "h", "b"],
                                       "_item_type": ["Part", "Machine", "Part", "Part", "Hinge", "Part"],
                                       "_role": ["out", "with", "in", "in", "out", "out"]}),
            "o2o": pd.DataFrame({"_item_id": ["h", "h"], "_linked_item_id": ["a", "b"],
                                 "_link_type": ["created from", "created from"]})}


def triples(t):
    return (set(zip(t["relations"]["_record_id"], t["relations"]["_item_id"], t["relations"]["_role"])),
            set(zip(t["o2o"]["_item_id"], t["o2o"]["_linked_item_id"], t["o2o"]["_link_type"])))


def test_round_trip_in_every_format():
    t = tables()
    with tempfile.TemporaryDirectory() as d:
        for fmt in FORMATS:
            path = write(t, os.path.join(d, f"log.{fmt}"), fmt)
            back = read(path, fmt)
            assert len(back["events"]) == 3 and len(back["objects"]) == 4, fmt
            assert triples(back) == triples(t), f"{fmt}: links changed in the round trip"
            got = pd.to_datetime(back["events"].sort_values("_record_id")["_timestamp"], utc=True).tolist()
            assert got == t["events"]["_timestamp"].tolist(), f"{fmt}: timestamps changed"
            acts = dict(zip(back["events"]["_record_id"], back["events"]["_activity"]))
            assert acts == {"e1": "Cut", "e2": "Join", "e3": "Cut"}, fmt


def test_keyed_sqlite_meets_all_24_constraints():
    with tempfile.TemporaryDirectory() as d:
        path = write(tables(), os.path.join(d, "log.sqlite"), "sqlite")
        ok, bad = ocel20_rel_validation.apply(path)
        assert not bad and len(ok) == 24, bad


def test_unkeyed_pm4py_sqlite_misses_the_key_constraints():
    with tempfile.TemporaryDirectory() as d:
        path = write(tables(), os.path.join(d, "log.sqlite"), "sqlite", keys=False)
        ok, bad = ocel20_rel_validation.apply(path)
        assert len(bad) == 11 and all("key" in c for c in bad), bad


def test_duplicate_link_fails_when_keys_are_added():
    t = tables()
    t["relations"] = pd.concat([t["relations"], t["relations"].iloc[[0]]], ignore_index=True)
    with tempfile.TemporaryDirectory() as d:
        try:
            write(t, os.path.join(d, "log.sqlite"), "sqlite")
        except sqlite3.IntegrityError as e:
            print("   caught:", e)
            return
    raise AssertionError("a duplicate event-object link was not caught")


def test_links_to_unknown_objects_are_refused_in_every_format():
    # pm4py's writers silently drop such links, so write() must refuse instead of losing them
    dangling_o2o = tables()
    dangling_o2o["o2o"] = pd.concat([dangling_o2o["o2o"], pd.DataFrame(
        {"_item_id": ["h"], "_linked_item_id": ["ghost"], "_link_type": ["created from"]})], ignore_index=True)
    dangling_e2o = tables()
    dangling_e2o["relations"] = pd.concat([dangling_e2o["relations"], pd.DataFrame(
        {"_record_id": ["e3"], "_item_id": ["ghost"], "_item_type": ["Part"], "_role": ["in"]})], ignore_index=True)
    with tempfile.TemporaryDirectory() as d:
        for name, t in (("O2O", dangling_o2o), ("E2O", dangling_e2o)):
            for fmt in FORMATS:
                try:
                    write(t, os.path.join(d, f"log.{fmt}"), fmt)
                except ValueError:
                    continue
                raise AssertionError(f"{name} link to an unknown object was written as {fmt}")


def with_isolated(object_id, object_type, mass):
    t = tables()
    t["objects"] = pd.concat([t["objects"], pd.DataFrame(
        {"_item_id": [object_id], "_item_type": [object_type], "mass": [mass]})], ignore_index=True)
    return t


def test_isolated_objects_are_kept_in_every_format():
    # Amendment 26 Oct: pm4py drops objects with no event link; OCEL 2.0 allows them, so write() adds them back
    t = with_isolated("p", "Part", 0.25)
    with tempfile.TemporaryDirectory() as d:
        for fmt in FORMATS:
            path = write(t, os.path.join(d, f"log.{fmt}"), fmt)
            in_file = file_objects(path, fmt).set_index("_item_id")          # the file itself, no pm4py reader
            assert "p" in in_file.index and in_file.at["p", "_item_type"] == "Part", f"{fmt}: not in the file"
            assert float(in_file.at["p", "mass"]) == 0.25, f"{fmt}: attribute not in the file"
            back = read(path, fmt)
            objs = back["objects"].set_index("_item_id")
            assert "p" in objs.index, f"{fmt}: the isolated object was dropped"
            assert objs.at["p", "_item_type"] == "Part", fmt
            assert float(objs.at["p", "mass"]) == 0.25, f"{fmt}: attribute value lost"
            assert len(back["objects"]) == 5 and triples(back) == triples(t), fmt
        ok, bad = ocel20_rel_validation.apply(os.path.join(d, "log.sqlite"))
        assert not bad, f"keyed SQLite with a restored object fails: {bad}"


def test_isolated_object_of_an_unwritten_type_is_refused():
    t = with_isolated("q", "Pin", 0.1)               # no linked object is a Pin: no type declaration to use
    with tempfile.TemporaryDirectory() as d:
        for fmt in FORMATS:
            try:
                write(t, os.path.join(d, f"log.{fmt}"), fmt)
            except ValueError:
                continue
            raise AssertionError(f"{fmt}: an object of an undeclared type was written or silently dropped")


def test_unknown_format_is_rejected():
    try:
        write(tables(), "unused", "csv")
    except ValueError:
        return
    raise AssertionError("unknown format accepted")


def test_inputs_are_not_changed():
    t = tables()
    before = {k: v.copy() for k, v in t.items()}
    with tempfile.TemporaryDirectory() as d:
        write(t, os.path.join(d, "log.sqlite"), "sqlite")
    assert all(t[k].equals(before[k]) for k in t)


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
    print(f"ALL {len(tests)} EXPORT TESTS PASSED")
