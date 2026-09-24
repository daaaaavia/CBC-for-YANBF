"""Previews: icon, flat banner, WAV waveform, and the software-rendered .glb banner."""
import math
import os
import time

from _common import CASE_GLB, check, finish, isolate, S
isolate("preview")
import preview
import pipeline as pl

REAL = CASE_GLB  # a textured game-case model (fixtures.py), like a real banner


print("preview module")
w16, w8, w24 = (os.path.join(S, "wav", n) for n in ("s16.wav", "u8.wav", "s24.wav"))  # fixtures.py
for p, desc in ((w16, "1.00 s · 44100 Hz · 16-bit · stereo"), (w8, "0.50 s · 22050 Hz · 8-bit · mono"),
                (w24, "0.50 s · 22050 Hz · 24-bit · mono")):
    img, info = preview.wav_preview(p)
    col = img.getpixel((150, 10)); img.save(os.path.basename(p) + ".png")  # 0.8 amplitude peaks at y~7
    check(info.describe() == desc and col == preview.WAVE_FG, f"{os.path.basename(p)}: {info.describe()}")
try:
    preview.wav_preview(os.path.join(S, "wav", "junk.wav"))
    check(False, "junk wav raises")
except Exception:
    check(True, "junk wav raises")

img, info = preview.icon_preview(os.path.join(S, "icon48.png"))
check(img.size == (170, 100) and info.startswith("48×48 PNG"), f"icon preview: {info}")
img, info = preview.icon_preview(os.path.join(S, "lim", "i49.png"))
check(info.startswith("49×48"), "oversize icon still previewed")
img, info = preview.banner_image_preview(os.path.join(S, "banner256.png"))
check(img.size == (300, 180) and info.startswith("256×128 PNG"), f"banner png: {info}")
img, info = preview.banner_image_preview(os.path.join(S, "big_banner.png"))
check(img.size == (300, 180), "oversized banner scaled to fit")
img, info = preview.banner_image_preview(os.path.join(S, "lim", "junk.png"))
check(info == "", "unreadable banner -> placeholder")

m = preview.load_glb(REAL)
t = time.perf_counter()
img = preview.render(m, ss=2)
dt = time.perf_counter() - t
check(img.size == (300, 180), f"real model render {dt:.3f}s")
# centre of the cover must be textured (not the black inner layer, not background)
px = img.getpixel((150, 90))
check(px != preview.BG and sum(px) > 60, f"cover visible at centre: {px}")
back = preview.render(m, yaw=math.pi, ss=1)
check(back.getpixel((150, 90)) != preview.BG, "back side renders")
small = preview.render(m, zoom=0.25)
check(small.getpixel((150, 30)) == preview.BG and small.getpixel((150, 90)) != preview.BG, "zoom 0.25 shrinks model")
tst = preview.load_glb(os.path.join(S, "test.glb"))
check(preview.render(tst, zoom=8).getpixel((150, 90)) != preview.BG, "CCW quad is front-facing (not culled)")
check(preview.render(tst, yaw=math.pi, zoom=8).getpixel((150, 90)) == preview.BG, "single-sided quad culled from behind")
check(preview.banner_camera()["pos"] == (0, 1, 44.786), "camera read from banner-camera.gltf")

print("GUI")
import tkinter as tk
import yanbf_cbc as g

root = tk.Tk()
root.withdraw()
app = g.App(root)
root.update()


def pump(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


check(app.icon_preview["image"] and app.icon_preview_info["text"] == "", "icon placeholder at start")
check(str(app.play_btn["state"]) == "disabled", "play disabled without audio")
app.icon_var.set(os.path.join(S, "icon48.png")); root.update()
check(app.icon_preview_info["text"].startswith("48×48"), "icon preview updates")
app.mode_var.set(pl.MODE_PNG)
app.banner_var.set(os.path.join(S, "banner256.png")); root.update()
check(app.banner_preview_info["text"].startswith("256×128"), "png banner preview")
app.mode_var.set(pl.MODE_GLB)  # clears the png
app.banner_var.set(REAL)
check(pump(lambda: app.glb_mesh is not None), "glb loads in background")
check(pump(lambda: "HOME Menu banner camera" in app.banner_preview_info["text"]), f"glb info: {app.banner_preview_info['text']!r}")
gen = app._render_gen
check(pump(lambda: app._photos.get("banner") is not None), "glb rendered")


class E:
    def __init__(self, x, y, delta=0):
        self.x, self.y, self.delta = x, y, delta


app._on_drag_start(E(100, 100)); app._on_drag(E(160, 110))
check(pump(lambda: not app._drag_pending) and app.view["yaw"] > 0.5, "drag rotates")
app._request_final_render()
check("rotated" in app.banner_preview_info["text"], "info says rotated")
app._on_wheel(E(0, 0, 120))
check(abs(app.view["zoom"] - 1.25) < 1e-9 and "not the real size" in app.banner_preview_info["text"], "wheel zooms")
app._reset_view()
check(app.view == {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0} and "HOME Menu banner camera" in app.banner_preview_info["text"],
      "double-click resets")
bad = os.path.join(S, "bad.glb")
app.banner_var.set(bad)
check(pump(lambda: "Error" in app.banner_preview_info["text"] or ":" in app.banner_preview_info["text"]),
      f"broken glb shows error: {app.banner_preview_info['text']!r}")
app.audio_var.set(w16); root.update()
check(app.audio_preview_info["text"].startswith("1.00 s") and str(app.play_btn["state"]) == "normal", "audio preview + play")
app.audio_var.set(os.path.join(S, "wav", "junk.wav")); root.update()
check("Error" in app.audio_preview_info["text"] or "RIFF" in app.audio_preview_info["text"] or app.audio_preview_info["text"],
      f"bad wav message: {app.audio_preview_info['text']!r}")
app.audio_var.set(""); root.update()
check(str(app.play_btn["state"]) == "disabled", "clearing audio disables play")
root.destroy()

finish()
