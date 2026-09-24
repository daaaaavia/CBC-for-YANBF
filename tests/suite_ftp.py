"""Send to 3DS (FTP): ftp3ds against a real local FTP server, then the window end to end."""
import logging
import os
import shutil
import threading
import time

from _common import check, finish, isolate, S
isolate("ftp")
import settings
import ftp3ds
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler, ThrottledDTPHandler
from pyftpdlib.servers import FTPServer
logging.getLogger("pyftpdlib").setLevel(logging.ERROR)



SD = os.path.join(S, "ftp_sd")
shutil.rmtree(SD, ignore_errors=True)
os.makedirs(SD)


def serve(read_limit=0):
    auth = DummyAuthorizer()
    auth.add_anonymous(SD, perm="elradfmwMT")
    dtp = ThrottledDTPHandler
    dtp.read_limit = read_limit
    h = type("H", (FTPHandler,), {"authorizer": auth, "dtp_handler": dtp, "banner": "ftpd test"})
    srv = FTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
    return srv, srv.socket.getsockname()[1]


srv, PORT = serve()
big = os.path.join(S, "ftp_big.bin")
with open(big, "wb") as f:
    f.write(os.urandom(3 * 1024 * 1024 + 123))

print("parsing")
check(ftp3ds.parse_host(" 192.168.1.20 ") == ("192.168.1.20", None), "plain IP")
check(ftp3ds.parse_host("ftp://192.168.1.20:5000/") == ("192.168.1.20", None), "pasted ftp:// URL with port")
check(ftp3ds.parse_host("")[1] is not None and ftp3ds.parse_host("1.2 .3")[1] is not None, "empty / spaces rejected")
check(ftp3ds.parse_port("5000") == (5000, None) and ftp3ds.parse_port("x")[1] and ftp3ds.parse_port("70000")[1],
      "port parsing")
check(ftp3ds.normalize_dir("cias") == "/cias/" and ftp3ds.normalize_dir("sd:\\a\\b\\") == "/a/b/"
      and ftp3ds.normalize_dir("") == "/", "folder normalizing")
check(ftp3ds.sd_path("sd:/roms/nds/G.nds") == "/roms/nds/G.nds" and ftp3ds.sd_path("roms/x.nds") == "/roms/x.nds",
      "ROM path -> FTP path")

print("ftp3ds against a local server")
ftp = ftp3ds.connect("127.0.0.1", PORT)
seen = []
n = ftp3ds.upload(ftp, big, "/a/b/big.bin", lambda s, t: seen.append((s, t)))
check(n == os.path.getsize(big) and open(os.path.join(SD, "a", "b", "big.bin"), "rb").read() == open(big, "rb").read(),
      "uploads into new nested folders, byte-identical")
check(seen[0] == (0, n) and seen[-1] == (n, n) and len(seen) > 10, f"progress reported ({len(seen)} updates)")
check(not os.path.exists(os.path.join(SD, "a", "b", "big.bin.part")), "no .part left behind")
check(ftp3ds.remote_size(ftp, "/a/b/big.bin") == n and ftp3ds.remote_size(ftp, "/a/b/nope") is None, "remote_size")
small = os.path.join(S, "ftp_small.bin")
open(small, "wb").write(b"new")
ftp3ds.upload(ftp, small, "/a/b/big.bin")
check(open(os.path.join(SD, "a", "b", "big.bin"), "rb").read() == b"new", "replaces an existing file")
ls = ftp3ds.listdir(ftp, "/a/")
check(ls == [("b", True, None)], f"listdir: {ls}")
ftp3ds.close(ftp)
srv.close_all()

print("cancel mid-transfer (throttled server)")
srv, PORT2 = serve(read_limit=400 * 1024)
ftp = ftp3ds.connect("127.0.0.1", PORT2)
cancel = threading.Event()
threading.Timer(0.8, cancel.set).start()
try:
    ftp3ds.upload(ftp, big, "/c/big.bin", None, cancel)
    check(False, "cancel raises Cancelled")
except ftp3ds.Cancelled:
    check(True, "cancel raises Cancelled")
