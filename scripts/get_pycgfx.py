"""Set up processes/YANBF/pycgfx: skyfloogle's pycgfx with this project's two fixes.

pycgfx has no license that allows sharing it, so the repository doesn't contain it.
This downloads the original from GitHub at a pinned commit, applies
patches/pycgfx.patch (the fixes are described in patches/pycgfx-PATCH_NOTES.txt) and
checks the result is byte-for-byte the tested version. Needs git on the PATH.

    python scripts/get_pycgfx.py            (does nothing if it's already set up)
    python scripts/get_pycgfx.py --force    (replace an existing copy)
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

REPO_URL = "https://github.com/skyfloogle/pycgfx.git"
COMMIT = "1f78850086f3a77c41e07162e842f97a5bf3c18a"  # upstream HEAD, 2 June 2025
MAIN_SHA256 = "52c5b8487e92f39f9271224c239738301def6deb385ae718ed201972cc1ea2b9"  # patched main.py

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(ROOT, "patches", "pycgfx.patch")
NOTES = os.path.join(ROOT, "patches", "pycgfx-PATCH_NOTES.txt")
DEST = os.path.join(ROOT, "processes", "YANBF", "pycgfx")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def git(*args, cwd=None):
    # autocrlf off: the patch and the hash are for LF line endings, on every system
    subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "advice.detachedHead=false", *args],
                   cwd=cwd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="replace an existing copy")
    force = ap.parse_args().force
    main_py = os.path.join(DEST, "main.py")
    if os.path.isfile(main_py) and not force:
        if sha256(main_py) == MAIN_SHA256:
            print(f"pycgfx is already set up: {DEST}")
            return 0
        print(f"{main_py} exists but isn't the expected patched version.\n"
              "Run again with --force to replace it.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "pycgfx")
        print(f"Downloading pycgfx {COMMIT[:7]} from {REPO_URL}")
        git("clone", "--quiet", REPO_URL, src)
        git("checkout", "--quiet", COMMIT, cwd=src)
        print("Applying patches/pycgfx.patch")
        git("apply", PATCH, cwd=src)
        got = sha256(os.path.join(src, "main.py"))
        if got != MAIN_SHA256:
            print(f"The patched main.py isn't the tested version (sha256 {got}). Nothing was changed.",
                  file=sys.stderr)
            return 1
        if os.path.isdir(DEST):
            shutil.rmtree(DEST)
        os.makedirs(DEST)
        shutil.copytree(os.path.join(src, "cgfx"), os.path.join(DEST, "cgfx"))
        for name in ("main.py", "banner-camera.gltf", "cgfx.hexpat"):
            shutil.copy2(os.path.join(src, name), os.path.join(DEST, name))
        shutil.copy2(os.path.join(src, "README.md"), os.path.join(DEST, "README_ORIGINAL.md"))
        shutil.copy2(NOTES, os.path.join(DEST, "PATCH_NOTES.txt"))
    print(f"pycgfx is set up: {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
