"""Set up ctrtool in processes/Project_CTR/ from Project_CTR's own release.

The same as the app's "Download and set up automatically" button, for the command
line (e.g. a build machine). No license has been published for ctrtool, so the
repository doesn't contain it. This downloads the tested release (ctrtool v1.3.0)
for this computer straight from GitHub and checks it by SHA-256.

    python scripts/get_ctrtool.py            (does nothing if it's already set up)
    python scripts/get_ctrtool.py --force    (replace an existing copy)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import ctrtool_setup as cs  # noqa: E402
import paths  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="replace an existing copy")
    force = ap.parse_args().force
    state = cs.status()
    if state == "ok" and not force:
        cs.prepare()
        print(f"ctrtool {cs.VERSION} is already set up: {paths.CTRTOOL}")
        return 0
    if state == "wrong" and not force:
        print(f"{paths.CTRTOOL} is a different ctrtool. Run again with --force to replace it.", file=sys.stderr)
        return 1
    if cs.variant() is None:
        print("There's no pinned ctrtool build for this system; put ctrtool in "
              f"{paths.CTRTOOL_DIR} yourself.", file=sys.stderr)
        return 1
    print(f"Downloading {cs.zip_name()} from {cs.REPO}")
    try:
        cs.install_from_zip(cs.download())
    except (cs.SetupError, OSError) as ex:
        print(f"Failed: {ex}", file=sys.stderr)
        return 1
    print(f"Set up ctrtool {cs.VERSION}: {paths.CTRTOOL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
