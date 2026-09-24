"""Setting up pycgfx (skyfloogle's .glb -> CGFX converter) in processes/YANBF/pycgfx/.

pycgfx has no license that allows sharing it, so the GitHub version of YANBF-CBC
doesn't include it. This module checks what's installed and can set it up:

  * download(): the exact tested version (commit 1f78850, 2 June 2025) as a zip
    straight from github.com/skyfloogle/pycgfx - no git needed
  * install_from_zip(): unzip the needed files, apply this project's two fixes
    (PATCH, the same as patches/pycgfx.patch) and check every file by SHA-256
  * status(): 'ok' (the tested, fixed version), 'stock' (the original files of that
    version, placed by hand - fix_stock() adds the two fixes), 'missing' or 'wrong'

Everything is checked against hashes of the tested version, so a newer or older
pycgfx is never used by mistake.
"""

import hashlib
import io
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile

import paths

COMMIT = "1f78850086f3a77c41e07162e842f97a5bf3c18a"
SHORT = COMMIT[:7]
DATE = "2 June 2025"
REPO = "https://github.com/skyfloogle/pycgfx"
ZIP_URL = f"{REPO}/archive/{COMMIT}.zip"  # what the user downloads by hand
DOWNLOAD_URL = f"https://codeload.github.com/skyfloogle/pycgfx/zip/{COMMIT}"  # same zip, no redirect
TIMEOUT = 30
ZIP_SIZE = 3365659  # bytes; GitHub doesn't send a length for this zip, so progress uses this

# SHA-256 of the files at COMMIT (LF line endings, as GitHub serves them)
STOCK_MAIN = "8ed86c8f403f76adea97859d9ef1cf3689013617f87b31e8e8ccb763e4b9b896"
PATCHED_MAIN = "52c5b8487e92f39f9271224c239738301def6deb385ae718ed201972cc1ea2b9"
FILES = {  # needed to run; main.py is checked separately (stock or patched)
    "banner-camera.gltf": "c830b751743c6fe89c7d6bd81cc155759beaa7883ed06b6836b94d42968c3ab0",
    "cgfx/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "cgfx/animation.py": "b14e0734e6a371fb83c8767b81603f60bc01f661ccbe2030f49771432fc00966",
    "cgfx/canm.py": "f746dafb0b133bc0114fc8f3c6fdcdca452c34fd5c2876ddd5de70d16cc1cd07",
    "cgfx/cenv.py": "f43021ecc762b499cc8bed5bbf02edadb56b983c80b9e23322f847ddda3b15aa",
    "cgfx/cflt.py": "587260228d6f002ea58a236d37a9772bf0227c5d7b5f266276f0340794882dff",
    "cgfx/cgfx.py": "1b009a15600e62ad20c503206817bc101585441926c598bf25b5791fefa633fe",
    "cgfx/cmdl.py": "b75116d48fc0b72bbed69b9bc5c2a4fbe304d578dfe0e2a1fc5a50f84836c65c",
    "cgfx/dict.py": "d29cea0abdb3735de2f189b0d4b2a3c02d75eb1184c936049c37bf73d75d921a",
    "cgfx/luts.py": "08fbef437c7f3b729906cd01895ce0695ee126eadef82531b4dd1346e1a3a10f",
    "cgfx/mtob.py": "4eecd2abc1015ad15b85f06f7cf00e04b478f746973dc0708b259105f01e4d39",
    "cgfx/patricia.py": "bf120761d281733a7c1e02ef2f805e7174fb95b051766a0d3ee11d6cb8dfaa49",
    "cgfx/primitives.py": "c6b475be1392c8a1cfc0bb5c8ddf1ab1a180759e2a67fca25fe89611b04027e3",
    "cgfx/shared.py": "a5f570c9a17482f52b125bd77a19f9cc35fa9ba2bd151d114888cec2583e0add",
    "cgfx/sobj.py": "464250500e96c1178d8ca66a791d961354224b0d2880b9f58661626d8498a6f7",
    "cgfx/swizzler.py": "f63bd6e163a3a70342b40a2f041e7aad4c2693bddcf0843a10d1112a85353389",
    "cgfx/txob.py": "8b1aae4afd9337f234493800a84b77f50897706dc436d648fa86aaf01c82b9e9",
}
EXTRAS = {"cgfx.hexpat": "cgfx.hexpat", "README.md": "README_ORIGINAL.md"}  # copied too, not required

