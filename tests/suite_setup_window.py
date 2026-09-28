"""The Set up downloads window (pycgfx + ctrtool in one window): shown at startup while
either is missing, each file's section folds away once it checks out, it can't be
closed until both do, by-hand placement + Check again, the automatic download (both,
in turn), offline errors, Build reopening it, and the Mac version (by hand only).
Works offline: the downloads are rebuilt from the installed copies."""
import io
import os
import platform
import shutil
import sys
import time
import zipfile

from _common import S, check, finish, isolate
isolate("setup_window")
import ctrtool_setup as cs
import paths
import platform_util as pu
import pycgfx_setup as ps

REAL_PYCGFX, REAL_CTR = paths.PYCGFX_DIR, paths.CTRTOOL_DIR
if not ps.is_ready(REAL_PYCGFX) or not cs.is_ready(REAL_CTR):
    from _common import skip
    skip("pycgfx and ctrtool must be set up - run scripts/get_pycgfx.py and scripts/get_ctrtool.py")
EXE = pu.exe_name("ctrtool")
read = lambda p: open(p, "rb").read()
REAL = sys.platform

# the downloads, rebuilt from the installed copies
PYC_FILES = {"main.py": ps.apply_patch(read(os.path.join(REAL_PYCGFX, "main.py")), reverse=True)}
for rel in ps.FILES:
    PYC_FILES[rel] = read(os.path.join(REAL_PYCGFX, *rel.split("/")))


def zip_of(files, top):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, data in files.items():
            z.writestr(top + rel, data)
    return buf.getvalue()


PYC_ZIP = zip_of(PYC_FILES, f"pycgfx-{ps.COMMIT}/")
CTR_ZIP = zip_of({EXE: read(os.path.join(REAL_CTR, EXE))}, "")


def use(pycgfx_dir, ctr_dir):
    """Point the app at scratch folders (None = the real, set-up one)."""
    for d in (pycgfx_dir, ctr_dir):
        if d:
            shutil.rmtree(d, ignore_errors=True)
    paths.PYCGFX_DIR = pycgfx_dir or REAL_PYCGFX
    paths.PYCGFX_MAIN = os.path.join(paths.PYCGFX_DIR, "main.py")
    paths.CTRTOOL_DIR = ctr_dir or REAL_CTR
    paths.CTRTOOL = os.path.join(paths.CTRTOOL_DIR, EXE)
    paths.REQUIRED[:] = [(p, d) for p, d in paths.REQUIRED if "pycgfx" not in p and os.path.basename(p) != EXE] + \
                        [(paths.PYCGFX_DIR, True), (paths.PYCGFX_MAIN, False), (paths.CTRTOOL, False)]


PD, CD = os.path.join(S, "sw_pycgfx"), os.path.join(S, "sw_ctrtool")

import tkinter as tk  # noqa: E402
import yanbf_cbc as g  # noqa: E402
errors = []
g.messagebox.showerror = lambda *a, **k: errors.append(a)


def start():
    global root
    root = tk.Tk(); root.withdraw()
    a = g.App(root); root.deiconify(); root.update(); a.startup_checks(); root.update()
    return a


def pump(cond=lambda: False, secs=5):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.02)
        if cond():
            return True
    return False


def texts(win):
    out = []

    def walk(x):
        for c in x.winfo_children():
            try:
                out.append(str(c.cget("text")))
            except tk.TclError:
                pass
            walk(c)
    walk(win)
    return "\n".join(out)


def shown(w, key):
    return w.rows[key]["body"].winfo_manager() != ""


print("both missing")
use(PD, CD)
app = start()
w = app.setup_win
check(w is not None and w.win.title() == "Set up downloads" and errors == [], "one window at startup, no error box")
check(paths.PYCGFX_MAIN in app.missing and paths.CTRTOOL in app.missing and "required tools" in app.status_var.get(),
      "Build blocked")
blob = texts(w.win)
check(f"Use exactly pycgfx {ps.SHORT} ({ps.DATE})" in blob and f"Use exactly ctrtool {cs.VERSION}" in blob,
      "says exactly which versions")
check(ps.ZIP_URL in blob and cs.zip_url() in blob and "Not the green Code button" in blob, "links both downloads")
check("main.py, banner-camera.gltf and the cgfx folder" in blob and w.rows["pycgfx"]["path_var"].get() == PD
      and w.rows["ctrtool"]["path_var"].get() == CD, "says what goes where, for each")
check(shown(w, "pycgfx") and shown(w, "ctrtool") and "Still needed: pycgfx and ctrtool" in w.status_label.cget("text"),
      "both sections open, both still needed")
check(str(w.close_btn.cget("state")) == "disabled", "Done disabled")

print("can't be closed until both are set up")
w.try_close(); root.update()
check(w.win.winfo_exists() and "needed before this window can close" in w.status_label.cget("text"), "close button refused")
w.win.event_generate("<Escape>"); root.update()
check(w.win.winfo_exists(), "Escape refused")
w.win.tk.call(w.win.protocol("WM_DELETE_WINDOW"))  # what the title bar's X runs
root.update()
check(w.win.winfo_exists(), "the window's X refused")

