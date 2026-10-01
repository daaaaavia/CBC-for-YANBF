"""Change the icon, titles, banner or banner sound of an existing CIA. The editor page
in the main window is cia_edit_page.py.

Only unencrypted CIAs can be edited - forwarders (from this program or others) and
most homebrew. Encrypted ones (eShop / retail) are refused.

A CIA is: header | certificates | ticket | TMD | contents | meta (a copy of the icon).
Content 0 is an NCCH: header | exheader | [logo] | ExeFS (icon, banner, .code, …) | RomFS.
The new icon/banner go into the ExeFS; then everything that depends on it is fixed:
the ExeFS hashes, the NCCH layout and header hashes, content 0's size and SHA-256 in
the TMD (and the TMD's own hash chain), the CIA header sizes and the icon copy in
meta. The Title ID, product code, program and RomFS don't change, and the title
version (in the TMD and the ticket) goes up by one, so the edited CIA installs over
the original as an update - with the same version, FBI won't replace the installed
title and it has to be deleted first. Signatures aren't redone: a home-built CIA's
chain is already broken, and custom firmware (needed for forwarders) ignores it.
"""

import hashlib
import io
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field

from PIL import Image

import paths
import pipeline as pl
import platform_util as pu

MEDIA = 0x200
SMDH_SIZE = 0x36C0
LANGS = 16  # SMDH title slots (Japanese, English, French, …)
TITLE_LIMITS = {"short": 0x40, "long": 0x80, "publisher": 0x40}  # UTF-16 characters

_sha = lambda b: hashlib.sha256(b).digest()
_al = lambda n, a: (n + a - 1) // a * a


class EditError(Exception):
    pass


# ---------------------------------------------------------------------- CIA
def _sig_size(sig_type):
    try:
        return {0x10000: 0x240, 0x10001: 0x140, 0x10002: 0x80,
                0x10003: 0x240, 0x10004: 0x140, 0x10005: 0x80}[sig_type]
    except KeyError:
        raise EditError("This file's TMD has an unknown signature type - is it a CIA?")


def _parse_cia(data):
    if len(data) < 0x2020:
        raise EditError("This file is too small to be a CIA")
    hsize, typ, ver, cert, tik, tmd, meta, content = struct.unpack_from("<IHHIIIIQ", data, 0)
    if hsize != 0x2020 or content == 0 or len(data) < hsize + cert + tik + tmd + content:
        raise EditError("This file isn't a CIA (or it's damaged)")
    off = _al(hsize, 64)
    secs = {}
    for name, size in (("certs", cert), ("ticket", tik), ("tmd", tmd), ("content", content), ("meta", meta)):
        secs[name] = data[off:off + size]
        off = _al(off + size, 64)
    return data[:hsize], secs


def _build_cia(header, secs):
    h = bytearray(header)
    struct.pack_into("<IIII", h, 8, len(secs["certs"]), len(secs["ticket"]), len(secs["tmd"]), len(secs["meta"]))
    struct.pack_into("<Q", h, 0x18, len(secs["content"]))
    out = bytearray(h)
    for name in ("certs", "ticket", "tmd", "content", "meta"):
        out += b"\0" * (_al(len(out), 64) - len(out))
        out += secs[name]
    return bytes(out)


def _tmd_layout(tmd):
    """(header offset, number of contents, content-info offset, chunk-records offset)"""
    h = _sig_size(struct.unpack_from(">I", tmd, 0)[0])
    count = struct.unpack_from(">H", tmd, h + 0x9E)[0]
    infos = h + 0xC4
    return h, count, infos, infos + 64 * 0x24


def _content0(secs):
    """(chunk record offset in the TMD, content 0 bytes, the contents after it)"""
    tmd = secs["tmd"]
    h, count, infos, chunks = _tmd_layout(tmd)
    pos = 0
    for i in range(count):
        rec = chunks + i * 0x30
        cid, index, ctype, size = struct.unpack_from(">IHHQ", tmd, rec)
        if index == 0:
            if ctype & 1:
                raise EditError("This CIA is encrypted (eShop / retail), so it can't be edited. Only "
                                "unencrypted CIAs - forwarders and most homebrew - can.")
            return rec, secs["content"][pos:pos + size], secs["content"][pos + size:]
        pos += size
    raise EditError("This CIA has no main content")


