"""ctrtool setup: status checks, install from Project_CTR's release zip, manual
placement, the Mac builds, --check-tools and the command line. (The Set up downloads
window: suite_setup_window.) Works offline: the 'release zip' is rebuilt from the installed copy.
Set YANBF_NETWORK_TESTS=1 to also download the real zip from GitHub."""
import io
import os
import platform
import shutil
import subprocess
import sys
import zipfile

from _common import ROOT, S, check, finish, isolate
isolate("ctrtool")
import ctrtool_setup as cs
import paths
import platform_util as pu

REAL_DIR, REAL_PYCGFX = paths.CTRTOOL_DIR, paths.PYCGFX_DIR
if not cs.is_ready(REAL_DIR):
    from _common import skip
    skip("ctrtool isn't set up - run scripts/get_ctrtool.py first")
EXE = pu.exe_name("ctrtool")
with open(os.path.join(REAL_DIR, EXE), "rb") as f:
    GOOD = f.read()
REAL = sys.platform


class on:
    def __init__(self, plat, machine=None):
        self.plat, self.machine = plat, machine

    def __enter__(self):
        self._m = platform.machine
        sys.platform = self.plat
        if self.machine:
            platform.machine = lambda: self.machine

    def __exit__(self, *exc):
        sys.platform = REAL
        platform.machine = self._m


def make_zip(blob=GOOD, name=EXE, top=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(top + name, blob)
    return buf.getvalue()


def use_dest(dest):
    """Point the app at a scratch ctrtool folder."""
    shutil.rmtree(dest, ignore_errors=True)
    paths.CTRTOOL_DIR = dest
    paths.CTRTOOL = os.path.join(dest, EXE)
    paths.REQUIRED[:] = [(p, d) for p, d in paths.REQUIRED if os.path.basename(p) != EXE] + [(paths.CTRTOOL, False)]


def use_pycgfx(dest):
    paths.PYCGFX_DIR = dest
    paths.PYCGFX_MAIN = os.path.join(dest, "main.py")
    paths.REQUIRED[:] = [(p, d) for p, d in paths.REQUIRED if "pycgfx" not in p] + \
                        [(dest, True), (paths.PYCGFX_MAIN, False)]


print("module")
with on("win32"):
    check(cs.variant() == "win_x64" and cs.zip_name() == "ctrtool-v1.3.0-win_x64.zip", "Windows build")
with on("darwin", "arm64"):
    check(cs.variant() == "macos_arm64", "Apple Silicon build")
with on("darwin", "x86_64"):
    check(cs.variant() == "macos_x86_64" and cs.zip_url().endswith("/ctrtool-v1.3.0/ctrtool-v1.3.0-macos_x86_64.zip"),
          "Intel Mac build, from Project_CTR's release")
D = os.path.join(S, "ctrtool_test")
use_dest(D)
check(cs.status() == "missing", "no file -> missing")
check(cs.install_from_zip(make_zip(top="ctrtool-v1.3.0/")) == paths.CTRTOOL and cs.status() == "ok",
      "install from the release zip -> ok")
if REAL != "win32":
    check(os.access(paths.CTRTOOL, os.X_OK), "installed as runnable")
try:
    cs.install_from_zip(make_zip(GOOD + b"x")); check(False, "other build rejected")
except cs.SetupError as ex:
    check("isn't ctrtool 1.3.0" in str(ex), f"other build rejected: {ex}")
check(cs.status() == "ok", "a rejected zip leaves the working copy alone")
for junk, want in ((b"not a zip", "isn't a valid zip"), (make_zip(name="readme.txt"), f"has no {EXE}")):
    try:
        cs.install_from_zip(junk); check(False, "junk rejected")
    except cs.SetupError as ex:
        check(want in str(ex), f"rejected: {ex}")
with open(paths.CTRTOOL, "ab") as f:
    f.write(b"#")
check(cs.status() == "wrong", "an edited file -> wrong")

print("placing it by hand")
use_dest(D); os.makedirs(D)
with open(os.path.join(D, cs.zip_name()), "wb") as f:
    f.write(make_zip())
note = cs.tidy_manual_placement()
check(note == f"Unzipped {cs.zip_name()}" and cs.status() == "ok" and os.listdir(D) == [EXE],
      f"the zip itself put in the folder -> installed, zip removed: {note}")
use_dest(D); os.makedirs(os.path.join(D, "ctrtool-v1.3.0-x"))
with open(os.path.join(D, "ctrtool-v1.3.0-x", EXE), "wb") as f:
    f.write(GOOD)
note = cs.tidy_manual_placement()
check(note and "Moved" in note and cs.status() == "ok" and os.listdir(D) == [EXE], f"unzipped folder put inside: {note}")

print("--check-tools + command line")
use_dest(D)
report = os.path.join(S, "ctrtool_report.txt")
r = subprocess.run([sys.executable, os.path.join(ROOT, "app", "yanbf_cbc.py"), "--check-tools", report],
                   capture_output=True, text=True)
with open(report, encoding="utf-8") as f:
    rep = f.read()
check(r.returncode == 0 and "runs: makerom" in rep, f"--check-tools passes on the real install: {r.returncode}")
real_ctrtool = os.path.join(REAL_DIR, EXE)
hidden = real_ctrtool + ".hidden"
os.replace(real_ctrtool, hidden)
try:
    r = subprocess.run([sys.executable, os.path.join(ROOT, "app", "yanbf_cbc.py"), "--check-tools", report],
                       capture_output=True, text=True)
    with open(report, encoding="utf-8") as f:
        rep = f.read()
    check(r.returncode == 0 and f"missing: {real_ctrtool}" in rep,
          "--check-tools: no ctrtool is reported, not an error (it's downloaded separately)")
finally:
    os.replace(hidden, real_ctrtool)
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "get_ctrtool.py")], capture_output=True, text=True)
check(r.returncode == 0 and "already set up" in r.stdout, f"get_ctrtool.py on the real install: {r.stdout.strip()}")
if os.environ.get("YANBF_NETWORK_TESTS") == "1":
    use_dest(D)
    cs.install_from_zip(cs.download())
    check(cs.status() == "ok", "real download from GitHub installs and checks out")
finish()
