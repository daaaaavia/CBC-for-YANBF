"""'Set up pycgfx' window: shown at startup when processes/YANBF/pycgfx/ isn't the
tested version (see pycgfx_setup). Offers an automatic download or step-by-step
manual placement, and stays away once the files check out.

On macOS only the manual option is shown: the Mac app doesn't download pycgfx for
the user. The files go in ~/Library/Application Support/YANBF-CBC/pycgfx there."""

import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import ttk

import paths
import platform_util as pu
import pycgfx_setup as ps
import theme


class PycgfxWindow:
    def __init__(self, app, on_ready):
        self.app = app
        self.on_ready = on_ready  # called once the files check out
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self._status = ("", "hint")
        self.auto = not pu.is_mac()  # the Mac app never downloads pycgfx itself
        self.auto_btn = self.bar = None
        root = app.root

        win = self.win = tk.Toplevel(root)
        theme.decorate(win)
        win.title("Set up pycgfx")
        win.transient(root)
        win.resizable(False, False)
        win.geometry(f"+{root.winfo_rootx() + 150}+{root.winfo_rooty() + 70}")
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda e: self.close())

        base = tkfont.nametofont("TkDefaultFont").actual()
        bold = (base["family"], base["size"], "bold")
        big = (base["family"], base["size"] + 3, "bold")
        link_font = (base["family"], base["size"], "underline")
        wrap = 600
        f = ttk.Frame(win, padding=18)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="One more file is needed: pycgfx", font=big).pack(anchor="w")
        ttk.Label(f, wraplength=wrap, justify="left", text=(
            "YANBF-CBC uses pycgfx, by skyfloogle, to turn 3D (.glb) banners into the 3DS banner "
            "format. It isn't included with this program because its author hasn't published a "
            "license that allows sharing it, so it has to come from skyfloogle's own GitHub.")
        ).pack(anchor="w", pady=(6, 0))

        # the version warning, in the theme's warning colours
        box = tk.Frame(f, bg=theme.current.warn_bg, padx=10, pady=8)
        box.pack(fill="x", pady=(12, 0))
        self._warn_box = box
        self._warn_labels = [
            tk.Label(box, text=f"Use exactly this version: pycgfx {ps.SHORT} ({ps.DATE})", font=bold,
                     bg=theme.current.warn_bg, fg=theme.current.warn_fg, anchor="w"),
            tk.Label(box, wraplength=wrap - 20, justify="left", anchor="w",
                     bg=theme.current.warn_bg, fg=theme.current.warn_fg, text=(
                         "This build of YANBF-CBC was made and tested with that version. Newer or older "
                         "versions of pycgfx are not accepted - the program checks every file. It then "
                         "adds its own two fixes (logo billboarding and a crash fix) automatically, so "
                         "don't edit the files yourself.")),
        ]
        for lbl in self._warn_labels:
            lbl.pack(anchor="w", fill="x")

        cap = lambda parent, text: self.app._reg(ttk.Label(parent, text=text, wraplength=wrap, justify="left",
                                                           foreground=theme.current.caption_fg), "caption")
        if self.auto:
            # option 1: automatic
            ttk.Separator(f).pack(fill="x", pady=(14, 10))
            ttk.Label(f, text="Option 1 - automatic (recommended)", font=bold).pack(anchor="w")
            cap(f, f"Downloads version {ps.SHORT} (about {ps.ZIP_SIZE / 1048576:.1f} MB) from {ps.REPO}, "
                   "adds the fixes and puts the files in the right place.").pack(anchor="w", pady=(2, 6))
            row = ttk.Frame(f)
            row.pack(fill="x")
            self.auto_btn = ttk.Button(row, text="Download and set up automatically", style="Accent.TButton",
                                       command=self.start_download)
            self.auto_btn.pack(side="left")
            self.bar = ttk.Progressbar(row, maximum=1000, value=0, length=230)
            self.bar.pack(side="left", padx=(12, 0))

        # option 2 (the only one on a Mac): by hand
        ttk.Separator(f).pack(fill="x", pady=(14, 10))
        ttk.Label(f, text="Option 2 - by hand" if self.auto else "Download it by hand", font=bold).pack(anchor="w")
        steps = ttk.Frame(f)
        steps.pack(fill="x", pady=(4, 0))
        steps.columnconfigure(1, weight=1)
        ttk.Label(steps, text="1.").grid(row=0, column=0, sticky="nw", padx=(0, 6))
        s1 = ttk.Frame(steps)
        s1.grid(row=0, column=1, sticky="w")
        ttk.Label(s1, text=f"Download this exact version ({ps.SHORT}) as a zip:").pack(anchor="w")
        self.link = self.app._reg(ttk.Label(s1, text=ps.ZIP_URL, font=link_font, cursor="hand2",
                                            foreground=theme.current.link_fg), "link")
        self.link.pack(anchor="w")
        self.link.bind("<Button-1>", lambda e: webbrowser.open(ps.ZIP_URL))
        cap(s1, "Not the green Code button on the main page - that gives the newest version.").pack(anchor="w")

        ttk.Label(steps, text="2.").grid(row=1, column=0, sticky="nw", padx=(0, 6), pady=(8, 0))
        s2 = ttk.Frame(steps)
        s2.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(s2, wraplength=wrap - 20, justify="left", text=(
            "Unzip it, then copy main.py, banner-camera.gltf and the cgfx folder into this folder "
            "(or just put the zip itself there):")).pack(anchor="w")
        prow = ttk.Frame(s2)
        prow.pack(fill="x", pady=(4, 0))
        self.path_var = tk.StringVar(value=paths.PYCGFX_DIR)
        e = tk.Entry(prow, textvariable=self.path_var, state="readonly", width=62,
                     readonlybackground=theme.current.field_bg, **theme.current.entry_opts)
        self.app._reg(e, "entry")
        ttk.Button(prow, text="Open folder" if pu.is_windows() else f"Show in {pu.file_manager()}",
                   command=self.open_folder).pack(side="right", padx=(6, 0))
        e.pack(side="left", fill="x", expand=True, ipady=2)
        e.xview_moveto(1.0)  # a long path shows its end (the pycgfx folder), not the drive

        ttk.Label(steps, text="3.").grid(row=2, column=0, sticky="nw", padx=(0, 6), pady=(8, 0))
        s3 = ttk.Frame(steps)
        s3.grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Label(s3, text="Press Check again. The program checks the version and adds the fixes.").pack(anchor="w")
        self.check_btn = ttk.Button(s3, text="Check again", command=self.check_again)
        self.check_btn.pack(anchor="w", pady=(4, 0))

        # status + close
        ttk.Separator(f).pack(fill="x", pady=(14, 8))
        self.status_label = ttk.Label(f, text="", wraplength=wrap, justify="left", font=theme.current.font_status)
        self.status_label.pack(anchor="w")
        bottom = ttk.Frame(f)
        bottom.pack(fill="x", pady=(10, 0))
        cap(bottom, "Until pycgfx is set up, Build CIA stays disabled. This window comes back at the next "
                    "start, or when you press Build.").pack(side="left")
        self.close_btn = ttk.Button(bottom, text="Not now", command=self.close)
        self.close_btn.pack(side="right")

        self.refresh(initial=True)
        self._poll_id = win.after(50, self._poll)

    # ------------------------------------------------------------------ state
    def _set_status(self, text, kind):
        self._status = (text, kind)
        color = {"ok": theme.current.status_ok, "bad": theme.current.status_bad,
                 "busy": theme.current.status_busy, "hint": theme.current.hint_fg}[kind]
        self.status_label.configure(text=text, foreground=color)

    def refresh(self, initial=False):
        """Check the folder and show where things stand. Returns True once ready."""
        state, problems = ps.status()
        if state == "ok":
            self._done()
            return True
        if state == "missing":
            self._set_status("pycgfx isn't set up yet.", "hint" if initial else "bad")
        else:
            listed = ", ".join(problems[:4]) + (f" and {len(problems) - 4} more" if len(problems) > 4 else "")
            self._set_status(f"The files in the folder aren't pycgfx version {ps.SHORT} "
                             f"(missing or different: {listed}). Use the exact version linked above"
                             + (", or the automatic option (it replaces them)." if self.auto else "."), "bad")
        return False

    def _done(self):
        self._set_status(f"pycgfx {ps.SHORT} is set up, with the fixes. You can build CIAs now.", "ok")
        self._set_auto("disabled")
        self.check_btn.configure(state="disabled")
        self.close_btn.configure(text="Done")
        if self.bar is not None:
            self.bar.configure(value=1000)
        self.on_ready()

    def restyle(self):
        theme.set_title_bar(self.win)
        self._set_status(*self._status)
        self._warn_box.configure(bg=theme.current.warn_bg)
        for lbl in self._warn_labels:
            lbl.configure(bg=theme.current.warn_bg, fg=theme.current.warn_fg)

    def _set_auto(self, state):
        if self.auto_btn is not None:
            self.auto_btn.configure(state=state)

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    # ------------------------------------------------------------------ actions
    def open_folder(self):
        os.makedirs(paths.PYCGFX_DIR, exist_ok=True)
        pu.open_path(paths.PYCGFX_DIR)

    def check_again(self):
        if self.busy():
            return
        try:
            note = ps.tidy_manual_placement()
            if ps.fix_stock():
                self.app.log("ok", f"Added this project's two fixes to pycgfx {ps.SHORT}")
        except (ps.SetupError, OSError) as ex:
            self._set_status(str(ex), "bad")
            return
        if note:
            self.app.log("info", note)
        if not self.refresh():
            self.win.bell()

    def start_download(self):
        if self.busy() or not self.auto:
            return
        self.cancel.clear()
        self._set_auto("disabled")
        self.check_btn.configure(state="disabled")
        self.bar.configure(value=0)
        self._set_status(f"Downloading pycgfx {ps.SHORT} from GitHub…", "busy")
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    def _work(self):
        q = self.q
        try:
            data = ps.download(lambda n, total: q.put(("progress", (n, total or ps.ZIP_SIZE))), self.cancel)
            q.put(("status", "Checking the files and adding the fixes…"))
            ps.install_from_zip(data)
            q.put(("done", None))
        except ps.SetupError as ex:
            q.put(("error", str(ex)))
        except OSError as ex:
            reason = getattr(ex, "reason", None) or ex
            q.put(("error", f"Couldn't download it ({reason}). Check the internet connection, or use "
                            "option 2."))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "progress":
                    n, total = data
                    self.bar.configure(value=min(1000, 1000 * n / total))
                    self._set_status(f"Downloading pycgfx {ps.SHORT}… {n / 1048576:.1f} MB", "busy")
                elif kind == "status":
                    self._set_status(data, "busy")
                elif kind == "done":
                    self.app.log("ok", f"pycgfx {ps.SHORT} downloaded from GitHub and set up, with the fixes")
                    self.refresh()
                elif kind == "error":
                    self.bar.configure(value=0)
                    self._set_auto("normal")
                    self.check_btn.configure(state="normal")
                    self._set_status(data, "bad")
        except queue.Empty:
            pass
        self._poll_id = self.win.after(50, self._poll)

    def close(self):
        self.cancel.set()
        try:
            self.win.after_cancel(self._poll_id)
        except tk.TclError:
            pass
        self.win.destroy()