print("by hand, one at a time")
os.makedirs(PD, exist_ok=True)
with open(os.path.join(PD, "pycgfx-1f78850.zip"), "wb") as f:
    f.write(PYC_ZIP)
w.check_again(); root.update()
check(ps.is_ready(PD) and not shown(w, "pycgfx") and "✓" in w.rows["pycgfx"]["state"].cget("text"),
      "pycgfx zip placed + Check again -> set up, its section folds away")
check(shown(w, "ctrtool") and "Still needed: ctrtool" in w.status_label.cget("text"), "ctrtool still needed")
w.try_close(); root.update()
check(w.win.winfo_exists(), "still can't close with one missing")
with open(os.path.join(CD, cs.zip_name()), "wb") as f:
    f.write(CTR_ZIP)
w.check_again(); root.update()
check(cs.is_ready(CD) and not shown(w, "ctrtool") and "Both files are set up" in w.status_label.cget("text"),
      "ctrtool placed -> both set up")
check(app.missing == [] and "required tools" not in app.status_var.get() and str(w.close_btn.cget("state")) == "normal",
      "Build unblocked, Done enabled")
check("Unzipped pycgfx-1f78850.zip" in app.log_text.get("1.0", "end"), "log says the pycgfx zip was unzipped")
w.close_btn.invoke(); root.update()
check(not app._setup_open(), "Done closes it")
app._on_close()

print("once set up, it stays away")
app = start()
check(app.setup_win is None and app.missing == [], "no window at the next start")
app._on_close()

print("only one missing")
use(None, CD)
app = start()
w = app.setup_win
check(w is not None and not shown(w, "pycgfx") and shown(w, "ctrtool"), "pycgfx folded (✓), ctrtool open")
app._on_close()

print("automatic: downloads whichever are missing, in turn")
calls = []


def fake(data):
    def download(progress=None, cancel=None):
        for n in range(0, len(data), 65536):
            progress and progress(n, None)
        calls.append(len(data))
        return data
    return download


real = ps.download, cs.download
ps.download, cs.download = fake(PYC_ZIP), fake(CTR_ZIP)
use(PD, CD)
app = start()
w = app.setup_win
if REAL == "darwin":
    check(w.auto_btn is None, "Mac: no automatic option")
else:
    w.auto_btn.invoke()
    check(pump(lambda: "Both files are set up" in w.status_label.cget("text"), 10), f"automatic: {w.status_label.cget('text')}")
    check(len(calls) == 2 and app.missing == [] and float(w.bar.cget("value")) == 1000, "both downloaded, checked, installed")
    log = app.log_text.get("1.0", "end")
    check("pycgfx 1f78850 downloaded" in log and "ctrtool 1.3.0 downloaded" in log, "both logged")
app._on_close()
calls.clear()
use(None, CD)
app = start()
w = app.setup_win
if REAL != "darwin":
    w.auto_btn.invoke()
    check(pump(lambda: "Both files are set up" in w.status_label.cget("text"), 10) and calls == [len(CTR_ZIP)],
          "only the missing one is downloaded")
app._on_close()

print("offline")
ps.download = cs.download = lambda progress=None, cancel=None: (_ for _ in ()).throw(OSError("no route to host"))
use(PD, CD)
app = start()
w = app.setup_win
if REAL != "darwin":
    w.auto_btn.invoke()
    check(pump(lambda: "Couldn't download pycgfx" in w.status_label.cget("text")), f"offline: {w.status_label.cget('text')}")
    check("option 2" in w.status_label.cget("text") and str(w.auto_btn.cget("state")) == "normal", "offline -> try again or option 2")
ps.download, cs.download = real

print("Build reopens it")
w.close(); root.update()  # (only possible from code - the user can't close it)
app.start_build(); root.update()
check(app._setup_open(), "pressing Build without the files reopens the window")
app._on_close()


class on_mac:
    def __enter__(self):
        self._m = platform.machine
        sys.platform = "darwin"
        platform.machine = lambda: "arm64"

    def __exit__(self, *exc):
        sys.platform = REAL
        platform.machine = self._m


print("on a Mac: by hand only")
use(PD, CD)
root = tk.Tk(); root.withdraw()
app = g.App(root); root.deiconify(); root.update()
with on_mac():
    app.open_setup(); root.update()
    w = app.setup_win
    blob = texts(w.win)
check(w.auto_btn is None and w.bar is None and "Option 1" not in blob
      and "Download and set up automatically" not in blob, "no automatic option")
check("Download them by hand" in blob and blob.count("Show in Finder") == 2, "by-hand steps, Show in Finder for each")
check("macos_arm64" in w.rows["ctrtool"]["link"].cget("text") and "Intel is macos_x86_64" in blob,
      "links the Mac ctrtool, says which chip is which")
w.start_download(); root.update()
check(not w.busy(), "start_download does nothing on a Mac")
w.close(); root.update()
app.open_setup(); root.update()
check(app.setup_win.auto_btn is not None if REAL != "darwin" else app.setup_win.auto_btn is None,
      "this system's window: automatic option only off a Mac")
app._on_close()
finish()
