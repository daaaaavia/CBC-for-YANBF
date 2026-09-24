"""HOME Menu preview: the backdrop, and one faint pixel grid over the whole screen -
background, banner model and name/nameModel logo alike."""
import importlib.util
import math
import os
import time

from _common import CASE_GLB, S, check, check_speed, finish, isolate
isolate("grid")
from PIL import Image
import home_bg, home_preview as hp, preview


# the real HOME Menu screenshot is in the private repo; without it it's the drawn backdrop
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
gl = grid.convert("L")
check(gl.getpixel((0, 0)) == 255 and gl.getpixel((2, 0)) == int(255 * hp.GRID_GAP) and hp.GRID_GAP == 0.94,
      "one faint grid: centres untouched, gaps at 94%")
check(all(gl.getpixel((x, 7)) < 255 for x in range(2, 1200, 3)) and all(gl.getpixel((7, y)) < 255 for y in range(2, 720, 3)),
      "grid has all 400x240 cells")


def grid_applied_evenly(model_path, angle, label):
    """Every screen pixel - background, model and logo - keeps its exact colour at its
    2x2 centre, and its gap is that colour at GRID_GAP (to the nearest level)."""
    mesh = preview.load_glb(model_path)
    spin, bills = preview.find_spin_node(mesh), preview.find_billboard_nodes(mesh)
    native, mask = preview.render(preview.pose(mesh, angle, spin, bills), size=(400, 240), background=bg,
                                  want_mask=True)
    frame = hp.to_screen(native, grid)
    kinds = {"background": 0, "model": 0}
    bad_centre = worst_gap = 0
    for y in range(240):
        for x in range(400):
            o = native.getpixel((x, y))
            kinds["model" if mask.getpixel((x, y)) else "background"] += 1
            if frame.getpixel((x * 3, y * 3)) != o or frame.getpixel((x * 3 + 1, y * 3 + 1)) != o:
                bad_centre += 1
            gap = frame.getpixel((x * 3 + 2, y * 3))
            worst_gap = max(worst_gap, max(abs(int(v * hp.GRID_GAP) - c) for c, v in zip(gap, o)))
    check(kinds["model"] > 2000 and kinds["background"] > 50000,
          f"{label}: {kinds['model']} model and {kinds['background']} background pixels checked")
    check(bad_centre == 0, f"{label}: every pixel's centre is its exact colour (model included, no brightening)")
    check(worst_gap <= 1, f"{label}: every gap is its pixel at {hp.GRID_GAP:.0%} (worst {worst_gap} level off)")
    return native, mask, frame


native, mask, frame = grid_applied_evenly(CASE_GLB, math.radians(40), "textured case")
grid_applied_evenly(os.path.join(S, "banner_sibling.glb"), math.radians(30), "model + name/nameModel logo")

# the model gets exactly the same grid as the background: same gap/centre ratio
flat = lambda x, y: native.getpixel((x, y)) == native.getpixel((x + 1, y))
m_px = next((x, y) for y in range(80, 160) for x in range(150, 250) if mask.getpixel((x, y)) and flat(x, y)
            and sum(native.getpixel((x, y))) > 150)
b_px = next((x, y) for y in range(60, 200) for x in range(0, 60) if not mask.getpixel((x, y)) and flat(x, y))
ratios = []
for x, y in (m_px, b_px):
    centre, gap = frame.getpixel((x * 3, y * 3)), frame.getpixel((x * 3 + 2, y * 3))
    ratios.append(sum(gap) / sum(centre))
check(all(abs(r - hp.GRID_GAP) < 0.02 for r in ratios) and abs(ratios[0] - ratios[1]) < 0.02,
      f"gap/centre on the model {ratios[0]:.3f} = on the background {ratios[1]:.3f}")

# the faint app-grid tiles: their contrast survives (3x3 cell averages track the original)
cells = frame.convert("L").resize((400, 240), Image.BOX)
orig = native.convert("L")
region = [(x, y) for y in range(60, 200) for x in range(0, 400) if mask.getpixel((x, y)) == 0]
o = [orig.getpixel(p) for p in region]
c = [cells.getpixel(p) for p in region]
mo, mc = sum(o) / len(o), sum(c) / len(c)
cov = sum((a - mo) * (b - mc) for a, b in zip(o, c))
corr = cov / math.sqrt(sum((a - mo) ** 2 for a in o) * sum((b - mc) ** 2 for b in c))
contrast = (math.sqrt(sum((b - mc) ** 2 for b in c) / len(c)) / math.sqrt(sum((a - mo) ** 2 for a in o) / len(o)))
check(corr > 0.99 and contrast > 0.94, f"tile pattern kept: correlation {corr:.4f}, contrast {contrast:.0%} of original")
if SCREENSHOT:  # white badge text in the real status bar
    txt = [frame.getpixel((x, y)) for x in range(160, 320) for y in range(20, 45)]
    check(max(sum(p) for p in txt) >= 3 * 250, "white 'Internet' text stays white")

mesh = preview.load_glb(CASE_GLB)
spin, bills = preview.find_spin_node(mesh), preview.find_billboard_nodes(mesh)
t = time.perf_counter()
for k in range(10):
    hp.to_screen(preview.render(preview.pose(mesh, k * 0.3, spin, bills), size=(400, 240), background=bg), grid)
ms = (time.perf_counter() - t) * 100
check_speed(ms < 45, f"frame incl. grid: {ms:.1f} ms")

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
