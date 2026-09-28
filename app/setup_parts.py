"""The files CBC for YANBF can't include (no license allows sharing them), as parts
of the 'Set up downloads' window (setup_window.py): pycgfx and ctrtool. Each part
has its wording and its checks; the window does the rest."""

import ctrtool_setup as cs
import paths
import platform_util as pu
import pycgfx_setup as ps


class Part:
    key = name = ""
    errors = (OSError,)  # exceptions whose message is shown to the user

    def version(self):  # e.g. "pycgfx 1f78850 (2 June 2025)"
        raise NotImplementedError

    def what(self):  # one line: what it's for and where it comes from
        raise NotImplementedError

    def link_label(self):
        return f"Download exactly {self.version()}:"

    def link_url(self):
        raise NotImplementedError

    def link_caption(self):
        return ""

    def place_text(self):
        raise NotImplementedError

    def folder(self):
        raise NotImplementedError

    def state(self):
        """('ok' | 'missing' | 'wrong' | 'stock', [problem files])"""
        raise NotImplementedError

    def wrong_text(self, problems):
        raise NotImplementedError

    def prepare_manual(self):
        """Tidy up files placed by hand. Returns [(log kind, message)]."""
        return []

    def fetch(self, progress, cancel):
        raise NotImplementedError

    def install(self, data):
        raise NotImplementedError

    def download_size(self):
        raise NotImplementedError

    def downloaded_log(self):
        raise NotImplementedError


class Pycgfx(Part):
    key = name = "pycgfx"
    errors = (ps.SetupError, OSError)

    def version(self):
        return f"pycgfx {ps.SHORT} ({ps.DATE})"

    def what(self):
        return ("By skyfloogle. Turns 3D (.glb) banners into the 3DS banner format. It comes from "
                "skyfloogle's GitHub, and the program adds its own two fixes (logo billboarding and "
                "a crash fix) automatically, so don't edit the files.")

    def link_label(self):
        return f"Download exactly {self.version()} as a zip:"

    def link_url(self):
        return ps.ZIP_URL

    def link_caption(self):
        return "Not the green Code button on the main page - that gives the newest version."

    def place_text(self):
        return ("Unzip it and copy main.py, banner-camera.gltf and the cgfx folder into this folder "
                "(or just put the zip itself there):")

    def folder(self):
        return paths.PYCGFX_DIR

    def state(self):
        return ps.status()

    def wrong_text(self, problems):
        listed = ", ".join(problems[:4]) + (f" and {len(problems) - 4} more" if len(problems) > 4 else "")
        return f"The files there aren't pycgfx {ps.SHORT} (missing or different: {listed})."

    def prepare_manual(self):
        notes = []
        note = ps.tidy_manual_placement()
        if ps.fix_stock():
            notes.append(("ok", f"Added this project's two fixes to pycgfx {ps.SHORT}"))
        if note:
            notes.append(("info", note))
        return notes

    def fetch(self, progress, cancel):
        return ps.download(progress, cancel)

    def install(self, data):
        ps.install_from_zip(data)

    def download_size(self):
        return ps.ZIP_SIZE

    def downloaded_log(self):
        return f"pycgfx {ps.SHORT} downloaded from GitHub and set up, with the fixes"


class Ctrtool(Part):
    key = name = "ctrtool"
    errors = (cs.SetupError, OSError)

    def version(self):
        return f"ctrtool {cs.VERSION} ({cs.DATE})"

    def what(self):
        return "From 3DSGuy's Project_CTR. Reads finished CIAs. It comes from Project_CTR's own release page."

    def link_url(self):
        return cs.zip_url()

    def link_caption(self):
        if pu.is_mac():
            return (f"That's {cs.zip_name()}. On the release page, Apple Silicon (M1 or later) is "
                    "macos_arm64 and Intel is macos_x86_64.")
        return f"That's {cs.zip_name()}."

    def place_text(self):
        return f"Put the zip itself in this folder, or unzip it and put {pu.exe_name('ctrtool')} there:"

    def folder(self):
        return paths.CTRTOOL_DIR

    def state(self):
        return cs.status(), []

    def wrong_text(self, problems):
        return f"The {pu.exe_name('ctrtool')} there isn't ctrtool {cs.VERSION} for this computer."

    def prepare_manual(self):
        note = cs.tidy_manual_placement()
        cs.prepare()  # a Mac needs it runnable and out of quarantine
        return [("info", note)] if note else []

    def fetch(self, progress, cancel):
        return cs.download(progress, cancel)

    def install(self, data):
        cs.install_from_zip(data)

    def download_size(self):
        return cs.zip_size()

    def downloaded_log(self):
        return f"ctrtool {cs.VERSION} downloaded from Project_CTR's releases and set up"


PARTS = (Pycgfx(), Ctrtool())
