"""YANBF-CBC - YANBF Custom Banner CIA builder (tkinter GUI, entry point)."""

import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import filedialog, messagebox, ttk

# Imported here too so PyInstaller bundles what the disk-loaded pycgfx needs.
import argparse  # noqa: F401
import gltflib  # noqa: F401
from PIL import Image, ImageDraw, ImageTk

import dragdrop
import ftp_window
import home_preview
import nds
import paths
import pipeline as pl
import platform_util as pu
import preview
import pycgfx_setup
import pycgfx_window
import settings
import theme

APP_TITLE = "YANBF-CBC - Custom Banner CIA Builder (unofficial)"


def _load_colors():
    """Colours/fonts of the active theme (App picks Light/Dark/System from settings and
    calls this again whenever the theme changes)."""
    global T, ERR_BG, OK_BG, LOCK_BG, ERR_FG, WARN_FG, WARN_BG, PLACEHOLDER_FG, CAPTION_FG
    global ENTRY_OPTS, SPIN_OPTS
    T = theme.current
    theme.apply_preview(preview)
    ERR_BG = T.err_bg
    OK_BG = T.field_bg
    LOCK_BG = T.lock_bg
    ERR_FG = T.err_fg
    WARN_FG = T.warn_fg
    WARN_BG = T.warn_bg
    PLACEHOLDER_FG = T.placeholder_fg
    CAPTION_FG = T.caption_fg
    ENTRY_OPTS = T.entry_opts
    SPIN_OPTS = T.spin_opts


_load_colors()

CAPTIONS = {
    "nds": "Optional. Fills in the fields below from the ROM header and locks them (press Edit to change one). "
           "The ROM itself is not copied.",
    "icon": "PNG, exactly 48×48 px (the 3DS HOME Menu icon size).",
    pl.MODE_GLB: f".glb file, at most {pl.GLB_LIMIT_TEXT} (the 3DS's limit for the converted banner). "
                 "New to 3D banners? Template… saves a Blender file that's already set up - "
                 "edit it, then export it as .glb.",
    pl.MODE_PNG: "PNG, max 256×128 px (the 3DS flat banner size).",
    "audio": f"PCM .wav, at most {pl.AUDIO_MAX_TEXT} long. Leave empty to use a 1-second silent placeholder.",
}

# Shown in the Credits window (the README says the same).
UNOFFICIAL = ("Unofficial: YANBF-CBC isn't affiliated with, endorsed or supported by any of these "
              "projects or by Nintendo. Please report problems with this app to YANBF-CBC, not to them.")


def bold_default():
    base = tkfont.nametofont("TkDefaultFont").actual()
    return (base["family"], base["size"], "bold")


# Shown in the Credits window (same as the README's Credits section).
CREDITS = [
    {"name": "YANBF - Yet Another nds-Bootstrap Forwarder", "url": "https://github.com/YANBForwarder/YANBF",
     "by": "lifehackerhansol (generator, CIA template), Pk11 / Epicpkmn11 (bannergif.py, testing), "
           "Olmectron (GUI wrapper). YANBF thanks devkitPro and RocketRobz, and launches nds-bootstrap.",
     "what": "The forwarder itself (forwarder.elf, build-cia.rsf, the generator this app follows).",
     "license": "GPL-2.0 (bootstrap, © 2010 Dave \"WinterMute\" Murphy) / MIT (the rest)"},
    {"name": "pycgfx", "url": "https://github.com/skyfloogle/pycgfx",
     "by": "skyfloogle",
     "what": "Converts .glb models to the CGFX banner format; its banner camera drives the previews. "
             "The copy used here is patched (see PATCH_NOTES.txt); the patches aren't upstream.",
     "license": "no license shown on GitHub - see the repository"},
    {"name": "bannertool", "url": "https://github.com/Epicpkmn11/bannertool",
     "by": "Epicpkmn11 (maintainer; fork of Mtgxyz/bannertool), originally by Steveice10",
     "what": "Builds the HOME Menu icon (makesmdh) and the banner (makebanner).",
     "license": "MIT"},
    {"name": "cwavtool", "url": "https://github.com/PabloMK7/cwavtool",
     "by": "PabloMK7 (based on Steveice10's bannertool; uses David Bryant's adpcm-xq and "
           "Jack Andersen's gc-dspadpcm-encode)",
     "what": "Converts the banner audio (.wav) to CWAV.",
     "license": "MIT (per its README)"},
    {"name": "Project_CTR", "url": "https://github.com/3DSGuy/Project_CTR",
     "by": "3DSGuy (forked from bkifft/Project_CTR)",
     "what": "makerom builds the .cia; ctrtool is included for checking finished CIAs.",
     "license": "no license shown on GitHub - see the repository"},
    {"name": "tkinterdnd2 + tkdnd (Mac version only)", "url": "https://github.com/Eliav2/tkinterdnd2",
     "by": "Eliav2 and pmgagne (tkinterdnd2); Georgios Petasis (tkdnd)",
     "what": "Drag and drop from Finder in the macOS app. The Windows version doesn't use them.",
     "license": "MIT (tkinterdnd2) / BSD-style (tkdnd)"},
]

# Fields that a .nds can fill in: key -> (label, check(value) -> error or None)
LOCKABLE = {
    "rom": ("ROM path", lambda v: None),
    "title": ("Title", lambda v: None if v.strip() else "Title is required"),
    "publisher": ("Publisher", lambda v: None),
    "product": ("Product Code", lambda v: None if v.strip() else "Product Code is required"),
    "uid": ("Unique ID", lambda v: pl.parse_unique_id(v)[1]),
    "minor": ("Version", lambda v: pl.parse_minor(v)[1]),
}


