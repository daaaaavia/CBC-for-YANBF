"""Path resolution for CBC for YANBF.

Every path the app uses is derived from BASE_DIR:
  * frozen Windows exe: the folder containing the .exe
  * frozen macOS app: CBC-for-YANBF.app/Contents/Resources (where processes/ is copied),
    or the folder containing the .app if processes/ sits next to it
  * source mode: the parent of app/ (the project folder)

On Windows and in source mode, settings, the Unique ID registry and output/ live in
BASE_DIR too. A Mac app can't write inside its own bundle, so there they go to
~/Library/Application Support/CBC-for-YANBF/ (settings, IDs, pycgfx, ctrtool) and
~/Documents/CBC-for-YANBF/output. Folders from before the rename (YANBF-CBC) are
moved there the first time.

Never use __file__ (frozen), sys.argv[0] or os.getcwd() for this.
"""

import os
import sys

import platform_util as pu


def _base_dir(frozen, executable, source_file):
    if not frozen:
        return os.path.dirname(os.path.dirname(os.path.abspath(source_file)))
    exe_dir = os.path.dirname(os.path.abspath(executable))
    if pu.is_mac() and os.path.basename(exe_dir) == "MacOS":
        contents = os.path.dirname(exe_dir)
        resources = os.path.join(contents, "Resources")
        if os.path.isdir(os.path.join(resources, "processes")):
            return resources
        return os.path.dirname(os.path.dirname(contents))  # the folder holding the .app
    return exe_dir


NAME = "CBC-for-YANBF"  # folder name for the Mac app's own data
OLD_NAME = "YANBF-CBC"  # the name before the rename


def _move_old(parent):
    """The app used to be called YANBF-CBC: move its folder to the new name, once."""
    old, new = os.path.join(parent, OLD_NAME), os.path.join(parent, NAME)
    if os.path.isdir(old) and not os.path.exists(new):
        try:
            os.rename(old, new)
        except OSError:
            pass


def _user_dirs(frozen, base_dir, home, migrate=False):
    """(folder for settings.json + unique_ids.json, output folder, pycgfx folder, ctrtool folder)."""
    if pu.is_mac() and frozen:
        library, documents = os.path.join(home, "Library", "Application Support"), os.path.join(home, "Documents")
        if migrate:
            _move_old(library)
            _move_old(documents)
        support = os.path.join(library, NAME)
        return (support, os.path.join(documents, NAME, "output"),
                os.path.join(support, "pycgfx"), os.path.join(support, "ctrtool"))
    return (base_dir, os.path.join(base_dir, "output"), os.path.join(base_dir, "processes", "YANBF", "pycgfx"),
            os.path.join(base_dir, "processes", "Project_CTR"))


FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = _base_dir(FROZEN, sys.executable, __file__)
DATA_DIR, OUTPUT_DIR, PYCGFX_DIR, CTRTOOL_DIR = _user_dirs(FROZEN, BASE_DIR, os.path.expanduser("~"), migrate=True)

PROCESSES_DIR = os.path.join(BASE_DIR, "processes")
PROJECT_CTR_DIR = os.path.join(PROCESSES_DIR, "Project_CTR")
YANBF_DIR = os.path.join(PROCESSES_DIR, "YANBF")
GENERATOR_DATA_DIR = os.path.join(YANBF_DIR, "generator", "data")

CTRTOOL = os.path.join(CTRTOOL_DIR, pu.exe_name("ctrtool"))  # downloaded, see ctrtool_setup
MAKEROM = os.path.join(PROJECT_CTR_DIR, pu.exe_name("makerom"))
BANNERTOOL = os.path.join(PROJECT_CTR_DIR, pu.exe_name("bannertool"))
CWAVTOOL = os.path.join(PROJECT_CTR_DIR, pu.exe_name("cwavtool"))

PYCGFX_MAIN = os.path.join(PYCGFX_DIR, "main.py")
RSF = os.path.join(GENERATOR_DATA_DIR, "build-cia.rsf")
FORWARDER_ELF = os.path.join(GENERATOR_DATA_DIR, "forwarder.elf")

DEFAULT_ROM_PATH_TXT = os.path.join(YANBF_DIR, "generator", "default_path.txt")

ID_REGISTRY = os.path.join(DATA_DIR, "unique_ids.json")
SETTINGS = os.path.join(DATA_DIR, "settings.json")
if DATA_DIR != BASE_DIR:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass

# Blender template for 3D banners, offered by the "Blender template…" button. It's
# bundled into the exe (build with --add-data "..\banner.blend;."), so it works
# even without the loose copy; in source mode it's read from the project folder.
BANNER_TEMPLATE = os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), "banner.blend")

# (path, is_directory)
REQUIRED = [
    (CTRTOOL, False),
    (MAKEROM, False),
    (BANNERTOOL, False),
    (CWAVTOOL, False),
    (PYCGFX_DIR, True),
    (PYCGFX_MAIN, False),
    (RSF, False),
    (FORWARDER_ELF, False),
]


def find_missing():
    """Return the full paths of required files/folders that don't exist."""
    missing = []
    for path, is_dir in REQUIRED:
        ok = os.path.isdir(path) if is_dir else os.path.isfile(path)
        if not ok:
            missing.append(path)
    return missing


def rel(path):
    """Short path relative to BASE_DIR, for user-facing messages."""
    try:
        return os.path.relpath(path, BASE_DIR)
    except ValueError:
        return path
