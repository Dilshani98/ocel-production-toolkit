import os, sys, json, tempfile, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import pandas as pd
from make_synthetic import build, write, N_SHEETS, N_CLONES, N_TYPOS, N_DRIFT, DRIFT_S, N_SWAPPED

# The synthetic example: deterministic, learnable (enough complete objects), every damage present in the tables
# exactly as logged, no dangling references, and the committed files equal a fresh build.

COMMITTED = os.path.join(HERE, "..", "synthetic")


def frames():
    tables, log = build(1)
    ev = tables["events"].set_index("event_ref")
    rel = tables["relations"]
    return tables, log, ev, rel


def test_same_seed_same_bytes_other_seed_differs():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c:
        write(a, 1), write(b, 1), write(c, 2)
        h = lambda d, f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
        files = ["events.csv", "objects.csv", "relations.csv", "o2o.csv", "damage_log.json"]
        assert all(h(a, f) == h(b, f) for f in files), "not deterministic"
        assert h(a, "events.csv") != h(c, "events.csv"), "the seed has no effect"


def test_committed_files_equal_a_fresh_build():
    with tempfile.TemporaryDirectory() as d:
        write(d, 1)
        for f in ("events.csv", "objects.csv", "relations.csv", "o2o.csv", "damage_log.json"):
            assert open(os.path.join(d, f), "rb").read().replace(b"\r\n", b"\n") == \
                open(os.path.join(COMMITTED, f), "rb").read().replace(b"\r\n", b"\n"), \
                f"examples/synthetic/{f} is out of date: run examples/make_synthetic.py"


def test_enough_complete_objects_per_lifecycle_type():
    tables, log, ev, rel = frames()
    acts = rel.assign(act=rel["event_ref"].map(ev["step"])).groupby("thing_id")["act"].agg(frozenset)
    kind = tables["objects"].set_index("thing_id")["thing_kind"]
    full = {"SteelSheet": {"SplitCoil", "HeatSheet", "FormPart"}, "FormedPart": {"FormPart", "InspectPart"}}
    for typ, need in full.items():
        n = sum(1 for o, a in acts.items() if kind[o] == typ and need <= a)
        assert n >= 30, f"{typ}: only {n} complete objects"


def test_typos_and_drift_are_in_the_tables_as_logged():
    tables, log, ev, rel = frames()
    assert len(log["label_typos"]) == N_TYPOS
    for t in log["label_typos"]:
        assert ev.at[t["event"], "step"] == t["recorded"] != t["right"]
    counts = ev["step"].value_counts()
    assert all(counts[t["recorded"]] / len(ev) < 0.02 for t in log["label_typos"]), "a typo is not rare"
    drift = log["timestamp_drift"]
    assert len(drift["events"]) == N_DRIFT and drift["seconds"] == DRIFT_S
    for d in drift["events"]:
        assert pd.Timestamp(ev.at[d["event"], "recorded_at"]) - pd.Timestamp(d["right_time"]) == \
            pd.Timedelta(seconds=DRIFT_S)
    pos = [ev.index.get_loc(d["event"]) for d in drift["events"]]
    heat_rows = [i for i, s in enumerate(ev["step"]) if s == "HeatSheet"]
    assert pos == heat_rows[heat_rows.index(pos[0]):heat_rows.index(pos[0]) + N_DRIFT], "drift block not contiguous"


def test_clones_missing_links_and_swaps_are_in_the_tables_as_logged():
    tables, log, ev, rel = frames()
    links = set(zip(rel["event_ref"], rel["thing_id"]))
    o2o = set(zip(tables["o2o"]["thing_id"], tables["o2o"]["other_thing"]))
    assert len(log["clones"]) == N_CLONES
    for c in log["clones"]:
        assert all((e, c["clone"]) in links and (e, c["original"]) not in links for e in c["moved_events"])
        assert any(o == c["original"] for _, o in links), "the original kept no event"
    for r in log["removed_links"]:
        assert (r["event"], r["object"]) not in links
    assert len(log["swapped_o2o"]) == N_SWAPPED
    for s in log["swapped_o2o"]:
        assert (s["source"], s["recorded_target"]) in o2o and (s["source"], s["right_target"]) not in o2o


def test_no_dangling_references_and_unique_ids():
    tables, log, ev, rel = frames()
    objs = set(tables["objects"]["thing_id"])
    assert ev.index.is_unique and tables["objects"]["thing_id"].is_unique
    assert rel["event_ref"].isin(ev.index).all() and rel["thing_id"].isin(objs).all()
    assert tables["o2o"]["thing_id"].isin(objs).all() and tables["o2o"]["other_thing"].isin(objs).all()
    assert len(ev) == N_SHEETS * 6


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
    print(f"ALL {len(tests)} SYNTHETIC EXAMPLE TESTS PASSED")
