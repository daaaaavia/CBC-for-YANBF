"""Unique ID options: offset spinner, start field, low-IDs warning, past-max error, persistence."""
import json
import os

from _common import check, finish, isolate, S
import paths
isolate("idopts")

import nds
import settings
FTP = {"ftp_host": "", "ftp_port": 5000, "ftp_cia_dir": "/cias/"}  # FTP defaults (Send to 3DS)


print("settings module")
check(settings.MAX_OFFSET == 3071, "max offset 3071 (FF400 + 3071 = FFFFF)")
check(settings.load() == {"id_start": 0xFF400, "theme": "system", **FTP}, "no file -> default FF400")
vo, vs = settings.validate_offset, settings.validate_id_start
check(vo("0") == (0xFF400, None) and vo("1024") == (0xFF800, None) and vo("3071") == (0xFFFFF, None),
      "offsets 0 / 1024 / 3071 -> FF400 / FF800 / FFFFF")
e = vo("3072")[1]
check(e == "Offset 3072 (ID 100000) is past the highest ID (FFFFF). The largest offset is 3071 (start FFFFF).",
      f"offset 3072 past max: {e}")
check(vo("-1")[1] == "The offset can't be negative" and vo("abc")[1] == "The offset must be a whole number"
      and vo("")[1] == "Enter an offset, e.g. 0", "bad offsets")
check(vs("ff800") == (0xFF800, None) and vs("0xFFFFF") == (0xFFFFF, None), "hex start accepted")
check(vs("FF3FF")[1] == "Must be FF400 or higher (offset 0)", f"start below FF400: {vs('FF3FF')[1]}")
check(vs("100000")[1].startswith("Start 100000 is past the highest ID (FFFFF)"), "start past max")
check(vs("FG")[1] == "Not hexadecimal: invalid character(s) 'G'", "bad hex")
# warning boundary: 19 or fewer IDs left
check(settings.ids_left(settings.ID_DEFAULT_START + 3052) == 20 and settings.low_ids_warning(0xFF400 + 3052) is None,
      "offset 3052 leaves 20 IDs: no warning")
w = settings.low_ids_warning(0xFF400 + 3053)
check(settings.ids_left(0xFF400 + 3053) == 19 and w == "Only 19 IDs left from FFFED to FFFFF: you'll run out after 19 more new games.",
      f"offset 3053 leaves 19: {w}")
check(settings.low_ids_warning(0xFFFFF) == "Only 1 ID left from FFFFF to FFFFF: you'll run out after 1 more new game.",
      "offset 3071 leaves 1 (singular wording)")
settings.save({"id_start": 0xFF600})
check(json.load(open(paths.SETTINGS)) == {"id_start": "0xFF600", "theme": "system", **FTP} and settings.load()["id_start"] == 0xFF600,
      "save/load round trip")
open(paths.SETTINGS, "w").write("{not json")
check(settings.load() == {"id_start": 0xFF400, "theme": "system", **FTP}, "damaged file -> default")
json.dump({"id_start": "0xF8000"}, open(paths.SETTINGS, "w"))
check(settings.load() == {"id_start": 0xFF400, "theme": "system", **FTP}, "saved start below FF400 ignored")
os.remove(paths.SETTINGS)

print("suggestions")
check(nds.suggest_unique_id("AAAA", start=0xFF600) == (0xFF600, False), "empty registry -> start")
nds.record_unique_id("OLDE", 0xFF400)
nds.record_unique_id("OLD2", 0xFF401)
check(nds.suggest_unique_id("NEWE", start=0xFF400) == (0xFF402, False), "default start continues after used")
check(nds.suggest_unique_id("NEWE", start=0xFF600) == (0xFF600, False), "higher start skips to start")
check(nds.suggest_unique_id("OLDE", start=0xFF600) == (0xFF400, True), "already-built game keeps its ID")

print("GUI")
import tkinter as tk
import yanbf_cbc as g
root = tk.Tk()
root.withdraw()
app = g.App(root)
root.update()
btn, ent = app.id_options_btn, app.uid_entry
check(btn.master is ent.master and btn.winfo_manager() == "pack" and btn.pack_info()["side"] == "left",
      "Options… sits on the Unique ID row, right beside the box")
