"""Run every test script and print a pass / fail / skip summary.

    python tests/run_all.py                 tests that need no generated data
    python tests/run_all.py --with-data     also the tests on data/messy (run tests/generate_datasets.py first)

Each test is a plain script with asserts; it runs in its own process from the project root, and passes if it exits
with 0. Old manual scripts in tests/legacy/ and the experiment and data scripts are not tests and are not run.
Exit code 1 if any test failed.
"""
import argparse
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEST_DIRS = ("tests", "reconstruction/tests", "evaluation/tests", "examples/tests")
EXTRA = ("tests/verify_messy_output.py",)               # a check script that is a test, without the test_ prefix
NEEDS_DATA = {"reconstruction/tests/test_cleaning.py", "reconstruction/tests/test_mapping.py",
              "reconstruction/tests/test_profiling.py", "reconstruction/tests/test_timestamp_repair.py",
              "tests/verify_messy_output.py", "tests/test_id_realism.py"}
ARGS = {"reconstruction/tests/test_timestamp_repair.py": [["sev0_05"], ["sev0_15"], ["sev0_3"]]}


def discover(root=ROOT, test_dirs=TEST_DIRS, extra=EXTRA):
    """Test scripts as project-relative paths with forward slashes, sorted. Legacy folders are never searched."""
    found = set()
    for d in test_dirs:
        found |= {os.path.relpath(p, root).replace(os.sep, "/") for p in glob.glob(os.path.join(root, d, "test_*.py"))}
    found |= {e for e in extra if os.path.exists(os.path.join(root, e))}
    found.discard("tests/run_all.py")
    return sorted(found)


def plan(scripts, with_data, needs_data=NEEDS_DATA, args=ARGS):
    """One (script, arguments, skip reason or None) row per run."""
    rows = []
    for s in scripts:
        for a in args.get(s, [[]]):
            skip = None if with_data or s not in needs_data else "needs data: run tests/generate_datasets.py"
            rows.append((s, a, skip))
    return rows


def run(rows, root=ROOT, timeout=1800, python=sys.executable):
    results = []
    for script, a, skip in rows:
        name = " ".join([script] + a)
        if skip:
            results.append((name, "SKIP", 0.0, skip))
            print(f"SKIP  {name} ({skip})", flush=True)
            continue
        start = time.perf_counter()
        try:
            done = subprocess.run([python, script] + a, cwd=root, capture_output=True, text=True, timeout=timeout)
            status = "PASS" if done.returncode == 0 else "FAIL"
            last = [l for l in (done.stdout + done.stderr).strip().splitlines() if l.strip()]
            note = last[-1][:160] if last else ""
        except subprocess.TimeoutExpired:
            status, note = "FAIL", f"timed out after {timeout} s"
        seconds = time.perf_counter() - start
        results.append((name, status, seconds, note))
        print(f"{status}  {name} ({seconds:.0f} s){'' if status == 'PASS' else ': ' + note}", flush=True)
    return results


def summary(results):
    count = lambda s: sum(1 for r in results if r[1] == s)
    lines = ["", f"{count('PASS')} passed, {count('FAIL')} failed, {count('SKIP')} skipped "
                 f"({len(results)} runs, {sum(r[2] for r in results):.0f} s)"]
    lines += [f"   FAILED: {r[0]}: {r[3]}" for r in results if r[1] == "FAIL"]
    if count("SKIP"):
        lines.append("   skipped runs need data/messy: python tests/generate_datasets.py, then --with-data")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run every test script.")
    parser.add_argument("--with-data", action="store_true", help="also run the tests on generated data")
    parser.add_argument("--timeout", type=int, default=1800, help="seconds per test script")
    args = parser.parse_args(argv)
    results = run(plan(discover(), args.with_data), timeout=args.timeout)
    print(summary(results))
    return 1 if any(r[1] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
