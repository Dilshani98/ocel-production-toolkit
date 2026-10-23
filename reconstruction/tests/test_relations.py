import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np
import pandas as pd
from reconstruction.relations import recover_missing_links, RelationSettings

# A small synthetic line. Each Join event links a Left part ("in"), a Hinge ("out"), a Pin ("in") and machine M1
# ("with"). Left parts are cut 95-105 s before their Join (machine MC); hinges are packed 45-55 s after it
# (machine MP). Pins have no other event. Joins are 600 s apart, so normally each orphan fits one event only.

T0 = pd.Timestamp("2024-01-01 06:00:00", tz="UTC")
N = 60


class Line:
    def __init__(self, seed=3):
        rng = np.random.default_rng(seed)
        self.events, self.rel = [], []
        self.objects = [("M1", "Machine"), ("MC", "Machine"), ("MP", "Machine")]
        self.join_time = {}
        for k in range(N):
            t = T0 + pd.Timedelta(seconds=600 * k)
            self.add_join(k, t, rng)

    def event(self, eid, act, t, links):
        self.events.append((eid, act, t))
        self.rel += [(eid, o, r) for o, r in links]

    def add_join(self, k, t, rng):
        left, hinge, pin = f"L{k}", f"H{k}", f"P{k}"
        self.objects += [(left, "Left"), (hinge, "Hinge"), (pin, "Pin")]
        self.join_time[k] = t
        self.event(f"cut{k}", "Cut", t - pd.Timedelta(seconds=float(rng.integers(95, 106))), [(left, "out"), ("MC", "with")])
        self.event(f"join{k}", "Join", t, [(left, "in"), (hinge, "out"), (pin, "in"), ("M1", "with")])
        self.event(f"pack{k}", "Pack", t + pd.Timedelta(seconds=float(rng.integers(45, 56))), [(hinge, "in"), ("MP", "with")])

    def drop(self, event, obj):
        before = len(self.rel)
        self.rel = [(e, o, r) for e, o, r in self.rel if not (e == event and o == obj)]
        assert len(self.rel) == before - 1, f"link {event}-{obj} not found"

    def tables(self):
        types = dict(self.objects)
        return {"events": pd.DataFrame(self.events, columns=["_record_id", "_activity", "_timestamp"]),
                "objects": pd.DataFrame(self.objects, columns=["_item_id", "_item_type"]),
                "relations": pd.DataFrame(self.rel, columns=["_record_id", "_item_id", "_role"]).assign(
                    _item_type=lambda d: d["_item_id"].map(types)),
                "o2o": pd.DataFrame(columns=["_item_id", "_linked_item_id", "_link_type"])}


def make_clash(line):
    """Put join21 1 s after join20 and both cuts exactly 100 s before their joins, so L20 fits join21
    (gap 101 s) and L21 fits join20 (gap 99 s): both inside the 95-105 s range."""
    t20 = line.join_time[20]
    times = {"join21": t20 + pd.Timedelta(seconds=1), "cut20": t20 - pd.Timedelta(seconds=100),
             "cut21": t20 + pd.Timedelta(seconds=1) - pd.Timedelta(seconds=100),
             "pack21": t20 + pd.Timedelta(seconds=51)}
    line.events = [(e, a, times.get(e, t)) for e, a, t in line.events]


def added(out, before):
    key = lambda d: set(zip(d["_record_id"], d["_item_id"], d["_role"]))
    return key(out["relations"]) - key(before["relations"])


def test_clean_table_gets_no_additions():
    t = Line().tables()
    out, report, links = recover_missing_links(t)
    assert report["missing_links"] == 0 and len(links) == 0
    assert out["relations"].equals(t["relations"]), "relations changed on a clean table"


def test_r1_adds_the_dominant_object_with_its_usual_role():
    line = Line()
    for k in (3, 9, 17, 30, 44):
        line.drop(f"join{k}", "M1")
    t = line.tables()
    out, report, _ = recover_missing_links(t)
    assert added(out, t) == {(f"join{k}", "M1", "with") for k in (3, 9, 17, 30, 44)}
    assert report["added_R1"] == 5 and report["added_R2"] == 0


