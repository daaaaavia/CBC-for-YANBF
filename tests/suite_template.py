"""Template… button: saves a copy of the Blender banner template (3D Model mode only)."""
import filecmp, importlib, os, sys
from _common import check, finish, isolate, S
import paths
isolate("template")
import tkinter as tk
import pipeline as pl
import yanbf_cbc as g


print("paths")
check(paths.BANNER_TEMPLATE == os.path.join(paths.BASE_DIR, "banner.blend") and os.path.isfile(paths.BANNER_TEMPLATE),
      "source mode: banner.blend in the project folder")
sys._MEIPASS = os.path.join(S, "_MEI123")
importlib.reload(paths)
check(paths.BANNER_TEMPLATE == os.path.join(S, "_MEI123", "banner.blend"), "frozen: read from the exe's bundled data")
del sys._MEIPASS
importlib.reload(paths)
isolate("template", fresh=False)  # the reload reset the scratch paths

print("button")
root = tk.Tk(); root.withdraw()
app = g.App(root); root.update()
b = app.template_btn
check(b.winfo_ismapped() or b.grid_info() != {}, "shown in 3D Model mode")
check(str(b.grid_info()["row"]) == str(app.banner_entry.grid_info()["row"] + 1) and b.grid_info()["column"] == 2,
      "sits under Browse…, next to the .glb caption")
check("Template…" in app.banner_caption_var.get(), "caption tells people what it's for")
app.mode_var.set(pl.MODE_PNG); root.update()
check(b.grid_info() == {}, "hidden in Flat Image mode")
app.mode_var.set(pl.MODE_GLB); root.update()
check(b.grid_info() != {}, "back in 3D Model mode")

print("saving")
dest = os.path.join(S, "tp_out", "My banner.blend")
os.makedirs(os.path.dirname(dest), exist_ok=True)
if os.path.exists(dest):
    os.remove(dest)
asked = []
g.filedialog.asksaveasfilename = lambda **k: (asked.append(k), dest)[1]
b.invoke(); root.update()
check(os.path.isfile(dest) and filecmp.cmp(dest, paths.BANNER_TEMPLATE, shallow=False), "saves a byte-identical copy")
k = asked[0]
check(k["initialfile"].endswith(".blend") and k["defaultextension"] == ".blend", f"suggests a .blend name: {k['initialfile']}")
downloads = os.path.join(os.path.expanduser("~"), "Downloads")
if os.path.isdir(downloads):
    check(k["initialdir"] == downloads, f"starts in Downloads: {k['initialdir']}")
else:
    check(k["initialdir"] is None, "no Downloads folder: the dialog picks its own start")
log = app.log_text.get("1.0", "end")
check("Saved the 3D banner template" in log and "Blender 5.2" in log and "glTF Binary (.glb)" in log,
      "log says where it went and how to export")
g.filedialog.asksaveasfilename = lambda **k: ""
before = app.log_text.get("1.0", "end")
b.invoke(); root.update()
check(app.log_text.get("1.0", "end") == before, "cancel does nothing")
errs = []
g.messagebox.showerror = lambda *a, **k: errs.append((a, k))
real = paths.BANNER_TEMPLATE
paths.BANNER_TEMPLATE = os.path.join(S, "nope.blend")
b.invoke(); root.update()
check(errs and "nope.blend" in errs[0][1]["detail"], "missing template -> error with the path")
paths.BANNER_TEMPLATE = real
app._on_close()
finish()
