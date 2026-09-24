"""Drag-and-drop tests: routing, hit-testing, and a real WM_DROPFILES message."""
import ctypes
import os
import time

from _common import WINDOWS, check, finish, isolate, S, skip

if not WINDOWS:
    skip("this suite sends real Windows messages (WM_DROPFILES); tkdnd drops are tested in suite_platform")
from ctypes import wintypes  # noqa: E402
ctypes.windll.user32.SetProcessDPIAware()
isolate("dragdrop")
import pipeline as pl



import tkinter as tk
import yanbf_cbc as g

root = tk.Tk()
root.attributes("-topmost", True)
app = g.App(root)
root.geometry("+30+30")


def pump(n=20):
    for _ in range(n):
        root.update()
        time.sleep(0.01)


pump()
check(app.drop_target is not None and app.drop_target.enabled, "drop target registered once the window is shown")

ICON = os.path.join(S, "icon48.png")
BANNER = os.path.join(S, "banner256.png")
GLB = os.path.join(S, "test.glb")
WAV = os.path.join(S, "wav", "s16.wav")
NDS = os.path.join(S, "roms", "Two Lines.nds")
JPG = os.path.join(S, "photo.jpg")

print("routing")
r = app.route_drop
check(r(NDS, None) == "nds" and r(NDS, "icon") == "nds", ".nds -> ROM anywhere")
check(r(WAV, "banner") == "audio", ".wav -> audio even if dropped on banner")
check(r(GLB, None) == "banner_glb", ".glb -> 3D banner")
check(r(ICON, None) == "icon" and r(BANNER, None) == "banner_png", "loose .png routed by size")
check(r(os.path.join(S, "lim", "i32.png"), None) == "banner_png", "loose 32x32 .png isn't an icon any more -> banner")
check(r(ICON, "banner") == "banner_png" and r(BANNER, "icon") == "icon", ".png follows the row it was dropped on")
check(r(JPG, "icon") == "icon" and r(JPG, None) is None, "unknown type -> row under cursor, else unsure")

print("hit-testing")


def center(w):
    return w.winfo_rootx() + w.winfo_width() // 2, w.winfo_rooty() + w.winfo_height() // 2


zones = {
    "nds entry": (app.nds_entry, "nds"), "icon entry": (app.icon_entry, "icon"),
    "icon error row": (app.icon_err, "icon"), "banner entry": (app.banner_entry, "banner"),
    "audio entry": (app.audio_entry, "audio"), "icon preview": (app.icon_preview, "icon"),
    "banner preview": (app.banner_preview, "banner"), "audio preview": (app.audio_preview, "audio"),
    "title entry": (app.title_entry, None), "log": (app.log_text, None),
}
for name, (w, want) in zones.items():
    got = app.zone_at(*center(w))
    check(got == want, f"{name} -> {got}")

print("real WM_DROPFILES")
k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]


def drop(files, screen_xy):
    hwnd = app.drop_target.hwnd
    pt = wintypes.POINT(*screen_xy)
    u32.ScreenToClient(hwnd, ctypes.byref(pt))
    names = ("\0".join(files) + "\0\0").encode("utf-16-le")
    header = (20).to_bytes(4, "little") + pt.x.to_bytes(4, "little", signed=True) + \
        pt.y.to_bytes(4, "little", signed=True) + (0).to_bytes(4, "little") + (1).to_bytes(4, "little")
    data = header + names
    h = k32.GlobalAlloc(0x0042, len(data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
    p = k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    u32.PostMessageW(hwnd, 0x0233, h, 0)
    pump(30)


drop([ICON], center(app.icon_entry))
check(app.icon_var.get() == ICON, "icon dropped on icon row")
drop([BANNER], center(app.banner_preview))
check(app.mode_var.get() == pl.MODE_PNG and app.banner_var.get() == BANNER, "png dropped on banner preview -> flat banner")
drop([GLB], center(app.icon_entry))
check(app.mode_var.get() == pl.MODE_GLB and app.banner_var.get() == GLB and app.icon_var.get() == ICON,
      ".glb dropped on icon row -> banner switches to 3D, icon untouched")
app.icon_var.set(""); app.banner_var.set(""); app.audio_var.set(""); pump()
drop([NDS, ICON, GLB, WAV], center(app.log_text))
check(app.nds_var.get() == NDS and app.icon_var.get() == ICON and app.banner_var.get() == GLB
      and app.audio_var.get() == WAV, "4 files dropped at once on the log -> each routed by type")
check(app.title_var.get() == "Some Game" and app.locks["title"]["state"] == "locked", ".nds drop autofills + locks")
drop([JPG], center(app.icon_entry))
check(app.icon_var.get() == JPG and "JPEG" in app.icon_err["text"], "jpg on icon row -> shown with the PNG error")
before = app.audio_var.get()
drop([JPG], center(app.title_entry))
log = app.log_text.get("1.0", "end")
check(app.audio_var.get() == before and "Not sure where photo.jpg goes" in log, "jpg on title row -> warning only")
drop([S], center(app.icon_entry))
check("Dropped folder" in app.log_text.get("1.0", "end"), "folder drop ignored with warning")
check("Dropped Two Lines.nds → NDS ROM" in log, "drop is logged")
root.destroy()

finish()
