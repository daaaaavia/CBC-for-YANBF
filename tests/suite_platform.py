"""Windows / macOS differences (platform_util.py, paths.py): tool names, where a frozen
.app finds processes/, where user data goes, subprocess flags, the audio and 'open'
commands, macOS dark mode, drag and drop through tkdnd, and the Mac pycgfx window
(manual only). Runs on either system: sys.platform is switched to test the other."""
import os
import subprocess
import sys

from _common import S, check, finish, isolate
isolate("platform")
import paths
import platform_util as pu

REAL = sys.platform


class on:
    """with on("darwin"): ... - pretend to be another platform."""

    def __init__(self, plat):
        self.plat = plat

    def __enter__(self):
        sys.platform = self.plat

    def __exit__(self, *exc):
        sys.platform = REAL


print("tool names + subprocess flags")
with on("darwin"):
    check(pu.exe_name("makerom") == "makerom" and pu.popen_flags() == {}, "macOS: no .exe, no creationflags")
    check(pu.file_manager() == "Finder", "macOS: Finder")
with on("win32"):
    check(pu.exe_name("makerom") == "makerom.exe", "Windows: makerom.exe")
    check(pu.popen_flags() == {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)},
          "Windows: no console window for the tools")
    check(pu.file_manager() == "Explorer", "Windows: Explorer")
check(os.path.basename(paths.CTRTOOL) == pu.exe_name("ctrtool"), f"this system's tool path: {paths.CTRTOOL}")
if REAL != "win32":
    r = subprocess.run(["true"], **pu.popen_flags())
    check(r.returncode == 0, "subprocess accepts the flags on this system")

print("commands")
with on("darwin"):
    check(pu.audio_command("/a/b.wav") == ["afplay", "/a/b.wav"], "macOS audio: afplay")
    check(pu.open_command("/a/out") == ["open", "/a/out"], "macOS open: open")
with on("linux"):
    check(pu.open_command("/a/out") == ["xdg-open", "/a/out"], "Linux open: xdg-open")
check(pu.parse_apple_style(0, "Dark\n") is True, "defaults says Dark -> dark")
check(pu.parse_apple_style(1, "") is False, "defaults fails (light mode) -> light")
check(pu.parse_apple_style(0, "Light") is False, "anything else -> light")

import theme  # noqa: E402
real_run = subprocess.run
for code, out, want in ((0, "Dark\n", True), (1, "", False)):
    subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, code, out, "")
    with on("darwin"):
        got = theme.system_is_dark()
    check(got is want, f"theme.system_is_dark on macOS (exit {code}) -> {got}")
subprocess.run = real_run

print("frozen .app paths")
home = os.path.join(S, "platform_home")
app = os.path.join(S, "platform_mac", "YANBF-CBC.app")
exe = os.path.join(app, "Contents", "MacOS", "YANBF-CBC")
res = os.path.join(app, "Contents", "Resources")
os.makedirs(os.path.dirname(exe), exist_ok=True)
with on("darwin"):
    check(paths._base_dir(True, exe, "x") == os.path.join(S, "platform_mac"),
          "no processes/ in the bundle -> the folder holding the .app")
    os.makedirs(os.path.join(res, "processes"), exist_ok=True)
    check(paths._base_dir(True, exe, "x") == res, "processes/ in Contents/Resources -> used")
    data, out, pyc = paths._user_dirs(True, res, home)
    support = os.path.join(home, "Library", "Application Support", "YANBF-CBC")
    check(data == support, f"settings + IDs in Application Support: {data}")
    check(out == os.path.join(home, "Documents", "YANBF-CBC", "output"), f"output in Documents: {out}")
    check(pyc == os.path.join(support, "pycgfx"), f"pycgfx in Application Support: {pyc}")
    check(not any(p.startswith(app) for p in (data, out, pyc)), "nothing written inside the bundle")
    src = paths._user_dirs(False, S, home)
    check(src[0] == S, "macOS from source: next to the project, as on Windows")
