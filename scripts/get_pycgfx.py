"""Set up processes/YANBF/pycgfx: skyfloogle's pycgfx with this project's two fixes.

The same as the app's "Download and set up automatically" button, for the command
line (e.g. a build machine). pycgfx has no license that allows sharing it, so the
repository doesn't contain it. This downloads the tested version (commit 1f78850)
straight from GitHub, applies the fixes (patches/pycgfx.patch; described in
patches/pycgfx-PATCH_NOTES.txt) and checks every file by SHA-256. No git needed.

    python scripts/get_pycgfx.py            (does nothing if it's already set up)
    python scripts/get_pycgfx.py --force    (replace an existing copy)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import paths  # noqa: E402
import pycgfx_setup as ps  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="replace an existing copy")
    force = ap.parse_args().force
    state, problems = ps.status()
    if state == "ok" and not force:
        print(f"pycgfx {ps.SHORT} is already set up: {paths.PYCGFX_DIR}")
        return 0
    if state == "stock" and not force:
        ps.fix_stock()
        print(f"Added the fixes to pycgfx {ps.SHORT}: {paths.PYCGFX_DIR}")
        return 0
    if state == "wrong" and not force:
        print(f"{paths.PYCGFX_DIR} holds a different pycgfx (missing or different: {', '.join(problems)}).\n"
              "Run again with --force to replace it.", file=sys.stderr)
        return 1
    print(f"Downloading pycgfx {ps.SHORT} ({ps.DATE}) from {ps.REPO}")
    try:
        ps.install_from_zip(ps.download())
    except (ps.SetupError, OSError) as ex:
        print(f"Failed: {ex}", file=sys.stderr)
        return 1
    print(f"pycgfx {ps.SHORT} is set up, with the fixes: {paths.PYCGFX_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
