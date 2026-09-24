"""FTP client side of 'Send to 3DS': talks to an FTP server app running on the 3DS
(ftpd, which shows its IP and port - usually 5000 - on screen).

Everything here blocks, so the GUI calls it from a worker thread. Each operation
opens its own short connection, so an idle 3DS (or a dropped Wi-Fi link) never
leaves a stale session behind.

Uploads go to '<name>.part' first and are renamed into place only when complete,
so a cancelled or failed transfer never leaves a half-written .cia or ROM under
the real name (a truncated ROM would make the forwarder fail to boot).
"""

import ftplib
import os
import posixpath
import socket
import time

DEFAULT_PORT = 5000  # ftpd's default
DEFAULT_CIA_DIR = "/cias/"
TIMEOUT = 10  # seconds, per network operation
BLOCK = 64 * 1024


class Cancelled(Exception):
    pass


def parse_host(text):
    """Return (host, error) for the IP / host name box."""
    s = (text or "").strip()
    if not s:
        return None, "Enter the 3DS's IP address (ftpd shows it on screen)"
    if s.lower().startswith("ftp://"):
        s = s[6:]
    s = s.split("/", 1)[0]
    if ":" in s:  # '192.168.1.20:5000' pasted into the host box
        s = s.rsplit(":", 1)[0]
    if not s or any(c.isspace() for c in s):
        return None, "Not a valid IP address or host name"
    return s, None


def parse_port(text):
    s = (text or "").strip()
    try:
        n = int(s)
    except ValueError:
        return None, "The port must be a number (ftpd uses 5000)"
    if not 1 <= n <= 65535:
        return None, "The port must be 1-65535"
    return n, None


def normalize_dir(text):
    """SD card folder: forward slashes, leading and trailing '/'."""
    d = (text or "").strip().replace("\\", "/")
    if d.lower().startswith("sd:"):
        d = d[3:]
    d = "/" + d.strip("/")
    return d if d == "/" else d + "/"


def sd_path(rom_path):
    """The ROM path field ('/roms/nds/Game.nds' or 'sd:/roms/…') as an FTP path."""
    p = (rom_path or "").strip().replace("\\", "/")
    if p.lower().startswith("sd:"):
        p = p[3:]
    if not p:
        return ""
    return "/" + p.lstrip("/")


def human_size(n):
    if n is None:
        return "?"
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,} bytes" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def connect(host, port, timeout=TIMEOUT):
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login()  # anonymous; ftpd accepts any login
    try:
        ftp.voidcmd("TYPE I")
    except ftplib.all_errors:
        pass
    return ftp


def close(ftp):
    try:
        ftp.quit()
    except (ftplib.all_errors, AttributeError):
        try:
            ftp.close()
        except Exception:
            pass


def describe_error(ex):
    """Plain-English reason for a failed connection or transfer."""
    if isinstance(ex, Cancelled):
        return "Cancelled"
    if isinstance(ex, ConnectionRefusedError):
        return "Connection refused - is ftpd running on the 3DS, and is the port right?"
    if isinstance(ex, (socket.timeout, TimeoutError)):
        return ("Timed out - check the IP address, that the 3DS is on the same network, "
                "and that the firewall allows the connection")
    if isinstance(ex, socket.gaierror):
        return "Unknown host name - enter the IP address ftpd shows"
    if isinstance(ex, ftplib.error_perm):
        return f"The 3DS refused: {ex}"
    if isinstance(ex, OSError) and getattr(ex, "winerror", None) in (10051, 10065):
        return "Network unreachable - is the PC on the same network as the 3DS?"
    return f"{type(ex).__name__}: {ex}"


def listdir(ftp, path):
    """[(name, is_dir, size)] of a remote folder, folders first, then by name."""
    entries = []
    try:
        for name, facts in ftp.mlsd(path, facts=["type", "size"]):
            t = facts.get("type", "").lower()
            if name in (".", "..") or t in ("cdir", "pdir"):
                continue
            size = int(facts["size"]) if facts.get("size", "").isdigit() else None
            entries.append((name, t == "dir", None if t == "dir" else size))
    except ftplib.error_perm:  # server without MLSD: parse a unix-style LIST
        lines = []
        ftp.retrlines("LIST " + path, lines.append)
        for line in lines:
            parts = line.split(None, 8)
            if len(parts) < 9 or parts[8] in (".", ".."):
                continue
            is_dir = parts[0].startswith("d")
            size = int(parts[4]) if parts[4].isdigit() and not is_dir else None
            entries.append((parts[8], is_dir, size))
    entries.sort(key=lambda e: (not e[1], e[0].lower()))
    return entries


def remote_size(ftp, path):
    """Size of a remote file, or None if it isn't there."""
    try:
        return ftp.size(path)
    except ftplib.error_perm:
        pass
    # some servers only answer SIZE in some modes; fall back to the folder listing
    folder, name = posixpath.split(path)
    try:
        for n, is_dir, size in listdir(ftp, folder or "/"):
            if n == name and not is_dir:
                return size if size is not None else 0
    except ftplib.error_perm:
        pass
    return None


def makedirs(ftp, folder):
    """Create a remote folder and its parents (existing ones are fine)."""
    cur = ""
    for part in folder.strip("/").split("/"):
        if not part:
            continue
        cur += "/" + part
        try:
            ftp.mkd(cur)
        except ftplib.error_perm:
            pass  # already exists (or can't be made - the upload will say so)


def upload(ftp, local, remote, progress=None, cancel=None):
    """Upload local -> remote (full path) via remote + '.part'.

    progress(sent, total) is called as data goes out; cancel is a threading.Event
    that stops the transfer (raising Cancelled). The .part file is removed if the
    upload doesn't finish."""
    total = os.path.getsize(local)
    folder = posixpath.dirname(remote)
    if folder and folder != "/":
        makedirs(ftp, folder)
    part = remote + ".part"
    sent = 0
    if progress:
        progress(0, total)

    def on_block(block):
        nonlocal sent
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        sent += len(block)
        if progress:
            progress(sent, total)

    try:
        with open(local, "rb") as f:
            ftp.storbinary("STOR " + part, f, BLOCK, on_block)
    except BaseException:
        _discard(ftp, part)
        raise
    try:
        ftp.delete(remote)  # replacing: FAT won't rename over an existing file
    except ftplib.error_perm:
        pass
    ftp.rename(part, remote)
    return total


def _discard(ftp, part):
    """Best-effort removal of a partial upload (the data connection may be broken,
    so fall back to a fresh control connection)."""
    try:
        ftp.abort()
    except Exception:
        pass
    try:
        ftp.delete(part)
        return
    except Exception:
        pass
    try:
        host, port = ftp.host, ftp.port
        again = connect(host, port)
        try:
            again.delete(part)
        finally:
            close(again)
    except Exception:
        pass


class Rate:
    """Smoothed transfer speed for the progress text."""

    def __init__(self):
        self.t0 = time.monotonic()
        self.last = (self.t0, 0)
        self.bps = None

    def update(self, sent):
        now = time.monotonic()
        t, s = self.last
        if now - t >= 0.5:
            inst = (sent - s) / (now - t)
            self.bps = inst if self.bps is None else self.bps * 0.6 + inst * 0.4
            self.last = (now, sent)
        return self.bps
