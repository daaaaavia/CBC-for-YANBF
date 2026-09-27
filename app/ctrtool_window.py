"""'Set up ctrtool' window: shown at startup when ctrtool isn't the pinned Project_CTR
release (see ctrtool_setup). The window itself is setup_window.SetupWindow; this adds
ctrtool's wording and checks. On macOS only the manual option is shown, and ctrtool
goes in ~/Library/Application Support/CBC-for-YANBF/ctrtool."""

import ctrtool_setup as cs
import paths
import platform_util as pu
from setup_window import SetupWindow


class CtrtoolWindow(SetupWindow):
    title = "Set up ctrtool"
    heading = "One more file is needed: ctrtool"
    intro = ("CBC for YANBF uses ctrtool, from 3DSGuy's Project_CTR, to read and check finished CIAs. "
             "No license has been published for it, so it isn't included with this program and has "
             "to come from Project_CTR's own release page. CBC for YANBF is unofficial and not connected "
             "to Project_CTR, so please don't report problems with this setup to them.")
    warn_title = f"Use exactly this version: ctrtool {cs.VERSION} ({cs.DATE})"
    warn_text = ("This build of CBC for YANBF was made and tested with that release. Other versions "
                 "aren't accepted - the program checks the file.")
    link_label = f"Download ctrtool {cs.VERSION} for this computer:"
    link_caption = ""
    check_text = "Press Check again. The program checks the version."
    missing_text = "ctrtool isn't set up yet."
    done_text = f"ctrtool {cs.VERSION} is set up. You can build CIAs now."
    errors = (cs.SetupError, OSError)

    def __init__(self, app, on_ready):
        name = cs.zip_name()
        self.link_url = cs.zip_url()
        self.auto_caption = (f"Downloads {name} (about {cs.zip_size() / 1048576:.1f} MB) from Project_CTR's "
                             "GitHub releases, checks it and puts ctrtool in the right place.")
        self.link_caption = (f"That's {name}. On a Mac, pick the right one for your chip: Apple Silicon "
                             "(M1 or later) is macos_arm64, Intel is macos_x86_64." if pu.is_mac() else "")
        self.place_text = (f"Put the zip itself in this folder, or unzip it and put {pu.exe_name('ctrtool')} "
                           "there:")
        super().__init__(app, on_ready)

    def folder(self):
        return paths.CTRTOOL_DIR

    def state(self):
        return cs.status(), []

    def wrong_text(self, problems):
        return (f"The {pu.exe_name('ctrtool')} in the folder isn't ctrtool {cs.VERSION} for this computer. "
                "Use the exact file linked above" + (", or the automatic option (it replaces it)."
                                                     if self.auto else "."))

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

    def download_start_text(self):
        return f"Downloading ctrtool {cs.VERSION} from GitHub…"

    def download_status(self, n):
        return f"Downloading ctrtool {cs.VERSION}… {n / 1048576:.1f} MB"

    def installing_text(self):
        return "Checking the file…"

    def downloaded_log(self):
        return f"ctrtool {cs.VERSION} downloaded from Project_CTR's releases and set up"
