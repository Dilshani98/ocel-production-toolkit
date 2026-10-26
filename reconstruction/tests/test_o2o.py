import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from reconstruction.o2o import repair_o2o

# A small synthetic plant. Sheet S_k is split from coil C1/C2 (Split event) and is "created from" that coil.
# Formed part F_k is formed from S_k (Form event) and "created from" S_k. Pack P_j holds hinges H_j_0..3
# (Pack event) and is "created from" each of them. Workstations W0-W2 are "located at" facility FA but never
# share an event with it (a natural 0%-support group). Tools T0-T9 are "located at" benches B0-B9 and meet
# them in ten different activities (no single meeting activity).

T0 = pd.Timestamp("2024-01-01 06:00:00", tz="UTC")
N_SHEETS, N_PACKS = 40, 12


class Plant:
    def __init__(self):
        self.events, self.rel, self.o2o, self.objects = [], [], [], []
        self.n = 0
        self.objects += [("C1", "Coil"), ("C2", "Coil"), ("FA", "Facility")]
        for k in range(N_SHEETS):
            s, f, c = f"S{k}", f"F{k}", "C1" if k % 2 else "C2"
            self.objects += [(s, "Sheet"), (f, "Formed")]
            self.event("Split", k * 60, [(s, "out"), (c, "on")])
            self.event("Form", k * 60 + 30, [(s, "in"), (f, "out")])
            self.o2o += [(s, c, "created from"), (f, s, "created from")]
        for j in range(N_PACKS):
            p = f"P{j}"
            hinges = [f"H{j}_{i}" for i in range(4)]
            self.objects += [(p, "Pack")] + [(h, "Hinge") for h in hinges]
            self.event("Pack", 5000 + j * 60, [(p, "out")] + [(h, "in") for h in hinges])
            self.o2o += [(p, h, "created from") for h in hinges]
        for w in range(3):
            self.objects.append((f"W{w}", "Workstation"))
            self.event("Shift", 9000 + w, [(f"W{w}", "at")])
            self.o2o.append((f"W{w}", "FA", "located at"))
        for t in range(10):
            self.objects += [(f"T{t}", "Tool"), (f"B{t}", "Bench")]
            self.event(f"Job{t}", 9500 + t, [(f"T{t}", "with"), (f"B{t}", "at")])
            self.o2o.append((f"T{t}", f"B{t}", "located at"))

    def event(self, act, sec, links):
        eid = f"e{self.n}"
        self.n += 1
        self.events.append((eid, act, T0 + pd.Timedelta(seconds=sec)))
        self.rel += [(eid, o, r) for o, r in links]
        return eid

    def retarget(self, source, old, new):
        assert (source, old) in {(a, b) for a, b, _ in self.o2o}, f"no link {source}->{old}"
        self.o2o = [(a, new if (a == source and b == old) else b, q) for a, b, q in self.o2o]

    def drop_e2o(self, obj, activity):
        evs = {e for e, a, _ in self.events if a == activity}
        self.rel = [(e, o, r) for e, o, r in self.rel if not (o == obj and e in evs)]

    def tables(self):
        types = dict(self.objects)
        return {"events": pd.DataFrame(self.events, columns=["_record_id", "_activity", "_timestamp"]),
                "objects": pd.DataFrame(self.objects, columns=["_item_id", "_item_type"]),
                "relations": pd.DataFrame(self.rel, columns=["_record_id", "_item_id", "_role"]).assign(
                    _item_type=lambda d: d["_item_id"].map(types)),
                "o2o": pd.DataFrame(self.o2o, columns=["_item_id", "_linked_item_id", "_link_type"])}


def links(t):
    return set(zip(t["o2o"]["_item_id"], t["o2o"]["_linked_item_id"], t["o2o"]["_link_type"]))


def test_clean_table_gets_no_changes():
    t = Plant().tables()
    out, report, decisions = repair_o2o(t)
    assert report["detected"] == 0 and len(decisions) == 0 and links(out) == links(t)


def test_single_swapped_target_is_repaired():
    p = Plant()
    p.retarget("F3", "S3", "S7")
    out, report, _ = repair_o2o(p.tables())
    assert ("F3", "S3", "created from") in links(out) and ("F3", "S7", "created from") not in links(out)
    assert report["repaired"] == 1 and report["flagged"] == 0


