"""The .nds input: header parsing, field filling and locking, and the Unique ID registry."""
import os

from _common import FAKE_TOOLS, S, check, finish, isolate
import nds
import pipeline as pl

isolate("nds")
ROMS = os.path.join(S, "roms")  # made by fixtures.make_nds
gta = os.path.join(ROMS, "Grand Theft Auto - Chinatown Wars (USA).nds")
two = os.path.join(ROMS, "Two Lines.nds")
one = os.path.join(ROMS, "One Line.nds")
nob = os.path.join(ROMS, "No Banner.nds")
junk = os.path.join(ROMS, "junk.nds")

print("header parsing")
i = nds.read_nds(gta)
check((i.game_code, i.title, i.publisher, i.rom_version) ==
      ("YGXE", "Grand Theft Auto Chinatown Wars", "Rockstar Games", 1), f"3 lines: {i}")
i = nds.read_nds(two)
check((i.title, i.publisher) == ("Some Game", "Some Publisher"), "2 lines -> title, publisher")
i = nds.read_nds(one)
check((i.title, i.publisher, i.rom_version) == ("Only Title", "", 70), "1 line -> no publisher")
i = nds.read_nds(nob)
check(i.title == "GTACHINATOWN", "no banner -> header title")
check(pl.check_input_file(pl.KIND_NDS, junk) == "Not a valid NDS ROM: File is too small to be an NDS ROM", "junk rejected")
check(pl.check_input_file(pl.KIND_NDS, os.path.join(S, "test.glb")) == "ROM must be a .nds file", "wrong extension")
check(nds.default_rom_dir() == "/roms/nds/", "default dir from default_path.txt")

print("registry")
check(nds.suggest_unique_id("YGXE") == (0xFF400, False), "empty registry -> FF400")
nds.record_unique_id("YGXE", 0xFF400)
check(nds.suggest_unique_id("YGXE") == (0xFF400, True), "same game reuses its ID")
check(nds.suggest_unique_id("ABCE") == (0xFF401, False), "new game -> next free")
nds.record_unique_id("name:Other", 0xFF3F0)  # out-of-range IDs don't move the counter
check(nds.suggest_unique_id("ABCE") == (0xFF401, False), "out-of-range ID ignored for next")

print("GUI")
import tkinter as tk
import yanbf_cbc as g

root = tk.Tk()
root.withdraw()
app = g.App(root)
root.update()
shown = lambda k: app.locks[k]["button"].winfo_manager() == "grid"
st = lambda: (str(app.build_btn["state"]), app.status_var.get())
check(not any(shown(k) for k in app.locks), "no Edit buttons without a .nds")
app.icon_var.set(os.path.join(S, "icon48.png"))
app.banner_var.set(os.path.join(S, "test.glb"))
app.nds_var.set(gta); root.update()
vals = {k: app.locks[k]["var"].get() for k in app.locks}
check(vals == {"rom": "/roms/nds/Grand Theft Auto - Chinatown Wars (USA).nds",
               "title": "Grand Theft Auto Chinatown Wars", "publisher": "Rockstar Games",
               "product": "CTR-H-YGXE", "uid": "FF400", "minor": "1"}, f"filled: {vals}")
check(all(app.locks[k]["state"] == "locked" and shown(k) for k in app.locks), "all six locked with Edit shown")
check(str(app.title_entry["state"]) == "readonly" and str(app.minor_spin["state"]) == "disabled",
      "entries readonly, spinbox disabled")
check(st() == ("normal", "Ready"), f"ready with .nds {st()}")

app._toggle_lock("title"); root.update()
check(str(app.title_entry["state"]) == "normal" and app.locks["title"]["button"]["text"] == "Save", "Edit -> editable + Save")
check(st()[0] == "disabled" and "save Title" in st()[1], f"unsaved edit blocks build {st()}")
app.title_var.set(""); root.update()
check(str(app.locks["title"]["button"]["state"]) == "disabled", "Save disabled when empty")
app._toggle_lock("title"); root.update()
check(app.locks["title"]["state"] == "editing", "cannot save empty title")
app.title_var.set("GTA CW"); root.update()
app._toggle_lock("title"); root.update()
check(app.locks["title"]["state"] == "locked" and app.title_var.get() == "GTA CW" and st()[0] == "normal",
      "Save relocks with the edited value")
