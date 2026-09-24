"""HOME Menu preview: option C background, full grid on the model, faint grid on the background."""
import importlib.util
import math
import time

from _common import CASE_GLB, check, finish, isolate
isolate("grid")
from PIL import Image
import home_bg, home_preview as hp, preview


# the real HOME Menu screenshot is only on the author's PC; everywhere else it's the drawn backdrop
SCREENSHOT = importlib.util.find_spec("home_bg_screenshot") is not None
bg = home_bg.load()
if SCREENSHOT:
    import home_bg_screenshot
    check(bg.tobytes() == home_bg_screenshot.load().tobytes(), "backdrop is the real 400x240 screen, pixel for pixel")
else:
    check(bg.tobytes() == home_bg.drawn().tobytes(), "no screenshot: backdrop is the drawn 400x240 screen")
check(bg.size == (400, 240) and bg.mode == "RGB", "backdrop is 400x240 RGB")
check(hp.DISPLAY == (1200, 720), "window shows 3x (1200x720)")

grid = hp.pixel_grid()
mg, bgg = (g.convert("L") for g in grid)
check(mg.getpixel((0, 0)) == 255 and mg.getpixel((2, 0)) == int(255 * hp.GRID_GAP / hp.GRID_LIFT), "model grid: full gaps")
check(bgg.getpixel((0, 0)) == 255 and bgg.getpixel((2, 0)) == int(255 * hp.BG_GRID_GAP), "background grid: faint gaps")
check(all(bgg.getpixel((x, 7)) < 255 for x in range(2, 1200, 3)) and all(bgg.getpixel((7, y)) < 255 for y in range(2, 720, 3)),
      "faint grid still has all 400x240 cells")

mesh = preview.load_glb(CASE_GLB)
spin, bills = preview.find_spin_node(mesh), preview.find_billboard_nodes(mesh)
native, mmask = preview.render(preview.pose(mesh, math.radians(40), spin, bills), size=(400, 240),
                               background=bg, want_mask=True)
frame = hp.to_screen(native, grid, mmask)

# every background pixel keeps its exact colour at its centre, and its gaps stay within BG_GRID_GAP
bg_px = [(x, y) for y in range(240) for x in range(400) if mmask.getpixel((x, y)) == 0]
check(len(bg_px) > 80000, f"{len(bg_px)} background pixels checked")
exact = all(frame.getpixel((x * 3, y * 3)) == bg.getpixel((x, y)) and frame.getpixel((x * 3 + 1, y * 3 + 1)) == bg.getpixel((x, y))
            for x, y in bg_px)
check(exact, "every background pixel's 2x2 centre is its exact original colour")
short = max(max(int(o * hp.BG_GRID_GAP) - c for c, o in zip(frame.getpixel((x * 3 + 2, y * 3)), bg.getpixel((x, y))))
            for x, y in bg_px)
check(short <= 1, f"background gaps no darker than {hp.BG_GRID_GAP:.0%} of the original (+1 level rounding): "
                  f"worst {short} level(s) below")

# the faint app-grid tiles: their contrast survives (3x3 cell averages track the original)
cells = frame.convert("L").resize((400, 240), Image.BOX)
orig = native.convert("L")
region = [(x, y) for y in range(60, 200) for x in range(0, 400) if mmask.getpixel((x, y)) == 0]
o = [orig.getpixel(p) for p in region]
c = [cells.getpixel(p) for p in region]
mo, mc = sum(o) / len(o), sum(c) / len(c)
cov = sum((a - mo) * (b - mc) for a, b in zip(o, c))
corr = cov / math.sqrt(sum((a - mo) ** 2 for a in o) * sum((b - mc) ** 2 for b in c))
contrast = (math.sqrt(sum((b - mc) ** 2 for b in c) / len(c)) / math.sqrt(sum((a - mo) ** 2 for a in o) / len(o)))
check(corr > 0.99 and contrast > 0.94, f"tile pattern kept: correlation {corr:.4f}, contrast {contrast:.0%} of original")
# status bar text: white badge text stays white
if SCREENSHOT:  # white badge text in the real status bar
    txt = [frame.getpixel((x, y)) for x in range(160, 320) for y in range(20, 45)]
    check(max(sum(p) for p in txt) >= 3 * 250, "white 'Internet' text stays white")

# the model still gets the full grid
cx, cy = 200, 120
check(mmask.getpixel((cx, cy)) == 255, "screen centre is on the model")
centre, gap = frame.getpixel((cx * 3, cy * 3)), frame.getpixel((cx * 3 + 2, cy * 3))
ratio = sum(gap) / max(1, sum(centre))
check(abs(ratio - hp.GRID_GAP / hp.GRID_LIFT) < 0.05, f"model: gap/centre = {ratio:.2f} (full grid)")

t = time.perf_counter()
for k in range(10):
    n, m = preview.render(preview.pose(mesh, k * 0.3, spin, bills), size=(400, 240), background=bg, want_mask=True)
    hp.to_screen(n, grid, m)
ms = (time.perf_counter() - t) * 100
check(ms < 45, f"frame incl. grid: {ms:.1f} ms")

import tkinter as tk
import yanbf_cbc as g2
root = tk.Tk(); root.withdraw()
app = g2.App(root)
app.banner_var.set(CASE_GLB)
end = time.time() + 10
while time.time() < end and str(app.home_btn["state"]) != "normal":
    root.update(); time.sleep(0.01)
app.open_home_preview()
w = app.home_win
end = time.time() + 1.5
while time.time() < end:
    root.update(); time.sleep(0.01)
check(w.last_frame.size == (1200, 720), "window frames are 1200x720")
check(len(w._fps) >= 15, f"animating at {len(w._fps)} fps")
app._on_close()
finish()