# This project's two fixes to main.py - identical to patches/pycgfx.patch.
PATCH = """\
diff --git a/main.py b/main.py
index 86057cf..f2f4789 100755
--- a/main.py
+++ b/main.py
@@ -420,6 +420,8 @@ def make_bones(
         node = gltf.model.nodes[node_id]
         bone = Bone()
         bone.name = node.name or f"Node {node_id}"
+        if bone.name == "name" or bone.name == "nameModel":
+            bone.billboard_mode = BillboardMode.YAxial
         bone_dict.add(bone.name, bone)
         bone.joint_id = node_id
         bone.flags = (
@@ -760,8 +762,9 @@ def convert_gltf(gltf: gltflib.GLTF) -> CGFX:
                 )
             sobj_mesh = SOBJMesh(cmdl)
             cmdl.meshes.add(sobj_mesh)
+            sobj_mesh.mesh_node_name = cmdl.skeleton.bones[node_to_bone[node_id]]
             sobj_mesh.name = (
-                (mesh.name or cmdl.skeleton.bones[node_to_bone[node_id]])
+                (mesh.name or sobj_mesh.mesh_node_name)
                 + "_"
                 + mtob.name
             )
"""

PATCH_NOTES = """\
This main.py is a PATCHED version of skyfloogle/pycgfx, not the stock release.

Two fixes applied vs. the original:
1. Every SOBJMesh now gets mesh_node_name set (was left blank in stock pycgfx).
2. Any bone literally named "name" or "nameModel" gets YAxial billboard mode
   applied automatically (stock pycgfx never sets this).

Both were required to get a working, non-crashing, non-spinning billboard
logo on real 3DS hardware. Do not replace this with the stock pycgfx
main.py unless you re-apply these two fixes.
"""


class SetupError(Exception):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def apply_patch(data, patch=PATCH, reverse=False):
    """Apply a unified diff (one file) to data (bytes, LF). reverse=True undoes it.
    Raises SetupError if the text doesn't match the patch's context."""
    lines = data.decode("utf-8").split("\n")
    out, pos = [], 0
    for hunk in re.split(r"(?m)^(?=@@ )", patch)[1:]:
        head, *body = hunk.rstrip("\n").split("\n")
        start = int(re.match(r"@@ -(\d+)", head).group(1)) - 1
        old, new = [], []
        for ln in body:
            tag, text = ln[:1], ln[1:]
            if reverse and tag in "+-":
                tag = "-" if tag == "+" else "+"
            if tag in " -":
                old.append(text)
            if tag in " +":
                new.append(text)
        if lines[start:start + len(old)] != old:  # not at the header's line (e.g. reversing): look for it
            start = _find(lines, old, pos)
        out += lines[pos:start] + new
        pos = start + len(old)
    return "\n".join(out + lines[pos:]).encode("utf-8")


def _find(lines, block, start):
    for i in range(start, len(lines) - len(block) + 1):
        if lines[i:i + len(block)] == block:
            return i
    raise SetupError("main.py doesn't match the version the fixes are for")


def status(dest=None):
    """('ok' | 'stock' | 'missing' | 'wrong', [files that are missing or different])."""
    dest = dest or paths.PYCGFX_DIR
    bad, missing = [], []
    for rel, want in FILES.items():
        data = _read(os.path.join(dest, *rel.split("/")))
        if data is None:
            missing.append(rel)
        elif _sha(data) != want:
            bad.append(rel)
    main = _read(os.path.join(dest, "main.py"))
    if main is None:
        missing.insert(0, "main.py")
    elif _sha(main) not in (PATCHED_MAIN, STOCK_MAIN):
        bad.insert(0, "main.py")
    if not bad and not missing:
        return ("ok" if _sha(main) == PATCHED_MAIN else "stock"), []
    if not bad and len(missing) == len(FILES) + 1:
        return "missing", missing
    return "wrong", bad + missing


