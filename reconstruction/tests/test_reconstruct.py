import os, sys, json, hashlib, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pandas as pd
from pm4py.objects.ocel.validation import ocel20_rel_validation
from reconstruction.reconstruct import reconstruct, main
from reconstruction.export import read
from test_o2o import Plant

# End to end: four messy CSV files with their own column names -> the user-facing command -> OCEL 2.0 file,
# repair report, change lists and review lists. Damage: one misspelled activity, one wrong O2O target.

COLUMNS = {"record_id_col": "rid", "activity_col": "act", "timestamp_col": "when", "item_id_col": "thing",
           "item_type_col": "kind", "linked_item_id_col": "other", "link_type_col": "how", "role_col": "as"}


def write_inputs(folder):
    p = Plant()
    # The export refuses an object type none of whose objects has an event (pm4py drops the whole type);
    # the facility gets one event of its own so this test is about the command, not that limitation.
    p.event("Audit", 9900, [("FA", "at")])
    p.retarget("F3", "S3", "S7")                                  # wrong "created from" target
    form_events = [e for e, a, _ in p.events if a == "Form"]
    p.events = [(e, "Formm" if e == form_events[5] else a, t) for e, a, t in p.events]   # one typo
    t = p.tables()
    names = {"events": {"_record_id": "rid", "_activity": "act", "_timestamp": "when"},
             "objects": {"_item_id": "thing", "_item_type": "kind"},
             "relations": {"_record_id": "rid", "_item_id": "thing", "_item_type": "kind", "_role": "as"},
             "o2o": {"_item_id": "thing", "_linked_item_id": "other", "_link_type": "how"}}
    files = {}
    for kind, cols in names.items():
        files[kind] = f"{kind}_export.csv"
        t[kind].rename(columns=cols).to_csv(os.path.join(folder, files[kind]), index=False)
    return {"folder": folder, "files": files, "columns": COLUMNS}, form_events[5]


def digest(folder):
    return {f: hashlib.sha256(open(os.path.join(folder, f), "rb").read()).hexdigest()
            for f in sorted(os.listdir(folder))}


def test_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        inp, out = os.path.join(d, "in"), os.path.join(d, "out")
        os.makedirs(inp)
        config, typo_event = write_inputs(inp)
        before = digest(inp)
        rep = reconstruct(config, out)
        assert digest(inp) == before, "the input files were changed"
        for f in ("log.sqlite", "repair_report.json", "repair_report.md", "changes_labels.csv",
                  "changes_repaired_o2o.csv", "review_e2o_links.csv", "review_o2o_links.csv", "review_identity.csv"):
            assert os.path.exists(os.path.join(out, f)), f"missing output {f}"
        assert rep["changed"]["activity labels"] == 1 and rep["changed"]["object-to-object links repaired"] == 1
        assert rep["changed"]["timestamps"] == 0 and rep["changed"]["objects merged into another ID"] == 0
        labels = pd.read_csv(os.path.join(out, "changes_labels.csv"))
        assert labels.to_dict("records") == [{"event": typo_event, "old_label": "Formm", "new_label": "Form"}]
        o2o = pd.read_csv(os.path.join(out, "changes_repaired_o2o.csv"))
        assert o2o[["source", "old_target", "new_target"]].values.tolist() == [["F3", "S7", "S3"]]
        log = read(os.path.join(out, "log.sqlite"), "sqlite")
        assert ("F3", "S3", "created from") in set(zip(log["o2o"]["_item_id"], log["o2o"]["_linked_item_id"],
                                                        log["o2o"]["_link_type"]))
        assert "Formm" not in set(log["events"]["_activity"])
        ok, bad = ocel20_rel_validation.apply(os.path.join(out, "log.sqlite"))
        assert not bad, bad
        md = open(os.path.join(out, "repair_report.md"), encoding="utf-8").read()
        assert "## Changed" in md and "## Left alone, and why" in md


def test_command_line_and_formats():
    with tempfile.TemporaryDirectory() as d:
        inp, out = os.path.join(d, "in"), os.path.join(d, "out")
        os.makedirs(inp)
        config, _ = write_inputs(inp)
        cfg = os.path.join(d, "mapping.json")
        json.dump(config, open(cfg, "w"))
        main(["--config", cfg, "--out", out, "--formats", "sqlite", "json"])
        assert os.path.exists(os.path.join(out, "log.sqlite")) and os.path.exists(os.path.join(out, "log.json"))
        assert json.load(open(os.path.join(out, "repair_report.json")))["changed"]["activity labels"] == 1


def test_wrong_column_name_is_refused():
    with tempfile.TemporaryDirectory() as d:
        config, _ = write_inputs(d)
        config["columns"] = {**config["columns"], "activity_col": "no_such_column"}
        try:
            reconstruct(config, os.path.join(d, "out"))
        except ValueError as e:
            print("   caught:", e)
            return
        raise AssertionError("a wrong column name was accepted")


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
    print(f"ALL {len(tests)} RECONSTRUCT TESTS PASSED")
