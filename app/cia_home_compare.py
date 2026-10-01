"""The CIA editor's HOME Menu preview - the banner as it is now and as it will be,
side by side, animated on the HOME Menu top screen.

It reuses the generator's HOME Menu preview pieces (home_preview.py, preview.py: the
backdrop, banner camera, renderer, spin and billboard) without changing them; the
generator's own preview window is untouched.

Each side is one of:
  * a 3D banner (a .glb): rendered exactly like the generator's preview
  * a flat banner (a picture): drawn on the same 26 x 13 quad (y -7.5..5.5) that
    bannertool's flat-banner model uses, through the same camera
  * unknown: a 3D banner with no .glb to draw it from - the backdrop and a note
Both sides spin together (same angle and speed). Two screens at the generator's 3x
would be 2400 px wide, so the screens are 2x (or 1x on a narrow display).
"""

import math
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageChops, ImageDraw, ImageTk

import home_bg
import home_preview as hp
import platform_util as pu
import preview
import theme

# bannertool's flat-banner model: a 26 x 13 rectangle, centre (0, -1), facing the camera
FLAT_X, FLAT_Y = (-13.0, 13.0), (-7.5, 5.5)


def flat_mesh(image):
    """A preview.Mesh of a flat banner: the picture on bannertool's quad."""
    tex = image.convert("RGBA").resize((256, 128), Image.LANCZOS)
    (x0, x1), (y0, y1) = FLAT_X, FLAT_Y
    pts = [(x0, y1, 0.0), (x1, y1, 0.0), (x1, y0, 0.0), (x0, y0, 0.0)]  # TL, TR, BR, BL
    uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]  # glTF style: v down
    mat = preview.Material(color=(1.0, 1.0, 1.0, 1.0), texture=tex, alpha_mode="BLEND", alpha_cutoff=0.5,
                           double_sided=True)
    tris = [(0, 3, 2, 0, (uv[0], uv[3], uv[2]), (1, 1, 1, 1)), (0, 2, 1, 0, (uv[0], uv[2], uv[1]), (1, 1, 1, 1))]
    return preview.Mesh(verts=list(pts), tris=tris, materials=[mat], center=(0.0, (y0 + y1) / 2, 0.0),
                        radius=math.hypot(x1 - x0, y1 - y0) / 2, triangle_count=2,
                        vert_src=[(-1, p) for p in pts])


class Side:
    """What one screen shows: ('glb', mesh) | ('flat', image) | ('none', note), + a caption."""

    def __init__(self, kind, value, caption, sound=None):
        self.kind, self.value, self.caption, self.sound = kind, value, caption, sound
        if kind == "flat":
            self.mesh = flat_mesh(value)
        elif kind == "glb":
            self.mesh = value
        else:
            self.mesh = None
        self.spin = preview.find_spin_node(self.mesh) if kind == "glb" else None
        self.bills = preview.find_billboard_nodes(self.mesh) if kind == "glb" else ()


def _grid(size, scale):
    """The faint pixel-gap grid at `scale` (the generator's is for 3x)."""
    if scale < 2:
        return None
    g = round(255 * hp.GRID_GAP)
    im = Image.new("L", size, 255)
    d = ImageDraw.Draw(im)
    for x in range(scale - 1, size[0], scale):
        d.line((x, 0, x, size[1]), fill=g)
    for y in range(scale - 1, size[1], scale):
        d.line((0, y, size[0], y), fill=g)
    return im.convert("RGB")


