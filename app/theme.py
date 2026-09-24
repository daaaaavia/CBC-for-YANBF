"""Light / dark appearance.

'light' is the original look. 'dark' is a Windows-style dark mode. The user picks
System (follow Windows' app mode), Light or Dark; the choice is saved in settings.json.
Themes can be switched while the program runs: apply() restyles ttk, and the GUI
restyles its own tk widgets using the colours here. Switching back to light restores
Tk's own default widget colours, captured from real widgets before any theming.
"""

import ctypes
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk

PREFS = ("system", "light", "dark")
PREF_LABELS = {"system": "System", "light": "Light", "dark": "Dark"}


@dataclass
class Theme:
    name: str
    # fields
    field_bg: str
    lock_bg: str
    err_bg: str
    err_fg: str
    warn_bg: str
    warn_fg: str
    placeholder_fg: str
    flash_bg: str  # field flash after a drag-and-drop
    caption_fg: str
    hint_fg: str
    info_fg: str  # blue info text (ID options dialog)
    # status label
    status_ok: str
    status_bad: str
    status_busy: str
    # log
    log_tags: dict
    font_status: tuple
    font_mono: tuple
    # tk widget options at creation / restyle. Keys missing here fall back to Tk's
    # defaults on restyle (see widget_opts()).
    entry_opts: dict = field(default_factory=dict)
    spin_opts: dict = field(default_factory=dict)
    text_opts: dict = field(default_factory=dict)
    label_opts: dict = field(default_factory=dict)  # plain tk.Labels (errors, images)
    screen_border: str = "black"  # HOME preview window
    # locked (.nds-filled) fields: tinted background, dimmed text, padlock on the Edit button
    lock_fg: str = "#46505c"
    lock_icon: str = "#46505c"
    link_fg: str = "#0a5fb4"  # clickable links (Credits window)
    # Pillow colours for the preview panel images (RGB)
    img_panel_bg: tuple = (214, 218, 224)
    img_placeholder_bg: tuple = (236, 236, 236)
    img_placeholder_fg: tuple = (120, 120, 120)
    img_placeholder_line: tuple = (200, 200, 200)
    img_wave_bg: tuple = (250, 250, 250)
    img_wave_mid: tuple = (210, 210, 210)
    img_wave_fg: tuple = (0, 128, 138)
    img_check: tuple = ((255, 255, 255), (222, 222, 222))


LIGHT = Theme(
    name="light",
    field_bg="white", lock_bg="#d9e1eb",
    err_bg="#ffd6d6", err_fg="#c00000", warn_bg="#fff1c6", warn_fg="#9a6700",
    placeholder_fg="#9a9a9a", flash_bg="#d6f5d6",
    caption_fg="#555555", hint_fg="#888888", info_fg="#1f4fbf",
    status_ok="#1a8a1a", status_bad="#c00000", status_busy="#1f4fbf",
    log_tags={
        "step": {"foreground": "#1f4fbf", "background": "", "font": ("Consolas", 9, "bold")},
        "cmd": {"foreground": "#808080", "background": ""},
        "out": {"foreground": "#202020", "background": ""},
        "info": {"foreground": "#00808a", "background": ""},
        "ok": {"foreground": "#1a8a1a", "background": ""},
        "warn": {"foreground": "#b07800", "background": ""},
        "err": {"foreground": "#d00000", "background": ""},
        "bigwarn": {"foreground": "white", "background": "#e06000", "font": ("Consolas", 9, "bold")},
        "fail": {"foreground": "white", "background": "#c00000", "font": ("Consolas", 10, "bold")},
        "done": {"foreground": "white", "background": "#1a8a1a", "font": ("Consolas", 10, "bold")},
    },
    font_status=("Segoe UI", 9, "bold"),
    font_mono=("Consolas", 9),
    entry_opts={"relief": "solid", "bd": 1},
    spin_opts={"relief": "solid", "bd": 1, "disabledforeground": "black"},
)

