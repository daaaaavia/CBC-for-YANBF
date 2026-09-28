"""Windows / macOS differences (platform_util.py, paths.py): tool names, where a frozen
.app finds processes/, where user data goes, subprocess flags, the audio and 'open'
commands, macOS dark mode and drag and drop through tkdnd. (The Mac setup window:
suite_setup_window.) Runs on either system: sys.platform is switched to test the other."""
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
app = os.path.join(S, "platform_mac", "CBC-for-YANBF.app")
exe = os.path.join(app, "Contents", "MacOS", "CBC-for-YANBF")
res = os.path.join(app, "Contents", "Resources")
os.makedirs(os.path.dirname(exe), exist_ok=True)
with on("darwin"):
    check(paths._base_dir(True, exe, "x") == os.path.join(S, "platform_mac"),
          "no processes/ in the bundle -> the folder holding the .app")
    os.makedirs(os.path.join(res, "processes"), exist_ok=True)
    check(paths._base_dir(True, exe, "x") == res, "processes/ in Contents/Resources -> used")
    data, out, pyc, ctr = paths._user_dirs(True, res, home)
    support = os.path.join(home, "Library", "Application Support", "CBC-for-YANBF")
    check(data == support, f"settings + IDs in Application Support: {data}")
    check(out == os.path.join(home, "Documents", "CBC-for-YANBF", "output"), f"output in Documents: {out}")
    check(pyc == os.path.join(support, "pycgfx"), f"pycgfx in Application Support: {pyc}")
    check(ctr == os.path.join(support, "ctrtool"), f"ctrtool in Application Support: {ctr}")
    check(not any(p.startswith(app) for p in (data, out, pyc, ctr)), "nothing written inside the bundle")
    # folders from before the rename (YANBF-CBC) move to the new name, once
    old_home = os.path.join(S, "platform_old_home")
    old_support = os.path.join(old_home, "Library", "Application Support", "YANBF-CBC")
    os.makedirs(os.path.join(old_support, "pycgfx"))
    with open(os.path.join(old_support, "unique_ids.json"), "w") as f:
        f.write("{}")
    os.makedirs(os.path.join(old_home, "Documents", "YANBF-CBC", "output", "Game"))
    data2, out2, pyc2, _ = paths._user_dirs(True, res, old_home, migrate=True)
    check(os.path.isfile(os.path.join(data2, "unique_ids.json")) and os.path.isdir(pyc2)
          and os.path.isdir(os.path.join(out2, "Game")) and not os.path.exists(old_support),
          "old YANBF-CBC folders moved to CBC-for-YANBF (IDs, pycgfx, output)")
    os.makedirs(old_support)
    paths._user_dirs(True, res, old_home, migrate=True)
    check(os.path.isdir(old_support) and os.path.isfile(os.path.join(data2, "unique_ids.json")),
          "never overwrites a CBC-for-YANBF folder that already exists")
    src = paths._user_dirs(False, S, home)
    check(src[0] == S, "macOS from source: next to the project, as on Windows")
with on("win32"):
    base = os.path.join(S, "win")
    check(paths._base_dir(True, os.path.join(base, "CBC-for-YANBF.exe"), "x") == base, "Windows exe: its folder")
    check(paths._user_dirs(True, base, home) ==
          (base, os.path.join(base, "output"), os.path.join(base, "processes", "YANBF", "pycgfx"),
           os.path.join(base, "processes", "Project_CTR")),
          "Windows: settings, output, pycgfx and ctrtool next to the exe, as before")

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
        import platform
        import tkinterdnd2
        # tkinterdnd2 0.6.3 has no tkdnd for Intel Macs with Tk 9
        rep = {"arm64": "osx-arm64", "x86_64": "osx-x64"}.get(platform.machine(), "linux-x64")
        rep += "-tcl9" if tk.TclVersion >= 9 else ""
        have = os.path.isdir(os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd", rep))
    except ImportError:
        have = False
    got.clear()
    root.update()
    d = dragdrop.FileDropTarget(root, lambda p, x, y: got.append((p, x, y)))
    check(d.enabled == have, f"enabled where tkdnd has a build for this system ({have})")
    if have:
        script = root.tk.call("bind", root, "<<Drop:DND_Files>>")
        # tkdnd passes %D as a list
        script = str(script).replace("%D", "{{/tmp/a b.glb}}").replace("%X", "5").replace("%Y", "6")
        check(root.tk.eval(script) == "copy" and got == [(["/tmp/a b.glb"], 5, 6)], f"bound drop script: {got}")
root.destroy()

finish()