def _update_tmd(tmd, rec, content0):
    t = bytearray(tmd)
    h, count, infos, chunks = _tmd_layout(t)
    struct.pack_into(">Q", t, rec + 8, len(content0))
    t[rec + 0x10:rec + 0x30] = _sha(content0)
    # content info records hash the chunk records; the header hashes the info records
    for i in range(64):
        start, n = struct.unpack_from(">HH", t, infos + i * 0x24)
        if n == 0:
            break
        t[infos + i * 0x24 + 4:infos + i * 0x24 + 0x24] = _sha(bytes(t[chunks + start * 0x30:chunks + (start + n) * 0x30]))
    t[h + 0xA4:h + 0xC4] = _sha(bytes(t[infos:infos + 64 * 0x24]))
    return bytes(t)


# title version: major (6 bits) . minor (6) . micro (4), in the TMD header and the ticket
def _tmd_version_at(tmd):
    return _tmd_layout(tmd)[0] + 0x9C


def _ticket_version_at(ticket):
    return _sig_size(struct.unpack_from(">I", ticket, 0)[0]) + 0xA6


def title_version(secs):
    return struct.unpack_from(">H", secs["tmd"], _tmd_version_at(secs["tmd"]))[0]


def version_text(v):
    return f"v{v >> 10}.{(v >> 4) & 0x3F}.{v & 0xF} ({v})"


def _bump_version(secs):
    """One more than the installed title's version, in the TMD and the ticket."""
    v = title_version(secs)
    if v >= 0xFFFF:
        raise EditError("This CIA's version is already the highest possible, so it can't go up again")
    for name, at in (("tmd", _tmd_version_at), ("ticket", _ticket_version_at)):
        b = bytearray(secs[name])
        struct.pack_into(">H", b, at(b), v + 1)
        secs[name] = bytes(b)


# ---------------------------------------------------------------------- NCCH / ExeFS
def _ncch_fields(n):
    if n[0x100:0x104] != b"NCCH":
        raise EditError("This CIA's main content isn't a program (NCCH)")
    if not n[0x18F] & 0x4:
        raise EditError("This CIA is encrypted (eShop / retail), so it can't be edited. Only "
                        "unencrypted CIAs - forwarders and most homebrew - can.")
    exefs_off, exefs_size, exefs_hash = (x * MEDIA for x in struct.unpack_from("<III", n, 0x1A0))
    romfs_off, romfs_size = (x * MEDIA for x in struct.unpack_from("<II", n, 0x1B0))
    if not exefs_size:
        raise EditError("This CIA has no ExeFS (no icon or banner to change)")
    return exefs_off, exefs_size, exefs_hash, romfs_off, romfs_size


def _exefs_files(exefs):
    files = []
    for i in range(10):
        name, off, size = struct.unpack_from("<8sII", exefs, i * 16)
        if size or name.strip(b"\0"):
            files.append((name.rstrip(b"\0").decode("ascii", "replace"), bytes(exefs[0x200 + off:0x200 + off + size])))
    return files


def _build_exefs(files):
    hdr = bytearray(0x200)
    body = bytearray()
    for i, (name, blob) in enumerate(files):
        struct.pack_into("<8sII", hdr, i * 16, name.encode(), len(body), len(blob))
        hdr[0x200 - 32 * (i + 1):0x200 - 32 * i] = _sha(blob)  # stored in reverse order
        body += blob
        body += b"\0" * (_al(len(body), MEDIA) - len(body))
    return bytes(hdr + body)


