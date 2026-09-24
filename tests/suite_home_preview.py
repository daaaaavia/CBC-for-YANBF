"""HOME Menu preview: worldModel spin, name/nameModel billboard, window."""
import math
import os
import time

from _common import CASE_GLB, check, check_speed, finish, isolate, S
isolate("home")
import preview



def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def verts_of(mesh, node_name):
    ni = mesh.node_names.index(node_name)
    return [i for i, (n, _) in enumerate(mesh.vert_src) if n == ni]


print("posing")
m = preview.load_glb("banner_sibling.glb")
spin, bills = preview.find_spin_node(m), preview.find_billboard_nodes(m)
check(m.node_names[spin] == "worldModel" and [m.node_names[i] for i in bills] == ["name", "nameModel"],
      "finds worldModel + name/nameModel (the exact names pycgfx billboards)")
box = verts_of(m, "worldModel")
p90 = preview.pose(m, math.radians(90), spin, bills)
v0, v90 = m.verts[box[0]], p90.verts[box[0]]  # (-4,-3,1) -> Ry(90): (1,-3,4)
check(close(v90, (1, -3, 4)), f"worldModel vertex rotates about Y: {v0} -> {tuple(round(x, 3) for x in v90)}")
logo = verts_of(m, "nameModel")
check(all(close(m.verts[i], p90.verts[i]) for i in logo), "sibling logo doesn't move while worldModel spins")

c = preview.load_glb("banner_child.glb")
spin_c, bills_c = preview.find_spin_node(c), preview.find_billboard_nodes(c)
check([c.node_names[i] for i in bills_c] == ["name", "nameModel"], "child layout: name + nameModel are billboards")
logo_c = verts_of(c, "nameModel")
for deg in (0, 37, 90, 180, 250):
    p = preview.pose(c, math.radians(deg), spin_c, bills_c)
    a, b, q = (p.verts[i] for i in logo_c[:3])
    n = ((b[1] - a[1]) * (q[2] - a[2]) - (b[2] - a[2]) * (q[1] - a[1]),
         (b[2] - a[2]) * (q[0] - a[0]) - (b[0] - a[0]) * (q[2] - a[2]),
         (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]))
    nl = math.sqrt(sum(x * x for x in n))
    check(n[2] / nl > 0.9999, f"child logo still faces the screen at {deg}° (normal z={n[2] / nl:.5f})")
p = preview.pose(c, math.radians(90), spin_c, ())
a, b, q = (p.verts[i] for i in logo_c[:3])
check(abs(a[2] - b[2]) > 1, "without billboard the child logo would turn with the spin (control)")

print("rendering")
bg = preview.Image.new("RGB", (400, 240), (240, 240, 240))
red, blue = (230, 25, 25), (25, 51, 230)
f0 = preview.render(preview.pose(m, 0, spin, bills), size=(400, 240), background=bg)
f90 = preview.render(preview.pose(m, math.radians(90), spin, bills), size=(400, 240), background=bg)
px0, px90 = f0.getpixel((200, 150)), f90.getpixel((200, 150))
check(px0[0] > 150 and px0[2] < 100, f"angle 0: red front face at centre {px0}")
check(px90[1] < 60 and px90[0] > 150 and px90[2] > 150,
      f"angle 90 (CCW from above): magenta left face now in front {px90}")
logo_px = [f.getpixel((200, 82)) for f in (f0, f90)]
check(all(p[1] > 120 and p[0] < 120 for p in logo_px), f"green logo visible at top in both frames {logo_px}")
real = preview.load_glb(CASE_GLB)
rs, rb = preview.find_spin_node(real), preview.find_billboard_nodes(real)
check(real.node_names[rs] == "worldModel" and rb == [], "case model: spins worldModel, no billboard node")
t = time.perf_counter()
for k in range(10):
    preview.render(preview.pose(real, k * 0.2, rs, rb), size=(400, 240), background=bg)
ms = (time.perf_counter() - t) * 100
check_speed(ms < 80, f"real model frame (pose + 400x240 render): {ms:.1f} ms")

print("window")
import tkinter as tk
import yanbf_cbc as g
root = tk.Tk()
root.withdraw()
app = g.App(root)
root.update()
check(str(app.home_btn["state"]) == "disabled", "button disabled with no model")


def pump(cond=lambda: False, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.01)
    return False


app.banner_var.set(os.path.join(S, "banner_child.glb"))
check(pump(lambda: str(app.home_btn["state"]) == "normal"), "button enabled once the .glb loads")
app.audio_var.set(os.path.join(S, "wav", "s16.wav")); root.update()
app.open_home_preview()
w = app.home_win
pump(secs=1.5)
info = w.info["text"]
check("Spinning: worldModel" in info and "Billboard: name, nameModel" in info, f"info: {info}")
fps = len(w._fps)
check(w.angle > math.radians(30) and fps >= 10, f"animating: angle {math.degrees(w.angle):.0f}° after 1.5 s, {fps} fps")
check(str(w.sound_btn["state"]) == "normal", "sound button enabled with audio")
w.toggle_pause(); a = w.angle; pump(secs=0.5)
check(abs(w.angle - a) < 1e-9, "pause stops the spin")
w.toggle_pause(); w.speed.set(-90); pump(secs=0.5)
check(w.angle != a, "negative speed spins the other way")
w.reset(); check(w.angle == 0, "reset")
app.banner_var.set(os.path.join(S, "banner_sibling.glb")); root.update()
check(w.closed, "changing the banner closes the window")
check(pump(lambda: str(app.home_btn["state"]) == "normal"), "new model loads")
app.open_home_preview()
check(app.home_win is not w and not app.home_win.closed, "reopens for the new model")
app._on_close()
finish()
