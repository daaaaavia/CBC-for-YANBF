"""Credits window + more visible locked fields, in light and dark."""
import os

from _common import check, finish, isolate, S
isolate("credits")
import settings
settings.save({"id_start": 0xFF400, "theme": "light"})
import tkinter as tk
import yanbf_cbc as g


def contrast(c1, c2, root):
    a = [v / 257 for v in root.winfo_rgb(c1)]
    b = [v / 257 for v in root.winfo_rgb(c2)]
    return sum(abs(x - y) for x, y in zip(a, b))


root = tk.Tk(); root.withdraw()
app = g.App(root); root.update()
nds_path = os.path.join(S, "roms", "Grand Theft Auto - Chinatown Wars (USA).nds")

for mode in ("light", "dark"):
    print(mode)
    app.theme_var.set(mode.capitalize()); app._on_theme_pick(); root.update()
    app.nds_var.set(""); root.update(); app.nds_var.set(nds_path); root.update()
    t, e, sp = app.locks["title"], app.title_entry, app.minor_spin
    check(t["state"] == "locked" and str(e["state"]) == "readonly", "title locked")
    diff = contrast(e["readonlybackground"], g.OK_BG, root)
    check(diff >= 30, f"locked background clearly differs from a normal field (diff {diff:.0f})")
    check(e["fg"] == g.T.lock_fg and sp["disabledforeground"] == g.T.lock_fg, f"locked text dimmed ({e['fg']})")
    b = t["button"]
    check(b["text"] == "Edit" and str(b["image"]) != "" and str(b["compound"]) == "left", "Edit button shows a padlock")
    app._toggle_lock("title"); root.update()
    check(str(e["state"]) == "normal" and e["fg"] == g.theme.widget_opts("Entry")["fg"]
          and b["text"] == "Save" and str(b["image"]) == "", "editing: normal text, Save without padlock")
    app._toggle_lock("title"); root.update()
    check(e["fg"] == g.T.lock_fg and str(b["image"]) != "", "saved: locked look again")

print("theme switch keeps the locked look")
app.theme_var.set("Light"); app._on_theme_pick(); root.update()
check(app.title_entry["fg"] == g.theme.LIGHT.lock_fg and app.title_entry["readonlybackground"] == g.theme.LIGHT.lock_bg,
      "switching dark -> light re-applies the light locked colours")
app.nds_var.set(""); root.update()
check(app.title_entry["fg"] == g.theme.widget_opts("Entry")["fg"] and str(app.title_entry["state"]) == "normal",
      "clearing the .nds restores normal text")

print("credits window")
app.open_credits(); root.update()
w = app.credits_win
check(w.winfo_exists() and w.title() == "Credits", "opens")
texts = []


def walk(x):
    for c in x.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except tk.TclError:
            pass
        walk(c)


walk(w)
blob = "\n".join(texts)
for name, url in (("YANBF", "https://github.com/YANBForwarder/YANBF"), ("pycgfx", "https://github.com/skyfloogle/pycgfx"),
                  ("bannertool", "https://github.com/Epicpkmn11/bannertool"), ("cwavtool", "https://github.com/PabloMK7/cwavtool"),
                  ("Project_CTR", "https://github.com/3DSGuy/Project_CTR")):
    check(name in blob and url in blob, f"lists {name} with its link")
for who in ("lifehackerhansol", "skyfloogle", "Epicpkmn11", "Steveice10", "PabloMK7", "3DSGuy"):
    check(who in blob, f"credits {who}")
opened = []
g.webbrowser.open = lambda u: opened.append(u)
app.credit_links[2].event_generate("<Button-1>"); root.update()
check(opened == ["https://github.com/Epicpkmn11/bannertool"], f"clicking a link opens it: {opened}")
app.open_credits(); root.update()
check(app.credits_win is w, "Credits… again brings the same window forward")
app.theme_var.set("Dark"); app._on_theme_pick(); root.update()
check(str(app.credit_links[0].cget("foreground")) == g.theme.DARK.link_fg, "links follow the theme")
w.destroy()
app._on_close()
finish()