class CompareWindow:
    def __init__(self, master, old, new, title=""):
        self.win = tk.Toplevel(master)
        theme.decorate(self.win)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        self.scale = 2 if self.win.winfo_screenwidth() >= 1700 else 1
        self.display = (hp.SCREEN[0] * self.scale, hp.SCREEN[1] * self.scale)
        self.grid = _grid(self.display, self.scale)
        self.background = home_bg.load()
        self.speed = tk.DoubleVar(value=hp.DEFAULT_SPEED)
        self.angle = 0.0
        self.running = True
        self.closed = False
        self.player = pu.AudioPlayer()
        self._last = time.perf_counter()
        self._photos = {}
        self.last_frames = {}

        outer = ttk.Frame(self.win, padding=10)
        outer.pack(fill="both", expand=True)
        screens = ttk.Frame(outer)
        screens.pack()
        self.screens, self.captions, self.sound_btns = {}, {}, {}
        for col, which in enumerate(("old", "new")):
            ttk.Label(screens, text="Now" if which == "old" else "New",
                      font=theme.current.font_status).grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else 12, 0))
            s = tk.Label(screens, bd=1, relief="solid", bg=theme.current.screen_border)
            s.grid(row=1, column=col, padx=(0 if col == 0 else 12, 0), pady=(2, 0))
            self.screens[which] = s
            c = ttk.Label(screens, foreground=theme.current.caption_fg, wraplength=self.display[0], justify="left")
            c.grid(row=2, column=col, sticky="w", padx=(0 if col == 0 else 12, 0), pady=(4, 0))
            self.captions[which] = c
            b = ttk.Button(screens, text="🔊 Play sound", command=lambda w=which: self.play(w))
            b.grid(row=3, column=col, sticky="w", padx=(0 if col == 0 else 12, 0), pady=(4, 0))
            self.sound_btns[which] = b

        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(10, 0))
        self.pause_btn = ttk.Button(row, text="❚❚ Pause", width=10, command=self.toggle_pause)
        self.pause_btn.pack(side="left")
        ttk.Button(row, text="Reset spin", command=self.reset).pack(side="left", padx=(6, 0))
        ttk.Label(row, text="Spin speed (both)").pack(side="left", padx=(16, 4))
        ttk.Scale(row, from_=-180, to=180, variable=self.speed, length=220,
                  command=lambda _v: self._speed_label()).pack(side="left")
        self.speed_text = ttk.Label(row, width=26)
        self.speed_text.pack(side="left", padx=(6, 0))
        ttk.Label(outer, foreground=theme.current.hint_fg, justify="left", wraplength=self.display[0] * 2,
                  text="Approximation, like the generator's HOME Menu preview: banner camera, worldModel spin and "
                       "name/nameModel billboard for 3D banners; a flat banner is drawn on bannertool's flat-banner "
                       "rectangle. The console's exact lighting and effects may differ.").pack(anchor="w", pady=(8, 0))

        self.set_sides(old, new, title)
        self._speed_label()
        self.win.after(10, self._tick)

    # ------------------------------------------------------------------ public
    def set_sides(self, old, new, title=""):
        self.sides = {"old": old, "new": new}
        self.win.title("HOME Menu preview - now vs new" + (f" - {title}" if title else ""))
        for which, side in self.sides.items():
            self.captions[which].configure(text=side.caption)
            self.sound_btns[which].configure(state="normal" if side.sound else "disabled")
        self.angle = 0.0
        self._render()

    def close(self):
        self.closed = True
        self.player.stop()
        self.win.destroy()

    def toggle_pause(self):
        self.running = not self.running
        self.pause_btn.configure(text="❚❚ Pause" if self.running else "▶ Play")
        self._last = time.perf_counter()

    def reset(self):
        self.angle = 0.0
        self._render()

    def play(self, which):
        path = self.sides[which].sound
        if path:
            try:
                self.player.play(path)
            except RuntimeError:
                pass

    def _speed_label(self):
        v = self.speed.get()
        self.speed_text.configure(text="0°/s (stopped)" if abs(v) < 0.5 else
                                  f"{v:+.0f}°/s ({360 / abs(v):.1f} s per turn)")

    # ------------------------------------------------------------------ animation
    def _tick(self):
        if self.closed:
            return
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        if self.running:
            self.angle = (self.angle + math.radians(self.speed.get()) * dt) % (2 * math.pi)
        t0 = time.perf_counter()
        self._render()
        spent = (time.perf_counter() - t0) * 1000
        # like the generator's preview: slow frames wait as long as they took
        delay = max(1, int(hp.FRAME_MS - spent)) if spent < hp.FRAME_MS else int(spent)
        self.win.after(delay, self._tick)

    def frame(self, which):
        """One screen at the native 400x240."""
        side = self.sides[which]
        if side.mesh is None:
            im = self.background.convert("RGB").copy()
            d = ImageDraw.Draw(im)
            d.rectangle((40, 90, 360, 150), fill=(40, 40, 40))
            d.text((200, 110), "3D banner", fill="white", anchor="mm")
            d.text((200, 130), "can't be drawn from the CIA alone", fill=(200, 200, 200), anchor="mm")
            return im
        spin = self.angle if side.kind == "glb" else 0.0  # (a flat banner doesn't spin)
        posed = preview.pose(side.mesh, spin, side.spin, side.bills)
        return preview.render(posed, size=hp.SCREEN, ss=1, background=self.background)

    def _render(self):
        for which in ("old", "new"):
            im = self.frame(which).resize(self.display, Image.NEAREST)
            if self.grid is not None:
                im = ImageChops.multiply(im, self.grid)
            self.last_frames[which] = im
            self._photos[which] = ImageTk.PhotoImage(im)
            self.screens[which].configure(image=self._photos[which])