def is_ready(dest=None):
    return status(dest)[0] == "ok"


def fix_stock(dest=None):
    """The original files of the tested version are in place: add the two fixes.
    Returns True if main.py was fixed."""
    dest = dest or paths.PYCGFX_DIR
    if status(dest)[0] != "stock":
        return False
    main_path = os.path.join(dest, "main.py")
    fixed = apply_patch(_read(main_path))
    if _sha(fixed) != PATCHED_MAIN:
        raise SetupError("Adding the fixes didn't give the tested main.py")
    with open(main_path, "wb") as f:
        f.write(fixed)
    with open(os.path.join(dest, "PATCH_NOTES.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PATCH_NOTES)
    return True


def tidy_manual_placement(dest=None):
    """Accept the usual ways of placing the files by hand: the downloaded zip itself
    dropped in the folder, or the whole unzipped 'pycgfx-...' folder put inside it.
    Returns a short description of what was done, or None."""
    dest = dest or paths.PYCGFX_DIR
    if not os.path.isdir(dest) or os.path.isfile(os.path.join(dest, "main.py")):
        return None
    for name in sorted(os.listdir(dest)):
        p = os.path.join(dest, name)
        if name.lower().endswith(".zip") and os.path.isfile(p):
            install_from_zip(_read(p), dest)  # replaces the folder, zip included
            return f"Unzipped {name}"
    subs = [n for n in os.listdir(dest) if os.path.isfile(os.path.join(dest, n, "main.py"))]
    if len(subs) == 1:
        inner = os.path.join(dest, subs[0])
        for n in os.listdir(inner):
            target = os.path.join(dest, n)
            if not os.path.exists(target):
                shutil.move(os.path.join(inner, n), target)
        shutil.rmtree(inner, ignore_errors=True)
        return f"Moved the files out of the {subs[0]} folder"
    return None


def download(progress=None, cancel=None):
    """The tested version's zip from GitHub, as bytes. progress(bytes_so_far, total or None)."""
    req = urllib.request.Request(DOWNLOAD_URL, headers={"User-Agent": "YANBF-CBC"})
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
    """Install the needed files from the tested version's zip (as downloaded from
    GitHub) into dest, with the two fixes. Checks everything before touching dest."""
    dest = dest or paths.PYCGFX_DIR
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise SetupError("The download isn't a valid zip file")
    names = {n.split("/", 1)[1]: n for n in z.namelist() if "/" in n and not n.endswith("/")}
    got = {}
    for rel in ["main.py", *FILES, *EXTRAS]:
        if rel not in names:
            if rel in EXTRAS:
                continue
            raise SetupError(f"The zip has no {rel} - is it the pycgfx download?")
        got[rel] = z.read(names[rel])
    wrong = [rel for rel, want in FILES.items() if _sha(got[rel]) != want]
    if _sha(got["main.py"]) != STOCK_MAIN or wrong:
        raise SetupError(f"This isn't pycgfx version {SHORT} ({DATE}) - "
                         f"{', '.join((['main.py'] if _sha(got['main.py']) != STOCK_MAIN else []) + wrong)} "
                         "differ. Use the exact version linked in the setup window.")
    got["main.py"] = apply_patch(got["main.py"])
    if _sha(got["main.py"]) != PATCHED_MAIN:
        raise SetupError("Adding the fixes didn't give the tested main.py")
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="pycgfx-", dir=parent)
    try:
        for rel, blob in got.items():
            out = os.path.join(tmp, *EXTRAS.get(rel, rel).split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(blob)
        with open(os.path.join(tmp, "PATCH_NOTES.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(PATCH_NOTES)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if not is_ready(dest):
        raise SetupError("The files were written but don't check out - try again")
    return sorted(got)
