"""'Set up downloads' window: one place to set up the files CBC for YANBF can't include
(no license allows sharing them) - pycgfx and ctrtool (see setup_parts.py).

Shown at startup (and when Build is pressed) while either isn't the tested version.
It can't be closed until both check out; quitting the program still works. Offers:
  * Windows: one button that downloads whichever are missing, checks them and puts
    them in place
  * by hand, for each file: the exact download link and the folder to put it in, then
    Check again
On macOS only the by-hand steps are shown: the Mac app doesn't download anything for
the user. The files go in ~/Library/Application Support/CBC-for-YANBF/ there.
A file that's already set up folds down to one ✓ line.
"""

import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import ttk

import platform_util as pu
import theme
from setup_parts import PARTS


class SetupWindow:
    title = "Set up downloads"

    def __init__(self, app, on_ready, parts=PARTS):
        self.app = app
        self.on_ready = on_ready  # called once everything checks out
        self.parts = parts
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.ready = False
        self._status = ("", "hint")
        self.auto = not pu.is_mac()  # the Mac app never downloads anything itself
        self.auto_btn = self.bar = None
        self.rows = {}  # part key -> widgets of its section
        root = app.root

        win = self.win = tk.Toplevel(root)
        theme.decorate(win)
        win.title(self.title)
        win.transient(root)
        win.resizable(False, False)
        win.geometry(f"+{root.winfo_rootx() + 150}+{root.winfo_rooty() + 40}")
        win.protocol("WM_DELETE_WINDOW", self.try_close)
        win.bind("<Escape>", lambda e: self.try_close())

        base = tkfont.nametofont("TkDefaultFont").actual()
        bold = (base["family"], base["size"], "bold")
        big = (base["family"], base["size"] + 3, "bold")
        link_font = (base["family"], base["size"], "underline")
        wrap = 620
        self._warn_labels = []
        f = ttk.Frame(win, padding=18)
        f.pack(fill="both", expand=True)
        cap = lambda parent, text, w=wrap: self.app._reg(
            ttk.Label(parent, text=text, wraplength=w, justify="left", foreground=theme.current.caption_fg), "caption")

        names = " and ".join(p.name for p in parts)
        ttk.Label(f, text=f"Two more files are needed: {names}", font=big).pack(anchor="w")
        ttk.Label(f, wraplength=wrap, justify="left", text=(
            "They aren't included with CBC for YANBF because no license allows sharing them, so they "
            "come from their authors' own pages. Use exactly the versions shown: the program checks "
            "every file and won't accept any other version. CBC for YANBF is unofficial and not "
            "connected to either project, so please don't report problems with this setup to them.")
        ).pack(anchor="w", pady=(6, 0))

        if self.auto:
            ttk.Separator(f).pack(fill="x", pady=(14, 10))
            ttk.Label(f, text="Option 1 - automatic (recommended)", font=bold).pack(anchor="w")
            total = sum(p.download_size() for p in parts) / 1048576
            cap(f, f"Downloads whichever are missing (about {total:.1f} MB for both) from GitHub, checks "
                   "them and puts them in the right place.").pack(anchor="w", pady=(2, 6))
            row = ttk.Frame(f)
            row.pack(fill="x")
            self.auto_btn = ttk.Button(row, text="Download and set up automatically", style="Accent.TButton",
                                       command=self.start_download)
            self.auto_btn.pack(side="left")
            self.bar = ttk.Progressbar(row, maximum=1000, value=0, length=250)
            self.bar.pack(side="left", padx=(12, 0))

        ttk.Separator(f).pack(fill="x", pady=(14, 10))
        ttk.Label(f, text="Option 2 - by hand" if self.auto else "Download them by hand", font=bold).pack(anchor="w")

        for part in parts:
            box = ttk.Frame(f)
            box.pack(fill="x", pady=(10, 0))
            head = ttk.Frame(box)
            head.pack(fill="x")
            ttk.Label(head, text=part.name, font=bold).pack(side="left")
            state_lbl = ttk.Label(head, text="", font=theme.current.font_status)
            state_lbl.pack(side="left", padx=(10, 0))
            body = ttk.Frame(box)
            warn = tk.Label(body, text=f"Use exactly {part.version()}", font=bold, anchor="w",
                            bg=theme.current.warn_bg, fg=theme.current.warn_fg, padx=8, pady=3)
            warn.pack(anchor="w", fill="x", pady=(4, 0))
            self._warn_labels.append(warn)
            cap(body, part.what()).pack(anchor="w", pady=(4, 0))
            ttk.Label(body, text="1. " + part.link_label()).pack(anchor="w", pady=(6, 0))
            link = self.app._reg(ttk.Label(body, text=part.link_url(), font=link_font, cursor="hand2",
                                           foreground=theme.current.link_fg), "link")
            link.pack(anchor="w", padx=(16, 0))
            link.bind("<Button-1>", lambda e, u=part.link_url(): webbrowser.open(u))
            if part.link_caption():
                cap(body, part.link_caption(), wrap - 16).pack(anchor="w", padx=(16, 0))
            ttk.Label(body, text="2. " + part.place_text(), wraplength=wrap, justify="left").pack(anchor="w", pady=(6, 0))
            prow = ttk.Frame(body)
            prow.pack(fill="x", pady=(4, 0), padx=(16, 0))
            try:  # so it's there to drop files into, even before "Open folder"
                os.makedirs(part.folder(), exist_ok=True)
            except OSError:
                pass
            path_var = tk.StringVar(value=part.folder())
            e = tk.Entry(prow, textvariable=path_var, state="readonly", width=62,
                         readonlybackground=theme.current.field_bg, **theme.current.entry_opts)
            self.app._reg(e, "entry")
            ttk.Button(prow, text="Open folder" if pu.is_windows() else f"Show in {pu.file_manager()}",
                       command=lambda p=part: self.open_folder(p)).pack(side="right", padx=(6, 0))
            e.pack(side="left", fill="x", expand=True, ipady=2)
            e.xview_moveto(1.0)  # a long path shows its end, not the drive
            self.rows[part.key] = {"state": state_lbl, "body": body, "path_var": path_var, "link": link,
                                   "shown": False}

        ttk.Separator(f).pack(fill="x", pady=(14, 8))
        crow = ttk.Frame(f)
        crow.pack(fill="x")
        self.check_btn = ttk.Button(crow, text="Check again", command=self.check_again)
        self.check_btn.pack(side="left")
        cap(crow, "After placing files by hand. The program checks the versions (and adds pycgfx's fixes).",
            wrap - 120).pack(side="left", padx=(10, 0))
        self.status_label = ttk.Label(f, text="", wraplength=wrap, justify="left", font=theme.current.font_status)
        self.status_label.pack(anchor="w", pady=(10, 0))
        bottom = ttk.Frame(f)
        bottom.pack(fill="x", pady=(10, 0))
        cap(bottom, "This window stays open until both files are set up. Until then, Build CIA is disabled.",
            wrap - 100).pack(side="left")
        self.close_btn = ttk.Button(bottom, text="Done", command=self.try_close, state="disabled")
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
        """Check both files and show where things stand. Returns True once all are ready."""
        waiting = []
        for part in self.parts:
            row = self.rows[part.key]
            state, problems = part.state()
            if state == "ok":
                text, color, show = f"✓ {part.version()} is set up", theme.current.status_ok, False
            elif state == "missing":
                text, color, show = "not set up yet", theme.current.hint_fg if initial else theme.current.status_bad, True
                waiting.append(part.name)
            else:
                text, color, show = part.wrong_text(problems), theme.current.status_bad, True
                waiting.append(part.name)
            row["state"].configure(text=text, foreground=color)
            if show != row["shown"]:
                if show:
                    row["body"].pack(fill="x")
                else:
                    row["body"].pack_forget()
                row["shown"] = show
        if not waiting:
            self._done()
            return True
        self._set_status(f"Still needed: {' and '.join(waiting)}.", "hint" if initial else "bad")
        return False

    def _done(self):
        self._set_status("Both files are set up. You can build CIAs now.", "ok")
        self._set_auto("disabled")
        self.check_btn.configure(state="disabled")
        self.close_btn.configure(state="normal")
        if self.bar is not None:
            self.bar.configure(value=1000)
        if not self.ready:
            self.ready = True
            self.on_ready()

    def restyle(self):
        theme.set_title_bar(self.win)
        self._set_status(*self._status)
        for lbl in self._warn_labels:
            lbl.configure(bg=theme.current.warn_bg, fg=theme.current.warn_fg)

    def _set_auto(self, state):
        if self.auto_btn is not None:
            self.auto_btn.configure(state=state)

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    # ------------------------------------------------------------------ actions
    def open_folder(self, part):
        os.makedirs(part.folder(), exist_ok=True)
        pu.open_path(part.folder())

    def check_again(self):
        if self.busy():
            return
        for part in self.parts:
            try:
                notes = part.prepare_manual()
            except part.errors as ex:
                self._set_status(f"{part.name}: {ex}", "bad")
                return
            for kind, text in notes:
                self.app.log(kind, text)
        if not self.refresh():
            self.win.bell()

    def start_download(self):
        if self.busy() or not self.auto:
            return
        todo = [p for p in self.parts if p.state()[0] != "ok"]
        if not todo:
            self.refresh()
            return
        self.cancel.clear()
        self._set_auto("disabled")
        self.check_btn.configure(state="disabled")
        self.bar.configure(value=0)
        self._set_status(f"Downloading {todo[0].name} from GitHub…", "busy")
        self.worker = threading.Thread(target=self._work, args=(todo,), daemon=True)
        self.worker.start()

    def _work(self, todo):
        q = self.q
        for part in todo:
            try:
                data = part.fetch(lambda n, total, p=part: q.put(("progress", (p, n, total or p.download_size()))),
                                  self.cancel)
                q.put(("status", f"Checking {part.name}…"))
                part.install(data)
                q.put(("installed", part))
            except OSError as ex:
                reason = getattr(ex, "reason", None) or ex
                q.put(("error", f"Couldn't download {part.name} ({reason}). Check the internet connection, "
                                "or use option 2."))
                return
            except part.errors as ex:
                q.put(("error", f"{part.name}: {ex}"))
                return
        q.put(("done", None))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "progress":
                    part, n, total = data
                    self.bar.configure(value=min(1000, 1000 * n / total))
                    self._set_status(f"Downloading {part.name}… {n / 1048576:.1f} MB", "busy")
                elif kind == "status":
                    self._set_status(data, "busy")
                elif kind == "installed":
                    self.app.log("ok", data.downloaded_log())
                    self.refresh()
                elif kind == "done":
                    self.refresh()
                elif kind == "error":
                    self.bar.configure(value=0)
                    self._set_auto("normal")
                    self.check_btn.configure(state="normal")
                    self._set_status(data, "bad")
        except queue.Empty:
            pass
        self._poll_id = self.win.after(50, self._poll)

    def try_close(self):
        """The close button, Escape and Done: only once both files are set up."""
        if self.ready or self.refresh():
            self.close()
            return
        self.win.bell()
        self._set_status("Both files are needed before this window can close. (Quitting the program still "
                         "works.)", "bad")

    def close(self):
        """Close for real (also used when the program quits)."""
        self.cancel.set()
        try:
            self.win.after_cancel(self._poll_id)
        except tk.TclError:
            pass
        self.win.destroy()
