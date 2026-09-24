"""User settings, saved as BASE_DIR/settings.json so they persist between runs.

  id_start - the first Unique ID offered to a new game. It's chosen as an offset
             from FF400 (the start of YANBF's range), so it runs from FF400
             (offset 0) to FFFFF (offset 3071, the top of the homebrew ID range).
  theme    - appearance: "system" (follow Windows, the default), "light" or "dark".
  ftp_host, ftp_port, ftp_cia_dir - the 3DS's FTP server (ftpd) and the SD card
             folder .cia files are sent to, remembered by the Send to 3DS window.

Each setting is read on its own: a missing or damaged value falls back to its
default without affecting the others.
"""

import json
import os

import paths

ID_DEFAULT_START = 0xFF400
ID_MIN_START = ID_DEFAULT_START  # offset 0
ID_MAX = 0xFFFFF
MAX_OFFSET = ID_MAX - ID_DEFAULT_START  # 3071
LOW_IDS_WARNING = 19  # warn when this many IDs or fewer are left before ID_MAX

THEMES = ("system", "light", "dark")
FTP_DEFAULT_PORT = 5000  # ftpd's default
FTP_DEFAULT_CIA_DIR = "/cias/"
DEFAULTS = {"id_start": ID_DEFAULT_START, "theme": "system",
            "ftp_host": "", "ftp_port": FTP_DEFAULT_PORT, "ftp_cia_dir": FTP_DEFAULT_CIA_DIR}


def load(path=None):
    data = dict(DEFAULTS)
    try:
        with open(path or paths.SETTINGS, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return data
    if not isinstance(raw, dict):
        return data
    try:
        start = int(str(raw.get("id_start", "")), 16)
        if validate_id_start(f"{start:X}")[1] is None:
            data["id_start"] = start
    except ValueError:
        pass
    if raw.get("theme") in THEMES:
        data["theme"] = raw["theme"]
    host = raw.get("ftp_host")
    if isinstance(host, str) and len(host) <= 255 and not any(c.isspace() for c in host):
        data["ftp_host"] = host
    port = raw.get("ftp_port")
    if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
        data["ftp_port"] = port
    cia_dir = raw.get("ftp_cia_dir")
    if isinstance(cia_dir, str) and cia_dir.strip():
        data["ftp_cia_dir"] = cia_dir
    return data


def save(data, path=None):
    path = path or paths.SETTINGS
    out = {"id_start": f"0x{data['id_start']:X}", "theme": data.get("theme", "system"),
           "ftp_host": data.get("ftp_host", ""), "ftp_port": data.get("ftp_port", FTP_DEFAULT_PORT),
           "ftp_cia_dir": data.get("ftp_cia_dir", FTP_DEFAULT_CIA_DIR)}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, path)


def _past_max(what):
    return (f"{what} is past the highest ID ({ID_MAX:X}). The largest offset is "
            f"{MAX_OFFSET} (start {ID_MAX:X}).")


def validate_id_start(text):
    """Return (start, error) for the hex 'start ID' field."""
    s = (text or "").strip()
    if s[:2].lower() == "0x":
        s = s[2:]
    if not s:
        return None, f"Enter a hex ID, e.g. {ID_DEFAULT_START:X}"
    bad = sorted({c for c in s if c not in "0123456789abcdefABCDEF"})
    if bad:
        return None, "Not hexadecimal: invalid character(s) " + " ".join(repr(c) for c in bad)
    v = int(s, 16)
    if v < ID_MIN_START:
        return None, f"Must be {ID_MIN_START:X} or higher (offset 0)"
    if v > ID_MAX:
        return None, _past_max(f"Start {v:X}")
    return v, None


def validate_offset(text):
    """Return (start, error) for the offset spinner (a whole number of IDs past FF400)."""
    s = (text or "").strip()
    if not s:
        return None, "Enter an offset, e.g. 0"
    try:
        n = int(s)
    except ValueError:
        return None, "The offset must be a whole number"
    if n < 0:
        return None, "The offset can't be negative"
    if n > MAX_OFFSET:
        return None, _past_max(f"Offset {n} (ID {ID_DEFAULT_START + n:X})")
    return ID_DEFAULT_START + n, None


def ids_left(start):
    """How many IDs there are from start up to and including ID_MAX."""
    return ID_MAX - start + 1


def low_ids_warning(start):
    left = ids_left(start)
    if left > LOW_IDS_WARNING:
        return None
    return (f"Only {left} ID{'s' if left != 1 else ''} left from {start:X} to {ID_MAX:X}: "
            f"you'll run out after {left} more new game{'s' if left != 1 else ''}.")