def test_r1_does_not_fire_below_99_percent():
    line = Line()
    line.rel = [(e, "M2" if (o == "M1" and e in ("join1", "join2")) else o, r) for e, o, r in line.rel]
    line.objects.append(("M2", "Machine"))
    line.drop("join5", "M1")                      # M1 now serves 57 of 59 Join events with a machine (96.6%)
    t = line.tables()
    out, report, links = recover_missing_links(t)
    assert report["missing_links"] == 1 and len(added(out, t)) == 0, "R1 fired below the 99% rule"


def test_r2_adds_a_doubly_unique_orphan():
    line = Line()
    line.drop("join10", "L10")
    t = line.tables()
    out, report, links = recover_missing_links(t)
    assert added(out, t) == {("join10", "L10", "in")} and report["added_R2"] == 1


def test_two_orphans_fitting_two_events_are_not_added():
    line = Line()
    make_clash(line)                              # each orphan now fits both events
    line.drop("join20", "L20")
    line.drop("join21", "L21")
    t = line.tables()
    out, report, links = recover_missing_links(t)
    assert len(added(out, t)) == 0 and report["possible"] == 2, report


def test_one_orphan_fitting_two_events_is_not_added():
    line = Line()
    make_clash(line)
    line.drop("join20", "L20")
    line.drop("join21", "L21")
    line.drop("cut21", "L21")                     # L21 has no events left: no timing, never fits
    t = line.tables()
    out, report, links = recover_missing_links(t)
    assert len(added(out, t)) == 0, "the single orphan fits two events, so it must not be added"


def test_object_with_no_events_is_never_added():
    line = Line()
    line.drop("join5", "P5")                      # the pin's only event: it has no timeline left
    t = line.tables()
    out, report, links = recover_missing_links(t)
    assert len(added(out, t)) == 0
    assert links.set_index("type").loc["Pin", "rule"] == "no candidate"


def test_untrusted_activity_pattern_is_skipped():
    line = Line()
    line.objects += [(f"Q{i}", "Quality") for i in range(40)] + [("M3", "Machine")]
    for i in range(40):
        links = [(f"Q{i}", "in")] + ([("M3", "with")] if i < 22 else [])   # 22 vs 18 events: ratio 1.22 < 1.5
        line.event(f"odd{i}", "Odd", T0 + pd.Timedelta(seconds=37 * i), links)
    t = line.tables()
    out, report, links = recover_missing_links(t)
    assert report["activities"]["Odd"]["trusted"] is False and report["missing_links"] == 0
    assert report["activities"]["Join"]["trusted"] is True


def test_eager_b4_fills_ambiguous_links():
    line = Line()
    make_clash(line)
    line.drop("join20", "L20")
    line.drop("join21", "L21")
    t = line.tables()
    out, report, _ = recover_missing_links(t, eager=True)
    assert report["added_eager"] == 2 and len(added(out, t)) == 2, "B4 should fill both, right or wrong"


def test_full_toolkit_runs_identity_then_recovery():
    from reconstruction.toolkit import run_full_toolkit
    line = Line()
    line.drop("join7", "M1")
    line.drop("join12", "L12")
    t = line.tables()
    out, report, extra = run_full_toolkit(t)
    assert added(out, t) == {("join7", "M1", "with"), ("join12", "L12", "in")}
    assert report["relations"]["added_R1"] == 1 and report["relations"]["added_R2"] == 1
    assert report["identity"]["merged_pairs"] == 0 and "links" in extra


def test_inputs_are_not_changed():
    line = Line()
    line.drop("join10", "L10")
    t = line.tables()
    before = {k: v.copy() for k, v in t.items()}
    recover_missing_links(t)
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
    print(f"ALL {len(tests)} RELATION TESTS PASSED")
