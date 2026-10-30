import os, sys, io, json, tempfile, contextlib, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from reconstruction.cli import main
from reconstruction.reconstruct import reconstruct
from test_o2o import Plant

# The command line on the committed synthetic example and on hand-made broken inputs: same files as the original
# command, dry run writes nothing, profile-only runs nothing, every input problem is reported, export refusals
# become one message, and config settings reach the toolkit.

EXAMPLE = os.path.join(ROOT, "examples", "synthetic")


def example_config(folder, **extra):
    cfg = json.load(open(os.path.join(EXAMPLE, "mapping.json")))
    cfg["folder"] = EXAMPLE
    cfg.update(extra)
    path = os.path.join(folder, "config.json")
    json.dump(cfg, open(path, "w"))
    return cfg, path


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def digest(folder, skip=()):
    return {f: hashlib.sha256(open(os.path.join(folder, f), "rb").read()).hexdigest()
            for f in sorted(os.listdir(folder)) if f not in skip}


def test_same_files_as_the_original_command():
    with tempfile.TemporaryDirectory() as d:
        cfg, path = example_config(d)
        reconstruct(cfg, os.path.join(d, "original"))
        code, out, err = run(["--config", path, "--out", os.path.join(d, "cli")])
        assert code == 0, err
        a, b = digest(os.path.join(d, "original")), digest(os.path.join(d, "cli"))
        assert sorted(a) == sorted(b), (sorted(a), sorted(b))
        differ = [f for f in a if a[f] != b[f]]
        assert not differ, f"files differ from the original command's: {differ}"
        assert [l.split(":")[0] for l in out.splitlines() if l.startswith("[")] == \
            ["[1/5] activity labels", "[2/5] timestamps", "[3/5] object identity", "[4/5] missing links",
             "[5/5] object-to-object links"], out


def test_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        _, path = example_config(d)
        target = os.path.join(d, "never")
        code, out, err = run(["--config", path, "--out", target, "--dry-run"])
        assert code == 0 and not os.path.exists(target), err
        assert "- activity labels: 5" in out and "Dry run: nothing was written." in out


def test_profile_only_runs_nothing():
    with tempfile.TemporaryDirectory() as d:
        _, path = example_config(d)
        code, out, err = run(["--config", path, "--profile-only"])
        assert code == 0, err
        assert "- events: 1440, objects: 520, event-to-object links: 2862, object-to-object links: 480" in out
        assert "- events earlier than the row before them (file order): 40 (2.78%)" in out
        assert "    InspectPrt (3 events) -> InspectPart (similarity 0.952)" in out
        assert "[1/5]" not in out and "Repair report" not in out


def test_input_problems_stop_before_running():
    with tempfile.TemporaryDirectory() as d:
        cfg, path = example_config(d)
        cfg["columns"]["timestamp_col"] = "time"
        cfg["columns"]["role_col"] = "job"
        json.dump(cfg, open(path, "w"))
        code, out, err = run(["--config", path, "--out", os.path.join(d, "o")])
        assert code == 2 and not os.path.exists(os.path.join(d, "o")) and out == "", (code, out)
        assert err.startswith("Found 2 problems in the input; nothing was run:") and '"time"' in err and '"job"' in err
        code, _, err = run(["--config", os.path.join(d, "none.json"), "--dry-run"])
        assert code == 2 and "config file not found" in err
        open(path, "w").write("{bad json")
        code, _, err = run(["--config", path, "--dry-run"])
        assert code == 2 and "not valid JSON (line 1" in err
        code, _, err = run(["--config", path])
        assert code == 2 and "--out is needed" in err


def test_export_refusal_is_one_message():
    with tempfile.TemporaryDirectory() as d:
        t = Plant().tables()                               # its facility has no event: the export refuses it
        names = {"events": {"_record_id": "rid", "_activity": "act", "_timestamp": "when"},
                 "objects": {"_item_id": "thing", "_item_type": "kind"},
                 "relations": {"_record_id": "rid", "_item_id": "thing", "_item_type": "kind", "_role": "as"},
                 "o2o": {"_item_id": "thing", "_linked_item_id": "other", "_link_type": "how"}}
        for kind, cols in names.items():
            t[kind].rename(columns=cols).to_csv(os.path.join(d, f"{kind}.csv"), index=False)
        cfg = {"folder": d, "files": {k: f"{k}.csv" for k in names},
               "columns": {"record_id_col": "rid", "activity_col": "act", "timestamp_col": "when", "item_id_col": "thing",
                           "item_type_col": "kind", "linked_item_id_col": "other", "link_type_col": "how",
                           "role_col": "as"}}
        json.dump(cfg, open(os.path.join(d, "c.json"), "w"))
        code, out, err = run(["--config", os.path.join(d, "c.json"), "--out", os.path.join(d, "o")])
        assert code == 1 and err.startswith("Export stopped: Cannot export object 'FA'"), (code, err)
        assert "Traceback" not in err and len(err.strip().splitlines()) == 1


def test_settings_in_the_config_reach_the_toolkit():
    with tempfile.TemporaryDirectory() as d:
        _, path = example_config(d, settings={"missing_links": {"min_events": 10000}})
        code, out, err = run(["--config", path, "--dry-run"])
        assert code == 0 and "- event-to-object links added: 0" in out, (code, err)
        _, path = example_config(d, settings={"missing_links": {"min_event": 10}})
        code, _, err = run(["--config", path, "--dry-run"])
        assert code == 2 and '"settings.missing_links.min_event" is not known' in err


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
    print(f"ALL {len(tests)} CLI TESTS PASSED")
