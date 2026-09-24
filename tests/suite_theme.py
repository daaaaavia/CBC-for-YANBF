"""Appearance setting: System (default) / Light / Dark, saved, applied live; Light = original look."""
import json
import os
import sys

from _common import WINDOWS, check, finish, isolate, S
import paths
isolate("theme")
import settings, theme, preview
import tkinter as tk
from tkinter import ttk
FTP = {"ftp_host": "", "ftp_port": 5000, "ftp_cia_dir": "/cias/"}  # FTP defaults (Send to 3DS)


print("settings")
check(settings.load()["theme"] == "system", "default is System")
json.dump({"id_start": "0xFF500", "theme": "bogus"}, open(paths.SETTINGS, "w"))
d = settings.load()
check(d == {"id_start": 0xFF500, "theme": "system", **FTP}, f"bad theme value falls back, id_start kept: {d}")
json.dump({"id_start": "nonsense", "theme": "dark"}, open(paths.SETTINGS, "w"))
check(settings.load() == {"id_start": 0xFF400, "theme": "dark", **FTP}, "bad id_start doesn't lose the theme")
settings.save({"id_start": 0xFF600, "theme": "light"})
check(json.load(open(paths.SETTINGS)) == {"id_start": "0xFF600", "theme": "light", **FTP}, "both settings saved together")
os.remove(paths.SETTINGS)

print("system detection")
real = theme.system_is_dark
check(isinstance(real(), bool), f"reads the system appearance (dark right now: {real()})")
theme.system_is_dark = lambda: True
check(theme.resolve("system") == "dark", "System follows Windows dark")
theme.system_is_dark = lambda: False
check(theme.resolve("system") == "light", "System follows Windows light")
check(theme.resolve("light") == "light" and theme.resolve("dark") == "dark", "explicit choices")
theme.system_is_dark = real

import yanbf_cbc as g


def snapshot(app, root):
    e, sp, lg = app.title_entry, app.minor_spin, app.log_text
    return {
        "ttk": ttk.Style(root).theme_use(),
        "root_bg": root["bg"],
        "entry": tuple(e.cget(k) for k in ("bg", "fg", "relief", "bd", "insertbackground", "readonlybackground",
                                           "selectbackground", "highlightthickness")),
        "spin": tuple(sp.cget(k) for k in ("bg", "fg", "relief", "bd", "buttonbackground", "disabledforeground")),
        "log": (lg.cget("bg"), lg.cget("fg"), lg.tag_cget("step", "foreground")),
        "err_label": (app.icon_err.cget("bg"), app.icon_err.cget("fg")),
        "img_label": app.icon_preview.cget("bg"),
        "caption": str(app.audio_preview_info.cget("foreground")),
        "preview_bg": preview.BG,
    }


print("light start = original look")
settings.save({"id_start": 0xFF400, "theme": "light"})
root = tk.Tk(); root.withdraw()
app = g.App(root); root.update()
light0 = snapshot(app, root)
print("   ", light0)
NATIVE = light0["ttk"]
if WINDOWS:  # Tk's own Windows defaults
    check(NATIVE == "vista", "native Windows ttk theme")
    check(light0["entry"][:4] == ("white", "SystemWindowText", "solid", 1), "fields as before")
    check(light0["log"][0] == "SystemWindow", "log background as before")
elif sys.platform == "darwin":  # Tk's own macOS defaults
    check(NATIVE == "aqua", "native macOS ttk theme")
check(light0["log"][2] == "#1f4fbf", "log step colour as before")
check(light0["preview_bg"] == (214, 218, 224), "preview colours as before")
check(app.theme_var.get() == "Light", "picker shows Light")

print("live switch to Dark")
app.theme_var.set("Dark"); app._on_theme_pick(); root.update()
dark = snapshot(app, root)
check(dark["ttk"] == "clam" and dark["root_bg"] == "#202020", "dark ttk theme + window")
check(dark["entry"][0] == "#2d2d2d" and dark["entry"][1] == "#f3f3f3", f"fields dark: {dark['entry']}")
check(dark["log"][0] == "#1b1b1b" and dark["err_label"][0] == "#202020", "log + labels dark")
check(dark["img_label"] == "#202020" and dark["preview_bg"] == (43, 43, 43), "preview panel dark")
check(settings.load()["theme"] == "dark", "choice saved to settings.json")
# a validated field keeps its error colour after the switch
app.icon_var.set(os.path.join(S, "lim", "i49.png")); root.update()
check(app.icon_entry["bg"] == g.ERR_BG == "#4d2328", "error highlight uses dark colours")

print("live switch back to Light = identical to the start")
app.theme_var.set("Light"); app._on_theme_pick(); root.update()
app.icon_var.set(""); root.update()
light1 = snapshot(app, root)
diff = {k: (light0[k], light1[k]) for k in light0 if light0[k] != light1[k]}
check(not diff, f"every checked property restored: {diff or 'identical'}")

print("System")
theme.system_is_dark = lambda: True
app.theme_var.set("System"); app._on_theme_pick(); root.update()
check(theme.current.name == "dark" and settings.load()["theme"] == "system", "System + Windows dark -> dark, saved")
theme.system_is_dark = lambda: False
app._watch_system_theme(); root.update()
check(theme.current.name == "light" and snapshot(app, root)["ttk"] == NATIVE,
      "Windows switches to light while running -> follows")
app.theme_var.set("Dark"); app._on_theme_pick(); root.update()
theme.system_is_dark = lambda: False
app._watch_system_theme(); root.update()
check(theme.current.name == "dark", "explicit Dark ignores Windows")
theme.system_is_dark = real
app._on_close()

print("persists across program runs")
root = tk.Tk(); root.withdraw()
app2 = g.App(root); root.update()
check(app2.theme_var.get() == "Dark" and theme.current.name == "dark" and ttk.Style(root).theme_use() == "clam",
      "next start opens in Dark")
app2._on_close()
os.remove(paths.SETTINGS)
root = tk.Tk(); root.withdraw()
app3 = g.App(root); root.update()
want = "dark" if real() else "light"
check(app3.theme_var.get() == "System" and theme.current.name == want, f"no setting -> System ({want} here)")
app3._on_close()
finish()
