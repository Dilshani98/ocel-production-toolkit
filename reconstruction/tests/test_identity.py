import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np
import pandas as pd
from reconstruction.identity import (resolve_identities, decide_fellegi_sunter, decide_closest,
                                     IdentitySettings, _attribute_level)
from reconstruction.baselines import apply_b3

# A small synthetic factory. Sheets go A -> B (about 60 s) -> C (about 1000 s); every event also has the
# hubs M (machine) and W (workstation); each sheet has a part P created from it that also appears in its
# C event (a specific neighbour). Cloning works like the injector: the clone takes the A link, and the
# part's O2O link moves to the clone for every other clone.

T0 = pd.Timestamp("2024-01-01 06:00:00", tz="UTC")


class Factory:
    def __init__(self, n_sheets=75, seed=1):
        self.rng = np.random.default_rng(seed)
        self.events, self.rel, self.o2o, self.objects = [], [], [], []
        self.n = 0
        self.objects += [("M", "Machine", None), ("W", "Workstation", None)]
        for i in range(n_sheets):
            self.sheet(i)

    def event(self, act, t, objs):
        eid = f"ev{self.n}"
        self.n += 1
        self.events.append((eid, act, t))
        for o, role in objs:
            self.rel.append((eid, o, role))
        return eid

    def sheet(self, i):
        s, p = f"s{i}", f"p{i}"
        t = T0 + pd.Timedelta(seconds=300 * i)
        tb = t + pd.Timedelta(seconds=float(60 + self.rng.integers(-3, 4)))
        tc = tb + pd.Timedelta(seconds=float(1000 + self.rng.integers(-40, 41)))
        mass = f"0.0{self.rng.integers(200, 210)}{self.rng.integers(1, 9)}"
        self.objects += [(s, "Sheet", mass), (p, "Part", None)]
        self.event("A", t, [(s, "out"), ("M", "with"), ("W", "at")])
        self.event("B", tb, [(s, "on"), ("M", "with"), ("W", "at")])
        self.event("C", tc, [(s, "in"), (p, "out"), ("M", "with"), ("W", "at")])
        self.o2o.append((p, s, "created from"))

    def clone(self, i, move_o2o):
        s, c = f"s{i}", f"c{i}"
        mass = next(m for o, ty, m in self.objects if o == s)
        self.objects.append((c, "Sheet", mass))
        a_event = next(e for e, act, _ in self.events if act == "A" and (e, s, "out") in self.rel)
        self.rel = [(e, c if (e == a_event and o == s) else o, r) for e, o, r in self.rel]
        if move_o2o:
            self.o2o = [(src, c if tgt == s else tgt, q) for src, tgt, q in self.o2o]
        return s, c

    def lose_link(self, i, act):
        s = f"s{i}"
        ev = {e for e, a, _ in self.events if a == act}
        self.rel = [(e, o, r) for e, o, r in self.rel if not (o == s and e in ev)]

    def tables(self):
        return {"events": pd.DataFrame(self.events, columns=["_record_id", "_activity", "_timestamp"]),
                "objects": pd.DataFrame(self.objects, columns=["_item_id", "_item_type", "mass"]),
                "relations": pd.DataFrame(self.rel, columns=["_record_id", "_item_id", "_role"]).assign(
                    _item_type=lambda d: d["_item_id"].map(dict((o, t) for o, t, _ in self.objects))),
                "o2o": pd.DataFrame(self.o2o, columns=["_item_id", "_linked_item_id", "_link_type"])}


def clusters_of(out):
    c = out["clusters"]
    return {frozenset(g["_item_id"]) for _, g in c.groupby("_cluster_id")}


def test_clear_clone_pairs_are_merged():
    f = Factory()
    true = {frozenset(f.clone(i, move_o2o=i % 2 == 0)) for i in range(0, 60, 4)}     # 15 clones
    out, report, pairs = resolve_identities(f.tables())
    got = clusters_of(out)
    print(f"   merged {len(got)} pairs; status {report['status_counts']}")
    assert got == true, f"wrong clusters: missing {true - got}, extra {got - true}"
    ids = set(out["objects"]["_item_id"])
    assert set(out["relations"]["_item_id"]) <= ids and set(out["o2o"]["_linked_item_id"]) <= ids, "dangling IDs"
    assert len(out["objects"]) == len(f.objects) - 15


def test_lost_memory_fragment_is_never_merged():
    f = Factory()
    f.clone(0, move_o2o=True)
    f.lose_link(10, "C")                       # s10 lost its C link: fragment {A, B}, no {C} fragment exists
    out, _, pairs = resolve_identities(f.tables())
    assert "s10" not in set(out["clusters"]["_item_id"])
    assert not (pairs["a"].eq("s10") | pairs["b"].eq("s10")).any(), "a fragment with no complement got a candidate"