time.sleep(0.5)
left = os.listdir(os.path.join(SD, "c"))
check(left == [], f"cancelled upload leaves nothing (found {left})")
ftp3ds.close(ftp)
srv.close_all()

print("errors")
try:
    ftp3ds.connect("127.0.0.1", PORT2, timeout=3)
    check(False, "refused")
except Exception as ex:
    msg = ftp3ds.describe_error(ex)
    check("refused" in msg.lower() or "timed out" in msg.lower(), f"plain message: {msg}")

# ------------------------------------------------------------------ GUI
print("Send to 3DS window")
srv, PORT = serve()
import tkinter as tk
import yanbf_cbc as g
from tkinter import messagebox
root = tk.Tk(); root.withdraw()
app = g.App(root); root.update()


def pump(cond, secs=15):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.02)
        if cond():
            return True
    return False


nds_path = os.path.join(S, "roms", "Grand Theft Auto - Chinatown Wars (USA).nds")
app.nds_var.set(nds_path); root.update()
cia = os.path.join(S, "ftp_test.cia")
open(cia, "wb").write(os.urandom(500_000))
app.last_cia = cia
app.open_send_window(); root.update()
w = app.ftp_win
check(w.win.winfo_exists() and w.win.title() == "Send to 3DS (FTP)", "opens")
check(w.rows["cia"]["name"].cget("text").startswith("ftp_test.cia"), "shows the .cia: " + w.rows["cia"]["name"].cget("text"))
check(w.rows["nds"]["name"].cget("text").startswith("Grand Theft Auto"), "shows the .nds: " + w.rows["nds"]["name"].cget("text"))
rom_dest = app.rom_var.get()
check(w.rows["nds"]["dest"].cget("text") == ftp3ds.sd_path(rom_dest), f"ROM goes to the ROM path field ({rom_dest})")
check(str(w.send_btn.cget("text")) == "Send both to 3DS" and "disabled" not in str(w.send_btn.cget("state")), "both ticked -> Send both")
app.rom_var.set("/roms/nds/Renamed.nds"); root.update()
check(w.rows["nds"]["dest"].cget("text") == "/roms/nds/Renamed.nds" and "renamed" in w.rows["nds"]["note"].cget("text"),
      "follows edits to the ROM path, and says it's renamed")
app.open_send_window(); root.update()
check(app.ftp_win is w, "Send to 3DS… again brings the same window forward")

w.host_var.set("127.0.0.1"); w.port_var.set(str(PORT))
os.makedirs(os.path.join(SD, "cias"), exist_ok=True)
w.connect()
check(pump(lambda: w.connected is not None and not w.busy()), "connects")
names = [w.tree.item(i, "text") for i in w.tree.get_children()]
check("cias/" in names, f"browser lists the SD card root: {names}")
check(settings.load()["ftp_host"] == "127.0.0.1" and settings.load()["ftp_port"] == PORT, "IP and port saved")

asked = []
messagebox.askyesno = lambda *a, **k: (asked.append(a), True)[1]
w.send()
check(pump(lambda: "Sent 2 files" in w.send_status.cget("text"), 20), "sends both: " + w.send_status.cget("text"))
check(open(os.path.join(SD, "cias", "ftp_test.cia"), "rb").read() == open(cia, "rb").read(), ".cia arrived in /cias/")
check(open(os.path.join(SD, "roms", "nds", "Renamed.nds"), "rb").read() == open(nds_path, "rb").read(),
      ".nds arrived at the ROM path")
check(asked == [], "no replace prompt for new files")
check(float(w.rows["cia"]["bar"].cget("value")) == 1000 and "Done" in w.rows["nds"]["prog"].cget("text"), "progress complete")

w.send()
check(pump(lambda: len(asked) == 1 and not w.busy() and "Sent 2" in w.send_status.cget("text"), 20) or bool(asked),
      "sending again asks before replacing")
check(asked and "Renamed.nds" in asked[0][1] and "ftp_test.cia" in asked[0][1], "prompt lists both files")
pump(lambda: not w.busy(), 10)
asked.clear()
messagebox.askyesno = lambda *a, **k: (asked.append(a), False)[1]
w.send()
pump(lambda: bool(asked) and not w.busy(), 10); root.update()
check(w.send_status.cget("text") == "Nothing sent", "saying No sends nothing")

