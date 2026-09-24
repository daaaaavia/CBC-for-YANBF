"""'Send to 3DS' window: uploads the built .cia and the .nds ROM to the 3DS over
FTP (the 3DS runs ftpd). Both files are listed together so they can go in one go:

  .cia     -> the chosen SD card folder (default /cias/), ready to install with FBI
  .nds ROM -> exactly the 'ROM path on SD card' from the main window, which is
              where the forwarder will look for it

Network work runs on a worker thread (see ftp3ds); results come back through a
queue polled from the Tk loop, like the build.
"""

import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk

import ftp3ds
import paths
import pipeline as pl
import settings
import theme

KEYS = ("cia", "nds")
PROGRESS_CHARS = 48  # width of the progress text beside each bar (size, speed, time left)


class SendWindow:
    def __init__(self, app):
        self.app = app
        root = app.root
        self.q = queue.Queue()
        self.worker = None
        self.cancel = threading.Event()
        self.cia_override = None  # a .cia picked with Choose… instead of the latest build
        self.cur_dir = "/"
        self.connected = None  # (host, port) of the last successful connection
        self._status = ("", "hint")

        win = self.win = tk.Toplevel(root)
        theme.decorate(win)
        win.title("Send to 3DS (FTP)")
        win.transient(root)
        win.minsize(760, 640)
        win.geometry(f"+{root.winfo_rootx() + 120}+{root.winfo_rooty() + 40}")
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda e: self.close())

        base = tkfont.nametofont("TkDefaultFont").actual()
        self.bold = (base["family"], base["size"], "bold")
        f = ttk.Frame(win, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)
        self._build_connection(f)
        self._build_files(f)
        self._build_browser(f)
        self._build_log(f)
        bottom = ttk.Frame(f)
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(bottom, text="Close", command=self.close).pack(side="right")

        self.refresh_files()
        self._set_status("Not connected", "hint")
        self._poll_id = win.after(50, self._poll)
        if not self.host_var.get():
            self.host_entry.focus_set()

    # ------------------------------------------------------------------ layout
    def _entry(self, parent, var, width):
        e = tk.Entry(parent, textvariable=var, width=width, bg=theme.current.field_bg,
                     readonlybackground=theme.current.lock_bg, **theme.current.entry_opts)
        return self.app._reg(e, "entry")

    def _caption(self, parent, text="", **kw):
        lbl = ttk.Label(parent, text=text, foreground=theme.current.caption_fg, justify="left", **kw)
        return self.app._reg(lbl, "caption")

    def _build_connection(self, f):
        box = ttk.LabelFrame(f, text="3DS", padding=10)
        box.grid(row=0, column=0, sticky="ew")
        s = self.app.settings
        self.host_var = tk.StringVar(value=s["ftp_host"])
        self.port_var = tk.StringVar(value=str(s["ftp_port"]))
        ttk.Label(box, text="IP address").grid(row=0, column=0, sticky="w")
        self.host_entry = self._entry(box, self.host_var, 18)
        self.host_entry.grid(row=0, column=1, sticky="w", padx=(6, 12), ipady=2)
        ttk.Label(box, text="Port").grid(row=0, column=2, sticky="w")
        self.port_entry = self._entry(box, self.port_var, 7)
        self.port_entry.grid(row=0, column=3, sticky="w", padx=(6, 12), ipady=2)
        self.connect_btn = ttk.Button(box, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=4, sticky="w")
        self.status_label = ttk.Label(box, text="", font=theme.current.font_status)
        self.status_label.grid(row=0, column=5, sticky="w", padx=(12, 0))
        box.columnconfigure(5, weight=1)
        self._caption(box, "Start ftpd on the 3DS - it shows the IP address and port (usually 5000). "
                           "The PC and the 3DS must be on the same network.",
                      wraplength=700).grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        for e in (self.host_entry, self.port_entry):
            e.bind("<Return>", lambda ev: self.connect())

    def _build_files(self, f):
        box = ttk.LabelFrame(f, text="Files to send", padding=10)
        box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(2, weight=1)
        self.rows = {}
        self.cia_dir_var = tk.StringVar(value=self.app.settings["ftp_cia_dir"])
        self.cia_dir_var.trace_add("write", lambda *_: self.refresh_files())
        r = 0
        for key, title in (("cia", "CIA"), ("nds", "NDS ROM")):
            if r:
                ttk.Separator(box).grid(row=r, column=0, columnspan=4, sticky="ew", pady=8)
                r += 1
            row = {"var": tk.BooleanVar(value=True)}
            row["check"] = ttk.Checkbutton(box, text=title, variable=row["var"], command=self._update_send_state)
            row["check"].grid(row=r, column=0, sticky="nw")
            row["name"] = ttk.Label(box, text="", font=self.bold)
            row["name"].grid(row=r, column=1, columnspan=2, sticky="w", padx=(10, 0))
            row["choose"] = ttk.Button(box, text="Choose…", width=9,
                                       command=self._choose_cia if key == "cia" else self._choose_nds)
            row["choose"].grid(row=r, column=3, sticky="e", padx=(6, 0))
            r += 1
            ttk.Label(box, text="From").grid(row=r, column=1, sticky="nw", padx=(10, 6))
            row["src"] = self._caption(box, wraplength=560)
            row["src"].grid(row=r, column=2, columnspan=2, sticky="w")
            r += 1
            ttk.Label(box, text="To").grid(row=r, column=1, sticky="nw", padx=(10, 6), pady=(4, 0))
            dest = ttk.Frame(box)
            dest.grid(row=r, column=2, columnspan=2, sticky="ew", pady=(4, 0))
            if key == "cia":
                self.cia_dir_entry = self._entry(dest, self.cia_dir_var, 22)
                self.cia_dir_entry.pack(side="left", ipady=1)
                row["dest"] = self._caption(dest)
                row["dest"].pack(side="left", padx=(6, 0))
            else:
                row["dest"] = ttk.Label(dest, text="")
                row["dest"].pack(side="left")
            r += 1
            row["note"] = self._caption(box, wraplength=600)
            row["note"].grid(row=r, column=2, columnspan=2, sticky="w")
            r += 1
            prog = ttk.Frame(box)
            prog.grid(row=r, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=(4, 0))
            prog.columnconfigure(0, weight=1)
            row["bar"] = ttk.Progressbar(prog, maximum=1000, value=0)
            row["bar"].grid(row=0, column=0, sticky="ew")
            # wide enough for the longest text, e.g. "1023.9 MB / 1023.9 MB  ·  1023.9 KB/s  ·  59:59 left"
            row["prog"] = self._caption(prog, width=PROGRESS_CHARS)
            row["prog"].grid(row=0, column=1, sticky="w", padx=(8, 0))
            r += 1
            self.rows[key] = row

        bar = ttk.Frame(box)
        bar.grid(row=r, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self.send_btn = ttk.Button(bar, text="Send to 3DS", style="Accent.TButton", command=self.send)
        self.send_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self.cancel_transfer, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.send_status = ttk.Label(bar, text="")
        self.send_status.pack(side="left", padx=(12, 0))

    def _build_browser(self, f):
        box = ttk.LabelFrame(f, text="3DS SD card", padding=10)
        box.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        nav = ttk.Frame(box)
        nav.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.up_btn = ttk.Button(nav, text="Up", width=5, command=self.go_up)
        self.up_btn.pack(side="left")
        self.path_label = ttk.Label(nav, text="(connect to browse)", font=self.bold)
        self.path_label.pack(side="left", padx=(8, 0))
        self.refresh_btn = ttk.Button(nav, text="Refresh", command=lambda: self.list_dir(self.cur_dir))
        self.refresh_btn.pack(side="right")
        self.mkdir_btn = ttk.Button(nav, text="New folder…", command=self.new_folder)
        self.mkdir_btn.pack(side="right", padx=(0, 6))
        self.use_dir_btn = ttk.Button(nav, text="Send CIAs to this folder", command=self.use_folder_for_cia)
        self.use_dir_btn.pack(side="right", padx=(0, 6))
        self.tree = ttk.Treeview(box, columns=("size",), height=7, selectmode="browse")
        self.tree.heading("#0", text="Name", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.column("#0", width=480, stretch=True)
        self.tree.column("size", width=110, anchor="e", stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self._on_tree_open)
        self.tree.bind("<Return>", self._on_tree_open)
        self._set_browse_state()

    def _build_log(self, f):
        box = ttk.Frame(f)
        box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(0, weight=1)
        t = self.log_text = self.app._reg(
            tk.Text(box, height=5, font=theme.current.font_mono, wrap="word", state="disabled",
                    **theme.current.text_opts), "log")
        t.grid(row=0, column=0, sticky="ew")
        sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
        sb.grid(row=0, column=1, sticky="ns")
        t.configure(yscrollcommand=sb.set)
        for tag, opts in theme.current.log_tags.items():
            t.tag_configure(tag, **opts)

    # ------------------------------------------------------------------ files
    def cia_source(self):
        """The .cia to send: one picked with Choose…, else this session's last build,
        else the build for the main window's current fields if it's in output/."""
        if self.cia_override:
            return self.cia_override, "chosen"
        last = getattr(self.app, "last_cia", None)
        if last and os.path.isfile(last):
            return last, "latest build"
        name = pl.output_name(self.app.rom_var.get(), self.app.title_var.get().strip())
        guess = os.path.join(paths.OUTPUT_DIR, name, name + ".cia")
        if os.path.isfile(guess):
            return guess, "built earlier"
        return None, None

    def nds_source(self):
        p = self.app.nds_var.get().strip()
        return (p, None) if p and os.path.isfile(p) else (None, p)

    def targets(self):
        """{key: (local, remote) or None} for the files that can be sent right now."""
        out = {}
        cia, _ = self.cia_source()
        folder = ftp3ds.normalize_dir(self.cia_dir_var.get())
        out["cia"] = (cia, folder + os.path.basename(cia)) if cia else None
        rom, _ = self.nds_source()
        dest = ftp3ds.sd_path(self.app.rom_var.get())
        out["nds"] = (rom, dest) if rom and dest else None
        return out

    def refresh_files(self):
        """Update both file rows from the main window (called whenever its fields change)."""
        if not self.win.winfo_exists():
            return
        tg = self.targets()
        # CIA
        row = self.rows["cia"]
        cia, how = self.cia_source()
        folder = ftp3ds.normalize_dir(self.cia_dir_var.get())
        if cia:
            row["name"].configure(text=f"{os.path.basename(cia)}   ({ftp3ds.human_size(_size(cia))}, {how})")
            row["src"].configure(text=cia)
            row["dest"].configure(text=f"→ {folder}{os.path.basename(cia)}")
            row["note"].configure(text="Install it on the 3DS with FBI (SD → cias).")
        else:
            row["name"].configure(text="No .cia yet")
            row["src"].configure(text="Build one in the main window, or Choose… an existing .cia.")
            row["dest"].configure(text=f"→ {folder}")
            row["note"].configure(text="")
        # NDS
        row = self.rows["nds"]
        rom, typed = self.nds_source()
        dest = ftp3ds.sd_path(self.app.rom_var.get())
        if rom:
            row["name"].configure(text=f"{os.path.basename(rom)}   ({ftp3ds.human_size(_size(rom))})")
            row["src"].configure(text=rom)
        else:
            row["name"].configure(text="No .nds selected")
            row["src"].configure(text=(f"Not found: {typed}" if typed else
                                       "Pick the ROM in the main window's NDS ROM box, or Choose… one here."))
        row["dest"].configure(text=dest or "(set 'ROM path on SD card' in the main window)")
        note = "The 'ROM path on SD card' from the main window - where the forwarder looks for the ROM."
        if rom and dest and os.path.basename(dest).lower() != os.path.basename(rom).lower():
            note += " The file is renamed to match it."
        row["note"].configure(text=note)
        for key in KEYS:
            if tg[key] is None:
                self.rows[key]["check"].state(["disabled"])
            else:
                self.rows[key]["check"].state(["!disabled"])
        self._update_send_state()

    def _choose_cia(self):
        start = os.path.dirname(self.cia_source()[0] or "") or paths.OUTPUT_DIR
        p = filedialog.askopenfilename(parent=self.win, title="Choose a .cia to send", initialdir=start,
                                       filetypes=[("CIA", "*.cia"), ("All files", "*.*")])
        if p:
            self.cia_override = os.path.normpath(p)
            self.rows["cia"]["var"].set(True)
            self.refresh_files()

    def _choose_nds(self):
        p = filedialog.askopenfilename(parent=self.win, title="Choose NDS ROM",
                                       filetypes=[("NDS ROM", "*.nds"), ("All files", "*.*")])
        if p:  # same as picking it in the main window, so the CIA fields and ROM path match it
            self.app.nds_var.set(os.path.normpath(p))
            self.rows["nds"]["var"].set(True)
            self.log("info", f"NDS ROM set to {os.path.basename(p)} (main window fields filled in from it)")
            self.refresh_files()

    def selected(self):
        tg = self.targets()
        return [(k, *tg[k]) for k in KEYS if tg[k] and self.rows[k]["var"].get()]

    # ------------------------------------------------------------------ state
    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def _update_send_state(self):
        if not self.win.winfo_exists():
            return
        n = len(self.selected())
        busy = self.busy()
        self.send_btn.configure(state="normal" if n and not busy else "disabled",
                                text="Send to 3DS" if n != 2 else "Send both to 3DS")
        self.connect_btn.configure(state="disabled" if busy else "normal")
        for key in KEYS:
            self.rows[key]["choose"].configure(state="disabled" if busy else "normal")
        self.cia_dir_entry.configure(state="disabled" if busy else "normal")
        self._set_browse_state()

    def _set_browse_state(self):
        ok = self.connected is not None and not self.busy()
        for b in (self.refresh_btn, self.mkdir_btn, self.use_dir_btn):
            b.configure(state="normal" if ok else "disabled")
        self.up_btn.configure(state="normal" if ok and self.cur_dir != "/" else "disabled")

    def _set_status(self, text, kind):
        self._status = (text, kind)
        color = {"ok": theme.current.status_ok, "bad": theme.current.status_bad,
                 "busy": theme.current.status_busy, "hint": theme.current.hint_fg}[kind]
        self.status_label.configure(text=text, foreground=color)

    def restyle(self):
        """Theme switched: fix the colours set directly on widgets."""
        theme.set_title_bar(self.win)
        self._set_status(*self._status)
        for tag, opts in theme.current.log_tags.items():
            self.log_text.tag_configure(tag, **opts)

    def log(self, tag, text):
        t = self.log_text
        t.configure(state="normal")
        t.insert("end", text + "\n", tag)
        t.see("end")
        t.configure(state="disabled")

    # ------------------------------------------------------------------ connection
    def _server(self):
        host, e = ftp3ds.parse_host(self.host_var.get())
        if e:
            return None, e
        port, e = ftp3ds.parse_port(self.port_var.get())
        if e:
            return None, e
        return (host, port), None

    def _remember(self, host, port):
        new = dict(self.app.settings, ftp_host=host, ftp_port=port,
                   ftp_cia_dir=ftp3ds.normalize_dir(self.cia_dir_var.get()))
        if new != self.app.settings:
            try:
                settings.save(new)
                self.app.settings = new
            except OSError as ex:
                self.log("warn", f"Couldn't save settings.json: {ex}")

    def _run(self, fn, *args):
        """Run fn(*args) on the worker thread; it reports through self.q."""
        self.cancel.clear()
        self.worker = threading.Thread(target=fn, args=args, daemon=True)
        self.worker.start()
        self._update_send_state()

    def connect(self):
        if self.busy():
            return
        server, e = self._server()
        if e:
            self._set_status(e, "bad")
            self.win.bell()
            return
        self._remember(*server)
        self._set_status(f"Connecting to {server[0]}:{server[1]}…", "busy")
        self._run(self._w_list, server, self.cur_dir if self.connected == server else "/", True)

    def list_dir(self, path):
        if self.busy() or self.connected is None:
            return
        self._run(self._w_list, self.connected, path, False)

    def go_up(self):
        if self.cur_dir != "/":
            self.list_dir(ftp3ds.normalize_dir(self.cur_dir.rstrip("/").rsplit("/", 1)[0]))

    def _on_tree_open(self, event=None):
        sel = self.tree.selection()
        if sel and self.tree.item(sel[0], "values")[0] == "":  # folders have no size
            self.list_dir(self.cur_dir + self.tree.item(sel[0], "text").rstrip("/") + "/")

    def new_folder(self):
        if self.busy() or self.connected is None:
            return
        name = simpledialog.askstring("New folder", f"New folder in {self.cur_dir}:", parent=self.win)
        name = (name or "").strip().strip("/")
        if not name:
            return
        if any(c in name for c in '\\/:*?"<>|'):
            messagebox.showerror("New folder", "A folder name can't contain \\ / : * ? \" < > |", parent=self.win)
            return
        self._run(self._w_mkdir, self.connected, self.cur_dir + name)

    def use_folder_for_cia(self):
        self.cia_dir_var.set(self.cur_dir)
        self.log("info", f"CIAs will be sent to {self.cur_dir}")

    # ------------------------------------------------------------------ sending
    def send(self):
        if self.busy():
            return
        items = self.selected()
        if not items:
            return
        server, e = self._server()
        if e:
            self._set_status(e, "bad")
            self.win.bell()
            return
        self._remember(*server)
        for key in KEYS:
            self.rows[key]["bar"].configure(value=0)
            self.rows[key]["prog"].configure(text="")
        self.send_status.configure(text="Checking the SD card…")
        self._run(self._w_check, server, items)

    def _start_upload(self, server, items, existing):
        if existing:
            lines = "\n".join(f"{path}  ({ftp3ds.human_size(size)})" for path, size in existing)
            if not messagebox.askyesno("Replace files on the 3DS?",
                                       "These files are already on the 3DS SD card:\n\n" + lines +
                                       "\n\nReplace them?", parent=self.win):
                self.send_status.configure(text="Nothing sent")
                return
        for key, local, remote in items:
            self.rows[key]["prog"].configure(text="Waiting…")
        self._run(self._w_upload, server, items)

    def cancel_transfer(self):
        if self.busy():
            self.cancel.set()
            self.send_status.configure(text="Cancelling…")

    # ------------------------------------------------------------------ worker side
    def _w_list(self, server, path, first):
        q = self.q
        try:
            ftp = ftp3ds.connect(*server)
            try:
                welcome = (ftp.getwelcome() or "").split("\n")[0]
                try:
                    entries = ftp3ds.listdir(ftp, path)
                except ftp3ds.ftplib.error_perm:
                    if path == "/":
                        raise
                    path = "/"
                    entries = ftp3ds.listdir(ftp, path)
            finally:
                ftp3ds.close(ftp)
            q.put(("listed", (server, path, entries, welcome if first else None)))
        except Exception as ex:
            q.put(("conn_error", (server, ftp3ds.describe_error(ex))))

    def _w_mkdir(self, server, path):
        q = self.q
        try:
            ftp = ftp3ds.connect(*server)
            try:
                ftp.mkd(path)
                parent = ftp3ds.normalize_dir(path.rsplit("/", 1)[0])
                entries = ftp3ds.listdir(ftp, parent)
            finally:
                ftp3ds.close(ftp)
            q.put(("log", ("ok", f"Created {path}")))
            q.put(("listed", (server, parent, entries, None)))
        except Exception as ex:
            q.put(("log", ("err", f"Couldn't create {path}: {ftp3ds.describe_error(ex)}")))
            q.put(("idle", None))

    def _w_check(self, server, items):
        q = self.q
        try:
            ftp = ftp3ds.connect(*server)
            try:
                existing = []
                for key, local, remote in items:
                    size = ftp3ds.remote_size(ftp, remote)
                    if size is not None:
                        existing.append((remote, size))
            finally:
                ftp3ds.close(ftp)
            q.put(("checked", (server, items, existing)))
        except Exception as ex:
            q.put(("conn_error", (server, ftp3ds.describe_error(ex))))
            q.put(("send_done", (0, len(items), False)))

    def _w_upload(self, server, items):
        q = self.q
        sent_ok = failed = 0
        cancelled = False
        try:
            ftp = ftp3ds.connect(*server)
        except Exception as ex:
            q.put(("conn_error", (server, ftp3ds.describe_error(ex))))
            q.put(("send_done", (0, len(items), False)))
            return
        q.put(("connected", server))
        try:
            for key, local, remote in items:
                if self.cancel.is_set():
                    cancelled = True
                    q.put(("file", (key, "cancelled", "Not sent")))
                    continue
                rate = ftp3ds.Rate()
                last = [0.0]

                def progress(sent, total, key=key, rate=rate, last=last):
                    now = time.monotonic()
                    bps = rate.update(sent)
                    if now - last[0] >= 0.1 or sent == total:
                        last[0] = now
                        q.put(("progress", (key, sent, total, bps)))

                q.put(("log", ("info", f"Sending {os.path.basename(local)} → {remote}")))
                t0 = time.monotonic()
                try:
                    total = ftp3ds.upload(ftp, local, remote, progress, self.cancel)
                    secs = max(time.monotonic() - t0, 0.001)
                    sent_ok += 1
                    q.put(("file", (key, "ok", f"Done - {ftp3ds.human_size(total)} in {secs:.1f} s "
                                               f"({ftp3ds.human_size(total / secs)}/s)")))
                    q.put(("log", ("ok", f"Sent {remote}")))
                except ftp3ds.Cancelled:
                    cancelled = True
                    q.put(("file", (key, "cancelled", "Cancelled - partial file removed")))
                    q.put(("log", ("warn", f"Cancelled {remote} (the partial file was removed)")))
                except Exception as ex:
                    failed += 1
                    q.put(("file", (key, "err", "Failed")))
                    q.put(("log", ("err", f"{remote}: {ftp3ds.describe_error(ex)}")))
                    try:  # the connection may be broken; carry on with a fresh one
                        ftp3ds.close(ftp)
                        ftp = ftp3ds.connect(*server)
                    except Exception as ex2:
                        q.put(("conn_error", (server, ftp3ds.describe_error(ex2))))
                        break
        finally:
            ftp3ds.close(ftp)
        q.put(("send_done", (sent_ok, failed, cancelled)))

    # ------------------------------------------------------------------ results (Tk side)
    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                getattr(self, "_on_" + kind)(data)
        except queue.Empty:
            pass
        self._poll_id = self.win.after(50, self._poll)

    def _after_worker(self):
        # the worker may not have quite finished yet; update the buttons once it has
        if self.busy():
            self.win.after(30, self._after_worker)
        else:
            self._update_send_state()

    def _on_log(self, data):
        self.log(*data)

    def _on_idle(self, data):
        self._after_worker()

    def _on_connected(self, server):
        self.connected = server
        self._set_status(f"Connected - {server[0]}:{server[1]}", "ok")

    def _on_listed(self, data):
        server, path, entries, welcome = data
        first = self.connected != server
        self._on_connected(server)
        if welcome is not None and first:
            self.log("ok", f"Connected to {server[0]}:{server[1]}" + (f" ({welcome})" if welcome else ""))
        self.cur_dir = path
        self.path_label.configure(text=path)
        self.tree.delete(*self.tree.get_children())
        for name, is_dir, size in entries:
            self.tree.insert("", "end", text=(name + "/") if is_dir else name,
                             values=("" if is_dir else ftp3ds.human_size(size),))
        self._after_worker()

    def _on_conn_error(self, data):
        server, msg = data
        self.connected = None
        self._set_status("Not connected", "bad")
        self.log("err", f"{server[0]}:{server[1]} - {msg}")
        self._after_worker()

    def _on_checked(self, data):
        server, items, existing = data
        self._on_connected(server)
        self.worker = None
        self._start_upload(server, items, existing)
        if not self.busy():
            self._update_send_state()

    def _on_progress(self, data):
        key, sent, total, bps = data
        row = self.rows[key]
        row["bar"].configure(value=1000 * sent / total if total else 1000)
        text = f"{ftp3ds.human_size(sent)} / {ftp3ds.human_size(total)}"
        if bps:
            text += f"  ·  {ftp3ds.human_size(bps)}/s"
            if sent < total:
                text += f"  ·  {_eta((total - sent) / bps)} left"
        row["prog"].configure(text=text)
        self.send_status.configure(text=f"Sending {os.path.basename(self.targets()[key][0]) if self.targets()[key] else ''}…")
        self.cancel_btn.configure(state="normal")

    def _on_file(self, data):
        key, result, text = data
        row = self.rows[key]
        if result == "ok":
            row["bar"].configure(value=1000)
        else:
            row["bar"].configure(value=0)
        row["prog"].configure(text=text)

    def _on_send_done(self, data):
        ok, failed, cancelled = data
        self.cancel_btn.configure(state="disabled")
        if cancelled:
            text = f"Cancelled ({ok} sent)" if ok else "Cancelled"
        elif failed:
            text = f"{failed} failed" + (f", {ok} sent" if ok else "") + " - see below"
        else:
            text = f"Sent {ok} file{'s' if ok != 1 else ''} to the 3DS"
            self.app.log("ok", f"Sent {ok} file{'s' if ok != 1 else ''} to the 3DS over FTP")
        self.send_status.configure(text=text)
        self._after_worker()
        if ok and self.connected:  # show what arrived
            self.win.after(50, lambda: self.list_dir(self.cur_dir))

    # ------------------------------------------------------------------ closing
    def close(self):
        if self.busy():
            if not messagebox.askyesno("Send to 3DS", "A transfer is running. Cancel it and close?",
                                       parent=self.win):
                return
            self.cancel.set()
        try:
            self.win.after_cancel(self._poll_id)
        except tk.TclError:
            pass
        self.win.destroy()


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _eta(seconds):
    """'42 s', '3:05' or '1:02:05' (h:mm:ss)."""
    s = int(seconds + 0.5)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"