with on("win32"):
    base = os.path.join(S, "win")
    check(paths._base_dir(True, os.path.join(base, "YANBF-CBC.exe"), "x") == base, "Windows exe: its folder")
    check(paths._user_dirs(True, base, home) ==
          (base, os.path.join(base, "output"), os.path.join(base, "processes", "YANBF", "pycgfx")),
          "Windows: settings, output and pycgfx next to the exe, as before")

print("audio player")
if REAL == "win32":
    p = pu.AudioPlayer()
    check(p.playing() is None, "Windows: winsound, timed by the caller")
else:
    import shutil
    fake = os.path.join(S, "platform_player")
    with open(fake, "w") as f:
        f.write("#!/bin/sh\nsleep 5\n")
    os.chmod(fake, 0o755)
    real_cmd = pu.audio_command
    pu.audio_command = lambda path: [fake, path]
    p = pu.AudioPlayer()
    p.play("x.wav")
    check(p.playing() is True, "playing while the player runs")
    p.stop()
    check(p.playing() is False, "stopped")
    pu.audio_command = real_cmd
    check(shutil.which(pu.audio_command("x")[0]) is not None or REAL != "darwin", "afplay exists on this Mac")

print("drag and drop through tkdnd")
import tkinter as tk  # noqa: E402
import dragdrop  # noqa: E402
root = tk.Tk()
got = []
t = dragdrop.FileDropTarget.__new__(dragdrop.FileDropTarget)
t.callback = lambda p, x, y: got.append((p, x, y))
res_ = t._on_tkdnd_drop(root, "{/Users/me/My ROM.nds} /Users/me/icon.png", "120", "80")
check(res_ == "copy" and got == [(["/Users/me/My ROM.nds", "/Users/me/icon.png"], 120, 80)],
      f"a tkdnd drop -> callback(paths, x, y): {got}")
if REAL != "win32":
    try:
        import tkinterdnd2  # noqa: F401
        have = True
    except ImportError:
        have = False
    got.clear()
    root.update()
    d = dragdrop.FileDropTarget(root, lambda p, x, y: got.append((p, x, y)))
    check(d.enabled == have, f"enabled when tkinterdnd2 is installed ({have})")
    if have:
        script = root.tk.call("bind", root, "<<Drop:DND_Files>>")
        # tkdnd passes %D as a list
        script = str(script).replace("%D", "{{/tmp/a b.glb}}").replace("%X", "5").replace("%Y", "6")
        check(root.tk.eval(script) == "copy" and got == [(["/tmp/a b.glb"], 5, 6)], f"bound drop script: {got}")
root.destroy()

print("pycgfx window on a Mac: manual only")
import pycgfx_setup as ps  # noqa: E402
import yanbf_cbc as g  # noqa: E402
empty = os.path.join(S, "platform_pycgfx")
paths.PYCGFX_DIR = empty
paths.PYCGFX_MAIN = os.path.join(empty, "main.py")
paths.REQUIRED[:] = [(p, d) for p, d in paths.REQUIRED if "pycgfx" not in p] + [(empty, True), (paths.PYCGFX_MAIN, False)]
g.messagebox.showerror = lambda *a, **k: None
root = tk.Tk(); root.withdraw()
a = g.App(root); root.deiconify(); root.update()
texts = []


def walk(x):
    for c in x.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except tk.TclError:
            pass
        walk(c)


with on("darwin"):
    a.open_pycgfx_setup(); root.update()
w = a.pycgfx_win
walk(w.win)
blob = "\n".join(texts)
check(w.auto_btn is None and w.bar is None and "Option 1" not in blob
      and "Download and set up automatically" not in blob, "no automatic download option")
check("Download it by hand" in blob and "Show in Finder" in blob, "manual steps + Show in Finder")
check(ps.ZIP_URL in blob and f"Use exactly this version: pycgfx {ps.SHORT}" in blob, "exact version + link")
w.start_download(); root.update()
check(not w.busy(), "start_download does nothing on a Mac")
w.close(); root.update()
a.open_pycgfx_setup(); root.update()
check(a.pycgfx_win.auto_btn is not None if REAL != "darwin" else a.pycgfx_win.auto_btn is None,
      "this system's window: automatic option only off a Mac")
a._on_close()
finish()