app._toggle_lock("uid"); app.uid_var.set("ZZ"); root.update()
check(str(app.locks["uid"]["button"]["state"]) == "disabled" and "'Z'" in app.uid_err["text"], "invalid uid can't be saved")
app.uid_var.set("FF4AA"); app._toggle_lock("uid"); root.update()
check(app.locks["uid"]["state"] == "locked" and app.uid_var.get() == "FF4AA", "uid saved")
app._toggle_lock("minor"); root.update()
check(str(app.minor_spin["state"]) == "normal", "spinbox unlocks")
app.minor_var.set("5"); app._toggle_lock("minor"); root.update()
check(str(app.minor_spin["state"]) == "disabled" and app.minor_var.get() == "5", "spinbox saved + relocked")

app.nds_var.set(two); root.update()
check(app.uid_var.get() == "FF401" and app.product_var.get() == "CTR-H-ABCE" and app.title_var.get() == "Some Game",
      "new .nds overwrites fields, next free ID")
app.nds_var.set(gta); root.update()
check(app.uid_var.get() == "FF400" and app.title_var.get() == "Grand Theft Auto Chinatown Wars", "reloading GTA reuses FF400")
app.nds_var.set(one); root.update()
check(app.publisher_var.get() == "" and app.locks["publisher"]["state"] == "free" and not shown("publisher"),
      "missing publisher left editable")
check(app.minor_var.get() == "" and app.locks["minor"]["state"] == "free" and "version" in st()[1],
      "version 70 not usable -> left editable, needed")
app.minor_var.set("0"); root.update()
app.nds_var.set(junk); root.update()
check("too small" in app.nds_err["text"] and st()[0] == "disabled" and "valid .nds" in st()[1], "junk .nds blocks build")
app.nds_var.set(""); root.update()
check(all(app.locks[k]["state"] == "free" and not shown(k) for k in app.locks) and app.title_var.get() == "Only Title",
      "clearing .nds unlocks everything and keeps values")
root.destroy()

print("pipeline")
tools = FAKE_TOOLS
job = pl.BuildJob(icon_path="icon48.png", banner_mode="png", banner_path="banner256.png", audio_path="",
                  rom_path="/roms/nds/Two Lines.nds", title="Some Game", publisher="P", product_code="CTR-H-ABCE",
                  unique_id="FF401", minor=0, nds_path=two)
lines = []
ok = pl.Pipeline(job, lambda t, s: lines.append((t, s)), tools=tools, output_root=os.path.join(S, "fake_out")).run()
check(ok and nds.suggest_unique_id("ABCE") == (0xFF401, True), "successful build records ABCE -> FF401")
check(not any(t == "warn" and "already used" in s for t, s in lines), "no collision warning for own ID")
job.unique_id, job.nds_path, job.rom_path = "FF400", one, "/roms/nds/One Line.nds"
lines = []
ok = pl.Pipeline(job, lambda t, s: lines.append((t, s)), tools=tools, output_root=os.path.join(S, "fake_out")).run()
check(ok and any(t == "warn" and "already used for YGXE" in s for t, s in lines), "reused ID from another game warns")
os.environ["FAKE_FAIL"] = "makerom"
job.unique_id, job.nds_path = "FF7AA", nob
ok = pl.Pipeline(job, lambda t, s: None, tools=tools, output_root=os.path.join(S, "fake_out")).run()
del os.environ["FAKE_FAIL"]
check(not ok and nds.suggest_unique_id("NOBE")[1] is False, "failed build doesn't record an ID")
job.nds_path = junk
lines = []
ok = pl.Pipeline(job, lambda t, s: lines.append((t, s)), tools=tools, output_root=os.path.join(S, "fake_out")).run()
check(not ok and any("NDS ROM:" in s for t, s in lines), "pipeline rejects invalid .nds")

finish()
