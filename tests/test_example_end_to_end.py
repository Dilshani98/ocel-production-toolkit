import os, sys, json, sqlite3, subprocess, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import pandas as pd
from pm4py.objects.ocel.validation import ocel20_rel_validation

# The README command, run exactly as a user would (from the project root, in its own process), on the committed
# synthetic example. Every change is checked against the example's damage log: nothing changed that was not
# damaged, and every damaged value that was repaired is now right. Counts are printed as they come.

EXAMPLE = os.path.join(ROOT, "examples", "synthetic")


def run_command(out):
    cmd = [sys.executable, "-m", "reconstruction.reconstruct", "--config",
           os.path.join("examples", "synthetic", "mapping.json"), "--out", out]
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, f"README command failed:\n{done.stderr[-2000:]}"
    return done.stdout


def test_readme_command_on_the_synthetic_example():
    log = json.load(open(os.path.join(EXAMPLE, "damage_log.json")))
    with tempfile.TemporaryDirectory() as out:
        stdout = run_command(out)
        assert "# Repair report" in stdout
        for f in ("log.sqlite", "repair_report.json", "repair_report.md", "changes_labels.csv",
                  "changes_timestamps.csv", "changes_merged_objects.csv", "changes_added_links.csv",
                  "changes_repaired_o2o.csv", "review_identity.csv", "review_e2o_links.csv", "review_o2o_links.csv"):
            assert os.path.exists(os.path.join(out, f)), f"missing output {f}"
        read = lambda n: pd.read_csv(os.path.join(out, f"changes_{n}.csv"), dtype=str)

        labels = read("labels")
        typos = {t["event"]: t["right"] for t in log["label_typos"]}
        assert set(labels["event"]) <= set(typos), "a label was changed that was not damaged"
        assert all(typos[e] == n for e, n in zip(labels["event"], labels["new_label"])), "a label was fixed wrongly"

        times = read("timestamps")
        right = {d["event"]: pd.Timestamp(d["right_time"]) for d in log["timestamp_drift"]["events"]}
        assert set(times["event"]) <= set(right), "a timestamp was changed that was not drifted"
        assert all(pd.Timestamp(t) == right[e] for e, t in zip(times["event"], times["new_time"])), \
            "a drifted timestamp was not restored exactly"

        merged = read("merged_objects")
        pairs = {frozenset((c["original"], c["clone"])) for c in log["clones"]}
        assert all(frozenset(p) in pairs for p in zip(merged["merged_id"], merged["kept_id"])), "a wrong merge"

        added = read("added_links")
        removed = {(r["event"], r["object"]) for r in log["removed_links"]}
        assert set(zip(added["event"], added["object"])) <= removed, "a link was added that was not removed"

        o2o = read("repaired_o2o")
        swaps = {(s["source"], s["recorded_target"]): s["right_target"] for s in log["swapped_o2o"]}
        assert all(swaps.get((s, old)) == new for s, old, new in
                   zip(o2o["source"], o2o["old_target"], o2o["new_target"])), "an O2O link was repaired wrongly"

        con = sqlite3.connect(os.path.join(out, "log.sqlite"))
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        con.close()                                       # a "with" block does not close it (Windows keeps the file)
        ok, bad = ocel20_rel_validation.apply(os.path.join(out, "log.sqlite"))
        assert len(ok) == 24 and not bad and not fk, f"constraints {len(ok)} ok, unsatisfied {bad}, FK {len(fk)}"
        print(f"   labels {len(labels)}/{len(typos)}, timestamps {len(times)}/{len(right)}, merges "
              f"{len(merged)}/{len(pairs)}, links {len(added)}/{len(removed)}, O2O {len(o2o)}/{len(swaps)}; "
              f"0 wrong changes; SQLite {len(ok)}/24 constraints, {len(fk)} FK violations")


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
    print(f"ALL {len(tests)} EXAMPLE END-TO-END TESTS PASSED")
