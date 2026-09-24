"""Test inputs, generated from code so the repository holds no test binaries.

build(folder) writes everything the suites use:

  icon48.png, banner256.png, photo.jpg, big_banner.png   images
  lim/                  size-limit cases (icons, banners, .glb sizes, junk)
  test.glb              a single red quad named nameModel (fast pycgfx conversion)
  banner_sibling.glb    COMMON -> world -> worldModel box + name -> nameModel logo
  banner_child.glb      the same with the logo under worldModel
  case.glb              a textured game case like a real banner model: ~490
                        triangles, double-sided textured covers, worldModel spin,
                        no billboard (stands in for the user's own model)
  bad.glb               'glTF' plus garbage
  wav/                  16/24/8-bit clips, the reference-length clip and junk
  roms/                 synthetic .nds headers (3, 2, 1 title lines, no banner, junk)
  fake/                 stand-in bannertool / cwavtool / makerom (FAKE_FAIL=<tool>
                        makes one fail), as .cmd on Windows or sh scripts elsewhere
"""

import io
import math
import os
import stat
import struct
import sys
import wave

from gltflib import (GLTF, Accessor, AccessorType, Asset, Attributes, Buffer, BufferTarget, BufferView,
                     ComponentType, GLBResource, GLTFModel, Image as GImage, Material, Mesh, Node,
                     PBRMetallicRoughness, Primitive, Sampler, Scene, Texture, TextureInfo)
from PIL import Image, ImageDraw

# The audio limit is the exact length of the reference clip the user chose:
# 141,000 frames at 48 kHz = 2.9375 s. ref.wav has exactly that length.
REF_FRAMES, REF_RATE = 141000, 48000


# ---------------------------------------------------------------- images
def _images(d):
    Image.new("RGBA", (48, 48), "red").save(os.path.join(d, "icon48.png"))
    Image.new("RGBA", (256, 128), "blue").save(os.path.join(d, "banner256.png"))
    Image.new("RGB", (40, 40), "blue").save(os.path.join(d, "photo.jpg"), format="JPEG")
    Image.new("RGB", (1024, 512), "green").save(os.path.join(d, "big_banner.png"))
    lim = os.path.join(d, "lim")
    os.makedirs(lim, exist_ok=True)
    for name, size in (("i48.png", (48, 48)), ("i49.png", (49, 48)), ("i48x49.png", (48, 49)),
                       ("i47.png", (47, 48)), ("i48x47.png", (48, 47)), ("i32.png", (32, 32)),
                       ("i24.png", (24, 24)), ("b256.png", (256, 128)), ("b257.png", (257, 128)),
                       ("b129.png", (256, 129))):
        Image.new("RGBA", size).save(os.path.join(lim, name))
    Image.new("RGB", (10, 10)).save(os.path.join(lim, "jpeg.png"), format="JPEG")
    _write(os.path.join(lim, "junk.png"), b"not an image")
    _write(os.path.join(lim, "m_ok.glb"), b"\0" * 0x80000)  # exactly 512 KB: allowed
    _write(os.path.join(lim, "m_big.glb"), b"\0" * (0x80000 + 1))  # one byte over
    _write(os.path.join(lim, "m_old.glb"), b"\0" * (500 * 1024))  # the old 500 KB rule


