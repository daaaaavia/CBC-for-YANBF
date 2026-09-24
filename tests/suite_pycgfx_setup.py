"""pycgfx setup: status checks, install from the GitHub zip (with the fixes), manual
placement, and the startup window (shown only while pycgfx isn't the tested version).

Works offline: the 'GitHub zip' is rebuilt from the installed copy (fixes undone).
Set YANBF_NETWORK_TESTS=1 to also download the real zip from GitHub."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import time
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

print("startup window")
import tkinter as tk
import yanbf_cbc as g
errors = []
g.messagebox.showerror = lambda *a, **k: errors.append((a, k))
use_dest(D)


def pump(cond=lambda: False, secs=5):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.02)
        if cond():
            return True
    return False


root = tk.Tk(); root.withdraw()
app = g.App(root); root.deiconify(); root.update()
check(paths.PYCGFX_MAIN in app.missing and "required tools" in app.status_var.get(), "Build blocked without pycgfx")
app.startup_checks(); root.update()
w = app.pycgfx_win
check(w is not None and w.win.winfo_exists() and w.win.title() == "Set up pycgfx", "window opens at startup")
check(errors == [], "no generic 'missing files' box on top of it")
texts = []


def walk(x):
    for c in x.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except tk.TclError:
            pass
        walk(c)


walk(w.win)
blob = "\n".join(texts)
check(f"Use exactly this version: pycgfx {ps.SHORT} ({ps.DATE})" in blob, "says exactly which version to use")
check(ps.ZIP_URL in blob and ps.COMMIT in ps.ZIP_URL and "Not the green Code button" in blob,
      "links that exact version's zip, warns about the newest one")
check("main.py, banner-camera.gltf and the cgfx folder" in blob and w.path_var.get() == D, "says what goes where")
check("isn't set up yet" in w.status_label.cget("text"), f"status: {w.status_label.cget('text')}")
w.check_again(); root.update()
check(app.pycgfx_win.win.winfo_exists() and "isn't set up" in w.status_label.cget("text"), "Check again with nothing there")
place(D); w.check_again(); root.update()
check("is set up" in w.status_label.cget("text") and w.close_btn.cget("text") == "Done" and app.missing == []
      and "required tools" not in app.status_var.get(), "by hand + Check again -> set up, Build unblocked")
check("Added this project's two fixes" in app.log_text.get("1.0", "end"), "log says the fixes were added")
w.close_btn.invoke(); root.update()
app._on_close()

root = tk.Tk(); root.withdraw()
app = g.App(root); root.deiconify(); root.update(); app.startup_checks(); root.update()
check(app.pycgfx_win is None and app.missing == [], "set up -> the window doesn't come back")
app._on_close()

print("automatic download")
shutil.rmtree(D)
calls = []


def fake_download(progress=None, cancel=None):
    data = make_zip()
    for n in range(0, len(data), 4096):
        progress and progress(n, None)
    calls.append(len(data))
    return data


real_download, ps.download = ps.download, fake_download
root = tk.Tk(); root.withdraw()
app = g.App(root); root.deiconify(); root.update(); app.startup_checks(); root.update()
w = app.pycgfx_win
check(w is not None, "deleted files -> the window comes back")
w.auto_btn.invoke()
check(pump(lambda: "is set up" in w.status_label.cget("text"), 10), f"automatic: {w.status_label.cget('text')}")
check(calls and ps.status() == ("ok", []) and app.missing == [] and float(w.bar.cget("value")) == 1000,
      "downloaded, fixed, checked, installed")
w.close(); app._on_close()

shutil.rmtree(D)
ps.download = lambda progress=None, cancel=None: (_ for _ in ()).throw(OSError("no route to host"))
root = tk.Tk(); root.withdraw()
app = g.App(root); root.deiconify(); root.update(); app.startup_checks(); root.update()
w = app.pycgfx_win
w.auto_btn.invoke()
check(pump(lambda: "Couldn't download" in w.status_label.cget("text")), f"offline: {w.status_label.cget('text')}")
check("option 2" in w.status_label.cget("text") and str(w.auto_btn.cget("state")) == "normal", "offline -> try option 2")
w.close(); root.update()
app.start_build(); root.update()
check(app._pycgfx_open(), "Build without pycgfx reopens the setup window")
app._on_close()
ps.download = real_download

print("command line + network")
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "get_pycgfx.py")], capture_output=True, text=True)
check(r.returncode == 0 and "already set up" in r.stdout, f"get_pycgfx.py on the real install: {r.stdout.strip()}")
if os.environ.get("YANBF_NETWORK_TESTS") == "1":
    use_dest(D)
    ps.install_from_zip(ps.download())
    check(ps.status() == ("ok", []), "real download from GitHub installs and checks out")
finish()