D = {  # Windows-style dark palette
    "bg": "#202020",
    "field": "#2d2d2d",
    "field_hi": "#383838",
    "border": "#4a4a4a",
    "text": "#f3f3f3",
    "sub": "#b4b4b4",
    "dim": "#8a8a8a",
    "accent": "#60cdff",
    "accent_dark": "#005a9e",
    "log": "#1b1b1b",
}

DARK = Theme(
    name="dark",
    field_bg=D["field"], lock_bg="#1d3045",
    err_bg="#4d2328", err_fg="#ff99a4", warn_bg="#4a3e16", warn_fg="#f4d35e",
    placeholder_fg=D["dim"], flash_bg="#1f4d33",
    caption_fg=D["sub"], hint_fg=D["dim"], info_fg=D["accent"],
    status_ok="#6ccb5f", status_bad="#ff99a4", status_busy=D["accent"],
    log_tags={
        "step": {"foreground": D["accent"], "background": "", "font": ("Consolas", 9, "bold")},
        "cmd": {"foreground": D["dim"], "background": ""},
        "out": {"foreground": "#dcdcdc", "background": ""},
        "info": {"foreground": "#4fd1c5", "background": ""},
        "ok": {"foreground": "#6ccb5f", "background": ""},
        "warn": {"foreground": "#f4d35e", "background": ""},
        "err": {"foreground": "#ff99a4", "background": ""},
        "bigwarn": {"foreground": "white", "background": "#c2410c", "font": ("Consolas", 9, "bold")},
        "fail": {"foreground": "white", "background": "#b3261e", "font": ("Consolas", 10, "bold")},
        "done": {"foreground": "white", "background": "#2e7d32", "font": ("Consolas", 10, "bold")},
    },
    font_status=("Segoe UI", 9, "bold"),
    font_mono=("Consolas", 9),
    # (bg / readonlybackground come from field_bg / lock_bg, which the GUI passes itself)
    entry_opts={"relief": "solid", "bd": 1, "fg": D["text"], "insertbackground": D["text"],
                "disabledforeground": D["dim"],
                "selectbackground": D["accent_dark"], "selectforeground": "white",
                "highlightthickness": 0},
    spin_opts={"relief": "solid", "bd": 1, "fg": D["text"], "insertbackground": D["text"],
               "disabledforeground": D["text"], "buttonbackground": D["field_hi"],
               "selectbackground": D["accent_dark"], "selectforeground": "white",
               "highlightthickness": 0},
    text_opts={"bg": D["log"], "fg": "#dcdcdc", "insertbackground": D["text"],
               "selectbackground": D["accent_dark"], "selectforeground": "white"},
    label_opts={"bg": D["bg"], "fg": D["text"]},
    screen_border=D["border"],
    lock_fg="#aac2dc",
    lock_icon="#b9c8d8",
    link_fg=D["accent"],
    img_panel_bg=(43, 43, 43),
    img_placeholder_bg=(45, 45, 45),
    img_placeholder_fg=(170, 170, 170),
    img_placeholder_line=(74, 74, 74),
    img_wave_bg=(30, 30, 30),
    img_wave_mid=(70, 70, 70),
    img_wave_fg=(96, 205, 255),
    img_check=((64, 64, 64), (52, 52, 52)),
)

THEMES = {"light": LIGHT, "dark": DARK}
current = LIGHT


def system_is_dark():
    """True if Windows is set to dark mode for apps."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def resolve(pref):
    """'system' / 'light' / 'dark' -> 'light' or 'dark'."""
    if pref == "system":
        return "dark" if system_is_dark() else "light"
    return pref if pref in THEMES else "light"


def use(name):
    global current
    current = THEMES[name]
    return current


def apply_preview(preview_module):
    """Point the preview module's image colours at the current theme."""
    t = current
    preview_module.BG = t.img_panel_bg
    preview_module.PLACEHOLDER_BG = t.img_placeholder_bg
    preview_module.PLACEHOLDER_FG = t.img_placeholder_fg
    preview_module.PLACEHOLDER_LINE = t.img_placeholder_line
    preview_module.WAVE_BG = t.img_wave_bg
    preview_module.WAVE_MID = t.img_wave_mid
    preview_module.WAVE_FG = t.img_wave_fg
    preview_module.CHECK = t.img_check


