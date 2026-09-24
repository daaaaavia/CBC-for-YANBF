"""The few things that differ between Windows and macOS (and Linux, which works for
running from source but isn't packaged).

Everything here checks sys.platform when it's called, not at import, so the tests can
switch it to 'darwin' on Windows and check the Mac behaviour.
"""

import os
import subprocess
import sys


def is_windows():
    return sys.platform == "win32"


def is_mac():
    return sys.platform == "darwin"


def exe_name(name):
    """Native tool file name: 'makerom' -> 'makerom.exe' on Windows, 'makerom' elsewhere."""
    return name + ".exe" if is_windows() else name


def popen_flags():
    """Extra subprocess arguments: no console window for the tools on Windows. Elsewhere
    nothing - a non-zero creationflags raises ValueError on macOS/Linux."""
    if is_windows():
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def file_manager():
    return "Explorer" if is_windows() else "Finder" if is_mac() else "the file manager"


def open_command(path):
    """Command that opens a folder or file in Finder / the desktop (not used on Windows)."""
    return ["open", path] if is_mac() else ["xdg-open", path]


def open_path(path):
    """Show a folder in Explorer / Finder."""
    if is_windows():
        os.startfile(path)
    else:
        subprocess.Popen(open_command(path), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------- dark mode
def parse_apple_style(returncode, output):
    """`defaults read -g AppleInterfaceStyle` prints 'Dark' in dark mode, and fails
    (the key doesn't exist) in light mode."""
    return returncode == 0 and output.strip().lower() == "dark"


def mac_is_dark():
    try:
        r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True,
                           text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return False
    return parse_apple_style(r.returncode, r.stdout)


# ---------------------------------------------------------------------- audio
def audio_command(path):
    """Player command for macOS (afplay, built in) or Linux."""
    return ["afplay", path] if is_mac() else ["paplay", path]


class AudioPlayer:
    """Play one .wav at a time, in the background. winsound on Windows; afplay on macOS."""

    def __init__(self):
        self.proc = None

    def play(self, path):
        """Start playing (stopping anything already playing). Raises RuntimeError if the
        file can't be played."""
        self.stop()
        if is_windows():
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        try:
            self.proc = subprocess.Popen(audio_command(path), stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as ex:
            raise RuntimeError(str(ex))

    def playing(self):
        """True while a clip plays (afplay still running). None on Windows, where
        winsound can't tell - the caller times the clip instead."""
        if is_windows():
            return None
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if is_windows():
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass
            return
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.proc = None