def _replace_in_ncch(ncch, new_files):
    n = bytearray(ncch)
    exefs_off, exefs_size, exefs_hash, romfs_off, romfs_size = _ncch_fields(n)
    files = _exefs_files(n[exefs_off:exefs_off + exefs_size])
    names = {name for name, _ in files}
    if set(new_files) - names:
        raise EditError(f"This CIA has no {', '.join(sorted(set(new_files) - names))} to replace")
    new_exefs = _build_exefs([(name, new_files.get(name, blob)) for name, blob in files])
    gap = romfs_off - (exefs_off + exefs_size) if romfs_size else 0  # keeps RomFS's alignment
    out = bytearray(bytes(n[:exefs_off]) + new_exefs + b"\0" * gap)
    new_romfs_off = len(out)
    if romfs_size:
        out += n[romfs_off:romfs_off + romfs_size]
        struct.pack_into("<I", out, 0x1B0, new_romfs_off // MEDIA)
    struct.pack_into("<I", out, 0x104, len(out) // MEDIA)
    struct.pack_into("<I", out, 0x1A4, len(new_exefs) // MEDIA)
    out[0x1C0:0x1E0] = _sha(new_exefs[:exefs_hash or MEDIA])
    return bytes(out)


# ---------------------------------------------------------------------- SMDH (icon + titles)
def smdh_titles(smdh):
    """English (short title, long title, publisher) of an icon.bin."""
    base = 0x8 + 1 * 0x200  # slot 1 = English
    get = lambda o, n: smdh[base + o:base + o + n * 2].decode("utf-16-le", "replace").split("\0")[0]
    return get(0, 0x40), get(0x80, 0x80), get(0x180, 0x40)


def smdh_with(smdh, titles=None, icon_from=None):
    """A copy of smdh with new titles (in every language slot) and/or the icon graphics
    of icon_from - keeping its other settings (ratings, region, flags)."""
    s = bytearray(smdh)
    if titles is not None:
        short, long_, pub = titles
        for lang in range(LANGS):
            base = 0x8 + lang * 0x200
            for off, n, text in ((0, 0x40, short), (0x80, 0x80, long_), (0x180, 0x40, pub)):
                enc = text[:n - 1].encode("utf-16-le")
                s[base + off:base + off + n * 2] = enc + b"\0" * (n * 2 - len(enc))
    if icon_from is not None:
        s[0x2040:SMDH_SIZE] = icon_from[0x2040:SMDH_SIZE]
    return bytes(s)


def _morton(i):
    x = (i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4)
    y = ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4)
    return x, y


def smdh_icon(smdh):
    """The 48x48 icon of an icon.bin as a PIL image (RGB565, 8x8 tiles, Morton order)."""
    img = Image.new("RGB", (48, 48))
    px = img.load()
    data = smdh[0x24C0:0x24C0 + 48 * 48 * 2]
    i = 0
    for ty in range(6):
        for tx in range(6):
            for k in range(64):
                v = data[i] | data[i + 1] << 8
                i += 2
                x, y = _morton(k)
                px[tx * 8 + x, ty * 8 + y] = ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)
    return img


# ---------------------------------------------------------------------- banner (CBMD) + sound (CWAV)
def banner_cwav(banner):
    """The CWAV sound inside a banner.bin, or None."""
    if banner[:4] != b"CBMD":
        raise EditError("The banner isn't a standard 3DS banner (CBMD)")
    off = struct.unpack_from("<I", banner, 0x84)[0]
    if not off or banner[off:off + 4] != b"CWAV":
        return None
    size = struct.unpack_from("<I", banner, off + 0xC)[0]
    return banner[off:off + size]


def banner_with_cwav(banner, cwav):
    """The same banner with a different sound."""
    off = struct.unpack_from("<I", banner, 0x84)[0]
    if not off:
        off = _al(len(banner), 0x20)
    out = bytearray(banner[:off]) + b"\0" * (off - len(banner[:off]))
    struct.pack_into("<I", out, 0x84, off)
    return bytes(out + cwav)


def cwav_seconds(cwav):
    """Length of a CWAV in seconds, or None."""
    try:
        count = struct.unpack_from("<H", cwav, 0x10)[0]
        for i in range(count):
            btype, _, boff = struct.unpack_from("<HHI", cwav, 0x14 + i * 12)
            if btype == 0x7000 and cwav[boff:boff + 4] == b"INFO":
                rate, _, end = struct.unpack_from("<III", cwav, boff + 0xC)
                return end / rate if rate else None
    except struct.error:
        pass
    return None


# ---------------------------------------------------------------------- old banner + sound, for previews
def lz11(data):
    """Decompress LZ11 (how CBMD stores its CGFX)."""
    if not data or data[0] != 0x11:
        raise EditError("The banner's model isn't LZ11-compressed")
    size = data[1] | data[2] << 8 | data[3] << 16
    pos = 4
    if size == 0:
        size = struct.unpack_from("<I", data, 4)[0]
        pos = 8
    out = bytearray()
    try:
        while len(out) < size:
            flags = data[pos]
            pos += 1
            for bit in range(8):
                if len(out) >= size:
                    break
                if not flags & (0x80 >> bit):
                    out.append(data[pos])
                    pos += 1
                    continue
                b = data[pos]
                ind = b >> 4
                if ind == 0:
                    count = ((b & 0xF) << 4 | data[pos + 1] >> 4) + 0x11
                    disp = ((data[pos + 1] & 0xF) << 8 | data[pos + 2]) + 1
                    pos += 3
                elif ind == 1:
                    count = ((b & 0xF) << 12 | data[pos + 1] << 4 | data[pos + 2] >> 4) + 0x111
                    disp = ((data[pos + 2] & 0xF) << 8 | data[pos + 3]) + 1
                    pos += 4
                else:
                    count = ind + 1
                    disp = ((b & 0xF) << 8 | data[pos + 1]) + 1
                    pos += 2
                for _ in range(count):
                    out.append(out[-disp])
    except IndexError:
        raise EditError("The banner's model is damaged")
    return bytes(out)


def banner_cgfx(banner):
    """The banner's CGFX model (the common one), decompressed."""
    off = struct.unpack_from("<I", banner, 0x8)[0]
    return lz11(banner[off:])


_ETC1_MODS = ((2, 8), (5, 17), (9, 29), (13, 42), (18, 60), (24, 80), (33, 106), (47, 183))


def _etc1_block(block, alpha=None):
    """One 4x4 ETC1 block (u64) -> 16 RGBA pixels, [y][x]."""
    hi, lo = block >> 32, block & 0xFFFFFFFF
    diff, flip = hi >> 1 & 1, hi & 1
    tables = (hi >> 5 & 7, hi >> 2 & 7)
    if diff:
        def c5(v, d):
            v = v + (d - 8 if d & 4 else d)  # 3-bit signed delta
            return (v << 3) | (v >> 2)
        r1, g1, b1 = hi >> 27 & 31, hi >> 19 & 31, hi >> 11 & 31
        base = (((r1 << 3) | (r1 >> 2), (g1 << 3) | (g1 >> 2), (b1 << 3) | (b1 >> 2)),
                (c5(r1, hi >> 24 & 7), c5(g1, hi >> 16 & 7), c5(b1, hi >> 8 & 7)))
    else:
        base = ((hi >> 28 & 15, hi >> 20 & 15, hi >> 12 & 15), (hi >> 24 & 15, hi >> 16 & 15, hi >> 8 & 15))
        base = tuple(tuple((c << 4) | c for c in b) for b in base)
    px = [[None] * 4 for _ in range(4)]
    for x in range(4):
        for y in range(4):
            i = x * 4 + y
            sub = (y >= 2) if flip else (x >= 2)
            msb, lsb = lo >> (i + 16) & 1, lo >> i & 1
            mod = _ETC1_MODS[tables[sub]][lsb]
            if msb:
                mod = -mod
            a = 255 if alpha is None else ((alpha >> (i * 4)) & 15) * 17
            px[y][x] = tuple(max(0, min(255, c + mod)) for c in base[sub]) + (a,)
    return px


def decode_texture(data, w, h, fmt):
    """A PICA200 texture (8x8 tiles, Morton order inside) as a PIL image."""
    img = Image.new("RGBA", (w, h))
    put = img.load()
    if fmt in (12, 13):  # ETC1 / ETC1A4: 4x4 blocks, 4 per 8x8 tile
        step = 16 if fmt == 13 else 8
        pos = 0
        for ty in range(0, h, 8):
            for tx in range(0, w, 8):
                for by, bx in ((0, 0), (0, 4), (4, 0), (4, 4)):
                    alpha = None
                    if fmt == 13:
                        alpha = struct.unpack_from("<Q", data, pos)[0]
                    block = struct.unpack_from("<Q", data, pos + step - 8)[0]
                    pos += step
                    for y, row in enumerate(_etc1_block(block, alpha)):
                        for x, p in enumerate(row):
                            put[tx + bx + x, ty + by + y] = p
        return img
    bpp = {0: 32, 1: 24, 2: 16, 3: 16, 4: 16, 5: 16, 6: 16, 7: 8, 8: 8, 9: 8, 10: 4, 11: 4}.get(fmt)
    if bpp is None:
        raise EditError(f"Unknown texture format {fmt}")

    def pixel(n):
        if bpp == 4:
            v = data[n // 2] >> (4 * (n & 1)) & 15
            v = v * 17
            return (v, v, v, 255) if fmt == 10 else (255, 255, 255, v)
        o = n * bpp // 8
        if fmt == 0:
            a, b, g, r = data[o:o + 4]
            return r, g, b, a
        if fmt == 1:
            b, g, r = data[o:o + 3]
            return r, g, b, 255
        if bpp == 16:
            v = data[o] | data[o + 1] << 8
            if fmt == 2:
                return (v >> 11 & 31) * 255 // 31, (v >> 6 & 31) * 255 // 31, (v >> 1 & 31) * 255 // 31, 255 * (v & 1)
            if fmt == 3:
                return (v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31, 255
            if fmt == 4:
                return (v >> 12) * 17, (v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17
            if fmt == 5:
                return data[o + 1], data[o + 1], data[o + 1], data[o]
            return data[o + 1], data[o], 0, 255  # HILO8
        v = data[o]
        if fmt == 7:
            return v, v, v, 255
        if fmt == 8:
            return 255, 255, 255, v
        return (v >> 4) * 17, (v >> 4) * 17, (v >> 4) * 17, (v & 15) * 17  # LA4

    n = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for k in range(64):
                x, y = _morton(k)
                put[tx + x, ty + y] = pixel(n)
                n += 1
    return img


def banner_texture(banner):
    """The first image texture in the banner's model - the whole picture of a flat
    banner (the model is just a textured rectangle), or None."""
    cgfx = banner_cgfx(banner)
    i = cgfx.find(b"TXOB")
    while i >= 4:
        t = i - 4
        if struct.unpack_from("<I", cgfx, t)[0] == 0x20000011:  # an image texture
            h, w = struct.unpack_from("<II", cgfx, t + 0x18)
            fmt = struct.unpack_from("<I", cgfx, t + 0x34)[0]
            img = t + 0x38 + struct.unpack_from("<I", cgfx, t + 0x38)[0]
            size = struct.unpack_from("<I", cgfx, img + 8)[0]
            data = img + 0xC + struct.unpack_from("<I", cgfx, img + 0xC)[0]
            return decode_texture(cgfx[data:data + size], w, h, fmt)
        i = cgfx.find(b"TXOB", i + 4)
    return None


def banner_source(cia_path):
    """The banner file a CIA was built from, if this program built it: ('glb' | 'png', path)."""
    folder = os.path.join(os.path.dirname(os.path.abspath(cia_path)), "input files")
    for ext, mode in ((".glb", pl.MODE_GLB), (".png", pl.MODE_PNG)):
        p = os.path.join(folder, "banner_source" + ext)
        if os.path.isfile(p):
            return mode, p
    return None


_IMA_STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
              97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
              724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
              4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
              18500, 20350, 22385, 24623, 27086, 29794, 32767]
_IMA_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8]


def cwav_to_wav(cwav):
    """Decode a CWAV (PCM8, PCM16, DSP-ADPCM or IMA-ADPCM) to WAV file bytes (16-bit)."""
    count = struct.unpack_from("<H", cwav, 0x10)[0]
    blocks = {}
    for i in range(count):
        btype, _, boff = struct.unpack_from("<HHI", cwav, 0x14 + i * 12)
        blocks[btype] = boff
    info, data = blocks.get(0x7000), blocks.get(0x7001)
    if info is None or data is None or cwav[info:info + 4] != b"INFO":
        raise EditError("The sound isn't a readable CWAV")
    enc = cwav[info + 8]
    rate, _, frames = struct.unpack_from("<III", cwav, info + 0xC)
    table = info + 0x1C
    nch = struct.unpack_from("<I", cwav, table)[0]
    body = data + 8
    channels = []
    for c in range(nch):
        ci = table + struct.unpack_from("<I", cwav, table + 4 + c * 8 + 4)[0]
        samples = body + struct.unpack_from("<I", cwav, ci + 4)[0]
        adpcm = ci + struct.unpack_from("<I", cwav, ci + 12)[0]  # relative to the channel info
        out = []
        if enc == 0:
            out = [struct.unpack_from("<b", cwav, samples + i)[0] << 8 for i in range(frames)]
        elif enc == 1:
            out = list(struct.unpack_from(f"<{frames}h", cwav, samples))
        elif enc == 2:  # DSP-ADPCM: 8-byte frames of 14 samples
            coefs = struct.unpack_from("<16h", cwav, adpcm)
            h1, h2 = struct.unpack_from("<hh", cwav, adpcm + 0x22)
            pos = samples
            while len(out) < frames:
                ps = cwav[pos]
                c1, c2 = coefs[(ps >> 4) * 2], coefs[(ps >> 4) * 2 + 1]
                scale = 1 << (ps & 15)
                for k in range(14):
                    if len(out) >= frames:
                        break
                    nib = cwav[pos + 1 + k // 2] >> (0 if k & 1 else 4) & 15
                    nib = nib - 16 if nib >= 8 else nib
                    s = ((nib * scale) << 11) + 1024 + c1 * h1 + c2 * h2
                    s = max(-32768, min(32767, s >> 11))
                    h2, h1 = h1, s
                    out.append(s)
                pos += 8
        elif enc == 3:  # IMA-ADPCM: low nibble first
            pred, index = struct.unpack_from("<hB", cwav, adpcm)
            for i in range(frames):
                nib = cwav[samples + i // 2] >> (4 * (i & 1)) & 15
                step = _IMA_STEPS[index]
                diff = step >> 3
                if nib & 1:
                    diff += step >> 2
                if nib & 2:
                    diff += step >> 1
                if nib & 4:
                    diff += step
                pred = max(-32768, min(32767, pred - diff if nib & 8 else pred + diff))
                index = max(0, min(88, index + _IMA_INDEX[nib & 7]))
                out.append(pred)
        else:
            raise EditError(f"Unknown sound encoding {enc}")
        channels.append(out)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack(f"<{nch}h", *s) for s in zip(*channels)))
    return buf.getvalue()


# ---------------------------------------------------------------------- reading
@dataclass
class CiaInfo:
    path: str
    title_id: str
    product_code: str
    icon: bytes  # icon.bin (SMDH)
    banner: bytes  # banner.bin (CBMD)
    titles: tuple = ("", "", "")
    sound_seconds: float = None
    has_sound: bool = False
    version: int = 0  # title version (see version_text)
    extra: dict = field(default_factory=dict)


def read_cia(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as ex:
        raise EditError(f"Couldn't read the file: {ex}")
    header, secs = _parse_cia(data)
    rec, c0, _ = _content0(secs)
    exefs_off, exefs_size, *_ = _ncch_fields(c0)
    files = dict(_exefs_files(c0[exefs_off:exefs_off + exefs_size]))
    if "icon" not in files or "banner" not in files:
        raise EditError("This CIA has no icon or banner to change")
    icon, banner = files["icon"], files["banner"]
    cwav = banner_cwav(banner)
    return CiaInfo(path=path, title_id=f"{struct.unpack_from('<Q', c0, 0x118)[0]:016x}",
                   product_code=c0[0x150:0x160].split(b"\0")[0].decode("ascii", "replace"),
                   icon=icon, banner=banner, titles=smdh_titles(icon),
                   sound_seconds=cwav_seconds(cwav) if cwav else None, has_sound=cwav is not None,
                   version=title_version(secs))


def edit_cia(data, banner=None, icon=None):
    """The CIA bytes with a new banner.bin and/or icon.bin, one version up."""
    header, secs = _parse_cia(data)
    rec, c0, rest = _content0(secs)
    _bump_version(secs)
    new = {k: v for k, v in (("banner", banner), ("icon", icon)) if v is not None}
    c0 = _replace_in_ncch(c0, new)
    secs["content"] = c0 + rest
    secs["tmd"] = _update_tmd(secs["tmd"], rec, c0)
    if icon is not None and len(secs["meta"]) >= 0x400 + SMDH_SIZE:
        m = bytearray(secs["meta"])
        m[0x400:0x400 + SMDH_SIZE] = icon[:SMDH_SIZE]
        secs["meta"] = bytes(m)
    return _build_cia(header, secs)


def check_cia(data):
    """Re-read an edited CIA and check every hash this module is responsible for.
    Returns a list of problems (empty = fine)."""
    problems = []
    header, secs = _parse_cia(data)
    rec, c0, _ = _content0(secs)
    tmd = secs["tmd"]
    size = struct.unpack_from(">Q", tmd, rec + 8)[0]
    if size != len(c0) or tmd[rec + 0x10:rec + 0x30] != _sha(c0):
        problems.append("content hash in the TMD")
    h, count, infos, chunks = _tmd_layout(tmd)
    if tmd[h + 0xA4:h + 0xC4] != _sha(tmd[infos:infos + 64 * 0x24]):
        problems.append("TMD content info hash")
    if struct.unpack_from(">H", secs["ticket"], _ticket_version_at(secs["ticket"]))[0] != title_version(secs):
        problems.append("ticket and TMD versions differ")
    exefs_off, exefs_size, exefs_hash, *_ = _ncch_fields(c0)
    exefs = c0[exefs_off:exefs_off + exefs_size]
    if c0[0x1C0:0x1E0] != _sha(exefs[:exefs_hash or MEDIA]):
        problems.append("ExeFS superblock hash")
    for i, (name, blob) in enumerate(_exefs_files(exefs)):
        if exefs[0x200 - 32 * (i + 1):0x200 - 32 * i] != _sha(blob):
            problems.append(f"ExeFS hash of {name}")
    return problems


# ---------------------------------------------------------------------- the edit job
@dataclass
class EditJob:
    cia_path: str
    icon_png: str = ""  # new icon image, or "" to keep it
    titles: tuple = None  # (short, long, publisher), or None to keep them
    banner_mode: str = ""  # pl.MODE_GLB / pl.MODE_PNG, or "" to keep the banner
    banner_path: str = ""
    wav_path: str = ""  # new sound, or "" to keep it


def output_path(cia_path):
    stem = os.path.splitext(os.path.basename(cia_path))[0]
    name = pl.sanitize_name(f"{stem} (edited)")
    return os.path.join(paths.OUTPUT_DIR, name, name + ".cia")


def validate(job):
    problems = []
    if not job.icon_png and job.titles is None and not job.banner_mode and not job.wav_path:
        problems.append("Choose at least one thing to change")
    if job.icon_png:
        err = pl.check_input_file(pl.KIND_ICON, job.icon_png)
        if err:
            problems.append(err)
    if job.titles is not None:
        if not job.titles[0].strip():
            problems.append("The title can't be empty")
        for text, (key, n) in zip(job.titles, TITLE_LIMITS.items()):
            if len(text) >= n:
                problems.append(f"The {key} title is too long ({len(text)} characters, the limit is {n - 1})")
    if job.banner_mode:
        err = pl.check_input_file(pl.KIND_GLB if job.banner_mode == pl.MODE_GLB else pl.KIND_BANNER_PNG, job.banner_path)
        if err:
            problems.append(err)
    if job.wav_path:
        err = pl.check_input_file(pl.KIND_AUDIO, job.wav_path)
        if err:
            problems.append(err)
    return problems


def _run(log, args):
    log("cmd", "> " + subprocess.list2cmdline(args))
    r = subprocess.run(args, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL,
                       **pu.popen_flags())
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            log("out" if r.returncode == 0 else "err", line)
    if r.returncode:
        raise EditError(f"{os.path.basename(args[0])} failed (exit code {r.returncode})")


def run(job, log):
    """Make the edited CIA. Returns its path. log(kind, text) like the build log."""
    problems = validate(job)
    if problems:
        raise EditError("; ".join(problems))
    info = read_cia(job.cia_path)
    log("info", f"Editing {job.cia_path} (Title ID {info.title_id}, {info.product_code}, "
                f"{version_text(info.version)})")
    with open(job.cia_path, "rb") as f:
        data = f.read()
    new_icon = new_banner = None
    with tempfile.TemporaryDirectory(prefix="cbc-edit-") as tmp:
        # icon: a new picture and/or titles, keeping the icon's other settings
        if job.icon_png or job.titles is not None:
            titles = job.titles if job.titles is not None else info.titles
            icon_from = None
            if job.icon_png:
                made = os.path.join(tmp, "icon.bin")
                _run(log, [paths.BANNERTOOL, "makesmdh", "-i", job.icon_png, "-s", titles[0], "-l", titles[1],
                           "-p", titles[2], "-o", made])
                with open(made, "rb") as f:
                    icon_from = f.read()
            new_icon = smdh_with(info.icon, titles=titles if job.titles is not None else None, icon_from=icon_from)
            log("ok", "New icon" + (" and titles" if job.titles is not None else "") if job.icon_png else "New titles")
        # sound: a new one, or the CIA's own
        cwav = None
        if job.wav_path:
            cwav_path = os.path.join(tmp, "audio.cwav")
            _run(log, [paths.CWAVTOOL, "-i", job.wav_path, "-o", cwav_path])
            with open(cwav_path, "rb") as f:
                cwav = f.read()
        # banner: a new one (with the new or the old sound), or the old one with a new sound
        if job.banner_mode:
            keep = cwav if cwav is not None else banner_cwav(info.banner)
            if keep is None:  # no sound in the old banner: 1 s of silence, like a new build
                wav = os.path.join(tmp, "silent.wav")
                pl.write_silent_wav(wav)
                cwav_path = os.path.join(tmp, "audio.cwav")
                _run(log, [paths.CWAVTOOL, "-i", wav, "-o", cwav_path])
                with open(cwav_path, "rb") as f:
                    keep = f.read()
            ca = os.path.join(tmp, "keep.cwav")
            with open(ca, "wb") as f:
                f.write(keep)
            out = os.path.join(tmp, "banner.bin")
            if job.banner_mode == pl.MODE_GLB:
                cgfx = os.path.join(tmp, "banner.cgfx")
                log("cmd", f"> pycgfx (in-process) {job.banner_path} -> {cgfx}")
                ok, printed, tb = pl.convert_glb(job.banner_path, cgfx)
                for line in printed.splitlines():
                    log("bigwarn" if "CGFX is too big" in line else "warn" if "WARNING" in line else "out", line)
                if not ok:
                    log("err", tb.rstrip())
                    raise EditError("Converting the .glb failed")
                _run(log, [paths.BANNERTOOL, "makebanner", "-ci", cgfx, "-ca", ca, "-o", out])
            else:
                _run(log, [paths.BANNERTOOL, "makebanner", "-i", job.banner_path, "-ca", ca, "-o", out])
            with open(out, "rb") as f:
                new_banner = f.read()
            log("ok", "New banner" + (" and sound" if cwav is not None else " (keeping the CIA's sound)"))
        elif cwav is not None:
            new_banner = banner_with_cwav(info.banner, cwav)
            log("ok", "New sound (keeping the CIA's banner)")
    edited = edit_cia(data, banner=new_banner, icon=new_icon)
    problems = check_cia(edited)
    if problems:
        raise EditError("The edited CIA didn't check out: " + ", ".join(problems))
    dest = output_path(job.cia_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(edited)
    # like a normal build, keep the banner's source file beside it (the editor's
    # "Now" preview uses it when this CIA is opened again)
    src = (job.banner_mode, job.banner_path) if job.banner_mode else banner_source(job.cia_path)
    folder = os.path.join(os.path.dirname(dest), "input files")
    for old in ("banner_source.glb", "banner_source.png"):
        if os.path.isfile(os.path.join(folder, old)):
            os.remove(os.path.join(folder, old))
    if src:
        os.makedirs(folder, exist_ok=True)
        shutil.copyfile(src[1], os.path.join(folder, "banner_source" + (".glb" if src[0] == pl.MODE_GLB else ".png")))
    log("ok", f"Checked and saved: {dest} ({len(edited):,} bytes). Same Title ID, version "
              f"{version_text(info.version + 1)}, so it installs over the original as an update.")
    return dest