# ------------------------------------------------------------------ Tk defaults

_DEFAULT_KEYS = {
    "Entry": ("bg", "fg", "relief", "bd", "insertbackground", "disabledforeground", "readonlybackground",
              "selectbackground", "selectforeground", "highlightthickness"),
    "Spinbox": ("bg", "fg", "relief", "bd", "insertbackground", "disabledforeground", "buttonbackground",
                "selectbackground", "selectforeground", "highlightthickness"),
    "Text": ("bg", "fg", "insertbackground", "selectbackground", "selectforeground"),
    "Label": ("bg", "fg"),
    "Toplevel": ("bg",),
}
_defaults = {}
_native_ttk = None


def _capture_defaults(root):
    """Record Tk's own default colours (the light look) before anything is themed."""
    global _native_ttk
    if _defaults:
        return
    _native_ttk = ttk.Style(root).theme_use()
    probes = {"Entry": tk.Entry(root), "Spinbox": tk.Spinbox(root), "Text": tk.Text(root),
              "Label": tk.Label(root), "Toplevel": root}
    for cls, w in probes.items():
        _defaults[cls] = {k: w.cget(k) for k in _DEFAULT_KEYS[cls]}
        if w is not root:
            w.destroy()


def widget_opts(cls):
    """Full option set for restyling a tk widget of class cls ('Entry', 'Spinbox',
    'Text', 'Label') in the current theme: Tk's defaults overridden by the theme."""
    theme_opts = {"Entry": current.entry_opts, "Spinbox": current.spin_opts,
                  "Text": current.text_opts, "Label": current.label_opts}[cls]
    return {**_defaults.get(cls, {}), **theme_opts}


def window_bg():
    return D["bg"] if current.name == "dark" else _defaults.get("Toplevel", {}).get("bg", "SystemButtonFace")


# ------------------------------------------------------------------ applying

