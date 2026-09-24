"""Animated HOME Menu preview window for a 3D (.glb) banner.

Shows the model on the 3DS top screen through the HOME Menu banner camera. The
whole frame (HOME Menu backdrop + model) is rendered at the native 400×240 and
scaled 3×, with a faint pixel grid imitating the gaps between the 3DS screen's
pixels - the same on the background and on the banner model, so every pixel keeps
its exact colour and no detail is lost. The model has:
  * the 'worldModel' node (else 'world') spinning about its own Y axis, as the
    HOME Menu does; the speed is adjustable because the exact rate isn't known
  * nodes named 'name' / 'nameModel' billboarded (YAxial) to face the screen,
    the mode the patched pycgfx gives those bones
It's rendered from the .glb (the source of the .cgfx), not from the .cgfx itself.
"""

import math
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageChops, ImageDraw, ImageTk

import home_bg
import platform_util as pu
import preview
import theme

SCREEN = (400, 240)  # 3DS top screen
SCALE = 3  # each 3DS pixel = 2x2 lit centre + 1-pixel gap
DISPLAY = (SCREEN[0] * SCALE, SCREEN[1] * SCALE)
DEFAULT_SPEED = 45.0  # degrees per second ("medium"); adjustable in the window
FRAME_MS = 33  # ~30 fps target
# The pixel grid is only a hint, the same over the whole screen (background, banner
# model and name/nameModel logo): pixel centres keep their exact colours and the gaps
# are barely darker, so no detail is lost - status bar text and icons, the faint
# app-grid tiles, and the model's textures and logo.
GRID_GAP = 0.94  # brightness of the gaps between pixels


def _grid_mask(gap):
    """Multiply mask at DISPLAY size: 255 on pixel centres, `gap` (0-1) on the last
    row/column of every 3DS pixel."""
    g = int(255 * gap)
    cell = Image.new("L", (SCALE, SCALE), 255)
    d = ImageDraw.Draw(cell)
    d.line((SCALE - 1, 0, SCALE - 1, SCALE), fill=g)
    d.line((0, SCALE - 1, SCALE, SCALE - 1), fill=g)
    row = Image.new("L", (DISPLAY[0], SCALE))
    for x in range(0, DISPLAY[0], SCALE):
        row.paste(cell, (x, 0))
    mask = Image.new("L", DISPLAY)
    for y in range(0, DISPLAY[1], SCALE):
        mask.paste(row, (0, y))
    return Image.merge("RGB", (mask, mask, mask))


def pixel_grid():
    return _grid_mask(GRID_GAP)


def to_screen(frame, grid):
    """400x240 frame -> DISPLAY image with the pixel grid."""
    return ImageChops.multiply(frame.resize(DISPLAY, Image.NEAREST), grid)


