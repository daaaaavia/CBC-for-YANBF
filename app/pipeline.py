"""Build pipeline for YANBF-CBC: validation helpers, BuildJob, pycgfx loader, Pipeline.

Order: icon -> pycgfx (.glb only) -> audio -> banner -> CIA.
"""

import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import wave
from dataclasses import dataclass
from fractions import Fraction

# These imports are not used directly here. pycgfx is loaded from disk at run
# time, so PyInstaller never analyses it; importing its dependencies here makes
# sure they are bundled into the exe.
import abc  # noqa: F401
import argparse  # noqa: F401
import collections  # noqa: F401
import enum  # noqa: F401
import itertools  # noqa: F401
import math  # noqa: F401
import struct  # noqa: F401
import typing  # noqa: F401

import gltflib  # noqa: F401
from PIL import Image

import nds
import paths

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# Largest allowed .glb: the same limit pycgfx checks the converted CGFX against
# (main.py write(): it warns when len(data) > 0x80000) - 524,288 bytes = 512 KB,
# which is also the HOME Menu's banner CGFX limit. Exactly 512 KB is allowed.
GLB_LIMIT = 0x80000
GLB_LIMIT_TEXT = "512 KB"
# Longest allowed banner audio: the exact length of the reference clip
# "Freshly-Picked - Tingle's Rosy Rupeeland.wav" (141000 frames at 48 kHz).
# Compared as a fraction so there's no float rounding at the boundary.
AUDIO_MAX_SECONDS = Fraction(141000, 48000)  # = 2.9375 s
AUDIO_MAX_TEXT = "2.9375 s"
ICON_SIZE = (48, 48)  # the icon must be exactly this size
BANNER_MAX = (256, 128)
MINOR_MAX = 63

KIND_ICON = "icon"
KIND_BANNER_PNG = "banner_png"
KIND_GLB = "glb"
KIND_NDS = "nds"
KIND_AUDIO = "audio"

MODE_GLB = "glb"
MODE_PNG = "png"


# ---------------------------------------------------------------- validation

def parse_unique_id(text):
    """Return (makerom_value, error). makerom_value is '0x<UPPERHEX>' or None."""
    s = (text or "").strip()
    if s[:2].lower() == "0x":
        s = s[2:]
    if not s:
        return None, "Required: 1-6 hex digits, e.g. FF3F0"
    bad = sorted({c for c in s if c not in "0123456789abcdefABCDEF"})
    if bad:
        return None, "Not hexadecimal: invalid character(s) " + " ".join(repr(c) for c in bad)
    if len(s) > 6:
        return None, "Too long: max 6 hex digits (0xFFFFFF)"
    return "0x" + s.upper(), None


def parse_minor(value):
    """Return (int, error) for the minor version (0-63)."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None, f"Version must be a whole number 0-{MINOR_MAX}"
    if not 0 <= n <= MINOR_MAX:
        return None, f"Version must be 0-{MINOR_MAX}"
    return n, None


_check_cache = {}
_check_lock = threading.Lock()


def check_input_file(kind, path):
    """Validate an upload. Returns None if OK, otherwise an error string.

    Shared by the GUI (live) and the pipeline (at build start). Results are
    cached by (kind, path, mtime, size) so unrelated typing doesn't reopen files.
    """
    if not path:
        return "No file selected"
    try:
        st = os.stat(path)
    except OSError:
        return "File not found"
    if not os.path.isfile(path):
        return "File not found"
    key = (kind, os.path.abspath(path), st.st_mtime_ns, st.st_size)
    with _check_lock:
        if key in _check_cache:
            return _check_cache[key]
    result = _check_uncached(kind, path, st.st_size)
    with _check_lock:
        _check_cache[key] = result
    return result


def _check_uncached(kind, path, size):
    if kind == KIND_GLB:
        if os.path.splitext(path)[1].lower() != ".glb":
            return "Model must be a .glb file"
        if size > GLB_LIMIT:
            return (f"Model is {size:,} bytes ({size / 1024:.1f} KB) - must be at most "
                    f"{GLB_LIMIT:,} bytes ({GLB_LIMIT_TEXT})")
        return None

    if kind == KIND_AUDIO:
        try:
            with wave.open(path, "rb") as w:
                frames, rate = w.getnframes(), w.getframerate()
        except (wave.Error, EOFError, OSError) as ex:
            return f"Can't read this WAV ({ex}) - use an uncompressed PCM .wav"
        if not rate:
            return "Can't read this WAV (sample rate is 0)"
        length = Fraction(frames, rate)
        if length > AUDIO_MAX_SECONDS:
            # truncate (never round up) to the fewest decimals that still show it's over
            for places in range(2, 10):
                shown = Fraction(math.floor(length * 10 ** places), 10 ** places)
                if shown > AUDIO_MAX_SECONDS:
                    break
            secs = f"{float(shown):.{places}f}".rstrip("0").rstrip(".")
            return f"Audio is {secs} s long - must be at most {AUDIO_MAX_TEXT}"
        return None

    if kind == KIND_NDS:
        if os.path.splitext(path)[1].lower() != ".nds":
            return "ROM must be a .nds file"
        try:
            nds.read_nds(path)
        except nds.NdsError as ex:
            return f"Not a valid NDS ROM: {ex}"
        return None

    if kind == KIND_ICON:
        label, (max_w, max_h) = "Icon", ICON_SIZE
    elif kind == KIND_BANNER_PNG:
        label, (max_w, max_h) = "Banner image", BANNER_MAX
    else:
        raise ValueError(f"unknown kind {kind!r}")

    try:
        with Image.open(path) as im:
            fmt = im.format
            w, h = im.size
    except Exception:
        return f"{os.path.basename(path)} is not a readable image file"
    if fmt != "PNG":
        return f"{label} must be a PNG (this file is {fmt})"
    if kind == KIND_ICON:  # the HOME Menu icon is exactly 48x48
        if (w, h) != ICON_SIZE:
            return f"{label} is {w}×{h} px - must be exactly {max_w}×{max_h} px"
    elif w > max_w or h > max_h:
        return f"{label} is {w}×{h} px - must be at most {max_w}×{max_h} px"
    return None


# ---------------------------------------------------------------- naming

_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}


def sanitize_name(name):
    """Make a string safe to use as a Windows file/folder name."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    s = s.rstrip(". ").strip()
    if not s:
        return "untitled"
    if s.split(".")[0].upper() in _RESERVED:
        s = "_" + s
    return s


