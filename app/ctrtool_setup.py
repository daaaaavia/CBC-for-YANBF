"""Setting up ctrtool (Project_CTR's CIA reader) in paths.CTRTOOL_DIR.

No license has been published for ctrtool, so CBC for YANBF doesn't include it. This
module checks what's installed and can set it up from Project_CTR's own release:
  * automatically (Windows): download the release zip, check it and unzip it
  * by hand: the user downloads the zip and puts it (or the unzipped ctrtool) in the
    folder; tidy_manual_placement() unzips it, and on a Mac makes it runnable
Only the pinned release is accepted - every build is checked by SHA-256 - so a newer
or older ctrtool is never used by mistake.
"""

import hashlib
import io
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

import paths
import platform_util as pu

TAG = "ctrtool-v1.3.0"
VERSION = "1.3.0"
DATE = "18 January 2026"
REPO = "https://github.com/3DSGuy/Project_CTR"
RELEASE_URL = f"{REPO}/releases/tag/{TAG}"  # the page the user downloads from by hand
TIMEOUT = 30

# Project_CTR's release builds: {variant: (zip size in bytes, SHA-256 of the program inside)}
BUILDS = {
    "win_x64": (442824, "79021f283b2199950eb22cf3c459806b9c8aaaf68f65c80100107d3454a1c224"),
    "macos_arm64": (883784, "e4bae2eb1b254af5f4849d5807c92b3caff768fab5d5ead5f50ca0fe4ac7ff81"),
    "macos_x86_64": (841994, "cb79d940548dbc36f19713ee0146e35486a9293a90ecb125b3c2fe122ee80508"),
}


class SetupError(Exception):
    pass


def variant():
    """This computer's build: win_x64, macos_arm64 or macos_x86_64 (None elsewhere)."""
    if pu.is_windows():
        return "win_x64"
    if pu.is_mac():
        return "macos_arm64" if platform.machine() == "arm64" else "macos_x86_64"
    return None


def zip_name(v=None):
    return f"{TAG}-{v or variant()}.zip"


def zip_url(v=None):
    return f"{REPO}/releases/download/{TAG}/{zip_name(v)}"


def zip_size(v=None):
    return BUILDS.get(v or variant(), (900000, None))[0]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _exe():
    return pu.exe_name("ctrtool")


def _target(dest):
    return os.path.join(dest or paths.CTRTOOL_DIR, _exe())


def status(dest=None):
    """'ok' | 'missing' | 'wrong'. Off Windows and macOS (running from source on Linux)
    any ctrtool is accepted, since there's no pinned build to compare with."""
    try:
        with open(_target(dest), "rb") as f:
            data = f.read()
    except OSError:
        return "missing"
    want = BUILDS.get(variant(), (None, None))[1]
    return "ok" if want is None or _sha(data) == want else "wrong"


def is_ready(dest=None):
    return status(dest) == "ok"


def _make_runnable(path):
    """macOS/Linux: a file from a zip or a browser download may lack the executable bit,
    and on a Mac the browser marks it as quarantined. It has passed the SHA-256 check
    against Project_CTR's release, so it's safe to clear both."""
    if pu.is_windows():
        return
    os.chmod(path, os.stat(path).st_mode | 0o111)
    if pu.is_mac():
        subprocess.run(["xattr", "-d", "com.apple.quarantine", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prepare(dest=None):
    """Make an OK ctrtool runnable (see _make_runnable). Returns True if it's ready."""
    if not is_ready(dest):
        return False
    try:
        _make_runnable(_target(dest))
    except OSError:
        pass
    return True


def tidy_manual_placement(dest=None):
    """Accept the usual ways of placing it by hand: the downloaded zip dropped in the
    folder, or the unzipped folder put inside it. Returns what was done, or None."""
    dest = dest or paths.CTRTOOL_DIR
    if not os.path.isdir(dest) or os.path.isfile(_target(dest)):
        return None
    for name in sorted(os.listdir(dest)):
        p = os.path.join(dest, name)
        if name.lower().startswith("ctrtool") and name.lower().endswith(".zip") and os.path.isfile(p):
            with open(p, "rb") as f:
                install_from_zip(f.read(), dest)
            os.remove(p)
            return f"Unzipped {name}"
    for name in sorted(os.listdir(dest)):
        inner = os.path.join(dest, name, _exe())
        if name.lower().startswith("ctrtool") and os.path.isfile(inner):
            shutil.move(inner, _target(dest))
            shutil.rmtree(os.path.join(dest, name), ignore_errors=True)
            return f"Moved {_exe()} out of the {name} folder"
    return None


def download(progress=None, cancel=None):
    """This computer's release zip from GitHub, as bytes. progress(bytes_so_far, total or None)."""
    req = urllib.request.Request(zip_url(), headers={"User-Agent": "CBC-for-YANBF"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        total = int(r.headers.get("Content-Length") or 0) or None
        buf = bytearray()
        while True:
            if cancel is not None and cancel.is_set():
                raise SetupError("Cancelled")
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            buf += chunk
            if progress:
                progress(len(buf), total)
    return bytes(buf)


def install_from_zip(data, dest=None):
    """Install ctrtool from Project_CTR's release zip into dest. Checks it before
    touching anything; the other tools in the folder are left alone."""
    dest = dest or paths.CTRTOOL_DIR
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise SetupError("The download isn't a valid zip file")
    names = [n for n in z.namelist() if n.rsplit("/", 1)[-1] == _exe()]
    if not names:
        raise SetupError(f"The zip has no {_exe()} - is it the {zip_name()} download?")
    blob = z.read(names[0])
    want = BUILDS.get(variant(), (None, None))[1]
    if want is not None and _sha(blob) != want:
        raise SetupError(f"This isn't ctrtool {VERSION} for this computer ({zip_name()}). "
                         "Use the exact file linked in the setup window.")
    os.makedirs(dest, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="ctrtool-", dir=dest)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, _target(dest))
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    _make_runnable(_target(dest))
    if not is_ready(dest):
        raise SetupError("ctrtool was written but doesn't check out - try again")
    return _target(dest)