w.rows["nds"]["var"].set(False); w._update_send_state()
check(str(w.send_btn.cget("text")) == "Send to 3DS", "untick one -> single send")
w.cia_dir_var.set("games/3ds")
check(w.rows["cia"]["dest"].cget("text") == "→ /games/3ds/ftp_test.cia", "CIA folder edit shows the full path")
messagebox.askyesno = lambda *a, **k: True
w.send()
check(pump(lambda: "Sent 1 file " in w.send_status.cget("text") or w.send_status.cget("text").endswith("Sent 1 file to the 3DS"), 20),
      "sends just the CIA: " + w.send_status.cget("text"))
check(os.path.isfile(os.path.join(SD, "games", "3ds", "ftp_test.cia")), "into the new CIA folder (created)")
check(settings.load()["ftp_cia_dir"] == "/games/3ds/", "CIA folder saved")
pump(lambda: not w.busy(), 5)

w.list_dir("/games/"); pump(lambda: w.cur_dir == "/games/" and not w.busy())
check([w.tree.item(i, "text") for i in w.tree.get_children()] == ["3ds/"], "browse into a folder")
w.go_up(); pump(lambda: w.cur_dir == "/" and not w.busy())
check(w.cur_dir == "/", "Up")

print("progress text fits (window at its minimum size)")
import tkinter.font as tkfont
root.deiconify(); w.win.deiconify(); w.win.geometry(f"{w.win.minsize()[0]}x640")  # shown for real: hidden windows have no width
for _ in range(5):
    root.update()
worst = [  # (sent, total, bytes/s) giving the longest texts: sizes up to 1023.9 MB, slow speeds -> h:mm:ss left
    (1073636966, 1073636966 * 1.0, 1048371), (104857600, 1073636966, 1048371), (1023 * 1024, 1073636966, 1023 * 1024),
    (1023 * 1024, 1073636966, 100 * 1024), (500, 1073636966, 900.5),
]
from ftp_window import _eta
check((_eta(42), _eta(185), _eta(3725), _eta(1192331)) == ("42 s", "3:05", "1:02:05", "331:12:11"),
      "time left: s, m:ss, then h:mm:ss")
for key in ("cia", "nds"):
    lbl = w.rows[key]["prog"]
    font = tkfont.Font(font=lbl.cget("font") or "TkDefaultFont")
    for sent, total, bps in worst:
        w._on_progress((key, sent, int(total), bps)); root.update()
        text = lbl.cget("text")
        check(font.measure(text) <= lbl.winfo_width(), f"{key}: fits ({font.measure(text)} <= {lbl.winfo_width()} px): {text}")
    w._on_file((key, "ok", f"Done - {ftp3ds.human_size(1073636966)} in 1234.5 s ({ftp3ds.human_size(1023 * 1024)}/s)"))
    root.update()
    text = lbl.cget("text")
    check(font.measure(text) <= lbl.winfo_width(), f"{key}: done message fits: {text}")
    check(w.rows[key]["bar"].winfo_width() >= 200, f"{key}: progress bar still {w.rows[key]['bar'].winfo_width()} px wide")

print("theme switch with the window open")
app.theme_var.set("Dark"); app._on_theme_pick(); root.update()
check(w.host_entry.cget("bg") == g.theme.DARK.field_bg, "entries follow the theme")
app.theme_var.set("Light"); app._on_theme_pick(); root.update()

print("no .cia / wrong port")
app.last_cia = None
app.nds_var.set(""); root.update()
w.rows["nds"]["var"].set(True)
check(w.rows["cia"]["name"].cget("text") == "No .cia yet" and "disabled" in w.send_btn.state(), "nothing to send -> disabled")
w.port_var.set(str(PORT2)); w.connect()
check(pump(lambda: w.connected is None and not w.busy() and "Not connected" in w.status_label.cget("text")),
      "bad port -> Not connected")
log = w.log_text.get("1.0", "end")
check("refused" in log.lower() or "timed out" in log.lower(), "explains why in the log")

w.close(); root.update()
check(not w.win.winfo_exists(), "closes")
app._on_close()
srv.close_all()
finish()