check("next free ID from FF400." in app.uid_caption_var.get(), "caption shows default start")
app.nds_var.set(os.path.join(S, "roms", "Two Lines.nds")); root.update()
check(app.uid_var.get() == "FF402", f"loaded .nds suggestion: {app.uid_var.get()}")

app.open_id_options(); root.update()
d = app.id_options_dialog
spin, start, save = d.offset_spin, d.start_entry, d.save_btn


def spin_type(text):
    spin.delete(0, "end"); spin.insert(0, text); root.update()


def start_type(text):
    start.delete(0, "end"); start.insert(0, text); root.update()


check(spin.get() == "0" and start.get() == "FF400", "opens at offset 0 / FF400")
spin.invoke("buttonup"); spin.invoke("buttonup"); root.update()
check(spin.get() == "2" and start.get() == "FF402", f"arrow up twice -> offset 2, start {start.get()}")
spin.invoke("buttondown"); root.update()
check(spin.get() == "1" and start.get() == "FF401", "arrow down -> offset 1")
spin_type("1024")
check(start.get() == "FF800" and "offset 1024" in d.info_label["text"] and "2,048 IDs left" in d.info_label["text"],
      f"typed offset updates start: {d.info_label['text']!r}")
start_type("FFA00")
check(spin.get() == str(0xFFA00 - 0xFF400), f"typed start updates offset: {spin.get()}")
spin_type("3052")
check(d.warn_label["text"] == "" and d.err_label["text"] == "" and str(save["state"]) == "normal",
      "3052: 20 left, no warning")
spin_type("3053")
check(d.warn_label["text"].startswith("⚠ Only 19 IDs left") and str(save["state"]) == "normal"
      and spin["bg"] == g.WARN_BG, "3053: 19 left -> warning, still savable")
spin_type("3071")
check("Only 1 ID left" in d.warn_label["text"] and start.get() == "FFFFF", "3071 -> FFFFF, 1 left")
spin_type("3072")
check(d.err_label["text"].startswith("Offset 3072 (ID 100000) is past the highest ID")
      and d.warn_label["text"] == "" and str(save["state"]) == "disabled" and spin["bg"] == g.ERR_BG,
      "3072: past-max error, Save disabled")
check(start.get() == "FFFFF", "invalid offset leaves the start field at its last good value")
start_type("100000")
check("is past the highest ID" in d.err_label["text"] and str(save["state"]) == "disabled"
      and start["bg"] == g.ERR_BG, "typed start past max -> error")
spin_type("abc")
check(d.err_label["text"] == "The offset must be a whole number", "non-number offset")
spin_type("3060")
check("Only 12 IDs left" in d.warn_label["text"], "warning again after fixing")
save.invoke(); root.update()
check(not d.winfo_exists() and settings.load(paths.SETTINGS)["id_start"] == 0xFF400 + 3060,
      "Save with a warning works and persists FFFF4")
check(app.uid_var.get() == "FFFF4", f"loaded ROM's fresh ID follows the new start: {app.uid_var.get()}")

app.open_id_options(); root.update()
d2 = app.id_options_dialog
check(d2.offset_spin.get() == "3060" and d2.start_entry.get() == "FFFF4" and "Only 12" in d2.warn_label["text"],
      "reopening shows the saved offset and its warning")
d2.offset_spin.delete(0, "end"); d2.offset_spin.insert(0, "5"); root.update()
d2.destroy(); root.update()  # cancel
check(settings.load(paths.SETTINGS)["id_start"] == 0xFFFF4, "closing without Save keeps the old setting")
root.destroy()

print("persists across program runs")
root = tk.Tk(); root.withdraw()
app2 = g.App(root); root.update()
check(app2.settings["id_start"] == 0xFFFF4 and "from FFFF4" in app2.uid_caption_var.get(),
      "a new App (next program start) loads the saved start")
app2._on_close()

finish()
