"""Path resolution for YANBF-CBC.

Every path the app uses is derived from BASE_DIR:
  * frozen (PyInstaller exe): the folder containing the .exe
  * source mode: the parent of app/, i.e. YANBF-CBC/

Never use __file__ (frozen), sys.argv[0] or os.getcwd() for this.
"""

import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROCESSES_DIR = os.path.join(BASE_DIR, "processes")
PROJECT_CTR_DIR = os.path.join(PROCESSES_DIR, "Project_CTR")
YANBF_DIR = os.path.join(PROCESSES_DIR, "YANBF")
GENERATOR_DATA_DIR = os.path.join(YANBF_DIR, "generator", "data")
PYCGFX_DIR = os.path.join(YANBF_DIR, "pycgfx")

CTRTOOL = os.path.join(PROJECT_CTR_DIR, "ctrtool.exe")
MAKEROM = os.path.join(PROJECT_CTR_DIR, "makerom.exe")
BANNERTOOL = os.path.join(PROJECT_CTR_DIR, "bannertool.exe")
CWAVTOOL = os.path.join(PROJECT_CTR_DIR, "cwavtool.exe")

PYCGFX_MAIN = os.path.join(PYCGFX_DIR, "main.py")
RSF = os.path.join(GENERATOR_DATA_DIR, "build-cia.rsf")
FORWARDER_ELF = os.path.join(GENERATOR_DATA_DIR, "forwarder.elf")

DEFAULT_ROM_PATH_TXT = os.path.join(YANBF_DIR, "generator", "default_path.txt")

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ID_REGISTRY = os.path.join(BASE_DIR, "unique_ids.json")
SETTINGS = os.path.join(BASE_DIR, "settings.json")

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
