"""Shared setup for the test suites.

Importing this:
  * puts app/ on sys.path;
  * picks the work folder S - $YANBF_TEST_DIR when run_all.py started the suite,
    otherwise a new temporary folder - generates the test inputs there (fixtures.py)
    if they aren't there yet, and makes it the current directory.

Call isolate("name") before importing the GUI so the suite uses its own settings.json,
unique_ids.json and output folder inside S. The user's real files next to the
program are never read or written.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app")
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import fixtures  # noqa: E402
import paths  # noqa: E402

WINDOWS = sys.platform == "win32"
S = os.environ.get("YANBF_TEST_DIR") or tempfile.mkdtemp(prefix="yanbf-tests-")
if not os.path.isfile(os.path.join(S, "case.glb")):
    fixtures.build(S)
os.chdir(S)

FAKE_TOOLS = fixtures.fake_tools(S)
REF_WAV = os.path.join(S, "wav", "ref.wav")  # exactly the audio limit: 141,000 frames at 48 kHz
CASE_GLB = os.path.join(S, "case.glb")  # stands in for a real textured banner model
failures = []


def isolate(name, fresh=True):
    """Point settings.json, unique_ids.json and output/ at files in S for this suite."""
    paths.ID_REGISTRY = os.path.join(S, f"{name}_ids.json")
    paths.SETTINGS = os.path.join(S, f"{name}_settings.json")
    paths.OUTPUT_DIR = os.path.join(S, f"{name}_output")
    if fresh:
        for p in (paths.ID_REGISTRY, paths.SETTINGS):
            if os.path.exists(p):
                os.remove(p)


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def skip(reason):
    """End the suite without running it (exit code 2 = skipped)."""
    print(f"SKIPPED: {reason}")
    sys.exit(2)


def finish():
    print()
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