# ---------------------------------------------------------------- glTF helpers
class _Glb:
    """Collects quads / meshes into one binary buffer."""

    def __init__(self):
        self.data = bytearray()
        self.views, self.accs, self.mats = [], [], []

    def _view(self, blob, target):
        while len(self.data) % 4:
            self.data += b"\0"
        self.views.append(BufferView(buffer=0, byteOffset=len(self.data), byteLength=len(blob), target=target))
        self.data += blob
        return len(self.views) - 1

    def _acc(self, view, ctype, count, atype, mn=None, mx=None):
        self.accs.append(Accessor(bufferView=view, componentType=ctype, count=count, type=atype, min=mn, max=mx))
        return len(self.accs) - 1

    def material(self, name, colour=(1, 1, 1, 1), texture=None, double_sided=False):
        pbr = PBRMetallicRoughness(baseColorFactor=list(colour),
                                   baseColorTexture=TextureInfo(index=texture) if texture is not None else None)
        self.mats.append(Material(name=name, pbrMetallicRoughness=pbr, doubleSided=double_sided or None))
        return len(self.mats) - 1

    def primitive(self, positions, indices, material, uvs=None, normals=None):
        ab, eb = BufferTarget.ARRAY_BUFFER.value, BufferTarget.ELEMENT_ARRAY_BUFFER.value
        f, v3, v2 = ComponentType.FLOAT.value, AccessorType.VEC3.value, AccessorType.VEC2.value
        xs, ys, zs = zip(*positions)
        pos = self._acc(self._view(b"".join(struct.pack("<3f", *p) for p in positions), ab), f, len(positions), v3,
                        [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
        attrs = Attributes(POSITION=pos)
        if normals:
            attrs.NORMAL = self._acc(self._view(b"".join(struct.pack("<3f", *n) for n in normals), ab), f,
                                     len(normals), v3)
        if uvs:
            attrs.TEXCOORD_0 = self._acc(self._view(b"".join(struct.pack("<2f", *t) for t in uvs), ab), f,
                                         len(uvs), v2)
        idx = self._acc(self._view(b"".join(struct.pack("<H", i) for i in indices), eb),
                        ComponentType.UNSIGNED_SHORT.value, len(indices), AccessorType.SCALAR.value)
        return Primitive(attributes=attrs, indices=idx, material=material)

    def quad(self, corners, material):
        return self.primitive(corners, [0, 1, 2, 0, 2, 3], material)

    def export(self, path, nodes, meshes, images=(), textures=(), samplers=()):
        model = GLTFModel(asset=Asset(version="2.0"), scenes=[Scene(nodes=[0])], scene=0, nodes=nodes,
                          meshes=meshes, materials=self.mats, buffers=[Buffer(byteLength=len(self.data))],
                          bufferViews=self.views, accessors=self.accs, images=list(images) or None,
                          textures=list(textures) or None, samplers=list(samplers) or None)
        GLTF(model=model, resources=[GLBResource(bytes(self.data))]).export(path)


def _test_glb(path):
    """One red quad named nameModel; every mesh and material is named (pycgfx needs that)."""
    g = _Glb()
    mat = g.material("QuadMat", (1, 0.2, 0.2, 1))
    prim = g.primitive([(-1, -0.5, 0), (1, -0.5, 0), (1, 0.5, 0), (-1, 0.5, 0)], [0, 1, 2, 0, 2, 3], mat,
                       normals=[(0, 0, 1)] * 4)
    g.export(path, [Node(name="nameModel", mesh=0)], [Mesh(name="QuadMesh", primitives=[prim])])


# box faces: (colour, 4 corners counter-clockwise seen from outside)
_FACES = {
    "front": ((0.9, 0.1, 0.1, 1), [(-4, -3, 1), (4, -3, 1), (4, 3, 1), (-4, 3, 1)]),
    "back": ((0.9, 0.9, 0.1, 1), [(4, -3, -1), (-4, -3, -1), (-4, 3, -1), (4, 3, -1)]),
    "right": ((0.1, 0.2, 0.9, 1), [(4, -3, 1), (4, -3, -1), (4, 3, -1), (4, 3, 1)]),
    "left": ((0.9, 0.1, 0.9, 1), [(-4, -3, -1), (-4, -3, 1), (-4, 3, 1), (-4, 3, -1)]),
    "top": ((0.6, 0.6, 0.6, 1), [(-4, 3, 1), (4, 3, 1), (4, 3, -1), (-4, 3, -1)]),
    "bottom": ((0.3, 0.3, 0.3, 1), [(-4, -3, -1), (4, -3, -1), (4, -3, 1), (-4, -3, 1)]),
}
_LOGO = [(-5, -1.2, 0), (5, -1.2, 0), (5, 1.2, 0), (-5, 1.2, 0)]


def _banner_glb(path, logo_under_world=False):
    """The official node layout: COMMON -> world -> worldModel (a box, one colour per
    face) and name -> nameModel (a green logo), as a sibling or under worldModel."""
    g = _Glb()
    box = [g.quad(c, g.material(f"{n}Mat", col)) for n, (col, c) in _FACES.items()]
    logo = g.quad(_LOGO, g.material("logoMat", (0.1, 0.8, 0.2, 1)))
    nodes = [
        Node(name="COMMON", children=[1] if logo_under_world else [1, 3]),
        Node(name="world", children=[2]),
        Node(name="worldModel", mesh=0, children=[3] if logo_under_world else None),
        Node(name="name", children=[4], translation=[0, 4.5, 2] if logo_under_world else [0, 4.5, 3]),
        Node(name="nameModel", mesh=1),
    ]
    g.export(path, nodes, [Mesh(name="Box", primitives=box), Mesh(name="Logo", primitives=[logo])])


def _cover_texture():
    """A bright, busy 256x256 'cover' so every part of it is clearly not background."""
    im = Image.new("RGB", (256, 256))
    d = ImageDraw.Draw(im)
    for y in range(0, 256, 32):
        for x in range(0, 256, 32):
            d.rectangle((x, y, x + 31, y + 31), fill=((x * 7 + 80) % 256, (y * 5 + 120) % 256, (x + y) % 200 + 55))
    d.rectangle((40, 100, 216, 156), fill=(250, 220, 40))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _case_glb(path):
    """A DS-case-like model: textured double-sided covers (front and back, each a
    subdivided grid) round a grey body, under COMMON -> world -> worldModel. About
    490 triangles, like a real banner model, so render timings stay meaningful."""
    g = _Glb()
    tex_view = g._view(_cover_texture(), None)
    cover = g.material("CoverMat", texture=0, double_sided=True)
    body = g.material("BodyMat", (0.8, 0.8, 0.8, 1))
    x0, x1, y0, y1, zf, zb = -6.0, 6.0, -4.7, 6.5, 0.85, -0.37
    nx, ny = 12, 10
    prims = []
    for z, flip in ((zf, False), (zb, True)):
        pos, uv, idx = [], [], []
        for j in range(ny + 1):
            for i in range(nx + 1):
                u, v = i / nx, j / ny
                pos.append((x0 + (x1 - x0) * (1 - u if flip else u), y0 + (y1 - y0) * v, z))
                uv.append((u, 1 - v))
        for j in range(ny):
            for i in range(nx):
                a = j * (nx + 1) + i
                b, c, e = a + 1, a + nx + 1, a + nx + 2
                idx += [a, b, e, a, e, c]
        prims.append(g.primitive(pos, idx, cover, uvs=uv))
    for corners in ([(x1, y0, zf), (x1, y0, zb), (x1, y1, zb), (x1, y1, zf)],
                    [(x0, y0, zb), (x0, y0, zf), (x0, y1, zf), (x0, y1, zb)],
                    [(x0, y1, zf), (x1, y1, zf), (x1, y1, zb), (x0, y1, zb)],
                    [(x0, y0, zb), (x1, y0, zb), (x1, y0, zf), (x0, y0, zf)]):
        prims.append(g.quad(corners, body))
    nodes = [Node(name="COMMON", children=[1]), Node(name="world", children=[2]),
             Node(name="worldModel", mesh=0)]
    g.export(path, nodes, [Mesh(name="Case", primitives=prims)],
             images=[GImage(bufferView=tex_view, mimeType="image/png", name="cover")],
             textures=[Texture(source=0, sampler=0, name="coverTex")], samplers=[Sampler()])


# ---------------------------------------------------------------- audio
def write_wav(path, width, channels, seconds=0.5, rate=22050, frames=None, silent=False):
    """A 440 Hz sine (or silence) with the given sample width in bytes (1, 2 or 3)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = frames if frames is not None else int(rate * seconds)
    if silent:
        data = b"\0" * n * channels * width
    else:
        out = bytearray()
        for i in range(n):
            v = math.sin(2 * math.pi * 440 * i / rate) * 0.8
            for _ in range(channels):
                if width == 1:
                    out += bytes([int(v * 127 + 128)])
                elif width == 2:
                    out += struct.pack("<h", int(v * 32767))
                else:
                    out += struct.pack("<i", int(v * 8388607))[:3]
        data = bytes(out)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(data)
    return path


def _audio(d):
    w = os.path.join(d, "wav")
    write_wav(os.path.join(w, "s16.wav"), 2, 2, 1.0, 44100)
    write_wav(os.path.join(w, "u8.wav"), 1, 1)
    write_wav(os.path.join(w, "s24.wav"), 3, 1)
    write_wav(os.path.join(w, "ref.wav"), 2, 2, rate=REF_RATE, frames=REF_FRAMES, silent=True)
    write_wav(os.path.join(w, "clip_288.wav"), 2, 2, rate=48000, frames=138240, silent=True)  # 2.88 s
    _write(os.path.join(w, "junk.wav"), b"RIFF nope")


# ---------------------------------------------------------------- ROMs
def make_nds(path, code="YGXE", title_lines=("Grand Theft Auto", "Chinatown Wars", "Rockstar Games"),
             version=1, banner=True):
    """A minimal NDS header (+ banner with the English title) - enough for nds.read_nds."""
    hdr = bytearray(0x200)
    hdr[0:12] = b"GTACHINATOWN"
    hdr[0x0C:0x10] = code.encode()
    hdr[0x10:0x12] = b"54"
    hdr[0x1E] = version
    body = b""
    if banner:
        struct.pack_into("<I", hdr, 0x68, 0x200)
        b = bytearray(0xA40)
        struct.pack_into("<H", b, 0, 1)
        t = "\n".join(title_lines).encode("utf-16-le")
        b[0x340:0x340 + len(t)] = t
        body = bytes(b)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, bytes(hdr) + body + b"\0" * 0x1000)
    return path


def _roms(d):
    r = os.path.join(d, "roms")
    make_nds(os.path.join(r, "Grand Theft Auto - Chinatown Wars (USA).nds"))
    make_nds(os.path.join(r, "Two Lines.nds"), code="ABCE", title_lines=("Some Game", "Some Publisher"), version=0)
    make_nds(os.path.join(r, "One Line.nds"), code="ONEE", title_lines=("Only Title",), version=70)
    make_nds(os.path.join(r, "No Banner.nds"), code="NOBE", banner=False)
    _write(os.path.join(r, "junk.nds"), b"junk")


# ---------------------------------------------------------------- stand-in tools
FAKE_TOOL = """import os, sys
tool, args = sys.argv[1], sys.argv[2:]
print(f'[fake {tool}] {args[0]}')
if os.environ.get('FAKE_FAIL') == tool:
    print(f'[fake {tool}] simulated failure', file=sys.stderr)
    sys.exit(3)
out = args[args.index('-o') + 1]
open(out, 'wb').write(b'FAKE ' + tool.encode())
"""


def fake_tools(d):
    """{tool: path} of stand-ins that write 'FAKE <tool>' to their -o file."""
    f = os.path.join(d, "fake")
    os.makedirs(f, exist_ok=True)
    _write(os.path.join(f, "fake.py"), FAKE_TOOL.encode())
    tools = {}
    for t in ("bannertool", "cwavtool", "makerom"):
        if sys.platform == "win32":
            p = os.path.join(f, t + ".cmd")
            _write(p, f'@"{sys.executable}" "%~dp0fake.py" {t} %*\r\n'.encode())
        else:
            p = os.path.join(f, t)
            _write(p, f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake.py" {t} "$@"\n'.encode())
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        tools[t] = p
    return tools


# ---------------------------------------------------------------- all
def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def build(d):
    os.makedirs(d, exist_ok=True)
    _images(d)
    _test_glb(os.path.join(d, "test.glb"))
    _banner_glb(os.path.join(d, "banner_sibling.glb"))
    _banner_glb(os.path.join(d, "banner_child.glb"), logo_under_world=True)
    _case_glb(os.path.join(d, "case.glb"))
    _write(os.path.join(d, "bad.glb"), b"glTF garbage")
    _audio(d)
    _roms(d)
    fake_tools(d)