def output_name(rom_path, title):
    """{name}: last part of the ROM path minus .nds, else the Title."""
    rp = (rom_path or "").strip().replace("\\", "/").rstrip("/")
    base = rp.rsplit("/", 1)[-1] if rp else ""
    if base.lower().startswith("sd:"):
        base = base[3:]
    if base.lower().endswith(".nds"):
        base = base[:-4]
    if not base.strip():
        base = title or ""
    return sanitize_name(base)


def romfs_path_text(rom_path):
    """Contents of romfs/path.txt, same format as YANBF generator.py makeromfs()."""
    p = (rom_path or "").strip()
    if not p:
        return ""
    p = p.replace("\\", "/")
    if p.lower().startswith("sd:"):
        p = p[3:]
    if not p.startswith("/"):
        p = "/" + p
    return "sd:" + p


def write_silent_wav(path, seconds=1.0, rate=44100, channels=2):
    frames = int(rate * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * channels * frames)


# ---------------------------------------------------------------- pycgfx

_pycgfx_module = None
_pycgfx_lock = threading.Lock()


def load_pycgfx(pycgfx_dir=None):
    """Load processes/YANBF/pycgfx/main.py from disk (cached)."""
    global _pycgfx_module
    with _pycgfx_lock:
        if _pycgfx_module is not None:
            return _pycgfx_module
        pycgfx_dir = pycgfx_dir or paths.PYCGFX_DIR
        main_py = os.path.join(pycgfx_dir, "main.py")
        if pycgfx_dir not in sys.path:
            sys.path.insert(0, pycgfx_dir)  # main.py imports cgfx.* as top-level
        spec = importlib.util.spec_from_file_location("yanbf_pycgfx_main", main_py)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _pycgfx_module = module
        return module


