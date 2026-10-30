import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import pandas as pd
from reconstruction.orchestrate import run_steps, STEPS
from reconstruction.complete import run_complete_toolkit
from reconstruction.pipeline import run_toolkit
from reconstruction.reconstruct import load_tables
from reconstruction.identity import IdentitySettings
from reconstruction.relations import RelationSettings
from reconstruction.o2o import O2OSettings
from test_o2o import Plant

# The step-by-step runner must give exactly what the frozen complete toolkit gives, and each settings object must
# reach its step (checked by settings that switch the step off, against the default result on the same data).


def synthetic():
    cfg = json.load(open(os.path.join(ROOT, "examples", "synthetic", "mapping.json")))
    cfg["folder"] = os.path.join(ROOT, "examples", "synthetic")
    return load_tables(cfg)


def damaged_plant():
    p = Plant()
    p.retarget("F3", "S3", "S7")
    form = [e for e, a, _ in p.events if a == "Form"]
    p.events = [(e, "Formm" if e == form[5] else a, t) for e, a, t in p.events]
    return p.tables()


def same(a, b):
    for k in a[0]:
        pd.testing.assert_frame_equal(a[0][k], b[0][k])
    assert json.dumps(a[1], default=str, sort_keys=True) == json.dumps(b[1], default=str, sort_keys=True)
    for k in a[2]:
        pd.testing.assert_frame_equal(a[2][k], b[2][k])


def test_equals_complete_toolkit_on_plant_and_example():
    for name, t in (("plant", damaged_plant()), ("synthetic", synthetic())):
        try:
            same(run_complete_toolkit(t), run_steps(t)[:3])
        except AssertionError as e:
            raise AssertionError(f"{name}: differs from run_complete_toolkit: {e}")


def test_progress_and_after_identity_tables():
    t = synthetic()
    seen = []
    out, report, extra, info = run_steps(t, progress=lambda i, n, s: seen.append((i, n)))
    assert seen == list(enumerate(STEPS, 1)) and [n for n, _ in info["timings"]] == list(STEPS)
    assert all(s >= 0 for _, s in info["timings"])
    ref = run_toolkit(t)[0]
    for k in ("events", "objects", "relations", "o2o"):
        pd.testing.assert_frame_equal(info["after_identity"][k], ref[k])


def test_each_setting_reaches_its_step():
    t = synthetic()
    base = run_steps(t)[1]
    assert base["identity"]["candidate_pairs"] > 0 and base["relations"]["added_R1"] > 0 and base["o2o"]["repaired"] > 0
    ident = run_steps(t, identity_settings=IdentitySettings(min_complete=10_000))[1]
    assert ident["identity"]["lifecycles"] == {} and ident["identity"]["candidate_pairs"] == 0
    rel = run_steps(t, relation_settings=RelationSettings(min_events=10_000))[1]
    assert rel["relations"]["added_R1"] + rel["relations"]["added_R2"] == 0
    o2o = run_steps(t, o2o_settings=O2OSettings(min_support=1.01))[1]
    assert o2o["o2o"]["repaired"] == 0, o2o["o2o"]


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
    print(f"ALL {len(tests)} ORCHESTRATE TESTS PASSED")
