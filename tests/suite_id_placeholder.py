"""Grey next-free-ID preview inside the empty Unique ID box."""
import os

from _common import check, finish, isolate, S
isolate("placeholder")

import nds


import tkinter as tk
import yanbf_cbc as g
root = tk.Tk()
root.withdraw()
app = g.App(root)
root.update()
ph = app.uid_placeholder
shown = lambda: ph.winfo_manager() == "place"

check(shown() and ph["text"] == "FF400  (next free ID)", f"empty box previews FF400: {ph['text']!r}")
check(str(ph.place_info().get("in")) == str(app.uid_entry), "drawn inside the Unique ID box")
check(app.uid_var.get() == "" and "unique ID" in app.status_var.get(), "preview isn't a value: Build still needs an ID")
app.uid_var.set("F"); root.update()
check(not shown(), "hidden as soon as you type")
app.uid_var.set(""); root.update()
check(shown(), "back when the box is emptied again")

# a build recorded an ID -> preview moves on
nds.record_unique_id("AAAE", 0xFF400)
nds.record_unique_id("BBBE", 0xFF401)
app.validate(); root.update()
check(ph["text"] == "FF402  (next free ID)", f"updates after IDs are used: {ph['text']!r}")

# changing the start in Options updates it
app.open_id_options(); root.update()
d = app.id_options_dialog
d.offset_spin.delete(0, "end"); d.offset_spin.insert(0, "256"); root.update()
d.save_btn.invoke(); root.update()
check(ph["text"] == "FF500  (next free ID)", f"follows the Options start: {ph['text']!r}")

# a loaded .nds fills the box -> preview hidden
app.nds_var.set(os.path.join(S, "roms", "Two Lines.nds")); root.update()
check(app.uid_var.get() == "FF500" and not shown(), "hidden when a .nds fills the ID")
app.nds_var.set(""); root.update()
app.uid_var.set(""); root.update()
check(shown() and ph["text"] == "FF500  (next free ID)", "shown again after clearing")

# clicking the preview focuses the box
root.deiconify(); root.update()
ph.event_generate("<Button-1>"); root.update()
check(root.focus_get() is app.uid_entry, "clicking the preview puts the cursor in the box")

# placeholder matches the box background
check(ph["bg"] == app.uid_entry["bg"], "same background as the box")
app._on_close()
finish()