class HomeMenuPreview:
    def __init__(self, master, mesh, title, audio_path=None):
        self.win = tk.Toplevel(master)
        theme.decorate(self.win)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.background = home_bg.load()  # native 400x240 HOME Menu top screen
        self.grid = pixel_grid()
        self.speed = tk.DoubleVar(value=DEFAULT_SPEED)
        self.angle = 0.0
        self.running = True
        self.closed = False
        self.player = pu.AudioPlayer()
        self._last = time.perf_counter()
        self._fps = []
        self._photo = None
        self.audio_path = audio_path

        outer = ttk.Frame(self.win, padding=10)
        outer.pack(fill="both", expand=True)
        self.screen = tk.Label(outer, bd=1, relief="solid", bg=theme.current.screen_border)
        self.screen.pack()

        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(8, 0))
        self.pause_btn = ttk.Button(row, text="❚❚ Pause", width=10, command=self.toggle_pause)
        self.pause_btn.pack(side="left")
        ttk.Button(row, text="Reset spin", command=self.reset).pack(side="left", padx=(6, 0))
        ttk.Label(row, text="Spin speed").pack(side="left", padx=(16, 4))
        ttk.Scale(row, from_=-180, to=180, variable=self.speed, length=220,
                  command=lambda _v: self._update_speed_label()).pack(side="left")
        self.speed_label = ttk.Label(row, width=26)
        self.speed_label.pack(side="left", padx=(6, 0))
        self.sound_btn = ttk.Button(row, text="🔊 Play banner sound", command=self.play_sound)
        self.sound_btn.pack(side="right")

        self.info = ttk.Label(outer, foreground=theme.current.caption_fg, justify="left", wraplength=1180)
        self.info.pack(anchor="w", pady=(8, 0))
        ttk.Label(outer, foreground=theme.current.hint_fg, wraplength=1180, justify="left",
                  text="Approximation rendered from the .glb: HOME Menu banner camera, worldModel spin "
                       "and name/nameModel billboard. The console's exact spin speed, lighting and "
                       "effects may differ.").pack(anchor="w", pady=(2, 0))

        self.set_mesh(mesh, title, audio_path)
        self._update_speed_label()
        self.win.after(10, self._tick)

    # ------------------------------------------------------------------ public
    def set_mesh(self, mesh, title, audio_path=None):
        self.mesh = mesh
        self.audio_path = audio_path
        self.spin_node = preview.find_spin_node(mesh)
        self.billboards = preview.find_billboard_nodes(mesh)
        self.win.title(f"HOME Menu preview - {title}")
        self.sound_btn.configure(state="normal" if audio_path else "disabled")
        self.angle = 0.0
        self._render_frame()

    def close(self):
        self.closed = True
        self.player.stop()
        self.win.destroy()

    # ------------------------------------------------------------------ controls
    def toggle_pause(self):
        self.running = not self.running
        self.pause_btn.configure(text="❚❚ Pause" if self.running else "▶ Play")
        self._last = time.perf_counter()

    def reset(self):
        self.angle = 0.0
        self._render_frame()

    def play_sound(self):
        if not self.audio_path:
            return
        try:
            self.player.play(self.audio_path)
        except RuntimeError:
            pass

    def _update_speed_label(self):
        v = self.speed.get()
        if abs(v) < 0.5:
            self.speed_label.configure(text="0°/s (stopped)")
        else:
            self.speed_label.configure(text=f"{v:+.0f}°/s ({360 / abs(v):.1f} s per turn)")

    # ------------------------------------------------------------------ animation
    def _tick(self):
        if self.closed:
            return
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        if self.running:
            self.angle = (self.angle + math.radians(self.speed.get()) * dt) % (2 * math.pi)
        t0 = time.perf_counter()
        self._render_frame()
        spent = (time.perf_counter() - t0) * 1000
        self._fps.append(now)
        self._fps = [t for t in self._fps if now - t < 1.0]
        # On a slow machine a frame can take longer than FRAME_MS. Then wait as long as
        # the frame took, so the window keeps at least half the time for clicks and redraws.
        delay = max(1, int(FRAME_MS - spent)) if spent < FRAME_MS else int(spent)
        self.win.after(delay, self._tick)

    def _render_frame(self):
        posed = preview.pose(self.mesh, self.angle, self.spin_node, self.billboards)
        native = preview.render(posed, size=SCREEN, ss=1, background=self.background)
        frame = to_screen(native, self.grid)
        self.last_frame = frame
        self._photo = ImageTk.PhotoImage(frame)
        self.screen.configure(image=self._photo)
        names = self.mesh.node_names
        spin = f"Spinning: {names[self.spin_node]}" if self.spin_node is not None else \
            "No 'worldModel' or 'world' node - nothing spins"
        bill = ("Billboard: " + ", ".join(names[i] for i in self.billboards)) if self.billboards else \
            "No 'name'/'nameModel' node - no billboard logo"
        fps = f"{len(self._fps)} fps" if self._fps else ""
        self.info.configure(text=" · ".join(x for x in (spin, bill, f"{self.mesh.triangle_count} triangles", fps) if x))