def test_clean_table_has_no_merges_and_is_unchanged():
    f = Factory()
    t = f.tables()
    out, report, pairs = resolve_identities(t)
    assert report["fragments"] == 0 and len(out["clusters"]) == 0 and len(pairs) == 0
    for k in ("objects", "relations", "o2o"):
        assert out[k].reset_index(drop=True).equals(t[k].reset_index(drop=True)), f"{k} changed"


def test_different_types_are_never_compared():
    f = Factory()
    f.clone(0, move_o2o=False)
    _, _, pairs = resolve_identities(f.tables())
    types = f.tables()["objects"].set_index("_item_id")["_item_type"]
    assert (pairs["a"].map(types) == pairs["b"].map(types)).all()


def test_learned_lifecycle():
    f = Factory()
    f.clone(0, move_o2o=False)
    _, report, _ = resolve_identities(f.tables())
    lc = report["lifecycles"]["Sheet"]
    assert lc["order"] == ["A", "B", "C"] and lc["usual"] == ["A", "B", "C"]
    assert "Part" not in report["lifecycles"], "a one-activity type has no lifecycle to split"
    assert report["hub_cutoff"] < 75, "hubs (degree about 75) must be above the cut-off"


def test_two_equal_candidates_are_ambiguous():
    p = pd.DataFrame({"a": ["x", "x"], "b": ["y", "z"], "weight": [5.0, 5.0], "posterior": [0.99, 0.99]})
    d = decide_fellegi_sunter(p, IdentitySettings())
    assert (d["status"] == "ambiguous").all(), d


def test_margin_and_bands():
    s = IdentitySettings()
    p = pd.DataFrame({"a": ["x", "x", "q", "r"], "b": ["y", "z", "w", "v"],
                      "weight": [5.0, 4.5, 6.0, 1.0], "posterior": [0.99, 0.95, 0.99, 0.7]})
    d = decide_fellegi_sunter(p, s).set_index("b")["status"]
    assert d["y"] == "ambiguous" and d["z"] == "ambiguous", "0.5-bit margin is below the 1-bit rule"
    assert d["w"] == "merged" and d["v"] == "possible"
    p.loc[1, "weight"] = 3.0                   # now a 2-bit margin
    d = decide_fellegi_sunter(p, s).set_index("b")["status"]
    assert d["y"] == "merged" and d["z"] == "ambiguous"


def test_mass_disagreement_loses_against_agreement():
    f = Factory()
    s, c = f.clone(0, move_o2o=False)
    for i in range(4, 60, 4):
        f.clone(i, move_o2o=i % 8 == 0)
    # A decoy fragment {B, C} with exactly the same times as s0 but a different mass and no shared neighbour
    s0_events = [e for e, o, _ in f.rel if o == "s0"]
    f.objects.append(("decoy", "Sheet", "0.09999"))
    for e in s0_events:
        f.rel.append((e, "decoy", "on"))
    out, _, pairs = resolve_identities(f.tables())
    assert frozenset(("s0", "c0")) in clusters_of(out), "the agreeing candidate should win"
    assert "decoy" not in set(out["clusters"]["_item_id"])


def test_attribute_tolerance():
    assert _attribute_level("0.02125", "0.0212") == "agree"     # one is a rounding of the other
    assert _attribute_level("0.02125", "0.0213") == "agree"
    assert _attribute_level("0.02125", "0.0215") == "disagree"
    assert _attribute_level("0.02125", None) == "unknown"
    assert _attribute_level("DC01", "DC01") == "agree" and _attribute_level("DC01", "DC04") == "disagree"


def test_one_to_one_conflicts():
    # Two fragments want the same partner y: only the closer one gets it (B3), and with Fellegi-Sunter
    # y's two equal candidates make both ambiguous.
    p = pd.DataFrame({"a": ["x", "z"], "b": ["y", "y"], "time_distance": [1.0, 2.0]})
    d = decide_closest(p).set_index("a")["status"]
    assert d["x"] == "merged" and d["z"] == "conflict", d
    p = pd.DataFrame({"a": ["x", "z"], "b": ["y", "y"], "weight": [5.0, 5.0], "posterior": [0.99, 0.99]})
    assert (decide_fellegi_sunter(p, IdentitySettings())["status"] == "ambiguous").all()


def test_b3_takes_closest_one_to_one():
    f = Factory()
    true = {frozenset(f.clone(i, move_o2o=False)) for i in range(0, 60, 6)}
    out, report = apply_b3(f.tables())
    assert clusters_of(out) == true and report["merged_pairs"] == len(true)


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
    print(f"ALL {len(tests)} IDENTITY TESTS PASSED")