def test_set_rule_restores_two_swapped_hinges():
    p = Plant()
    p.retarget("P1", "H1_0", "H5_2")
    p.retarget("P1", "H1_3", "H7_1")
    out, report, _ = repair_o2o(p.tables())
    got = {b for a, b, q in links(out) if a == "P1"}
    assert got == {f"H1_{i}" for i in range(4)}, got
    assert report["repaired"] == 2


def test_more_candidates_than_links_is_left_unchanged():
    p = Plant()
    p.retarget("P2", "H2_0", "H5_2")
    p.retarget("P2", "H2_1", "H7_1")
    p.objects.append(("HX", "Hinge"))
    pack2 = next(e for e, o, _ in p.rel if o == "P2")
    p.rel.append((pack2, "HX", "in"))                 # a third unlinked hinge in P2's pack event
    t = p.tables()
    out, report, decisions = repair_o2o(t)
    assert links(out) == links(t) and report["flagged"] == 2 and report["repaired"] == 0


def test_source_without_meeting_event_is_left_unchanged():
    p = Plant()
    p.retarget("F5", "S5", "S9")
    p.drop_e2o("F5", "Form")                          # F5 lost its Form event: no candidate
    t = p.tables()
    out, report, _ = repair_o2o(t)
    assert links(out) == links(t) and report["detected"] == 1 and report["flagged"] == 1


def test_correct_but_unsupported_link_is_kept():
    p = Plant()
    p.drop_e2o("S9", "Split")                         # S9's link to its coil is right but no longer supported
    t = p.tables()
    out, report, _ = repair_o2o(t)
    assert ("S9", "C1", "created from") in links(out) and report["repaired"] == 0


def test_non_verifiable_groups_are_skipped():
    p = Plant()
    p.retarget("T3", "B3", "B8")                      # tools meet benches in 10 different activities
    t = p.tables()
    out, report, _ = repair_o2o(t)
    g = {(r["source_type"], r["target_type"]): r for r in report["groups"]}
    assert not g[("Workstation", "Facility")]["verifiable"], "0%-support group must be skipped"
    assert not g[("Tool", "Bench")]["verifiable"], "scattered meeting activity must be skipped"
    assert links(out) == links(t) and report["detected"] == 0


def test_low_support_group_is_skipped():
    p = Plant()
    for k in range(25):                               # 25 of 40 formed-part links wrong: support 37.5% < 50%
        p.retarget(f"F{k}", f"S{k}", f"S{(k + 1) % N_SHEETS}")
    t = p.tables()
    out, report, _ = repair_o2o(t)
    g = {(r["source_type"], r["target_type"]): r for r in report["groups"]}
    assert g[("Formed", "Sheet")]["support"] < 0.5 and not g[("Formed", "Sheet")]["verifiable"]
    assert links(out) == links(t), "a group with too little support must not be repaired"


def test_b5_deletes_unsupported_links_including_correct_ones():
    p = Plant()
    p.retarget("F3", "S3", "S7")
    p.drop_e2o("S9", "Split")
    out, report, decisions = repair_o2o(p.tables(), delete=True)
    assert report["removed"] == 2
    assert ("F3", "S7", "created from") not in links(out) and ("S9", "C1", "created from") not in links(out)


def test_inputs_are_not_changed():
    p = Plant()
    p.retarget("F3", "S3", "S7")
    t = p.tables()
    before = {k: v.copy() for k, v in t.items()}
    repair_o2o(t)
    assert all(t[k].equals(before[k]) for k in t)


def test_complete_toolkit_repairs_after_the_frozen_pipeline():
    from reconstruction.complete import run_complete_toolkit
    p = Plant()
    p.retarget("F3", "S3", "S7")
    out, report, extra = run_complete_toolkit(p.tables())
    assert ("F3", "S3", "created from") in links(out) and report["o2o"]["repaired"] == 1
    assert {"identity", "relations", "o2o"} <= set(report) and "o2o_decisions" in extra


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
    print(f"ALL {len(tests)} O2O TESTS PASSED")