def apply(root):
    """Apply the current theme to ttk and the window background. Safe to call again
    to switch themes while running."""
    _capture_defaults(root)
    st = ttk.Style(root)
    root.option_clear()
    if current.name == "light":
        st.theme_use(_native_ttk)
        root.configure(bg=_defaults["Toplevel"]["bg"])
        set_title_bar(root)
        return

    c = D
    root.configure(bg=c["bg"])
    for opt, val in (("*Background", c["bg"]), ("*Foreground", c["text"]),
                     ("*TCombobox*Listbox.background", c["field"]),
                     ("*TCombobox*Listbox.foreground", c["text"]),
                     ("*TCombobox*Listbox.selectBackground", c["accent_dark"]),
                     ("*TCombobox*Listbox.selectForeground", "white")):
        root.option_add(opt, val)
    st.theme_use("clam")
    st.configure(".", background=c["bg"], foreground=c["text"], bordercolor=c["border"],
                 lightcolor=c["bg"], darkcolor=c["bg"], troughcolor=c["field"], focuscolor=c["accent"],
                 selectbackground=c["accent_dark"], selectforeground="white",
                 fieldbackground=c["field"], insertcolor=c["text"])
    st.map(".", background=[("disabled", c["bg"])], foreground=[("disabled", c["dim"])])
    st.configure("TFrame", background=c["bg"])
    st.configure("TLabel", background=c["bg"], foreground=c["text"])
    st.configure("TSeparator", background=c["border"])
    st.configure("TLabelframe", background=c["bg"], bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"])
    st.configure("TLabelframe.Label", background=c["bg"], foreground=c["sub"])
    st.configure("TButton", background=c["field"], foreground=c["text"], bordercolor=c["border"],
                 lightcolor=c["field"], darkcolor=c["field"], focuscolor=c["accent"], padding=(8, 2))
    st.map("TButton",
           background=[("disabled", "#262626"), ("pressed", "#262626"), ("active", c["field_hi"])],
           foreground=[("disabled", c["dim"])],
           bordercolor=[("focus", c["accent"])],
           lightcolor=[("pressed", "#262626"), ("active", c["field_hi"])],
           darkcolor=[("pressed", "#262626"), ("active", c["field_hi"])])
    st.configure("TRadiobutton", background=c["bg"], foreground=c["text"], indicatorbackground=c["field"],
                 indicatorforeground=c["accent"], upperbordercolor=c["border"], lowerbordercolor=c["border"])
    st.map("TRadiobutton", background=[("active", c["bg"])],
           indicatorbackground=[("active", c["field_hi"])])
    st.configure("TCombobox", fieldbackground=c["field"], background=c["field"], foreground=c["text"],
                 arrowcolor=c["sub"], bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"],
                 selectbackground=c["field"], selectforeground=c["text"])
    st.map("TCombobox", fieldbackground=[("readonly", c["field"])], background=[("active", c["field_hi"])],
           bordercolor=[("focus", c["accent"])])
    st.configure("Vertical.TScrollbar", background=c["field_hi"], troughcolor=c["log"], bordercolor=c["log"],
                 arrowcolor=c["sub"], lightcolor=c["field_hi"], darkcolor=c["field_hi"])
    st.map("Vertical.TScrollbar", background=[("active", "#4a4a4a")])
    st.configure("Horizontal.TScale", background=c["field_hi"], troughcolor=c["field"], bordercolor=c["border"],
                 lightcolor=c["field_hi"], darkcolor=c["field_hi"])
    # Send to 3DS window: checkboxes, progress bars, the SD card browser
    st.configure("TCheckbutton", background=c["bg"], foreground=c["text"], indicatorbackground=c["field"],
                 indicatorforeground=c["accent"], upperbordercolor=c["border"], lowerbordercolor=c["border"])
    st.map("TCheckbutton", background=[("active", c["bg"])],
           indicatorbackground=[("active", c["field_hi"])])
    st.configure("Horizontal.TProgressbar", background=c["accent_dark"], troughcolor=c["field"],
                 bordercolor=c["border"], lightcolor=c["accent_dark"], darkcolor=c["accent_dark"])
    st.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["text"],
                 bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"])
    st.map("Treeview", background=[("selected", c["accent_dark"])], foreground=[("selected", "white")])
    st.configure("Treeview.Heading", background=c["field_hi"], foreground=c["text"], bordercolor=c["border"],
                 lightcolor=c["field_hi"], darkcolor=c["field_hi"])
    st.map("Treeview.Heading", background=[("active", "#4a4a4a")])
    set_title_bar(root)


def style_combobox_list(cb):
    """Recolour a combobox's drop-down list (it may already exist from an earlier theme)."""
    try:
        popdown = cb.tk.call("ttk::combobox::PopdownWindow", cb)
        lb = f"{popdown}.f.l"
        if current.name == "dark":
            cb.tk.call(lb, "configure", "-background", D["field"], "-foreground", D["text"],
                       "-selectbackground", D["accent_dark"], "-selectforeground", "white")
        else:
            d = _defaults.get("Text", {})
            cb.tk.call(lb, "configure", "-background", d.get("bg", "SystemWindow"),
                       "-foreground", d.get("fg", "SystemWindowText"),
                       "-selectbackground", d.get("selectbackground", "SystemHighlight"),
                       "-selectforeground", d.get("selectforeground", "SystemHighlightText"))
    except tk.TclError:
        pass


def set_title_bar(win):
    """Dark or light Windows title bar to match the theme (no-op until the window exists)."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(win.wm_frame(), 16)
        val = ctypes.c_int(1 if current.name == "dark" else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer / older Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
        # repaint the frame so the change shows immediately
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    except (OSError, ValueError, AttributeError, tk.TclError):
        pass


def decorate(win):
    """Match a window's title bar to the theme once it's shown (Tk creates the real
    top-level window then)."""
    def on_map(event):
        if event.widget is win and not getattr(win, "_titlebar_done", False):
            win._titlebar_done = True
            set_title_bar(win)
    win.bind("<Map>", on_map, add="+")
