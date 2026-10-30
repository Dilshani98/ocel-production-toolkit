import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_all import discover, plan, run, summary

# The test runner on a made-up project: which scripts it finds, which it skips, and how it counts results.

SCRIPTS = {"tests/test_ok.py": "print('fine')",
           "tests/test_broken.py": "assert 1 == 2, 'deliberately broken'",
           "tests/legacy/test_old.py": "raise SystemExit(1)",
           "tests/helper.py": "raise SystemExit(1)",
           "pkg/tests/test_needs_data.py": "print('used data')",
           "pkg/tests/test_args.py": "import sys; assert sys.argv[1] in ('a', 'b'), sys.argv",
           "tests/check_extra.py": "print('extra ok')"}


def make(root):
    for path, code in SCRIPTS.items():
        os.makedirs(os.path.join(root, os.path.dirname(path)), exist_ok=True)
        open(os.path.join(root, path), "w").write(code + "\n")


def test_discovery_finds_tests_only():
    with tempfile.TemporaryDirectory() as d:
        make(d)
        found = discover(d, ("tests", "pkg/tests"), ("tests/check_extra.py", "tests/missing.py"))
        assert found == ["pkg/tests/test_args.py", "pkg/tests/test_needs_data.py", "tests/check_extra.py",
                         "tests/test_broken.py", "tests/test_ok.py"], found


def test_data_tests_are_skipped_unless_asked_and_args_expand():
    scripts = ["pkg/tests/test_args.py", "pkg/tests/test_needs_data.py", "tests/test_ok.py"]
    needs, args = {"pkg/tests/test_needs_data.py"}, {"pkg/tests/test_args.py": [["a"], ["b"]]}
    rows = plan(scripts, False, needs, args)
    assert [(s, a) for s, a, _ in rows] == [("pkg/tests/test_args.py", ["a"]), ("pkg/tests/test_args.py", ["b"]),
                                            ("pkg/tests/test_needs_data.py", []), ("tests/test_ok.py", [])]
    assert [r[2] is not None for r in rows] == [False, False, True, False]
    assert all(r[2] is None for r in plan(scripts, True, needs, args))


def test_pass_fail_skip_are_counted_and_failures_named():
    with tempfile.TemporaryDirectory() as d:
        make(d)
        rows = plan(discover(d, ("tests", "pkg/tests"), ("tests/check_extra.py",)), False,
                    {"pkg/tests/test_needs_data.py"}, {"pkg/tests/test_args.py": [["a"], ["b"]]})
        results = run(rows, root=d, timeout=60)
        status = {name: s for name, s, _, _ in results}
        assert status == {"pkg/tests/test_args.py a": "PASS", "pkg/tests/test_args.py b": "PASS",
                          "pkg/tests/test_needs_data.py": "SKIP", "tests/check_extra.py": "PASS",
                          "tests/test_broken.py": "FAIL", "tests/test_ok.py": "PASS"}, status
        text = summary(results)
        assert "4 passed, 1 failed, 1 skipped" in text and "deliberately broken" in text, text


def test_timeout_counts_as_failure():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "tests"))
        open(os.path.join(d, "tests", "test_slow.py"), "w").write("import time; time.sleep(30)\n")
        results = run([("tests/test_slow.py", [], None)], root=d, timeout=2)
        assert results[0][1] == "FAIL" and "timed out" in results[0][3], results


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
    print(f"ALL {len(tests)} RUN_ALL TESTS PASSED")
