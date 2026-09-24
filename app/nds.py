"""NDS ROM header reading and the Unique ID registry.

Header fields follow YANBF generator.py: game code at 0x0C, banner title
(English, UTF-16LE) at banner + 0x340, split into lines the same way.

The registry (BASE_DIR/unique_ids.json) remembers which Unique ID each game
was built with, so a rebuild of the same game reuses its ID (installs as an
update) and a new game gets the next free ID from the user's start setting
(default 0xFF400, where YANBF's range begins) up to 0xFFFFF.
"""

import json
import os
import struct
import threading
from dataclasses import dataclass

import paths

HEADER_SIZE = 0x200
BANNER_ENGLISH_TITLE = 0x340
ID_FIRST = 0xFF400  # default start (YANBF's range starts here)
ID_MAX = 0xFFFFF  # top of the homebrew ID range


class NdsError(Exception):
    pass


@dataclass
class NdsInfo:
    game_code: str  # e.g. "YGXE"
    maker_code: str  # e.g. "01"
    header_title: str  # 12-char internal name, e.g. "GTACHINATOWN"
    rom_version: int  # header byte 0x1E
    title: str  # from the banner, "" if none
    publisher: str  # from the banner, "" if none


def read_nds(path):
    """Read the header and English banner title. Raises NdsError."""
    try:
        with open(path, "rb") as f:
            hdr = f.read(HEADER_SIZE)
            if len(hdr) < HEADER_SIZE:
                raise NdsError("File is too small to be an NDS ROM")
            code = hdr[0x0C:0x10]
            if not all(0x20 < b < 0x7F for b in code):
                raise NdsError("No valid game code in the ROM header")
            info = NdsInfo(
                game_code=code.decode("ascii"),
                maker_code=hdr[0x10:0x12].decode("ascii", "replace"),
                header_title=hdr[0:12].split(b"\0", 1)[0].decode("ascii", "replace").strip(),
                rom_version=hdr[0x1E],
                title="",
                publisher="",
            )
            lines = []
            banner = struct.unpack_from("<I", hdr, 0x68)[0]
            if banner:
                f.seek(banner + BANNER_ENGLISH_TITLE)
                raw = f.read(0x100)
                if len(raw) == 0x100:
                    text = raw.decode("utf-16-le", "replace").split("\0", 1)[0]
                    lines = [s.strip() for s in text.replace("\r", "").split("\n") if s.strip()]
    except OSError as ex:
        raise NdsError(f"Could not read file: {ex.strerror or ex}")

    # Same split as YANBF: 3 lines = title, subtitle, publisher; 2 = title, publisher.
    if len(lines) >= 3:
        info.title, info.publisher = " ".join(lines[:-1]), lines[-1]
    elif len(lines) == 2:
        info.title, info.publisher = lines
    elif len(lines) == 1:
        info.title = lines[0]
    else:
        info.title = info.header_title
    return info


def default_rom_dir():
    """SD folder for ROMs, from YANBF's default_path.txt (fallback /roms/nds/)."""
    try:
        with open(paths.DEFAULT_ROM_PATH_TXT, encoding="utf-8") as f:
            d = f.read().strip().replace("\\", "/")
    except OSError:
        d = ""
    if not d:
        d = "/roms/nds/"
    if not d.startswith("/"):
        d = "/" + d
    if not d.endswith("/"):
        d += "/"
    return d


def sd_rom_path(nds_path):
    return default_rom_dir() + os.path.basename(nds_path)


def product_code(game_code):
    return f"CTR-H-{game_code}"


# ---------------------------------------------------------------- ID registry

_registry_lock = threading.Lock()


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): int(str(v), 16) for k, v in data.get("assigned", {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def registry_key(game_code, name):
    """Games are keyed by game code; builds without a ROM by output name."""
    return game_code if game_code else f"name:{name}"


def suggest_unique_id(key, registry_path=None, start=ID_FIRST):
    """Return (uid_int, reused). Reuses the key's ID (so a rebuild installs as an
    update), else the next free ID at or above `start` (the user's ID start
    setting; default FF400), up to FFFFF."""
    with _registry_lock:
        assigned = _load(registry_path or paths.ID_REGISTRY)
    if key in assigned:
        return assigned[key], True
    used = set(assigned.values())
    in_range = [u for u in used if start <= u <= ID_MAX]
    candidate = max(in_range) + 1 if in_range else start
    if candidate > ID_MAX or candidate in used:
        candidate = next((u for u in range(start, ID_MAX + 1) if u not in used), start)
    return candidate, False


def owners_of(uid, registry_path=None):
    """Keys that were built with this Unique ID."""
    with _registry_lock:
        assigned = _load(registry_path or paths.ID_REGISTRY)
    return [k for k, v in assigned.items() if v == uid]


def record_unique_id(key, uid, registry_path=None):
    path = registry_path or paths.ID_REGISTRY
    with _registry_lock:
        assigned = _load(path)
        assigned[key] = uid
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"assigned": {k: f"0x{v:X}" for k, v in sorted(assigned.items())}}, f, indent=2)
        os.replace(tmp, path)