class App:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.worker = None
        self.last_out_dir = None
        self.last_cia = None  # .cia from this session's last successful build
        self.ftp_win = None  # Send to 3DS window
        self.pycgfx_win = None  # Set up pycgfx window
        self.loaded_nds = None  # normalized path of the .nds the fields were filled from
        self.locks = {}  # key -> {"widget", "var", "button", "state": free|locked|editing}
        # previews
        self._photos = {}  # keep PhotoImage references alive
        self._preview_keys = {}  # what each preview currently shows
        self.glb_mesh = None  # posed at rest (billboards applied), for the panel preview
        self.glb_raw = None  # as loaded, for the HOME Menu preview
        self.home_win = None
        self._glb_key = None
        self.view = {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0}
        self._drag_from = None
        self._drag_pending = False
        self._fast_ok = True
        self._render_gen = 0
        self._audio_path = None
        self._audio_seconds = 0.0
        self._play_token = 0
        self.player = pu.AudioPlayer()
        self.settings = settings.load()
        self._uid_suggestion = None  # (hex, reused) last filled in from a .nds
        self._nds_game_code = None
        root.title(APP_TITLE)
        root.minsize(1120, 720)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        # appearance: System (follow Windows) / Light / Dark, saved in settings.json
        self._styled = []  # (widget, role) using theme colours; restyled when the theme changes
        self._lock_icons = {}  # theme name -> padlock PhotoImage
        self.theme_pref = self.settings["theme"]
        theme.use(theme.resolve(self.theme_pref))
        _load_colors()
        theme.apply(root)
        theme.decorate(root)

        self.nds_var = tk.StringVar()
        self.icon_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=pl.MODE_GLB)
        self.banner_var = tk.StringVar()
        self.audio_var = tk.StringVar()
        self.rom_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.publisher_var = tk.StringVar()
        self.product_var = tk.StringVar()
        self.uid_var = tk.StringVar()
        self.minor_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar()
        self.banner_caption_var = tk.StringVar(value=CAPTIONS[pl.MODE_GLB])

        self._build_ui()

        for v in (self.icon_var, self.banner_var, self.audio_var, self.rom_var, self.title_var,
                  self.publisher_var, self.product_var, self.uid_var, self.minor_var):
            v.trace_add("write", lambda *_: self.validate())
        self.mode_var.trace_add("write", lambda *_: self._on_mode_change())
        self.nds_var.trace_add("write", lambda *_: self._on_nds_change())

        self.missing = self.check_tools()
        self.validate()
        # Tk creates the real top-level window when it's first shown, so register then.
        self.drop_target = None
        root.bind("<Map>", self._enable_drop, add="+")
        self._poll_id = self.root.after(50, self._poll_queue)
        self._theme_watch_id = self.root.after(2000, self._watch_system_theme)

    def _enable_drop(self, event):
        if event.widget is not self.root or self.drop_target is not None:
            return
        # queue the drop: the callback runs inside a window procedure, not the Tk loop
        self.drop_target = dragdrop.FileDropTarget(
            self.root, lambda p, x, y: self.queue.put(("__drop__", (p, x, y))))
        if self.drop_target.enabled:
            self.log("info", f"Tip: drag files from {pu.file_manager()} onto the ROM, icon, banner or audio rows "
                             "(or their previews), or drop several at once anywhere in the window.")
        elif not pu.is_windows():
            self.log("info", "Drag and drop isn't available on this Mac (Intel Macs, or no tkinterdnd2) - "
                             "use the Browse buttons.")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        outer = ttk.Frame(body, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(1, weight=1)
        self._build_preview_panel(body)
        self.form = outer
        r = 0

        def label(text, row):
            ttk.Label(outer, text=text).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=(4, 0))

        def caption(row, text=None, textvariable=None):
            lbl = ttk.Label(outer, text=text, textvariable=textvariable, foreground=CAPTION_FG,
                            wraplength=560, justify="left")
            lbl.grid(row=row, column=1, sticky="w")
            return self._reg(lbl, "caption")

        def error_label(row):
            lbl = tk.Label(outer, text="", fg=ERR_FG, anchor="w", justify="left")
            lbl.grid(row=row, column=1, columnspan=2, sticky="w")
            return self._reg(lbl, "error")

        def entry(row, var, width=60, sticky="ew"):
            e = tk.Entry(outer, textvariable=var, width=width, bg=OK_BG, readonlybackground=LOCK_BG,
                         **ENTRY_OPTS)
            e.grid(row=row, column=1, sticky=sticky, pady=(4, 0), ipady=2)
            return self._reg(e, "entry")

        def button(row, text, command):
            b = ttk.Button(outer, text=text, width=9, command=command)
            b.grid(row=row, column=2, padx=(6, 0), pady=(4, 0), sticky="w")
            return b

        # 0. NDS ROM
        label("NDS ROM (.nds)", r)
        self.nds_entry = entry(r, self.nds_var)
        button(r, "Browse…", self._pick_nds)
        r += 1
        caption(r, CAPTIONS["nds"])
        self.nds_clear_btn = button(r, "Clear", lambda: self.nds_var.set(""))
        self.nds_clear_btn.grid_configure(pady=(2, 0), sticky="nw")
        r += 1
        self.nds_err = error_label(r); r += 1
        self.zone_rows = {"nds": range(0, r)}  # form rows that accept a dropped file, per field
        ttk.Separator(outer).grid(row=r, column=0, columnspan=3, sticky="ew", pady=(2, 6)); r += 1

        # 1. icon
        start = r
        label("Icon image (.png)", r)
        self.icon_entry = entry(r, self.icon_var)
        button(r, "Browse…", self._pick_icon)
        r += 1
        caption(r, CAPTIONS["icon"]); r += 1
        self.icon_err = error_label(r); r += 1
        self.zone_rows["icon"] = range(start, r)

        # 2. banner
        start = r
        label("Banner source", r)
        radios = ttk.Frame(outer)
        radios.grid(row=r, column=1, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Radiobutton(radios, text="3D Model (.glb)", value=pl.MODE_GLB, variable=self.mode_var).pack(side="left")
        ttk.Radiobutton(radios, text="Flat Image (.png)", value=pl.MODE_PNG,
                        variable=self.mode_var).pack(side="left", padx=(12, 0))
        r += 1
        self.banner_entry = entry(r, self.banner_var)
        button(r, "Browse…", self._pick_banner)
        r += 1
        caption(r, textvariable=self.banner_caption_var)
        # ready-made Blender file for 3D banners (3D Model mode only, see _on_mode_change)
        self.template_btn = button(r, "Template…", self.save_banner_template)
        self.template_btn.configure(width=10)  # "Template…" is a character longer than "Browse…"
        self.template_btn.grid_configure(pady=(2, 0), sticky="nw")
        r += 1
        self.banner_err = error_label(r); r += 1
        self.zone_rows["banner"] = range(start, r)

        # 3. audio
        start = r
        label("Audio (.wav)", r)
        self.audio_entry = entry(r, self.audio_var)
        button(r, "Browse…", self._pick_audio)
        r += 1
        caption(r, CAPTIONS["audio"]); r += 1
        self.audio_err = error_label(r); r += 1
        self.zone_rows["audio"] = range(start, r)

        # 4. ROM path
        label("ROM path on SD card", r)
        self.rom_entry = entry(r, self.rom_var)
        self._add_lock("rom", self.rom_entry, self.rom_var, r)
        r += 1
        caption(r, "e.g. /roms/nds/Some Game.nds (written to romfs/path.txt as sd:/…)"); r += 1

        # 5. title / publisher
        label("Title", r)
        self.title_entry = entry(r, self.title_var)
        self._add_lock("title", self.title_entry, self.title_var, r)
        r += 1
        label("Publisher", r)
        self.publisher_entry = entry(r, self.publisher_var)
        self._add_lock("publisher", self.publisher_entry, self.publisher_var, r)
        r += 1

        # 6. product code / unique id
        label("Product Code", r)
        self.product_entry = entry(r, self.product_var, width=24, sticky="w")
        self._add_lock("product", self.product_entry, self.product_var, r)
        r += 1
        caption(r, "e.g. CTR-H-TEST (from a .nds: CTR-H- + the game code)"); r += 1
        label("Unique ID (hex)", r)
        uid_row = ttk.Frame(outer)  # the box with its Options… button right beside it
        uid_row.grid(row=r, column=1, sticky="w", pady=(4, 0))
        self.uid_entry = self._reg(tk.Entry(uid_row, textvariable=self.uid_var, width=24, bg=OK_BG,
                                            readonlybackground=LOCK_BG, **ENTRY_OPTS), "entry")
        self.uid_entry.pack(side="left", ipady=2)
        self.id_options_btn = ttk.Button(uid_row, text="Options…", command=self.open_id_options)
        self.id_options_btn.pack(side="left", padx=(6, 0))
        # grey preview of the next free ID, drawn over the box while it's empty (not a value)
        self.uid_placeholder = self._reg(tk.Label(uid_row, text="", fg=PLACEHOLDER_FG, bg=OK_BG, bd=0,
                                                  cursor="xterm"), "placeholder")
        self.uid_placeholder.bind("<Button-1>", lambda e: self.uid_entry.focus_set())
        self._placeholder_key = None
        self._add_lock("uid", self.uid_entry, self.uid_var, r)
        r += 1
        self.uid_caption_var = tk.StringVar(value=self._uid_caption())
        caption(r, textvariable=self.uid_caption_var)
        r += 1
        self.uid_err = error_label(r); r += 1

        # 7. version
        label("Version (minor)", r)
        self.minor_spin = self._reg(tk.Spinbox(outer, from_=0, to=pl.MINOR_MAX, textvariable=self.minor_var,
                                               width=6, bg=OK_BG, readonlybackground=LOCK_BG,
                                               disabledbackground=LOCK_BG, **SPIN_OPTS), "spin")
        self.minor_spin.grid(row=r, column=1, sticky="w", pady=(4, 0), ipady=2)
        self._add_lock("minor", self.minor_spin, self.minor_var, r)
        r += 1
        self.minor_err = error_label(r); r += 1

        # 8. buttons + status
        bar = ttk.Frame(outer)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        self.build_btn = ttk.Button(bar, text="Build CIA", command=self.start_build, style="Accent.TButton")
        self.build_btn.pack(side="left")
        ttk.Button(bar, text="Open output folder", command=self.open_output).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Send to 3DS…", command=self.open_send_window).pack(side="left", padx=(8, 0))
        self.status_label = ttk.Label(bar, textvariable=self.status_var, font=T.font_status)
        # appearance picker (right-hand side of the button bar)
        self.theme_var = tk.StringVar(value=theme.PREF_LABELS[self.theme_pref])
        self.theme_box = self._reg(ttk.Combobox(bar, textvariable=self.theme_var, state="readonly", width=8,
                                                values=[theme.PREF_LABELS[p] for p in theme.PREFS]), "combo")
        self.theme_box.pack(side="right")
        self.theme_box.bind("<<ComboboxSelected>>", self._on_theme_pick)
        ttk.Label(bar, text="Theme").pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="Credits…", command=self.open_credits).pack(side="right", padx=(0, 14))
        # packed last, so a long "Needs: …" is what gets cut short, never the buttons
        self.status_label.pack(side="left", padx=(14, 0))
        r += 1

        # 9. log (a ttk scrollbar, so it can follow the light/dark theme)
        box = ttk.Frame(outer)
        box.grid(row=r, column=0, columnspan=3, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.log_text = self._reg(tk.Text(box, height=12, font=T.font_mono, wrap="word", state="disabled",
                                          **T.text_opts), "log")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)
        outer.rowconfigure(r, weight=1)
        for tag, opts in T.log_tags.items():
            self.log_text.tag_configure(tag, **opts)

    def _build_preview_panel(self, parent):
        side = ttk.Frame(parent, padding=(0, 10, 10, 10))
        side.grid(row=0, column=1, sticky="ns")

        def box(title):
            f = ttk.LabelFrame(side, text=title, padding=8)
            f.pack(fill="x", pady=(0, 8))
            return f

        def small(parent, role="caption"):
            fg = T.hint_fg if role == "hint" else CAPTION_FG
            lbl = ttk.Label(parent, foreground=fg, wraplength=300, justify="left")
            lbl.pack(anchor="w", pady=(4, 0))
            return self._reg(lbl, role)

        self.preview_zones = {}  # preview frame -> field a dropped file goes to
        f = box("Icon preview")
        self.preview_zones[f] = "icon"
        self.icon_preview = self._reg(tk.Label(f, bd=0), "image")
        self.icon_preview.pack(anchor="w")
        self.icon_preview_info = small(f)

        f = box("Banner preview")
        self.preview_zones[f] = "banner"
        self.banner_preview = self._reg(tk.Label(f, bd=0, cursor="fleur"), "image")
        self.banner_preview.pack(anchor="w")
        self.banner_preview_info = small(f)
        self.banner_preview_hint = small(f, role="hint")
        self.home_btn = ttk.Button(f, text="▶ HOME Menu preview…", command=self.open_home_preview,
                                   state="disabled")
        self.home_btn.pack(anchor="w", pady=(6, 0))
        b = self.banner_preview
        b.bind("<ButtonPress-1>", self._on_drag_start)
        b.bind("<B1-Motion>", self._on_drag)
        b.bind("<ButtonRelease-1>", lambda e: self._request_final_render())
        b.bind("<Double-Button-1>", lambda e: self._reset_view())
        b.bind("<MouseWheel>", self._on_wheel)

        f = box("Audio preview")
        self.preview_zones[f] = "audio"
        self.audio_preview = self._reg(tk.Label(f, bd=0), "image")
        self.audio_preview.pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(4, 0))
        self.play_btn = ttk.Button(row, text="▶ Play", width=9, command=self._toggle_play, state="disabled")
        self.play_btn.pack(side="left")
        self.audio_preview_info = self._reg(ttk.Label(row, foreground=CAPTION_FG, wraplength=210,
                                                      justify="left"), "caption")
        self.audio_preview_info.pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------ previews
    def _show(self, label, key, pil_image):
        photo = ImageTk.PhotoImage(pil_image)
        self._photos[key] = photo
        label.configure(image=photo)

    @staticmethod
    def _file_key(path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        return (os.path.abspath(path), st.st_mtime_ns, st.st_size) if os.path.isfile(path) else None

    def _update_previews(self):
        # icon
        key = self._file_key(self.icon_var.get().strip())
        if self._preview_keys.get("icon", 0) != key:
            self._preview_keys["icon"] = key
            if key is None:
                img, info = preview.placeholder((170, 100), "No icon selected"), ""
            else:
                img, info = preview.icon_preview(key[0])
            self._show(self.icon_preview, "icon", img)
            self.icon_preview_info.configure(text=info)

        # banner
        mode = self.mode_var.get()
        fkey = self._file_key(self.banner_var.get().strip())
        key = (mode, fkey)
        if self._preview_keys.get("banner", 0) != key:
            self._preview_keys["banner"] = key
            self.glb_mesh = None
            self.glb_raw = None
            self._glb_key = None
            self.home_btn.configure(state="disabled")
            if self._home_open():
                self.home_win.close()
            self._render_gen += 1
            self.banner_preview_hint.configure(text="")
            if fkey is None:
                self._show(self.banner_preview, "banner", preview.placeholder((300, 180), "No banner selected"))
                self.banner_preview_info.configure(text="")
            elif mode == pl.MODE_PNG:
                img, info = preview.banner_image_preview(fkey[0])
                self._show(self.banner_preview, "banner", img)
                self.banner_preview_info.configure(text=info)
            else:
                self._show(self.banner_preview, "banner", preview.placeholder((300, 180), "Loading model…"))
                self.banner_preview_info.configure(text="")
                self._load_glb_async(key, fkey[0])

        # audio
        key = self._file_key(self.audio_var.get().strip())
        if self._preview_keys.get("audio", 0) != key:
            self._preview_keys["audio"] = key
            self._stop_audio()
            self._audio_path = key[0] if key else None
            self._audio_seconds = 0.0
            if key is None:
                img = preview.placeholder((300, 64), "No audio: 1 s of silence will be used")
                info = ""
            else:
                try:
                    img, winfo = preview.wav_preview(key[0])
                    self._audio_seconds = winfo.seconds
                    info = winfo.describe()
                except Exception as ex:
                    img = preview.placeholder((300, 64), "Can't read this WAV")
                    info = f"{type(ex).__name__}: {ex}"
            self._show(self.audio_preview, "audio", img)
            self.audio_preview_info.configure(text=info)
            self.play_btn.configure(state="normal" if key else "disabled")
            if self._home_open():
                self.home_win.audio_path = self._audio_path
                self.home_win.sound_btn.configure(state="normal" if self._audio_path else "disabled")

    # -- .glb
    def _load_glb_async(self, key, path):
        self._glb_key = key
        q = self.queue

        def work():
            try:
                q.put(("__glb__", (key, preview.load_glb(path), None)))
            except Exception as ex:
                q.put(("__glb__", (key, None, f"{type(ex).__name__}: {ex}")))

        threading.Thread(target=work, daemon=True).start()

    def _on_glb_loaded(self, key, mesh, error):
        if key != self._glb_key:
            return  # a different file was picked meanwhile
        if mesh is None:
            self._show(self.banner_preview, "banner", preview.placeholder((300, 180), "Can't preview this model"))
            self.banner_preview_info.configure(text=error)
            return
        self.glb_raw = mesh
        # panel preview shows the rest pose with name/nameModel billboards applied
        self.glb_mesh = preview.pose(mesh, 0.0, preview.find_spin_node(mesh), preview.find_billboard_nodes(mesh))
        self.home_btn.configure(state="normal")
        self.view = {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0}
        self._fast_ok = True
        self.banner_preview_hint.configure(text="Drag to rotate · wheel to zoom · double-click to reset")
        self._request_final_render()

    def _glb_info(self):
        m = self.glb_mesh
        v = self.view
        parts = [f"{m.triangle_count} triangles"]
        if v["yaw"] or v["pitch"] or v["zoom"] != 1.0:
            view = "rotated" if v["yaw"] or v["pitch"] else "HOME Menu camera"
            if v["zoom"] != 1.0:
                view += f", zoomed {v['zoom']:.2g}× (not the real size)"
            parts.append(view)
        else:
            parts.append("HOME Menu banner camera")
        text = " · ".join(parts)
        if m.warnings:
            text += "\n(" + ", ".join(m.warnings) + ")"
        return text

    def _render_kwargs(self):
        v = self.view
        return {"yaw": v["yaw"], "pitch": v["pitch"], "zoom": v["zoom"]}

    def _request_final_render(self):
        """Full-quality render on a worker thread; only the latest request is shown."""
        if self.glb_mesh is None:
            return
        self._render_gen += 1
        gen, mesh, kw, q = self._render_gen, self.glb_mesh, self._render_kwargs(), self.queue

        def work():
            try:
                img = preview.render(mesh, size=(300, 180), ss=2, **kw)
            except Exception as ex:
                img = preview.placeholder((300, 180), f"Render failed: {type(ex).__name__}")
            q.put(("__render__", (gen, img)))

        threading.Thread(target=work, daemon=True).start()
        self.banner_preview_info.configure(text=self._glb_info())

    def _on_render_done(self, gen, img):
        if gen == self._render_gen:
            self._show(self.banner_preview, "banner", img)

    def _fast_render(self):
        """Half-resolution render on the UI thread while dragging (skipped for slow models)."""
        self._drag_pending = False
        if self.glb_mesh is None or not self._fast_ok:
            return
        t = time.perf_counter()
        img = preview.render(self.glb_mesh, size=(150, 90), ss=1, **self._render_kwargs())
        self._fast_ok = time.perf_counter() - t < 0.12
        self._render_gen += 1  # supersede any pending full render
        self._show(self.banner_preview, "banner", img.resize((300, 180), Image.BILINEAR))
        self.banner_preview_info.configure(text=self._glb_info())

    def _on_drag_start(self, event):
        self._drag_from = (event.x, event.y)

    def _on_drag(self, event):
        if self.glb_mesh is None or self._drag_from is None:
            return
        dx, dy = event.x - self._drag_from[0], event.y - self._drag_from[1]
        self._drag_from = (event.x, event.y)
        self.view["yaw"] += dx * 0.01
        self.view["pitch"] = max(-1.5, min(1.5, self.view["pitch"] + dy * 0.01))
        if not self._drag_pending:
            self._drag_pending = True
            self.root.after(15, self._fast_render)

    def _on_wheel(self, event):
        if self.glb_mesh is None:
            return
        z = self.view["zoom"] * (1.25 if event.delta > 0 else 0.8)
        self.view["zoom"] = 1.0 if abs(z - 1.0) < 0.01 else max(0.25, min(16.0, z))
        self._request_final_render()

    def _reset_view(self):
        if self.glb_mesh is None:
            return
        self.view = {"yaw": 0.0, "pitch": 0.0, "zoom": 1.0}
        self._request_final_render()

    # -- audio
    def _toggle_play(self):
        if self.play_btn["text"].startswith("■"):
            self._stop_audio()
            return
        if not self._audio_path:
            return
        try:
            self.player.play(self._audio_path)
        except RuntimeError as ex:
            self.audio_preview_info.configure(text=f"Can't play this file: {ex}")
            return
        self._play_token += 1
        token = self._play_token
        self.play_btn.configure(text="■ Stop")
        if self.player.playing() is None:
            # winsound can't say when it's done: time the clip
            ms = int(self._audio_seconds * 1000) + 250 if self._audio_seconds else 3000
            self.root.after(ms, lambda: self._play_ended(token))
        else:
            self.root.after(200, lambda: self._watch_play(token))

    def _watch_play(self, token):
        if token != self._play_token:
            return
        if self.player.playing():
            self.root.after(200, lambda: self._watch_play(token))
        else:
            self._play_ended(token)

    def _play_ended(self, token):
        if token == self._play_token:
            self.play_btn.configure(text="▶ Play")

    def _stop_audio(self):
        self._play_token += 1
        self.player.stop()
        self.play_btn.configure(text="▶ Play")

    def _home_open(self):
        return self.home_win is not None and not self.home_win.closed

    def open_home_preview(self):
        if self.glb_raw is None:
            return
        title = os.path.basename(self.banner_var.get().strip())
        if self._home_open():
            self.home_win.set_mesh(self.glb_raw, title, self._audio_path)
            self.home_win.win.lift()
        else:
            self.home_win = home_preview.HomeMenuPreview(self.root, self.glb_raw, title, self._audio_path)

    def _ftp_open(self):
        return self.ftp_win is not None and self.ftp_win.win.winfo_exists()

    def open_send_window(self):
        """Window that sends the .cia and the .nds ROM to the 3DS over FTP."""
        if self._ftp_open():
            self.ftp_win.win.deiconify()
            self.ftp_win.win.lift()
            self.ftp_win.win.focus_set()
            return
        self.ftp_win = ftp_window.SendWindow(self)

    def _on_close(self):
        if self._ftp_open():
            self.ftp_win.close()
            if self._ftp_open():  # kept open to finish a transfer
                return
        self._stop_audio()
        if self._home_open():
            self.home_win.close()
        if self._pycgfx_open():
            self.pycgfx_win.close()
        self.root.after_cancel(self._poll_id)
        self.root.after_cancel(self._theme_watch_id)
        self.root.destroy()

    # ------------------------------------------------------------------ appearance
    def _reg(self, widget, role):
        """Remember a widget that uses theme colours, so a theme switch can restyle it."""
        self._styled.append((widget, role))
        return widget

    def _on_theme_pick(self, event=None):
        pref = {v: k for k, v in theme.PREF_LABELS.items()}[self.theme_var.get()]
        self.theme_box.selection_clear()
        if pref == self.theme_pref:
            return
        self.theme_pref = pref
        new = dict(self.settings, theme=pref)
        try:
            settings.save(new)
            self.settings = new
        except OSError as ex:
            self.log("warn", f"Couldn't save settings.json: {ex}")
        self._apply_theme()
        note = f" (Windows is using {theme.current.name} mode)" if pref == "system" else ""
        self.log("info", f"Theme: {theme.PREF_LABELS[pref]}{note}")

    def _watch_system_theme(self):
        """With 'System' selected, follow Windows when it switches between light and dark."""
        if self.theme_pref == "system" and theme.resolve("system") != theme.current.name:
            self._apply_theme()
        self._theme_watch_id = self.root.after(2000, self._watch_system_theme)

    def _apply_theme(self):
        theme.use(theme.resolve(self.theme_pref))
        _load_colors()
        theme.apply(self.root)
        self._restyle()

    def _restyle(self):
        """Recolour every themed tk widget after a theme switch (ttk widgets follow the style)."""
        self._styled = [(w, role) for w, role in self._styled if w.winfo_exists()]
        label_opts = theme.widget_opts("Label")
        for w, role in self._styled:
            if role == "entry":
                w.configure(**{**theme.widget_opts("Entry"), "bg": OK_BG, "readonlybackground": LOCK_BG})
            elif role == "spin":
                w.configure(**{**theme.widget_opts("Spinbox"), "bg": OK_BG, "readonlybackground": LOCK_BG,
                               "disabledbackground": LOCK_BG})
            elif role in ("error", "warn"):
                w.configure(**{**label_opts, "fg": ERR_FG if role == "error" else WARN_FG})
            elif role == "placeholder":
                w.configure(fg=PLACEHOLDER_FG, bg=OK_BG)
            elif role == "image":
                w.configure(bg=label_opts["bg"])
            elif role == "caption":
                w.configure(foreground=CAPTION_FG)
            elif role == "hint":
                w.configure(foreground=T.hint_fg)
            elif role == "info":
                w.configure(foreground=T.info_fg)
            elif role == "log":
                w.configure(**theme.widget_opts("Text"))
                for tag, opts in T.log_tags.items():
                    w.tag_configure(tag, **opts)
            elif role == "combo":
                theme.style_combobox_list(w)
            elif role == "link":
                w.configure(foreground=T.link_fg)
        for key, lk in self.locks.items():  # re-apply the locked look in the new colours
            self._set_lock(key, lk["state"])
        for name in ("id_options_dialog", "credits_win"):
            dlg = getattr(self, name, None)
            if dlg is not None and dlg.winfo_exists():
                theme.set_title_bar(dlg)
        if self._ftp_open():
            self.ftp_win.restyle()
        if self._pycgfx_open():
            self.pycgfx_win.restyle()
        # previews: redraw with the new panel colours
        for key in ("icon", "audio"):
            self._preview_keys.pop(key, None)
        if self.glb_mesh is not None:
            self._request_final_render()
        elif self._glb_key is None:  # not waiting for a model to load
            self._preview_keys.pop("banner", None)
        if self._home_open():  # reopen the HOME Menu preview in the new look
            self.home_win.close()
            self.open_home_preview()
        self._placeholder_key = None
        building = self.worker is not None and self.worker.is_alive()
        self.validate()  # re-applies field error/warning colours and the status colour
        if building:
            self._set_status("Building…", T.status_busy)

    # ------------------------------------------------------------------ drag and drop
    DROP_LABELS = {"nds": "NDS ROM", "icon": "Icon", "banner_glb": "Banner (3D model)",
                   "banner_png": "Banner (flat image)", "audio": "Audio"}

    def zone_at(self, x_root, y_root):
        """Which field's row (or preview) is under a screen point: nds/icon/banner/audio or None."""
        w = self.root.winfo_containing(x_root, y_root)
        while w is not None:
            if w in self.preview_zones:
                return self.preview_zones[w]
            if w.master is self.form:
                try:
                    row = int(w.grid_info()["row"])
                except (KeyError, ValueError, tk.TclError):
                    return None
                return next((z for z, rows in self.zone_rows.items() if row in rows), None)
            w = w.master
        return None

    def route_drop(self, path, zone):
        """Field for a dropped file. Known file types go to their field wherever they're
        dropped; a .png goes to the row it was dropped on, otherwise icon if it's
        exactly 48×48 px, else flat banner. Unknown types go to the row under the
        cursor so validation can explain what's wrong. Returns None if unsure."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".nds":
            return "nds"
        if ext == ".wav":
            return "audio"
        if ext == ".glb":
            return "banner_glb"
        if ext == ".png":
            if zone == "icon":
                return "icon"
            if zone == "banner":
                return "banner_png"
            try:
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                return "icon"  # validation will report it as unreadable
            return "icon" if (w, h) == pl.ICON_SIZE else "banner_png"
        if zone == "banner":
            return "banner_png" if self.mode_var.get() == pl.MODE_PNG else "banner_glb"
        return zone

    def handle_drop(self, paths_, x_root, y_root):
        zone = self.zone_at(x_root, y_root)
        for path in paths_:
            name = os.path.basename(path)
            if os.path.isdir(path):
                self.log("warn", f"Dropped folder {name} ignored - drop the file itself")
                continue
            target = self.route_drop(path, zone)
            if target is None:
                self.log("warn", f"Not sure where {name} goes - drop it on the ROM, icon, banner or audio row")
                continue
            if target == "nds":
                self.nds_var.set(path)
                widget = self.nds_entry
            elif target == "icon":
                self.icon_var.set(path)
                widget = self.icon_entry
            elif target == "audio":
                self.audio_var.set(path)
                widget = self.audio_entry
            else:
                mode = pl.MODE_GLB if target == "banner_glb" else pl.MODE_PNG
                if self.mode_var.get() != mode:
                    self.mode_var.set(mode)
                self.banner_var.set(path)
                widget = self.banner_entry
            self.log("info", f"Dropped {name} → {self.DROP_LABELS[target]}")
            self._flash(widget)

    def _flash(self, widget):
        """Briefly highlight a field that just received a dropped file."""
        widget.configure(bg=T.flash_bg)
        self.root.after(700, self.validate)

    # ------------------------------------------------------------------ locking
    def _add_lock(self, key, widget, var, row):
        b = ttk.Button(self.form, text="Edit", width=9, command=lambda: self._toggle_lock(key))
        b.grid(row=row, column=2, padx=(6, 0), pady=(4, 0), sticky="w")
        b.grid_remove()
        self.locks[key] = {"widget": widget, "var": var, "button": b, "state": "free"}

    def _lock_icon(self):
        """Small padlock (drawn, so it looks the same everywhere) in the theme's colour."""
        if T.name not in self._lock_icons:
            k, size = 4, 14
            img = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            col = T.lock_icon
            d.arc((3.5 * k, 0.5 * k, 10.5 * k, 9.5 * k), 180, 360, fill=col, width=int(1.8 * k))  # shackle
            d.line((3.5 * k + 0.9 * k, 5 * k, 3.5 * k + 0.9 * k, 7 * k), fill=col, width=int(1.8 * k))
            d.line((10.5 * k - 0.9 * k, 5 * k, 10.5 * k - 0.9 * k, 7 * k), fill=col, width=int(1.8 * k))
            d.rounded_rectangle((1.5 * k, 6.5 * k, 12.5 * k, 13.5 * k), radius=1.5 * k, fill=col)  # body
            self._lock_icons[T.name] = ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
        return self._lock_icons[T.name]

    def _set_lock(self, key, state):
        """state: 'free' (no .nds), 'locked' (filled from .nds) or 'editing'.

        Locked fields are made obvious: tinted background (LOCK_BG), dimmed text and a
        padlock on the Edit button."""
        lk = self.locks[key]
        lk["state"] = state
        w = lk["widget"]
        # A readonly Spinbox still steps with its arrows, so lock it as disabled.
        is_spin = isinstance(w, tk.Spinbox)
        if state == "locked":
            w.configure(state="disabled" if is_spin else "readonly")
            w.configure(**({"disabledforeground": T.lock_fg} if is_spin else {"fg": T.lock_fg}))
        else:
            w.configure(state="normal")
            if not is_spin:
                w.configure(fg=theme.widget_opts("Entry")["fg"])
        if state == "free":
            lk["button"].grid_remove()
        elif state == "locked":
            lk["button"].configure(text="Edit", image=self._lock_icon(), compound="left", state="normal")
            lk["button"].grid()
        else:
            lk["button"].configure(text="Save", image="", state="normal")
            lk["button"].grid()

    def _toggle_lock(self, key):
        lk = self.locks[key]
        if lk["state"] == "locked":
            self._set_lock(key, "editing")
            w = lk["widget"]
            w.focus_set()
            try:
                w.selection_range(0, "end")
                w.icursor("end")
            except (AttributeError, tk.TclError):
                pass
        elif lk["state"] == "editing":
            if LOCKABLE[key][1](lk["var"].get()):
                self.root.bell()
                return
            self._set_lock(key, "locked")
        self.validate()

    # ------------------------------------------------------------------ credits
    def open_credits(self):
        """Window crediting the projects this app is built on (links open in the browser)."""
        existing = getattr(self, "credits_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_set()
            return
        win = tk.Toplevel(self.root)
        theme.decorate(win)
        self.credits_win = win
        win.title("Credits")
        win.transient(self.root)
        win.resizable(False, False)
        win.geometry(f"+{self.root.winfo_rootx() + 140}+{self.root.winfo_rooty() + 90}")
        f = ttk.Frame(win, padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="YANBF-CBC is a front end. The real work is done by these projects - "
                          "thanks to their authors.", wraplength=620, justify="left").pack(anchor="w")
        ttk.Label(f, text=UNOFFICIAL, wraplength=620, justify="left", font=bold_default()).pack(anchor="w", pady=(6, 0))
        base = tkfont.nametofont("TkDefaultFont").actual()
        bold = (base["family"], base["size"], "bold")
        link_font = (base["family"], base["size"], "underline")
        self.credit_links = []
        for c in CREDITS:
            ttk.Separator(f).pack(fill="x", pady=(10, 8))
            ttk.Label(f, text=c["name"], font=bold).pack(anchor="w")
            link = self._reg(ttk.Label(f, text=c["url"], foreground=T.link_fg, font=link_font,
                                       cursor="hand2"), "link")
            link.pack(anchor="w")
            link.bind("<Button-1>", lambda e, u=c["url"]: webbrowser.open(u))
            self.credit_links.append(link)
            for label, text in (("By", c["by"]), ("Used for", c["what"]), ("License", c["license"])):
                self._reg(ttk.Label(f, text=f"{label}: {text}", foreground=CAPTION_FG, wraplength=620,
                                    justify="left"), "caption").pack(anchor="w", pady=(2, 0))
        ttk.Button(f, text="Close", command=win.destroy).pack(anchor="e", pady=(14, 0))
        win.bind("<Escape>", lambda e: win.destroy())

    # ------------------------------------------------------------------ Unique ID options
    def _uid_caption(self):
        start = self.settings["id_start"]
        note = "" if start == settings.ID_DEFAULT_START else " (set in Options)"
        return ("1-6 hex digits, e.g. FF400 (0x prefix optional). Each installed CIA needs its own ID; "
                f"a .nds reuses the ID it was built with before, otherwise the next free ID from {start:X}{note}.")

    def open_id_options(self):
        """Dialog to choose where new Unique IDs start. Saved to settings.json."""
        dlg = tk.Toplevel(self.root)
        theme.decorate(dlg)
        self.id_options_dialog = dlg
        dlg.title("Unique ID options")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry(f"+{self.root.winfo_rootx() + 160}+{self.root.winfo_rooty() + 260}")
        f = ttk.Frame(dlg, padding=14)
        f.pack(fill="both", expand=True)
        base = settings.ID_DEFAULT_START
        current = self.settings["id_start"]

        # offset spinner (click the arrows or type) and the base ID it produces, kept in step
        ttk.Label(f, text=f"ID offset from {base:X}").grid(row=0, column=0, sticky="w")
        off_var = tk.StringVar(value=str(current - base))
        spin = self._reg(tk.Spinbox(f, from_=0, to=settings.MAX_OFFSET, increment=1, textvariable=off_var,
                                    width=8, bg=OK_BG, **SPIN_OPTS), "spin")
        spin.grid(row=0, column=1, sticky="w", padx=(8, 0), ipady=2)
        ttk.Label(f, text="→  new IDs start at (hex)").grid(row=0, column=2, sticky="w", padx=(12, 0))
        start_var = tk.StringVar(value=f"{current:X}")
        entry = self._reg(tk.Entry(f, textvariable=start_var, width=10, bg=OK_BG, **ENTRY_OPTS), "entry")
        entry.grid(row=0, column=3, sticky="w", padx=(6, 0), ipady=2)
        ttk.Button(f, text=f"Reset to {base:X}", command=lambda: off_var.set("0")).grid(
            row=0, column=4, padx=(10, 0))
        info = self._reg(ttk.Label(f, foreground=T.info_fg, wraplength=560, justify="left"), "info")
        info.grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))
        warn = self._reg(tk.Label(f, fg=WARN_FG, anchor="w", justify="left", wraplength=560), "warn")
        warn.grid(row=2, column=0, columnspan=5, sticky="w")
        err = self._reg(tk.Label(f, fg=ERR_FG, anchor="w", justify="left", wraplength=560), "error")
        err.grid(row=3, column=0, columnspan=5, sticky="w")
        self._reg(ttk.Label(f, foreground=CAPTION_FG, wraplength=560, justify="left", text=(
            "When you load a .nds for a game you haven't built before, it's given the first free ID at or "
            f"above the start (up to {settings.ID_MAX:X}, offset {settings.MAX_OFFSET}). Games you've already "
            "built keep their ID, so rebuilding them still installs as an update. Raise the offset if other "
            f"forwarders on your 3DS already use IDs from {base:X}. Saved in settings.json next to the program."
        )), "caption").grid(row=4, column=0, columnspan=5, sticky="w", pady=(6, 0))
        bar = ttk.Frame(f)
        bar.grid(row=5, column=0, columnspan=5, sticky="e", pady=(12, 0))
        save_btn = ttk.Button(bar, text="Save", width=10)
        save_btn.pack(side="left")
        ttk.Button(bar, text="Cancel", width=10, command=dlg.destroy).pack(side="left", padx=(6, 0))
        # handles for tests
        dlg.offset_spin, dlg.start_entry, dlg.save_btn = spin, entry, save_btn
        dlg.info_label, dlg.warn_label, dlg.err_label = info, warn, err

        state = {"source": "offset", "syncing": False}

        def result():
            """(start, error) from whichever field was edited last."""
            if state["source"] == "offset":
                return settings.validate_offset(off_var.get())
            return settings.validate_id_start(start_var.get())

        def edited(source):
            if state["syncing"]:
                return
            state["source"] = source
            value, error = result()
            if value is not None:  # mirror into the other field
                state["syncing"] = True
                if source == "offset":
                    start_var.set(f"{value:X}")
                else:
                    off_var.set(str(value - base))
                state["syncing"] = False
            refresh()

        def refresh():
            value, error = result()
            warning = settings.low_ids_warning(value) if value is not None else None
            bad = spin if state["source"] == "offset" else entry
            for w in (spin, entry):
                w.configure(bg=ERR_BG if (error and w is bad) else WARN_BG if warning else OK_BG)
            err.configure(text=error or "")
            warn.configure(text=("⚠ " + warning) if warning else "")
            save_btn.configure(state="disabled" if error else "normal")
            if value is None:
                info.configure(text="")
                return
            nxt, _ = nds.suggest_unique_id("\0new game", start=value)
            left = settings.ids_left(value)
            info.configure(text=f"New games start at {value:X} (offset {value - base} from {base:X}). "
                                f"{left:,} ID{'s' if left != 1 else ''} left up to {settings.ID_MAX:X}; "
                                f"the next new game would get {nxt:X}.")

        off_var.trace_add("write", lambda *_: edited("offset"))
        start_var.trace_add("write", lambda *_: edited("start"))

        def save():
            value, error = result()
            if error:
                self.root.bell()
                return
            new = dict(self.settings, id_start=value)
            try:
                settings.save(new)
            except OSError as ex:
                err.configure(text=f"Couldn't save settings.json: {ex}")
                return
            self.settings = new
            self.uid_caption_var.set(self._uid_caption())
            self.log("info", f"Unique ID options saved: new IDs start at {value:X}")
            self._refresh_uid_suggestion()
            self.validate()  # refreshes the next-free-ID preview in the box
            dlg.destroy()

        save_btn.configure(command=save)
        dlg.bind("<Return>", lambda e: save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        refresh()
        spin.focus_set()
        spin.selection_range(0, "end")
        dlg.grab_set()

    def _refresh_uid_suggestion(self):
        """After the ID start changes, re-suggest the ID of a loaded .nds, unless it was
        reused from an earlier build or the user edited it."""
        lk = self.locks["uid"]
        sugg = self._uid_suggestion
        if (self.loaded_nds is None or sugg is None or sugg[1] or lk["state"] != "locked"
                or self.uid_var.get().strip().upper() != sugg[0]):
            return
        uid, reused = nds.suggest_unique_id(nds.registry_key(self._nds_game_code, ""),
                                            start=self.settings["id_start"])
        self._uid_suggestion = (f"{uid:X}", reused)
        if f"{uid:X}" != sugg[0]:
            self.uid_var.set(f"{uid:X}")
            self.log("info", f"  Unique ID for the loaded ROM changed to {uid:X}")

    # ------------------------------------------------------------------ .nds
    def _on_nds_change(self):
        path = self.nds_var.get().strip()
        if not path:
            self.loaded_nds = None
            for key in self.locks:
                self._set_lock(key, "free")
        elif pl.check_input_file(pl.KIND_NDS, path) is None:
            norm = os.path.normcase(os.path.abspath(path))
            if norm != self.loaded_nds:
                self.loaded_nds = norm
                self._fill_from_nds(path)
        self.validate()

    def _fill_from_nds(self, path):
        info = nds.read_nds(path)
        self._nds_game_code = info.game_code
        uid, reused = nds.suggest_unique_id(nds.registry_key(info.game_code, ""),
                                            start=self.settings["id_start"])
        self._uid_suggestion = (f"{uid:X}", reused)
        values = {
            "rom": nds.sd_rom_path(path),
            "title": info.title,
            "publisher": info.publisher,
            "product": nds.product_code(info.game_code),
            "uid": f"{uid:X}",
            "minor": str(info.rom_version) if info.rom_version <= pl.MINOR_MAX else "",
        }
        for key, value in values.items():
            self.locks[key]["var"].set(value)
            self._set_lock(key, "locked" if value else "free")
        self.log("step", f"Loaded {os.path.basename(path)}")
        self.log("info", f"  game code {info.game_code}, internal name {info.header_title!r}, "
                         f"ROM version {info.rom_version}")
        if reused:
            self.log("info", f"  Unique ID {uid:X} reused: this game was built with it before, "
                             "so the new CIA installs as an update")
        else:
            self.log("info", f"  Unique ID {uid:X} is the next free ID")
        blank = [LOCKABLE[k][0] for k, v in values.items() if not v]
        if blank:
            self.log("warn", f"  Not in the ROM header, fill in by hand: {', '.join(blank)}")

    # ------------------------------------------------------------------ log
    def log(self, tag, text):
        t = self.log_text
        t.configure(state="normal")
        t.insert("end", text + "\n", tag)
        t.see("end")
        t.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                tag, text = self.queue.get_nowait()
                if tag == "__end__":
                    self._on_build_end(text)
                elif tag == "__glb__":
                    self._on_glb_loaded(*text)
                elif tag == "__render__":
                    self._on_render_done(*text)
                elif tag == "__drop__":
                    self.handle_drop(*text)
                elif tag == "__cia__":
                    self.last_cia = text
                else:
                    self.log(tag, text)
        except queue.Empty:
            pass
        self._poll_id = self.root.after(50, self._poll_queue)

    # ------------------------------------------------------------------ checks
    @staticmethod
    def find_missing():
        """Required files that are missing - pycgfx counts as missing unless it's the
        tested version (pycgfx_setup checks every file)."""
        missing = paths.find_missing()
        if not pycgfx_setup.is_ready() and paths.PYCGFX_MAIN not in missing:
            missing.append(paths.PYCGFX_MAIN)
        return missing

    def check_tools(self):
        missing = self.find_missing()
        if paths.PYCGFX_MAIN in missing and os.path.isfile(paths.PYCGFX_MAIN):
            self.log("err", f"pycgfx isn't the tested version ({pycgfx_setup.SHORT}) - see the setup window")
        if missing:
            self.log("err", f"Missing required files (program folder: {paths.BASE_DIR}):")
            for p in missing:
                self.log("err", "  " + p)
        else:
            self.log("info", f"Program folder: {paths.BASE_DIR}")
            self.log("ok", "All required tools found.")
        return missing

    def startup_checks(self):
        """After the window is shown: set up pycgfx if needed, report other missing files."""
        try:
            if pycgfx_setup.fix_stock():  # the original files were placed by hand
                self.log("ok", f"Added this project's two fixes to pycgfx {pycgfx_setup.SHORT}")
                self.missing = self.check_tools()
                self.validate()
        except (pycgfx_setup.SetupError, OSError) as ex:
            self.log("err", f"Couldn't add the fixes to pycgfx: {ex}")
        self.report_missing()

    def report_missing(self):
        """pycgfx gets its setup window; anything else missing gets the error box."""
        pyc_dir = os.path.normcase(paths.PYCGFX_DIR)
        others = [p for p in self.missing
                  if os.path.normcase(p) != pyc_dir and not os.path.normcase(p).startswith(pyc_dir + os.sep)]
        if len(others) < len(self.missing):
            self.open_pycgfx_setup()
        if others:
            self.show_missing_error(others)

    def _pycgfx_open(self):
        return self.pycgfx_win is not None and self.pycgfx_win.win.winfo_exists()

    def open_pycgfx_setup(self):
        if self._pycgfx_open():
            self.pycgfx_win.win.deiconify()
            self.pycgfx_win.win.lift()
            return
        self.pycgfx_win = pycgfx_window.PycgfxWindow(self, self._pycgfx_ready)

    def _pycgfx_ready(self):
        self.missing = self.check_tools()
        self.validate()

    def show_missing_error(self, items=None):
        short = "\n".join(paths.rel(p) for p in (items or self.missing))
        messagebox.showerror(
            "YANBF-CBC - missing files",
            "These required files are missing:\n\n" + short,
            detail=f"Paths are relative to the program's folder:\n{paths.BASE_DIR}\n\n"
                   "Full paths are listed in the log. Building is disabled until they are in place.",
            parent=self.root,
        )

    @staticmethod
    def _set_field(widget, err_label, error):
        widget.configure(bg=ERR_BG if error else OK_BG, readonlybackground=ERR_BG if error else LOCK_BG)
        if isinstance(widget, tk.Spinbox):
            widget.configure(disabledbackground=ERR_BG if error else LOCK_BG)
        if err_label is not None:
            err_label.configure(text=error or "")

    def validate(self):
        """Live validation. Returns True if Build may be enabled."""
        needs = []

        nds_path = self.nds_var.get().strip()
        e = pl.check_input_file(pl.KIND_NDS, nds_path) if nds_path else None
        self._set_field(self.nds_entry, self.nds_err, e)
        if e:
            needs.append("valid .nds")

        icon = self.icon_var.get().strip()
        e = pl.check_input_file(pl.KIND_ICON, icon) if icon else None
        self._set_field(self.icon_entry, self.icon_err, e)
        if not icon or e:
            needs.append("icon")

        banner = self.banner_var.get().strip()
        kind = pl.KIND_GLB if self.mode_var.get() == pl.MODE_GLB else pl.KIND_BANNER_PNG
        e = pl.check_input_file(kind, banner) if banner else None
        self._set_field(self.banner_entry, self.banner_err, e)
        if not banner or e:
            needs.append("banner")

        audio = self.audio_var.get().strip()
        e = pl.check_input_file(pl.KIND_AUDIO, audio) if audio else None
        self._set_field(self.audio_entry, self.audio_err, e)
        if e:
            needs.append("audio")

        if not self.title_var.get().strip():
            needs.append("title")
        if not self.product_var.get().strip():
            needs.append("product code")

        uid = self.uid_var.get().strip()
        _, e = pl.parse_unique_id(uid)
        self._set_field(self.uid_entry, self.uid_err, e if uid else None)
        if e:
            needs.append("unique ID")

        _, e = pl.parse_minor(self.minor_var.get())
        self._set_field(self.minor_spin, self.minor_err, e)
        if e:
            needs.append("version")

        editing = []
        for key, lk in self.locks.items():
            if lk["state"] == "editing":
                editing.append(LOCKABLE[key][0])
                valid = LOCKABLE[key][1](lk["var"].get()) is None
                lk["button"].configure(state="normal" if valid else "disabled")
        if editing:
            needs.append("save " + ", ".join(editing))

        if self.missing:
            needs.insert(0, "required tools")

        building = self.worker is not None and self.worker.is_alive()
        ok = not needs
        self.build_btn.configure(state="normal" if ok and not building else "disabled")
        if not building:
            self._set_status("Needs: " + ", ".join(needs) if needs else "Ready",
                             T.status_bad if needs else T.status_ok)
        self._update_previews()
        self._update_uid_placeholder()
        if self._ftp_open():
            self.ftp_win.refresh_files()
        return ok

    def _update_uid_placeholder(self):
        """Show the next free Unique ID in grey inside the empty ID box (preview only)."""
        if self.uid_var.get().strip():
            self.uid_placeholder.place_forget()
            return
        try:
            mtime = os.stat(paths.ID_REGISTRY).st_mtime_ns
        except OSError:
            mtime = None
        key = (paths.ID_REGISTRY, mtime, self.settings["id_start"])
        if key != self._placeholder_key:  # only re-read the registry when it or the start changed
            self._placeholder_key = key
            uid, _ = nds.suggest_unique_id("\0new game", start=self.settings["id_start"])
            self.uid_placeholder.configure(text=f"{uid:X}  (next free ID)")
        self.uid_placeholder.place(in_=self.uid_entry, x=4, rely=0.5, anchor="w")

    def _set_status(self, text, color):
        self.status_var.set(text)
        self.status_label.configure(foreground=color)

    # ------------------------------------------------------------------ pickers
    def _pick(self, var, title, types):
        path = filedialog.askopenfilename(parent=self.root, title=title, filetypes=types)
        if path:
            var.set(os.path.normpath(path))

    def _pick_nds(self):
        self._pick(self.nds_var, "Choose NDS ROM", [("NDS ROM", "*.nds"), ("All files", "*.*")])

    def _pick_icon(self):
        self._pick(self.icon_var, "Choose icon image", [("PNG image", "*.png"), ("All files", "*.*")])

    def _pick_banner(self):
        if self.mode_var.get() == pl.MODE_GLB:
            self._pick(self.banner_var, "Choose 3D banner model", [("glTF binary", "*.glb"), ("All files", "*.*")])
        else:
            self._pick(self.banner_var, "Choose banner image", [("PNG image", "*.png"), ("All files", "*.*")])

    def _pick_audio(self):
        self._pick(self.audio_var, "Choose banner audio", [("WAV audio", "*.wav"), ("All files", "*.*")])

    def save_banner_template(self):
        """Save a copy of the bundled Blender template (banner.blend) where the user chooses."""
        src = paths.BANNER_TEMPLATE
        if not os.path.isfile(src):
            messagebox.showerror("Blender template", "The Blender template isn't available.",
                                 detail=f"Expected it at:\n{src}", parent=self.root)
            return
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        dest = filedialog.asksaveasfilename(
            parent=self.root, title="Save the 3D banner template", initialfile="YANBF banner template.blend",
            initialdir=downloads if os.path.isdir(downloads) else None, defaultextension=".blend",
            filetypes=[("Blender file", "*.blend"), ("All files", "*.*")])
        if not dest:
            return
        dest = os.path.normpath(dest)
        try:
            shutil.copyfile(src, dest)
        except OSError as ex:
            self.log("err", f"Couldn't save the Blender template: {ex}")
            return
        self.log("ok", f"Saved the 3D banner template: {dest}")
        self.log("info", "  Open it in Blender 5.2 or newer (the version it was saved with). 'worldModel' is the part that spins and "
                         "'nameModel' the logo that always faces you. Replace them with your own models, then "
                         "File → Export → glTF 2.0, format glTF Binary (.glb), and pick the .glb here.")

    def _on_mode_change(self):
        mode = self.mode_var.get()
        self.banner_caption_var.set(CAPTIONS[mode])
        if mode == pl.MODE_GLB:
            self.template_btn.grid()
        else:
            self.template_btn.grid_remove()
        want = ".glb" if mode == pl.MODE_GLB else ".png"
        cur = self.banner_var.get().strip()
        if cur and os.path.splitext(cur)[1].lower() != want:
            self.banner_var.set("")
        self.validate()

    # ------------------------------------------------------------------ build
    def make_job(self):
        return pl.BuildJob(
            icon_path=self.icon_var.get().strip(),
            banner_mode=self.mode_var.get(),
            banner_path=self.banner_var.get().strip(),
            audio_path=self.audio_var.get().strip(),
            rom_path=self.rom_var.get().strip(),
            title=self.title_var.get().strip(),
            publisher=self.publisher_var.get().strip(),
            product_code=self.product_var.get().strip(),
            unique_id=self.uid_var.get().strip(),
            minor=self.minor_var.get().strip(),
            nds_path=self.nds_var.get().strip(),
        )

    def start_build(self):
        if self.worker is not None and self.worker.is_alive():
            return
        self.missing = self.find_missing()
        if self.missing:
            self.check_tools()
            self.validate()
            self.report_missing()
            return
        if not self.validate():
            return
        job = self.make_job()
        self.last_out_dir = os.path.join(paths.OUTPUT_DIR, pl.output_name(job.rom_path, job.title))
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.build_btn.configure(state="disabled")
        self._set_status("Building…", T.status_busy)

        q = self.queue

        def work():
            p = pl.Pipeline(job, lambda tag, text: q.put((tag, text)))
            ok = p.run()
            if ok and p.cia_path:
                q.put(("__cia__", p.cia_path))
            q.put(("__end__", ok))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_build_end(self, ok):
        self.worker = None
        self.validate()
        if ok:
            self._set_status("Done", T.status_ok)
        else:
            self._set_status("Failed - see log", T.status_bad)

    def open_output(self):
        target = self.last_out_dir if self.last_out_dir and os.path.isdir(self.last_out_dir) else paths.OUTPUT_DIR
        os.makedirs(target, exist_ok=True)
        pu.open_path(target)


def check_tools_report():
    """`YANBF-CBC --check-tools [report.txt]`: where the program looks for everything,
    what's missing, and the first line each native tool prints - no window. Used by
    the release builds to check a packaged app (a windowed exe has no console, so it
    can write to a file instead). Exit code 1 if anything other than pycgfx is missing."""
    import subprocess
    lines = [f"program folder: {paths.BASE_DIR}", f"settings + IDs: {paths.DATA_DIR}",
             f"output: {paths.OUTPUT_DIR}", f"pycgfx: {paths.PYCGFX_DIR}"]
    for tool in (paths.CTRTOOL, paths.MAKEROM, paths.BANNERTOOL, paths.CWAVTOOL):
        try:
            r = subprocess.run([tool], capture_output=True, text=True, errors="replace", timeout=20,
                               stdin=subprocess.DEVNULL, **pu.popen_flags())
            first = next((l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip()), "")
            lines.append(f"runs: {os.path.basename(tool)}: {first}")
        except (OSError, subprocess.SubprocessError) as ex:
            lines.append(f"can't run: {os.path.basename(tool)}: {ex}")
    missing = App.find_missing()
    lines += [f"missing: {p}" for p in missing]
    text = "\n".join(lines) + "\n"
    args = sys.argv[sys.argv.index("--check-tools") + 1:]
    if args:
        with open(args[0], "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        sys.stdout.write(text)
    others = [p for p in missing if not p.startswith(paths.PYCGFX_DIR)]
    return 1 if others or any(l.startswith("can't run") for l in lines) else 0


def main():
    if "--check-tools" in sys.argv:
        sys.exit(check_tools_report())
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    root.deiconify()
    root.after_idle(app.startup_checks)
    root.mainloop()


if __name__ == "__main__":
    main()
