"""'Set up pycgfx' window: shown at startup when the pycgfx folder isn't the tested
version (see pycgfx_setup). The window itself is setup_window.SetupWindow; this adds
pycgfx's wording and checks. On macOS only the manual option is shown, and the files
go in ~/Library/Application Support/YANBF-CBC/pycgfx."""

import paths
import pycgfx_setup as ps
from setup_window import SetupWindow


class PycgfxWindow(SetupWindow):
    title = "Set up pycgfx"
    heading = "One more file is needed: pycgfx"
    intro = ("YANBF-CBC uses pycgfx, by skyfloogle, to turn 3D (.glb) banners into the 3DS banner "
             "format. It isn't included with this program because its author hasn't published a "
             "license that allows sharing it, so it has to come from skyfloogle's own GitHub. YANBF-CBC "
             "is unofficial and not connected to pycgfx or skyfloogle, so please don't report problems "
             "with this setup to them.")
    warn_title = f"Use exactly this version: pycgfx {ps.SHORT} ({ps.DATE})"
    warn_text = ("This build of YANBF-CBC was made and tested with that version. Newer or older "
                 "versions of pycgfx are not accepted - the program checks every file. It then "
                 "adds its own two fixes (logo billboarding and a crash fix) automatically, so "
                 "don't edit the files yourself.")
    auto_caption = (f"Downloads version {ps.SHORT} (about {ps.ZIP_SIZE / 1048576:.1f} MB) from {ps.REPO}, "
                    "adds the fixes and puts the files in the right place.")
    link_label = f"Download this exact version ({ps.SHORT}) as a zip:"
    link_url = ps.ZIP_URL
    link_caption = "Not the green Code button on the main page - that gives the newest version."
    place_text = ("Unzip it, then copy main.py, banner-camera.gltf and the cgfx folder into this folder "
                  "(or just put the zip itself there):")
    check_text = "Press Check again. The program checks the version and adds the fixes."
    missing_text = "pycgfx isn't set up yet."
    done_text = f"pycgfx {ps.SHORT} is set up, with the fixes. You can build CIAs now."
    errors = (ps.SetupError, OSError)

    def folder(self):
        return paths.PYCGFX_DIR

    def state(self):
        return ps.status()

    def wrong_text(self, problems):
        listed = ", ".join(problems[:4]) + (f" and {len(problems) - 4} more" if len(problems) > 4 else "")
        return (f"The files in the folder aren't pycgfx version {ps.SHORT} "
                f"(missing or different: {listed}). Use the exact version linked above"
                + (", or the automatic option (it replaces them)." if self.auto else "."))

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

    def download_start_text(self):
        return f"Downloading pycgfx {ps.SHORT} from GitHub…"

    def download_status(self, n):
        return f"Downloading pycgfx {ps.SHORT}… {n / 1048576:.1f} MB"

    def installing_text(self):
        return "Checking the files and adding the fixes…"

    def downloaded_log(self):
        return f"pycgfx {ps.SHORT} downloaded from GitHub and set up, with the fixes"
