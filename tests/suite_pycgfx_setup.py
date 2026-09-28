"""pycgfx setup: status checks, install from the GitHub zip (with the fixes), manual
placement and the command line. (The Set up downloads window: suite_setup_window.)

Works offline: the 'GitHub zip' is rebuilt from the installed copy (fixes undone).
Set YANBF_NETWORK_TESTS=1 to also download the real zip from GitHub."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import zipfile

from _common import ROOT, S, check, finish, isolate
isolate("pycgfx")
import paths
import pycgfx_setup as ps

REAL = paths.PYCGFX_DIR  # the installed copy (read only)
if not ps.is_ready(REAL):
    from _common import skip
    skip("pycgfx isn't set up in processes/ - run scripts/get_pycgfx.py first")
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda p: open(p, "rb").read()

# the original files of the tested version, as GitHub serves them
STOCK = {"main.py": ps.apply_patch(read(os.path.join(REAL, "main.py")), reverse=True)}
for rel in ps.FILES:
    STOCK[rel] = read(os.path.join(REAL, *rel.split("/")))
STOCK["cgfx.hexpat"] = read(os.path.join(REAL, "cgfx.hexpat"))
STOCK["README.md"] = read(os.path.join(REAL, "README_ORIGINAL.md"))


def make_zip(files=STOCK, top=f"pycgfx-{ps.COMMIT}"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, data in files.items():
            z.writestr(f"{top}/{rel}", data)
        z.writestr(f"{top}/normal_demo.gif", b"GIF89a")  # extra files in the zip are ignored
    return buf.getvalue()


def place(dest, files=STOCK):
    for rel, data in files.items():
        p = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)


def use_dest(dest):
    """Point the app at a scratch pycgfx folder."""
    shutil.rmtree(dest, ignore_errors=True)
    paths.PYCGFX_DIR = dest
    paths.PYCGFX_MAIN = os.path.join(dest, "main.py")
    paths.REQUIRED[:] = [(p, d) for p, d in paths.REQUIRED if "pycgfx" not in p] + \
                        [(dest, True), (paths.PYCGFX_MAIN, False)]


print("module")
check(ps.PATCH == open(os.path.join(ROOT, "patches", "pycgfx.patch"), encoding="utf-8", newline="").read(),
      "built-in fixes = patches/pycgfx.patch")
check(sha(STOCK["main.py"]) == ps.STOCK_MAIN and sha(ps.apply_patch(STOCK["main.py"])) == ps.PATCHED_MAIN,
      "fixes turn the original main.py into the tested one (and back)")
D = os.path.join(S, "pycgfx_test")
use_dest(D)
check(ps.status() == ("missing", ["main.py", *ps.FILES]), "no folder -> missing")
got = ps.install_from_zip(make_zip())
check(ps.status() == ("ok", []) and "main.py" in got, "install from the GitHub zip -> ok")
check(os.path.isfile(os.path.join(D, "PATCH_NOTES.txt")) and os.path.isfile(os.path.join(D, "README_ORIGINAL.md"))
      and not os.path.exists(os.path.join(D, "normal_demo.gif")), "notes + original README added, demo GIFs skipped")
newer = dict(STOCK, **{"cgfx/cmdl.py": STOCK["cgfx/cmdl.py"] + b"\n# newer\n"})
try:
    ps.install_from_zip(make_zip(newer)); check(False, "other version rejected")
except ps.SetupError as ex:
    check(f"isn't pycgfx version {ps.SHORT}" in str(ex) and "cgfx/cmdl.py" in str(ex), f"other version rejected: {ex}")
check(ps.status() == ("ok", []), "a rejected zip leaves the working copy alone")
try:
    ps.install_from_zip(b"not a zip"); check(False, "junk rejected")
except ps.SetupError as ex:
    check("isn't a valid zip" in str(ex), "junk download rejected")
open(os.path.join(D, "cgfx", "sobj.py"), "ab").write(b"#")
check(ps.status() == ("wrong", ["cgfx/sobj.py"]), f"an edited file -> wrong, named: {ps.status()}")

print("placing files by hand")
use_dest(D); place(D)
check(ps.status()[0] == "stock", "original files placed -> 'stock'")
check(ps.fix_stock() and ps.status() == ("ok", []), "fix_stock adds the fixes -> ok")
use_dest(D); place(os.path.join(D, f"pycgfx-{ps.COMMIT}"))
note = ps.tidy_manual_placement()
check(note and "Moved the files out" in note and ps.status()[0] == "stock", f"whole unzipped folder put inside: {note}")
use_dest(D); os.makedirs(D); open(os.path.join(D, "pycgfx-1f78850.zip"), "wb").write(make_zip())
note = ps.tidy_manual_placement()
check(note == "Unzipped pycgfx-1f78850.zip" and ps.status() == ("ok", []) and
      not any(n.endswith(".zip") for n in os.listdir(D)), "the zip itself put in the folder -> installed")

print("command line + network")
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "get_pycgfx.py")], capture_output=True, text=True)
check(r.returncode == 0 and "already set up" in r.stdout, f"get_pycgfx.py on the real install: {r.stdout.strip()}")
if os.environ.get("YANBF_NETWORK_TESTS") == "1":
    use_dest(D)
    ps.install_from_zip(ps.download())
    check(ps.status() == ("ok", []), "real download from GitHub installs and checks out")
finish()
