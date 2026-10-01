"""'Edit existing CIA' mode of the main window - change the icon, titles, banner or
sound of an unencrypted CIA (see cia_edit.py).

yanbf_cbc.py calls install(app). That adds a mode switch above the form:
  New forwarder | Edit existing CIA
In edit mode the build form and its preview panel are hidden and this page takes
their place, with its own previews on the right. The button bar, status and log stay:
Build CIA becomes Save edited CIA, and Open output folder / Send to 3DS… use the
edited CIA. Files dropped on the window go to the editor. Nothing in the shared code
changes - the page only hides, shows and re-wires the main window's own widgets.
"""

import atexit
import os
import queue
import shutil
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

import cia_edit as ce
import paths
import pipeline as pl
import platform_util as pu
import preview
import theme

MODE_NEW, MODE_EDIT = "new", "edit"
CELL = (190, 114)  # one Now / New preview
BANNER = CELL
ICON_CELL = (190, 96)
SOUND = (190, 48)


def short_title(info):
    return info.titles[0]


class EditPage:
    def __init__(self, app):
        self.app = app
        self.mode = tk.StringVar(value=MODE_NEW)
        self.q = queue.Queue()
        self.worker = None
        self.info = None
        self.saved = None
        self._photos = {}
        self._preview_keys = {}
        self._hidden = []  # form widgets hidden in edit mode: (widget, grid info)

        outer = app.form
        self.body = outer.master
        self.bar = app.build_btn.master
        self.bar_row = int(self.bar.grid_info()["row"])
        self.side = next(w for w in self.body.grid_slaves(column=1))  # the build previews

        # the mode switch, above everything
        self.modebar = ttk.Frame(app.root, padding=(10, 8, 10, 0))
        self.modebar.pack(fill="x", before=self.body)
        for value, text in ((MODE_NEW, "New forwarder"), (MODE_EDIT, "Edit existing CIA")):
            ttk.Radiobutton(self.modebar, text=text, value=value, variable=self.mode, style="Toolbutton",
                            command=self._switch).pack(side="left", padx=(0, 4))
        ttk.Separator(app.root).pack(fill="x", before=self.body, padx=10, pady=(6, 0))

        # the page: the form on the left, previews on the right
        self.frame = ttk.Frame(outer)
        self.frame.columnconfigure(0, weight=1)
        self._build_form(ttk.Frame(self.frame))
        self._build_previews(ttk.Frame(self.frame, padding=(16, 0, 0, 0)))

        # the button bar: a Save button in Build's place; Open output folder and Send to 3DS… follow the mode
        self.save_btn = ttk.Button(self.bar, text="Save edited CIA", style="Accent.TButton", command=self.save)
        for child in self.bar.pack_slaves():
            text = str(child.cget("text")) if isinstance(child, ttk.Button) else ""
            if text == "Open output folder":
                self.open_btn = child
                child.configure(command=self.open_output)
            elif text == "Send to 3DS…":
                child.configure(command=self.send)

        # while editing, drops go to the editor and the status shows the editor's state
        self._app_validate, self._app_drop = app.validate, app.handle_drop
        app.validate = self._validate_app
        app.handle_drop = self._drop
        self._poll_id = app.root.after(50, self._poll)
        app.root.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event):
        """The program is closing: stop the timer and any sound."""
        if event.widget is not self.app.root:
            return
        try:
            self.app.root.after_cancel(self._poll_id)
        except tk.TclError:
            pass
        self._play_token += 1  # (the buttons are already gone - just stop the sound)
        if self._playing:
            self.player.stop()
        self._playing = None

    # ------------------------------------------------------------------ building the page
    def _entry(self, parent, var, width):
        e = tk.Entry(parent, textvariable=var, width=width, bg=theme.current.field_bg, **theme.current.entry_opts)
        self.app._reg(e, "entry")
        return e

    def _cap(self, parent, text, wrap=560):
        return self.app._reg(ttk.Label(parent, text=text, wraplength=wrap, justify="left",
                                       foreground=theme.current.caption_fg), "caption")

    def _build_form(self, f):
        f.grid(row=0, column=0, sticky="nsew")
        base = tkfont.nametofont("TkDefaultFont").actual()
        bold = (base["family"], base["size"], "bold")
        self._cap(f, "Change the icon, titles, banner or sound of a CIA you already have. Works on unencrypted "
                     "CIAs - forwarders (from this program or others) and most homebrew. The edited copy keeps "
                     "the Title ID and goes up one version, so it installs over the original as an update. "
                     "The original file isn't changed."
                  ).pack(anchor="w")

        self.vars = {k: tk.StringVar() for k in ("cia", "icon", "short", "long", "pub", "banner", "wav")}
        self.on = {k: tk.BooleanVar(value=False) for k in ("icon", "titles", "banner", "wav")}
        self.banner_mode = tk.StringVar(value=pl.MODE_GLB)

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="CIA", width=8).pack(side="left")
        self.cia_entry = self._entry(row, self.vars["cia"], 60)
        self.cia_entry.pack(side="left", fill="x", expand=True, ipady=2)
        ttk.Button(row, text="Browse…", command=self.pick_cia).pack(side="left", padx=(6, 0))

        cur = ttk.Frame(f)
        cur.pack(fill="x", pady=(10, 0))
        self.info_label = ttk.Label(cur, text="Open a CIA to see what it has now.", justify="left")
        self.info_label.pack(side="left", anchor="n")

        ttk.Separator(f).pack(fill="x", pady=(10, 6))
        ttk.Label(f, text="Change (tick what to replace)", font=bold).pack(anchor="w")
        grid = ttk.Frame(f)
        grid.pack(fill="x", pady=(4, 0))
        grid.columnconfigure(2, weight=1)
        self.entries = {}
        r = 0

        def pick_row(key, label, types):
            nonlocal r
            ttk.Checkbutton(grid, text=label, variable=self.on[key], command=self.validate).grid(
                row=r, column=0, sticky="w", pady=2)
            self.entries[key] = e = self._entry(grid, self.vars[key], 52)
            e.grid(row=r, column=2, sticky="ew", pady=2, ipady=2)
            ttk.Button(grid, text="Browse…", command=lambda: self.pick(key, types)).grid(
                row=r, column=3, padx=(6, 0), pady=2)
            r += 1

        pick_row("icon", "Icon picture", [("PNG image (48×48)", "*.png")])
        ttk.Checkbutton(grid, text="Titles", variable=self.on["titles"], command=self.validate).grid(
            row=r, column=0, sticky="nw", pady=2)
        tbox = ttk.Frame(grid)
        tbox.grid(row=r, column=2, columnspan=2, sticky="ew", pady=2)
        tbox.columnconfigure(1, weight=1)
        for i, (key, text) in enumerate((("short", "Title"), ("long", "Long title"), ("pub", "Publisher"))):
            ttk.Label(tbox, text=text).grid(row=i, column=0, sticky="w", padx=(0, 6))
            self._entry(tbox, self.vars[key], 40).grid(row=i, column=1, sticky="ew", pady=1, ipady=1)
            self.vars[key].trace_add("write", lambda *a: self._titles_typed())
        r += 1
        ttk.Checkbutton(grid, text="Banner", variable=self.on["banner"], command=self.validate).grid(
            row=r, column=0, sticky="w", pady=2)
        mbox = ttk.Frame(grid)
        mbox.grid(row=r, column=2, columnspan=2, sticky="w")
        for value, text in ((pl.MODE_GLB, "3D model (.glb)"), (pl.MODE_PNG, "Flat image (.png)")):
            ttk.Radiobutton(mbox, text=text, value=value, variable=self.banner_mode, command=self.validate).pack(
                side="left", padx=(0, 12))
        r += 1
        self.entries["banner"] = e = self._entry(grid, self.vars["banner"], 52)
        e.grid(row=r, column=2, sticky="ew", pady=2, ipady=2)
        ttk.Button(grid, text="Browse…", command=self.pick_banner).grid(row=r, column=3, padx=(6, 0), pady=2)
        r += 1
        pick_row("wav", "Sound", [("WAV sound", "*.wav")])
        self._cap(f, "A new banner keeps the CIA's sound unless Sound is ticked too. A new sound on its own keeps "
                     "the CIA's banner.").pack(anchor="w", pady=(4, 0))
        for key in ("icon", "banner", "wav"):
            self.vars[key].trace_add("write", lambda *a, k=key: self._file_picked(k))
        self.problems = ttk.Label(f, text="", wraplength=560, justify="left", foreground=theme.current.status_bad)
        self.problems.pack(anchor="w", pady=(6, 0))

    def _build_previews(self, side):
        side.grid(row=0, column=1, sticky="ns")
        base = tkfont.nametofont("TkDefaultFont").actual()
        small_bold = (base["family"], base["size"], "bold")
        self.cells = {}  # (part, "old" | "new") -> (image label, caption)
        self.play_btns = {}
        for part, title in (("icon", "Icon"), ("banner", "Banner"), ("wav", "Sound")):
            box = ttk.LabelFrame(side, text=title, padding=8)
            box.pack(fill="x", pady=(0, 8))
            for col, which in enumerate(("old", "new")):
                ttk.Label(box, text="Now" if which == "old" else "New", font=small_bold).grid(
                    row=0, column=col, sticky="w", padx=(0 if col == 0 else 10, 0))
                img = tk.Label(box, bd=0, bg=theme.widget_opts("Label")["bg"])
                self.app._reg(img, "image")
                img.grid(row=1, column=col, sticky="nw", padx=(0 if col == 0 else 10, 0), pady=(2, 0))
                cap = self._cap(box, "", CELL[0])
                cap.grid(row=2, column=col, sticky="nw", padx=(0 if col == 0 else 10, 0), pady=(2, 0))
                self.cells[(part, which)] = (img, cap)
                if part == "wav":
                    b = ttk.Button(box, text="▶ Play", width=9, command=lambda w=which: self.toggle_play(w))
                    b.grid(row=3, column=col, sticky="w", padx=(0 if col == 0 else 10, 0), pady=(4, 0))
                    self.play_btns[which] = b
            if part == "banner":  # like the generator's panel: the HOME Menu preview under the banner
                self.home_btn = ttk.Button(box, text="► HOME Menu preview…", command=self.open_home_preview,
                                           state="disabled")
                self.home_btn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.home_win = None
        self._home_key = None
        self.old = {}  # part -> (image, caption) of the CIA as it is now
        self.old_wav = None  # the CIA's sound, decoded to a .wav for the preview and Play
        self._tmp = tempfile.mkdtemp(prefix="cbc-edit-preview-")
        atexit.register(shutil.rmtree, self._tmp, True)
        self.player = pu.AudioPlayer()
        self._playing = None  # "old" | "new" | None
        self._play_token = 0

    # ------------------------------------------------------------------ switching modes
    def editing(self):
        return self.mode.get() == MODE_EDIT

    def _switch(self):
        app = self.app
        if self.editing():
            self._hidden = []
            for w in app.form.grid_slaves():
                if w is not self.frame and int(w.grid_info()["row"]) < self.bar_row:
                    self._hidden.append(w)
                    w.grid_remove()
            self.frame.grid(row=0, column=0, rowspan=self.bar_row, columnspan=3, sticky="nsew")
            self.side.grid_remove()
            app.build_btn.pack_forget()
            self.save_btn.pack(side="left", before=self.open_btn)
            self.validate()
        else:
            self.stop_audio()
            if self._home_open():
                self.home_win.close()
            self.frame.grid_remove()
            for w in self._hidden:
                w.grid()
            self._hidden = []
            self.side.grid()
            self.save_btn.pack_forget()
            app.build_btn.pack(side="left", before=self.open_btn)
            self._app_validate()

    def show_mode(self, mode):
        if self.mode.get() != mode:
            self.mode.set(mode)
            self._switch()

    # ------------------------------------------------------------------ picking
    def pick_cia(self):
        p = filedialog.askopenfilename(parent=self.app.root, title="Choose a CIA",
                                       filetypes=[("3DS CIA", "*.cia"), ("All files", "*.*")],
                                       initialdir=paths.OUTPUT_DIR if os.path.isdir(paths.OUTPUT_DIR) else None)
        if p:
            self.load(p)

    def pick(self, key, types):
        p = filedialog.askopenfilename(parent=self.app.root, title="Choose a file",
                                       filetypes=types + [("All files", "*.*")])
        if p:
            self.vars[key].set(p)

    def pick_banner(self):
        types = [("glTF binary", "*.glb")] if self.banner_mode.get() == pl.MODE_GLB else [("PNG image", "*.png")]
        p = filedialog.askopenfilename(parent=self.app.root, title="Choose a banner",
                                       filetypes=types + [("All files", "*.*")])
        if p:
            self.vars["banner"].set(p)

    def _file_picked(self, key):
        path = self.vars[key].get().strip()
        if key == "banner" and path:
            self.banner_mode.set(pl.MODE_GLB if path.lower().endswith(".glb") else pl.MODE_PNG)
        self.on[key].set(bool(path))
        self.validate()

    def _titles_typed(self):
        if self.info is not None:
            self.on["titles"].set(tuple(self.vars[k].get() for k in ("short", "long", "pub")) != self.info.titles)
        self.validate()

    def load(self, path):
        """Open a CIA and show what it has now."""
        self.vars["cia"].set(path)
        self.saved = None
        try:
            info = ce.read_cia(path)
        except ce.EditError as ex:
            self.info = None
            self.info_label.configure(text=str(ex), foreground=theme.current.status_bad)
            self.app.log("err", f"Can't edit {os.path.basename(path)}: {ex}")
            self.old, self.old_wav = {}, None
            self.validate()
            return
        self.info = None  # (so filling the title boxes doesn't tick Titles)
        for key, text in zip(("short", "long", "pub"), info.titles):
            self.vars[key].set(text)
        self.info = info
        self.on["titles"].set(False)
        short, long_, pub = info.titles
        sound = (f"{info.sound_seconds:.2f} s" if info.sound_seconds else "yes") if info.has_sound else "none"
        self.info_label.configure(foreground="", text=(
            f"Title: {short}\nLong title: {long_}\nPublisher: {pub or '(none)'}\n"
            f"Title ID: {info.title_id}   Product code: {info.product_code}\n"
            f"Version: {ce.version_text(info.version)} (the edited copy will be {ce.version_text(info.version + 1)})\n"
            f"Banner: {len(info.banner) / 1024:.0f} KB   Sound: {sound}"))
        self.app.log("info", f"Opened {path} to edit (Title ID {info.title_id})")
        self._load_old(info)
        self.validate()

    # ------------------------------------------------------------------ previews
    def _fit(self, im, size):
        """An image scaled down to fit size, centred on the preview background."""
        im = im.convert("RGBA")
        im.thumbnail(size)
        out = Image.new("RGBA", size, theme.current.img_panel_bg + (255,))
        out.alpha_composite(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
        return out

    def _load_old(self, info):
        """What the CIA has now: its icon, its banner (the file it was built from if this
        program built it, else the picture of a flat banner, else a note), its sound."""
        self.stop_audio()
        self.old = {"icon": (ce.smdh_icon(info.icon).resize((96, 96), 0), f"{short_title(info)}")}
        src = ce.banner_source(info.path)
        if src and src[0] == pl.MODE_PNG:
            im, _ = preview.banner_image_preview(src[1], BANNER)
            self.old["banner"] = (im, "Flat image (the file it was built from)")
        elif src:
            self.old["banner"] = (preview.placeholder(BANNER, "Rendering…"), "")
            threading.Thread(target=self._render_glb, args=(("old", info.path), src[1],
                             "3D model (the file it was built from)"), daemon=True).start()
        else:
            try:
                tex = ce.banner_texture(info.banner)
            except ce.EditError:
                tex = None
            if tex is not None and tex.size == (256, 128):
                self.old["banner"] = (self._fit(tex, BANNER), "Flat image (read from the CIA)")
            else:
                self.old["banner"] = (preview.placeholder(BANNER, "3D banner"),
                                      "A 3D banner. It can't be drawn from the CIA alone.")
        self.old_wav = None
        cwav = ce.banner_cwav(info.banner)
        if cwav is None:
            self.old["wav"] = (preview.placeholder(SOUND, "No sound"), "")
        else:
            try:
                self.old_wav = os.path.join(self._tmp, f"now-{len(os.listdir(self._tmp))}.wav")
                with open(self.old_wav, "wb") as f:
                    f.write(ce.cwav_to_wav(cwav))
                im, winfo = preview.wav_preview(self.old_wav, SOUND)
                self.old["wav"] = (im, winfo.describe())
            except Exception:
                self.old_wav = None
                self.old["wav"] = (preview.placeholder(SOUND, "Can't read the sound"), "")
        self._preview_keys.clear()

    def _update_previews(self):
        job = self.job()
        if self.info is None:
            for part, size in (("icon", ICON_CELL), ("banner", BANNER), ("wav", SOUND)):
                for which in ("old", "new"):
                    self._cell(part, which, ("none",), preview.placeholder(size, "Open a CIA"), "")
            self._set_play_state()
            self.home_btn.configure(state="disabled")
            return
        for part in ("icon", "banner", "wav"):
            self._cell(part, "old", ("old", self.info.path, id(self.old.get(part))), *self.old[part])
        # new icon
        if job.icon_png and not pl.check_input_file(pl.KIND_ICON, job.icon_png):
            with Image.open(job.icon_png) as im:
                self._cell("icon", "new", ("new", job.icon_png), im.convert("RGBA").resize((96, 96), 0),
                           "(new picture)")
        else:
            im, text = self.old["icon"]
            self._cell("icon", "new", ("same", self.info.path), im, "unchanged")
        # new banner
        kind = pl.KIND_GLB if job.banner_mode == pl.MODE_GLB else pl.KIND_BANNER_PNG
        if job.banner_mode and not pl.check_input_file(kind, job.banner_path):
            key = ("new", job.banner_mode, job.banner_path)
            if job.banner_mode == pl.MODE_PNG:
                im, _ = preview.banner_image_preview(job.banner_path, BANNER)
                self._cell("banner", "new", key, im, "Flat image")
            elif self._keys().get(("banner", "new")) != key:
                self._cell("banner", "new", key, preview.placeholder(BANNER, "Rendering…"), "")
                threading.Thread(target=self._render_glb, args=(key, job.banner_path, "3D model"), daemon=True).start()
        else:
            im, text = self.old["banner"]
            self._cell("banner", "new", ("same", self.info.path, id(self.old["banner"])), im, "unchanged")
        # new sound
        if job.wav_path and not pl.check_input_file(pl.KIND_AUDIO, job.wav_path):
            try:
                im, winfo = preview.wav_preview(job.wav_path, SOUND)
                self._cell("wav", "new", ("new", job.wav_path), im, winfo.describe())
            except Exception:
                self._cell("wav", "new", ("new", job.wav_path), preview.placeholder(SOUND, "Can't read this sound"), "")
        else:
            im, text = self.old["wav"]
            self._cell("wav", "new", ("same", self.info.path, id(self.old["wav"])), im,
                       "unchanged" if self.old_wav else text)
        self._set_play_state()
        self.home_btn.configure(state="normal")
        if self._home_open() and self._home_sources_key() != self._home_key:
            self.open_home_preview()  # keep an open HOME Menu preview up to date

    def _keys(self):
        return self._preview_keys

    def _cell(self, part, which, key, image, text):
        """Show an image + caption in a Now / New cell (only if it changed)."""
        if self._preview_keys.get((part, which)) == key:
            return
        self._preview_keys[(part, which)] = key
        img, cap = self.cells[(part, which)]
        if part == "icon":
            image = self._fit(image, ICON_CELL)
        self._photos[(part, which)] = ImageTk.PhotoImage(image)
        img.configure(image=self._photos[(part, which)])
        cap.configure(text=text)

    def _render_glb(self, key, path, text):
        try:
            mesh = preview.load_glb(path)
            posed = preview.pose(mesh, 0.0, preview.find_spin_node(mesh), preview.find_billboard_nodes(mesh))
            self.q.put(("render", (key, preview.render(posed, size=BANNER, ss=2), text)))
        except Exception:
            self.q.put(("render", (key, preview.placeholder(BANNER, "Can't preview this model"), "")))

    def _on_render(self, key, image, text):
        if key[0] == "old":
            if self.info is not None and key[1] == self.info.path:
                self.old["banner"] = (image, text)
                self._update_previews()
        elif self._preview_keys.get(("banner", "new")) == key:
            self._preview_keys.pop(("banner", "new"), None)
            self._cell("banner", "new", key, image, text)

    # -- the HOME Menu preview: now vs new, side by side
    def _home_open(self):
        return self.home_win is not None and not self.home_win.closed

    def _home_sources_key(self):
        job = self.job()
        kind = pl.KIND_GLB if job.banner_mode == pl.MODE_GLB else pl.KIND_BANNER_PNG
        new_banner = (job.banner_mode, job.banner_path) if job.banner_mode and not pl.check_input_file(
            kind, job.banner_path) else None
        return (self.info.path if self.info else None, new_banner, self._sound_path("new"))

    def _old_side(self):
        """What the CIA's banner is now, for the HOME Menu preview."""
        import cia_home_compare as hc
        info = self.info
        src = ce.banner_source(info.path)
        if src and src[0] == pl.MODE_GLB:
            return hc.Side("glb", preview.load_glb(src[1]), "3D model (the file it was built from)", self.old_wav)
        if src:
            with Image.open(src[1]) as im:
                return hc.Side("flat", im.copy(), "Flat image (the file it was built from)", self.old_wav)
        try:
            tex = ce.banner_texture(info.banner)
        except ce.EditError:
            tex = None
        if tex is not None and tex.size == (256, 128):
            return hc.Side("flat", tex, "Flat image (read from the CIA)", self.old_wav)
        return hc.Side("none", None, "A 3D banner - it can't be drawn from the CIA alone", self.old_wav)

    def open_home_preview(self):
        """Open (or update) the side-by-side HOME Menu preview."""
        if self.info is None:
            return
        import cia_home_compare as hc
        key = self._home_sources_key()
        try:
            old = self._old_side()
            new_banner, new_sound = key[1], key[2]
            if new_banner is None:
                new = hc.Side(old.kind, old.mesh if old.kind == "glb" else old.value, "unchanged", new_sound)
            elif new_banner[0] == pl.MODE_GLB:
                new = hc.Side("glb", preview.load_glb(new_banner[1]), "3D model", new_sound)
            else:
                with Image.open(new_banner[1]) as im:
                    new = hc.Side("flat", im.copy(), "Flat image", new_sound)
        except Exception as ex:
            self.app.log("err", f"Couldn't open the HOME Menu preview: {ex}")
            return
        self._home_key = key
        title = os.path.basename(self.info.path)
        if self._home_open():
            self.home_win.set_sides(old, new, title)
            self.home_win.win.lift()
        else:
            self.home_win = hc.CompareWindow(self.app.root, old, new, title)

    # -- playing the sounds
    def _sound_path(self, which):
        if which == "new":
            job = self.job()
            if job.wav_path and not pl.check_input_file(pl.KIND_AUDIO, job.wav_path):
                return job.wav_path
        return self.old_wav

    def _set_play_state(self):
        for which, b in self.play_btns.items():
            b.configure(state="normal" if self._sound_path(which) else "disabled",
                        text="■ Stop" if self._playing == which else "▶ Play")

    def toggle_play(self, which):
        if self._playing == which:
            self.stop_audio()
            return
        path = self._sound_path(which)
        if not path:
            return
        try:
            self.player.play(path)
        except RuntimeError as ex:
            self.app.log("err", f"Can't play the sound: {ex}")
            return
        self._play_token += 1
        token, self._playing = self._play_token, which
        self._set_play_state()
        if self.player.playing() is None:  # winsound: time the clip
            try:
                import wave
                with wave.open(path) as w:
                    ms = int(w.getnframes() / w.getframerate() * 1000) + 250
            except Exception:
                ms = 3000
            self.app.root.after(ms, lambda: self._play_ended(token))
        else:
            self.app.root.after(200, lambda: self._watch_play(token))

    def _watch_play(self, token):
        if token != self._play_token:
            return
        if self.player.playing():
            self.app.root.after(200, lambda: self._watch_play(token))
        else:
            self._play_ended(token)

    def _play_ended(self, token):
        if token == self._play_token:
            self._playing = None
            self._set_play_state()

    def stop_audio(self):
        self._play_token += 1
        if self._playing:
            self.player.stop()
        self._playing = None
        if getattr(self, "play_btns", None):
            self._set_play_state()

    # ------------------------------------------------------------------ checks + saving
    def job(self):
        v, on = self.vars, self.on
        return ce.EditJob(cia_path=v["cia"].get().strip(),
                          icon_png=v["icon"].get().strip() if on["icon"].get() else "",
                          titles=(v["short"].get(), v["long"].get(), v["pub"].get()) if on["titles"].get() else None,
                          banner_mode=self.banner_mode.get() if on["banner"].get() else "",
                          banner_path=v["banner"].get().strip() if on["banner"].get() else "",
                          wav_path=v["wav"].get().strip() if on["wav"].get() else "")

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def validate(self):
        """The editor's own checks. Returns the problems (empty = ready to save)."""
        problems = ce.validate(self.job()) if self.info else ["Open a CIA to edit"]
        self.problems.configure(text="\n".join(p for p in problems if p != "Open a CIA to edit"))
        self.save_btn.configure(state="normal" if not problems and not self.busy() else "disabled")
        if self.editing() and not self.busy():
            if problems:
                self.app._set_status("Needs: " + problems[0].rstrip("."), theme.current.status_bad)
            else:
                self.app._set_status("Ready to save", theme.current.status_ok)
        self._update_previews()
        return problems

    def _validate_app(self):
        ok = self._app_validate()  # keeps the build form's own state up to date
        if self.editing():
            self.validate()
        return ok

    def save(self):
        if self.validate() or self.busy():
            return
        job = self.job()
        self.save_btn.configure(state="disabled")
        self.app._set_status("Saving…", theme.current.status_busy)
        self.app.log("step", "== Edit an existing CIA ==")
        self.worker = threading.Thread(target=self._work, args=(job,), daemon=True)
        self.worker.start()

    def _work(self, job):
        try:
            self.q.put(("done", ce.run(job, lambda kind, text: self.q.put(("log", (kind, text))))))
        except (ce.EditError, OSError) as ex:
            self.q.put(("error", str(ex)))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    self.app.log(*data)
                elif kind == "render":
                    self._on_render(*data)
                elif kind == "done":
                    self.saved = data
                    self.app.log("done", "EDITED CIA SAVED")
                    self.worker = None
                    self.validate()
                    self.app._set_status("Saved - Send to 3DS… sends the edited CIA", theme.current.status_ok)
                elif kind == "error":
                    self.app.log("fail", "EDIT FAILED")
                    self.app.log("err", data)
                    self.worker = None
                    self.validate()
                    self.app._set_status("Failed - see log", theme.current.status_bad)
        except queue.Empty:
            pass
        self._poll_id = self.app.root.after(50, self._poll)

    # ------------------------------------------------------------------ the shared buttons + drops
    def open_output(self):
        if self.editing() and self.saved:
            pu.open_path(os.path.dirname(self.saved))
        else:
            self.app.open_output()

    def send(self):
        self.app.open_send_window()
        w = self.app.ftp_win
        if self.editing() and self.saved and w is not None:
            w.cia_override = self.saved
            w.refresh_files()

    def _drop(self, paths_, x_root, y_root):
        if not self.editing():
            return self._app_drop(paths_, x_root, y_root)
        for path in paths_:
            name = os.path.basename(path)
            ext = os.path.splitext(name)[1].lower()
            if os.path.isdir(path):
                self.app.log("warn", f"Dropped folder {name} ignored - drop the file itself")
            elif ext == ".cia":
                self.load(path)
            elif ext == ".glb":
                self.vars["banner"].set(path)
            elif ext == ".wav":
                self.vars["wav"].set(path)
            elif ext == ".png":
                is_icon = pl.check_input_file(pl.KIND_ICON, path) is None
                self.vars["icon" if is_icon else "banner"].set(path)
            else:
                self.app.log("warn", f"Not sure where {name} goes - drop a .cia, .png, .glb or .wav")
                continue
            self.app.log("info", f"Dropped {name} → editor")


def install(app):
    app.cia_edit_page = EditPage(app)
    return app.cia_edit_page
