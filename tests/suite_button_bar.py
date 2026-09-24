"""Button bar: no User guide button / F1 (removed), and a very long status never squeezes
the buttons."""
import os

from _common import check, finish, isolate
import paths
isolate("buttonbar")
import tkinter as tk
import yanbf_cbc as g


print("app")
check(not hasattr(paths, "USER_GUIDE"), "paths.USER_GUIDE gone")
root = tk.Tk(); root.withdraw()
app = g.App(root); root.update()
check(not hasattr(app, "open_user_guide"), "open_user_guide gone")
buttons = []


def walk(w):
    for c in w.winfo_children():
        if c.winfo_class() == "TButton":
            buttons.append(c)
        walk(c)


walk(root)
check(not any(b.cget("text") == "User guide" for b in buttons), "no User guide button")
check(root.bind("<F1>") == "", "F1 not bound")
readme = open(os.path.join(paths.BASE_DIR, "README.md"), encoding="utf-8").read()
check("USER_GUIDE" not in readme and "User Guide" not in readme and "make_guide_html" not in readme,
      "README doesn't mention the guide")

print("button bar at the minimum width")
root.deiconify(); root.geometry("1120x720"); root.update()
app._set_status("Needs: required tools, valid .nds, icon, banner, audio, title, product code, unique ID, version, "
                "save Title, Publisher, Product Code", g.T.status_bad)
root.update()
for text in ("Credits…", "Build CIA", "Send to 3DS…", "Open output folder"):
    b = next(b for b in buttons if b.cget("text") == text)
    check(b.winfo_width() >= b.winfo_reqwidth(), f"'{text}' keeps its full width with a very long status")
app._on_close()
finish()
