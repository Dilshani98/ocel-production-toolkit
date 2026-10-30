import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from reconstruction.checks import check_config, read_tables, check_columns, check_tables, parse_settings
from reconstruction.identity import IdentitySettings
from reconstruction.o2o import O2OSettings

# Hand-made configs and tables where the expected problems are known exactly.

COLUMNS = {"record_id_col": "id", "activity_col": "act", "timestamp_col": "when", "item_id_col": "obj",
           "item_type_col": "kind", "linked_item_id_col": "other", "link_type_col": "how", "role_col": "as"}


def config(folder, **over):
    c = {"folder": folder, "files": {k: f"{k}.csv" for k in ("events", "objects", "relations", "o2o")},
         "columns": dict(COLUMNS)}
    c.update(over)
    return c


def write_files(folder, events="id,act,when\ne1,A,2026-01-01 10:00\n"):
    files = {"events.csv": events, "objects.csv": "obj,kind\no1,T\n", "relations.csv": "id,obj,kind,as\ne1,o1,T,x\n",
             "o2o.csv": "obj,other,how\n"}
    for name, text in files.items():
        open(os.path.join(folder, name), "w").write(text)


def tables(**over):
    t = {"events": pd.DataFrame({"_record_id": ["e1", "e2"], "_activity": ["A", "B"],
                                 "_timestamp": ["2026-01-01 10:00", "2026-01-01 10:05"]}),
         "objects": pd.DataFrame({"_item_id": ["o1", "o2"], "_item_type": ["T", "T"]}),
         "relations": pd.DataFrame({"_record_id": ["e1", "e2"], "_item_id": ["o1", "o2"], "_item_type": ["T", "T"],
                                    "_role": ["x", "x"]}),
         "o2o": pd.DataFrame({"_item_id": ["o1"], "_linked_item_id": ["o2"], "_link_type": ["created from"]})}
    t.update(over)
    return t


def test_good_config_and_tables_have_no_problems():
    with tempfile.TemporaryDirectory() as d:
        write_files(d)
        c = config(d)
        assert check_config(c) == []
        raw, problems = read_tables(c)
        assert problems == [] and check_columns(raw, c) == []
    assert check_tables(tables()) == []
    assert check_tables(tables(o2o=tables()["o2o"].iloc[0:0])) == []          # no O2O links is allowed


def test_config_problems_are_all_listed_and_named():
    with tempfile.TemporaryDirectory() as d:
        write_files(d)
        os.remove(os.path.join(d, "objects.csv"))
        cols = {k: v for k, v in COLUMNS.items() if k != "role_col"}
        cols["colour_col"] = "c"
        c = config(d, columns=cols)
        del c["files"]["o2o"]
        problems = check_config(c)
        assert problems == ['config key "files.o2o" is missing', 'config key "columns.role_col" is missing',
                            'config key "columns.colour_col" is not known (expected: record_id_col, activity_col, '
                            'timestamp_col, item_id_col, item_type_col, linked_item_id_col, link_type_col, role_col)',
                            f"input file not found: {os.path.join(d, 'objects.csv')} (files.objects)"], problems
    assert check_config([1, 2]) == ['the config must be a JSON object with the keys "files" and "columns"']
    assert check_config({"folder": "no/such/folder", "files": {}, "columns": {}})[-1] == \
        "input folder not found: no/such/folder"
    assert len(check_config({})) == 2                                          # files and columns both named


def test_empty_file_and_missing_column():
    with tempfile.TemporaryDirectory() as d:
        write_files(d)
        open(os.path.join(d, "o2o.csv"), "w").close()
        c = config(d, columns={**COLUMNS, "timestamp_col": "time"})
        raw, problems = read_tables(c)
        assert problems == [f"{os.path.join(d, 'o2o.csv')}: the file is empty (not even a header row)"], problems
        assert check_columns(raw, c) == [f'{os.path.join(d, "events.csv")}: column "time" (columns.timestamp_col) '
                                         f'not found; the file has: id, act, when']


def test_table_problems_are_all_listed_with_counts_and_examples():
    ev = pd.DataFrame({"_record_id": ["e1", "e1", "e2", "e3", "e4"], "_activity": ["A"] * 5,
                       "_timestamp": ["2026-01-01 10:00", "2026-01-01 10:01", None, "  ", "not a date"]})
    rel = pd.DataFrame({"_record_id": ["e1", "e9"], "_item_id": ["o1", "o8"], "_item_type": ["T", "T"],
                        "_role": ["x", "x"]})
    o2o = pd.DataFrame({"_item_id": ["o7"], "_linked_item_id": ["o6"], "_link_type": ["created from"]})
    problems = check_tables(tables(events=ev, relations=rel, o2o=o2o))
    assert problems == ["events: 1 duplicate event IDs (e.g. e1)",
                        "events: 2 events have no timestamp (e.g. e2, e3)",
                        "events: 1 timestamps cannot be read as dates (e.g. not a date)",
                        "relations: 1 links point to events that do not exist (e.g. e9)",
                        "relations: 1 links point to objects that do not exist (e.g. o8)",
                        "o2o: 1 links point to objects that do not exist (source) (e.g. o7)",
                        "o2o: 1 links point to objects that do not exist (target) (e.g. o6)"], problems


def test_empty_tables_are_problems():
    t = tables()
    problems = check_tables(tables(events=t["events"].iloc[0:0], relations=t["relations"].iloc[0:0]),
                            {"events": "ev.csv", "objects": "ob.csv", "relations": "rel.csv", "o2o": "o.csv"})
    assert problems[:2] == ["ev.csv: the table has no rows", "rel.csv: the table has no rows"], problems


def test_settings_are_parsed_and_checked():
    s, problems = parse_settings({"identity": {"match_threshold": 0.95, "min_complete": 40}, "o2o": {"min_support": 1}})
    assert problems == []
    assert s["identity"] == IdentitySettings(match_threshold=0.95, min_complete=40)
    assert s["o2o"] == O2OSettings(min_support=1.0) and s["missing_links"] is None
    s, problems = parse_settings({"identity": {"min_complete": 2.5, "seed": True, "colour": 1}, "speed": {}})
    assert problems == ['config key "settings.identity.min_complete" must be a whole number, not 2.5',
                        'config key "settings.identity.seed" must be a whole number, not True',
                        'config key "settings.identity.colour" is not known (expected: min_complete, gap_margin, '
                        'match_threshold, nonmatch_threshold, margin_bits, min_pairs_for_em, n_random_pairs, '
                        'em_max_iter, em_tol, smoothing, seed)',
                        'config key "settings.speed" is not known (expected: identity, missing_links, o2o)'], problems
    assert parse_settings([1])[1] == ['config key "settings" must be an object with the sections: '
                                      'identity, missing_links, o2o']


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
    print(f"ALL {len(tests)} CHECKS TESTS PASSED")
