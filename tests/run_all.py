"""Run the test suites (tests/suite_*.py), each in its own process.

    python tests/run_all.py                 all suites
    python tests/run_all.py nds ftp         only suite_nds.py and suite_ftp.py
    python tests/run_all.py --keep          keep the work folder afterwards

Use the app's own Python (the one with requirements.txt installed), plus
tests/requirements-dev.txt for the FTP suite. The test inputs are generated once
into a temporary work folder that every suite shares. The GUI suites open real Tk
windows briefly, so run this on a desktop session. Exit code: 0 if nothing failed.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))


def main():
    ap = argparse.ArgumentParser(description="Run the YANBF-CBC test suites.")
    ap.add_argument("suites", nargs="*", help="suite names (e.g. nds for suite_nds.py); default: all")
    ap.add_argument("--keep", action="store_true", help="keep the work folder with the generated inputs")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every check, not just failures")
    args = ap.parse_args()

    found = {os.path.basename(p)[6:-3]: p for p in sorted(glob.glob(os.path.join(HERE, "suite_*.py")))}
    names = args.suites or list(found)
    unknown = [n for n in names if n not in found]
    if unknown:
        print(f"Unknown suite(s): {', '.join(unknown)}. Available: {', '.join(found)}")
        return 1

    work = tempfile.mkdtemp(prefix="yanbf-tests-")
    import fixtures
    fixtures.build(work)
    env = dict(os.environ, YANBF_TEST_DIR=work, PYTHONIOENCODING="utf-8")
    results = {}
    try:
        for n in names:
            t = time.perf_counter()
            r = subprocess.run([sys.executable, found[n]], env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            secs = time.perf_counter() - t
            status = {0: "passed", 2: "skipped"}.get(r.returncode, "FAILED")
            results[n] = status
            out = r.stdout + r.stderr
            print(f"{status:>7}  {n}  ({secs:.1f} s)")
            if args.verbose or status == "FAILED":
                print("\n".join("         " + line for line in out.rstrip().splitlines()))
            elif status == "skipped":
                print("         " + next((l for l in out.splitlines() if l.startswith("SKIPPED")), ""))
    finally:
        if args.keep:
            print(f"\nWork folder kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    failed = [n for n, s in results.items() if s == "FAILED"]
    passed = sum(s == "passed" for s in results.values())
    skipped = sum(s == "skipped" for s in results.values())
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