def convert_glb(in_path, out_path):
    """Run pycgfx in-process. Returns (ok, printed_text, traceback_or_None)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            m = load_pycgfx()
            gltf = m.gltflib.GLTF.load(in_path, load_file_resources=True)
            cgfx = m.convert_gltf(gltf)
            data = m.write(cgfx)
        with open(out_path, "wb") as f:
            f.write(data)
        return True, buf.getvalue(), None
    except Exception:
        return False, buf.getvalue(), traceback.format_exc()


# ---------------------------------------------------------------- job / pipeline

@dataclass
class BuildJob:
    icon_path: str
    banner_mode: str  # MODE_GLB or MODE_PNG
    banner_path: str
    audio_path: str  # "" = silent placeholder
    rom_path: str
    title: str
    publisher: str
    product_code: str
    unique_id: str
    minor: int = 0
    nds_path: str = ""  # optional; only read for its header, never copied


def validate_job(job):
    """Return a list of human-readable problems (empty if the job is valid)."""
    errors = []
    if job.nds_path:
        e = check_input_file(KIND_NDS, job.nds_path)
        if e:
            errors.append(f"NDS ROM: {e}")
    e = check_input_file(KIND_ICON, job.icon_path)
    if e:
        errors.append(f"Icon: {e}")
    if job.banner_mode == MODE_GLB:
        e = check_input_file(KIND_GLB, job.banner_path)
    elif job.banner_mode == MODE_PNG:
        e = check_input_file(KIND_BANNER_PNG, job.banner_path)
    else:
        e = f"unknown banner mode {job.banner_mode!r}"
    if e:
        errors.append(f"Banner: {e}")
    if job.audio_path:
        e = check_input_file(KIND_AUDIO, job.audio_path)
        if e:
            errors.append(f"Audio: {e}")
    if not (job.title or "").strip():
        errors.append("Title is required")
    if not (job.product_code or "").strip():
        errors.append("Product Code is required")
    _, e = parse_unique_id(job.unique_id)
    if e:
        errors.append(f"Unique ID: {e}")
    _, e = parse_minor(job.minor)
    if e:
        errors.append(e)
    return errors


class StepFailed(Exception):
    pass


class Pipeline:
    """Runs a BuildJob. `log(tag, text)` receives every log line.

    tags: step, cmd, out, info, ok, warn, err, bigwarn, fail, done
    `tools` / `output_root` can be overridden for testing.
    """

    def __init__(self, job, log, tools=None, output_root=None, required_check=True, registry_path=None):
        self.job = job
        self.log = log
        self.tools = tools or {
            "bannertool": paths.BANNERTOOL,
            "cwavtool": paths.CWAVTOOL,
            "makerom": paths.MAKEROM,
        }
        self.output_root = output_root or paths.OUTPUT_DIR
        self.registry_path = registry_path or paths.ID_REGISTRY
        self.required_check = required_check
        self.cia_path = None
        self.out_dir = None

    def _run(self, step, args):
        self.log("cmd", "> " + subprocess.list2cmdline(args))
        try:
            r = subprocess.run(
                args,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as ex:
            self.log("err", f"Could not start {args[0]}: {ex}")
            raise StepFailed(step)
        for line in (r.stdout or "").splitlines():
            self.log("out", line)
        for line in (r.stderr or "").splitlines():
            self.log("err" if r.returncode else "out", line)
        if r.returncode != 0:
            self.log("err", f"{step} exited with code {r.returncode}")
            raise StepFailed(step)
        self.log("ok", f"{step}: OK")

    def _expect(self, step, path):
        if not os.path.isfile(path):
            self.log("err", f"{step} did not produce {path}")
            raise StepFailed(step)

    def run(self):
        """Returns True on success."""
        step = "Checks"
        try:
            self.log("step", "== Checking inputs ==")
            if self.required_check:
                missing = paths.find_missing()
                if missing:
                    for p in missing:
                        self.log("err", f"Missing: {p}")
                    raise StepFailed(step)
            problems = validate_job(self.job)
            if problems:
                for p in problems:
                    self.log("err", p)
                raise StepFailed(step)
            job = self.job
            uid, _ = parse_unique_id(job.unique_id)
            minor, _ = parse_minor(job.minor)
            title = job.title.strip()
            publisher = (job.publisher or "").strip()
            product_code = job.product_code.strip()
            self.log("ok", "Inputs OK")

            name = output_name(job.rom_path, title)
            game_code = ""
            if job.nds_path:
                info = nds.read_nds(job.nds_path)
                game_code = info.game_code
                self.log("info", f"NDS ROM: {job.nds_path} (game code {game_code})")
            id_key = nds.registry_key(game_code, name)
            others = [k for k in nds.owners_of(int(uid, 16), self.registry_path) if k != id_key]
            if others:
                self.log("warn", f"Unique ID {uid} was already used for {', '.join(others)} - "
                                 "installing this CIA will replace that title on the 3DS")

            # -- output folders
            step = "Prepare output"
            out_dir = os.path.join(self.output_root, name)
            self.out_dir = out_dir
            in_dir = os.path.join(out_dir, "input files")
            romfs_dir = os.path.join(in_dir, "romfs")
            prod_dir = os.path.join(out_dir, "produced files")
            self.log("step", f"== Preparing output/{name} ==")
            if os.path.exists(out_dir):
                self.log("info", f"Removing previous build: {out_dir}")
                shutil.rmtree(out_dir)
            os.makedirs(romfs_dir)
            os.makedirs(prod_dir)

            icon_png = os.path.join(in_dir, "icon.png")
            shutil.copyfile(job.icon_path, icon_png)
            ext = ".glb" if job.banner_mode == MODE_GLB else ".png"
            banner_src = os.path.join(in_dir, "banner_source" + ext)
            shutil.copyfile(job.banner_path, banner_src)
            if job.audio_path:
                wav = os.path.join(in_dir, "audio.wav")
                shutil.copyfile(job.audio_path, wav)
            else:
                wav = os.path.join(in_dir, "silent_fallback.wav")
                write_silent_wav(wav)
                self.log("warn", "No audio selected - using a 1-second silent placeholder")

            path_txt = romfs_path_text(job.rom_path)
            with open(os.path.join(romfs_dir, "path.txt"), "w", encoding="utf-8", newline="") as f:
                f.write(path_txt)
            if path_txt:
                self.log("info", f"romfs/path.txt = {path_txt}")
            else:
                self.log("warn", "ROM path is empty - path.txt is empty, so the forwarder won't find the ROM")
            self.log("info", f"Output folder: {out_dir}")

            icon_bin = os.path.join(prod_dir, "icon.bin")
            cgfx_path = os.path.join(prod_dir, "banner.cgfx")
            cwav = os.path.join(prod_dir, "audio.cwav")
            banner_bin = os.path.join(prod_dir, "banner.bin")
            cia = os.path.join(out_dir, name + ".cia")

            # 1. icon
            step = "Icon (bannertool makesmdh)"
            self.log("step", f"== 1. {step} ==")
            self._run(step, [
                self.tools["bannertool"], "makesmdh",
                "-i", icon_png, "-s", title, "-l", title, "-p", publisher,
                "-f", "visible,allow3d,recordusage,extendedbanner",
                "-o", icon_bin,
            ])
            self._expect(step, icon_bin)

            # 2. pycgfx
            if job.banner_mode == MODE_GLB:
                step = "Banner model (pycgfx)"
                self.log("step", f"== 2. {step} ==")
                self.log("cmd", f"> pycgfx (in-process) {banner_src} -> {cgfx_path}")
                ok, printed, tb = convert_glb(banner_src, cgfx_path)
                for line in printed.splitlines():
                    if "CGFX is too big" in line:
                        self.log("bigwarn", line)
                    elif "WARNING" in line:
                        self.log("warn", line)
                    else:
                        self.log("out", line)
                if not ok:
                    self.log("err", tb.rstrip())
                    raise StepFailed(step)
                self._expect(step, cgfx_path)
                self.log("ok", f"{step}: OK ({os.path.getsize(cgfx_path)} bytes)")
            else:
                self.log("step", "== 2. Banner model (pycgfx) ==")
                self.log("info", "Skipped - flat image banner")

            # 3. audio
            step = "Audio (cwavtool)"
            self.log("step", f"== 3. {step} ==")
            self._run(step, [self.tools["cwavtool"], "-i", wav, "-o", cwav])
            self._expect(step, cwav)

            # 4. banner
            step = "Banner (bannertool makebanner)"
            self.log("step", f"== 4. {step} ==")
            if job.banner_mode == MODE_GLB:
                args = [self.tools["bannertool"], "makebanner", "-ci", cgfx_path, "-ca", cwav, "-o", banner_bin]
            else:
                args = [self.tools["bannertool"], "makebanner", "-i", banner_src, "-ca", cwav, "-o", banner_bin]
            self._run(step, args)
            self._expect(step, banner_bin)

            # 5. CIA
            step = "CIA (makerom)"
            self.log("step", f"== 5. {step} ==")
            self._run(step, [
                self.tools["makerom"], "-f", "cia", "-target", "t", "-exefslogo",
                "-rsf", paths.RSF,
                "-elf", paths.FORWARDER_ELF,
                "-banner", banner_bin, "-icon", icon_bin,
                f"-DAPP_ROMFS={romfs_dir}",
                "-major", "1", "-minor", str(minor), "-micro", "0",
                "-DAPP_VERSION_MAJOR=1",
                "-o", cia,
                f"-DAPP_PRODUCT_CODE={product_code}",
                f"-DAPP_TITLE={title}",
                f"-DAPP_UNIQUE_ID={uid}",
            ])
            self._expect(step, cia)
            self.cia_path = cia
            try:
                nds.record_unique_id(id_key, int(uid, 16), self.registry_path)
            except OSError as ex:
                self.log("warn", f"Could not update {self.registry_path}: {ex}")
            self.log("done", f" DONE: {cia} ({os.path.getsize(cia) // 1024} KB) ")
            return True
        except StepFailed as ex:
            self.log("fail", f" FAILED at step: {ex} ")
            return False
        except Exception:
            self.log("err", traceback.format_exc().rstrip())
            self.log("fail", f" FAILED at step: {step} ")
            return False
