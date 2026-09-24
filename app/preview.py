"""Preview rendering for the GUI: icon/banner thumbnails, a software .glb
renderer and a WAV waveform. Pure Pillow (no tkinter here), so it's testable.

The .glb renderer is a small scanline z-buffer rasterizer: static pose (node
transforms only; no animation, skinning or billboarding), base colour +
perspective-correct base colour texture, simple directional light. Its
default view is the 3DS HOME Menu banner camera from pycgfx's
banner-camera.gltf, so it shows roughly what the HOME Menu will show.
"""

import json
import math
import os
import struct
import wave
from array import array
from dataclasses import dataclass, field
from io import BytesIO

import gltflib
from PIL import Image, ImageChops, ImageDraw

import paths

# Image colours (theme.apply_preview() may replace these)
BG = (214, 218, 224)
PLACEHOLDER_BG = (236, 236, 236)
PLACEHOLDER_FG = (120, 120, 120)
PLACEHOLDER_LINE = (200, 200, 200)
WAVE_BG = (250, 250, 250)
WAVE_MID = (210, 210, 210)
WAVE_FG = (0, 128, 138)
CHECK = ((255, 255, 255), (222, 222, 222))
TEX_MAX = 256  # textures are downscaled to this for speed

# Fallback if banner-camera.gltf is missing: same values as that file.
CAMERA_DEFAULT = {"pos": (0.0, 1.0, 44.786), "yfov": 0.523599, "aspect": 1.66666666667,
                  "znear": 26.5, "zfar": 1000.0}


# ---------------------------------------------------------------- 2D helpers

def placeholder(size, text):
    img = Image.new("RGB", size, PLACEHOLDER_BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, size[0] - 1, size[1] - 1), outline=PLACEHOLDER_LINE)
    w = d.textlength(text)
    d.text(((size[0] - w) / 2, size[1] / 2 - 6), text, fill=PLACEHOLDER_FG)
    return img


def checkerboard(size, cell=8):
    img = Image.new("RGB", size, CHECK[0])
    d = ImageDraw.Draw(img)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=CHECK[1])
    return img


def _on_checker(im, box_size, scale, resample=Image.NEAREST):
    """im scaled by `scale` (shrunk further to fit), centred on a checkerboard box."""
    im = im.convert("RGBA")
    w, h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    fit = min(1.0, box_size[0] / w, box_size[1] / h)
    w, h = max(1, int(w * fit)), max(1, int(h * fit))
    im = im.resize((w, h), resample if fit == 1.0 else Image.LANCZOS)
    box = checkerboard(box_size)
    box.paste(im, ((box_size[0] - w) // 2, (box_size[1] - h) // 2), im)
    return box


def icon_preview(path, size=(170, 100)):
    """2x (pixel-exact) and 1x views side by side. Returns (image, info)."""
    try:
        with Image.open(path) as im:
            im.load()
            fmt, (w, h) = im.format, im.size
            img = Image.new("RGB", size, PLACEHOLDER_BG)
            img.paste(_on_checker(im, (100, 100), 2), (0, 0))
            img.paste(_on_checker(im, (56, 56), 1), (110, 22))
    except Exception:
        return placeholder(size, "Can't read this image"), ""
    return img, f"{w}×{h} {fmt} · shown at 2× and 1×"


def banner_image_preview(path, size=(300, 180)):
    try:
        with Image.open(path) as im:
            im.load()
            fmt, (w, h) = im.format, im.size
            img = _on_checker(im, size, 1)
    except Exception:
        return placeholder(size, "Can't read this image"), ""
    return img, f"{w}×{h} {fmt} · actual size"


# ---------------------------------------------------------------- WAV

@dataclass
class WavInfo:
    channels: int
    rate: int
    bits: int
    frames: int

    @property
    def seconds(self):
        return self.frames / self.rate if self.rate else 0.0

    def describe(self):
        ch = {1: "mono", 2: "stereo"}.get(self.channels, f"{self.channels} ch")
        return f"{self.seconds:.2f} s · {self.rate} Hz · {self.bits}-bit · {ch}"


def _samples(raw, width):
    """Raw PCM bytes -> (array of ints, full-scale value)."""
    if width == 1:
        return array("b", bytes((b - 128) & 0xFF for b in raw)), 128
    if width == 2:
        return array("h", raw[: len(raw) // 2 * 2]), 32768
    if width == 3:  # keep the top 16 bits of each 24-bit sample
        n = len(raw) // 3
        out = bytearray(n * 2)
        out[0::2] = raw[1: n * 3: 3]
        out[1::2] = raw[2: n * 3: 3]
        return array("h", bytes(out)), 32768
    if width == 4:
        return array("i", raw[: len(raw) // 4 * 4]), 2 ** 31
    raise ValueError(f"unsupported sample width {width}")


def wav_preview(path, size=(300, 64)):
    """Waveform image + WavInfo. Raises on files the wave module can't read."""
    with wave.open(path, "rb") as w:
        info = WavInfo(w.getnchannels(), w.getframerate(), w.getsampwidth() * 8, w.getnframes())
        width = w.getsampwidth()
        img = Image.new("RGB", size, WAVE_BG)
        d = ImageDraw.Draw(img)
        mid = size[1] / 2
        d.line((0, mid, size[0], mid), fill=WAVE_MID)
        per_col = max(1, math.ceil(info.frames / size[0]))
        for x in range(size[0]):
            raw = w.readframes(per_col)
            if not raw:
                break
            s, full = _samples(raw, width)
            if not s:
                continue
            lo, hi = min(s) / full, max(s) / full
            d.line((x, mid - hi * (mid - 1), x, mid - lo * (mid - 1)), fill=WAVE_FG)
    return img, info


# ---------------------------------------------------------------- glTF loading

_COMP = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_NORM = {"b": 127.0, "B": 255.0, "h": 32767.0, "H": 65535.0, "I": 4294967295.0}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


@dataclass
class Material:
    color: tuple  # base colour factor, 0-1 RGBA
    texture: object  # PIL RGBA image or None
    alpha_mode: str  # OPAQUE / MASK / BLEND
    alpha_cutoff: float
    double_sided: bool = False
    tex_data: bytes = None  # texture.tobytes() (RGBA), for fast sampling

    def __post_init__(self):
        if self.texture is not None:
            self.tex_data = self.texture.tobytes()


@dataclass
class Mesh:
    verts: list  # world-space (x, y, z)
    tris: list  # (i0, i1, i2, material index, (uv0, uv1, uv2) or None, flat rgba 0-1)
    materials: list
    center: tuple
    radius: float
    triangle_count: int = 0
    warnings: list = field(default_factory=list)
    # node tree, so pose() can re-transform per node (spin / billboard)
    node_names: list = field(default_factory=list)
    node_parents: list = field(default_factory=list)  # parent index or -1
    node_local: list = field(default_factory=list)  # 4x4 local matrices
    node_order: list = field(default_factory=list)  # parents before children
    vert_src: list = field(default_factory=list)  # (node index or -1 = identity, local (x, y, z))


def _buffer_bytes(gltf, buffer_index):
    buf = gltf.model.buffers[buffer_index]
    res = gltf.get_glb_resource() if buf.uri is None else gltf.get_resource(buf.uri)
    return res.data


def _bufferview_bytes(gltf, bv_index):
    bv = gltf.model.bufferViews[bv_index]
    data = _buffer_bytes(gltf, bv.buffer)
    start = bv.byteOffset or 0
    return data[start: start + bv.byteLength], bv.byteStride


def _read_accessor(gltf, index):
    acc = gltf.model.accessors[index]
    fmt, n = _COMP[acc.componentType], _NCOMP[acc.type]
    if acc.bufferView is None:
        return [(0.0,) * n] * acc.count
    data, stride = _bufferview_bytes(gltf, acc.bufferView)
    st = struct.Struct("<" + fmt * n)
    stride = stride or st.size
    base = acc.byteOffset or 0
    out = [st.unpack_from(data, base + i * stride) for i in range(acc.count)]
    if acc.normalized and fmt != "f":
        k = _NORM[fmt]
        out = [tuple(max(v / k, -1.0) for v in t) for t in out]
    return out


def _mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _node_matrix(node):
    if node.matrix:
        m = node.matrix  # column-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = node.translation or (0, 0, 0)
    qx, qy, qz, qw = node.rotation or (0, 0, 0, 1)
    sx, sy, sz = node.scale or (1, 1, 1)
    r = [
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ]
    return [
        [r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
        [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
        [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
        [0, 0, 0, 1],
    ]


def _load_image(gltf, index):
    img = gltf.model.images[index]
    if img.bufferView is not None:
        data, _ = _bufferview_bytes(gltf, img.bufferView)
    else:
        data = gltf.get_resource(img.uri).data
    im = Image.open(BytesIO(data)).convert("RGBA")
    if max(im.size) > TEX_MAX:
        im.thumbnail((TEX_MAX, TEX_MAX), Image.LANCZOS)
    return im


def _sample(tex, uv):
    u, v = uv
    x = int((u % 1.0) * tex.width) % tex.width
    y = int((v % 1.0) * tex.height) % tex.height
    return tuple(c / 255.0 for c in tex.getpixel((x, y)))


def load_glb(path):
    """Load a .glb/.gltf into a Mesh in world space (static pose)."""
    gltf = gltflib.GLTF.load(path, load_file_resources=True)
    model = gltf.model
    warnings = []

    textures = {}
    materials = []
    for m in model.materials or []:
        pbr = m.pbrMetallicRoughness
        color = tuple(pbr.baseColorFactor) if pbr and pbr.baseColorFactor else (1.0, 1.0, 1.0, 1.0)
        tex = None
        if pbr and pbr.baseColorTexture is not None:
            ti = pbr.baseColorTexture.index
            src = model.textures[ti].source if model.textures and ti < len(model.textures) else None
            if src is not None:
                if src not in textures:
                    try:
                        textures[src] = _load_image(gltf, src)
                    except Exception:
                        textures[src] = None
                        warnings.append("a texture couldn't be decoded")
                tex = textures[src]
        materials.append(Material(color, tex, m.alphaMode or "OPAQUE",
                                  m.alphaCutoff if m.alphaCutoff is not None else 0.5,
                                  bool(m.doubleSided)))
    default_mat = len(materials)
    materials.append(Material((0.8, 0.8, 0.8, 1.0), None, "OPAQUE", 0.5))

    verts, tris, vert_src = [], [], []
    nodes = model.nodes or []
    node_parents = [-1] * len(nodes)
    node_local = [_node_matrix(n) for n in nodes]
    node_order = []

    def visit(ni, parent, parent_index):
        node = nodes[ni]
        node_parents[ni] = parent_index
        node_order.append(ni)
        world = _mat_mul(parent, node_local[ni])
        if node.mesh is not None:
            # skinned meshes ignore the node transform (glTF spec)
            skinned = node.skin is not None
            mw = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] if skinned else world
            for prim in model.meshes[node.mesh].primitives:
                add_primitive(prim, mw, -1 if skinned else ni)
        for c in node.children or []:
            visit(c, world, ni)

    def add_primitive(prim, mw, node_index):
        mode = 4 if prim.mode is None else prim.mode
        if mode not in (4, 5, 6):
            return
        attrs = prim.attributes
        if attrs.POSITION is None:
            return
        pos = _read_accessor(gltf, attrs.POSITION)
        base = len(verts)
        for x, y, z in pos:
            vert_src.append((node_index, (x, y, z)))
            verts.append((
                mw[0][0] * x + mw[0][1] * y + mw[0][2] * z + mw[0][3],
                mw[1][0] * x + mw[1][1] * y + mw[1][2] * z + mw[1][3],
                mw[2][0] * x + mw[2][1] * y + mw[2][2] * z + mw[2][3],
            ))
        mi = prim.material if prim.material is not None and prim.material < default_mat else default_mat
        mat = materials[mi]
        uvs = None
        if mat.texture is not None:
            tc = model.materials[mi].pbrMetallicRoughness.baseColorTexture.texCoord or 0
            acc = getattr(attrs, f"TEXCOORD_{tc}", None)
            if acc is not None:
                uvs = _read_accessor(gltf, acc)
        idx = [i[0] for i in _read_accessor(gltf, prim.indices)] if prim.indices is not None else list(range(len(pos)))
        if mode == 4:
            faces = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx) - 2, 3)]
        elif mode == 5:
            faces = [(idx[i], idx[i + 1], idx[i + 2]) if i % 2 == 0 else (idx[i + 1], idx[i], idx[i + 2])
                     for i in range(len(idx) - 2)]
        else:
            faces = [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
        for a, b, c in faces:
            uv = (uvs[a], uvs[b], uvs[c]) if uvs else None
            if uv:
                cu = ((uv[0][0] + uv[1][0] + uv[2][0]) / 3, (uv[0][1] + uv[1][1] + uv[2][1]) / 3)
                t = _sample(mat.texture, cu)
                flat = tuple(t[k] * mat.color[k] for k in range(4))
            else:
                flat = mat.color
            tris.append((base + a, base + b, base + c, mi, uv, flat))

    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    if model.scenes:
        roots = model.scenes[model.scene or 0].nodes or []
    else:
        children = {c for n in nodes for c in (n.children or [])}
        roots = [i for i in range(len(nodes)) if i not in children]
    for r in roots:
        visit(r, identity, -1)

    if not tris:
        raise ValueError("no triangles found in the model")
    if model.animations:
        warnings.append("animations not previewed")
    if model.skins:
        warnings.append("skinning not previewed")
    xs, ys, zs = zip(*verts)
    center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    radius = max(math.dist(center, v) for v in verts) or 1.0
    return Mesh(verts, tris, materials, center, radius, len(tris), warnings,
                [n.name or "" for n in nodes], node_parents, node_local, node_order, vert_src)


# ---------------------------------------------------------------- HOME Menu posing

# Bones pycgfx (patched main.py make_bones) gives YAxial billboard mode.
BILLBOARD_NAMES = ("name", "nameModel")


def find_spin_node(mesh):
    """The node the HOME Menu spins: 'worldModel', else 'world' (any case). None if absent."""
    for want in ("worldmodel", "world"):
        for i in mesh.node_order:
            if mesh.node_names[i].lower() == want:
                return i
    return None


def find_billboard_nodes(mesh):
    return [i for i in mesh.node_order if mesh.node_names[i] in BILLBOARD_NAMES]


def _rot_y(angle):
    c, s = math.cos(angle), math.sin(angle)
    return [[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]]


def _billboard_y_axial(m):
    """YAxial billboard: keep the bone's Y axis, turn its Z axis to face the screen.

    The banner camera looks straight down -Z, so "facing the screen" is +Z. As in
    the non-viewpoint NW4C modes, every billboard faces the camera identically."""
    cols = [[m[r][c] for r in range(3)] for c in range(3)]  # X, Y, Z axes (with scale)
    sx, sy, sz = (math.sqrt(sum(v * v for v in col)) or 1.0 for col in cols)
    y = [v / sy for v in cols[1]]
    z = [0.0 - y[0] * y[2], 0.0 - y[1] * y[2], 1.0 - y[2] * y[2]]  # +Z minus its part along y
    zl = math.sqrt(sum(v * v for v in z))
    if zl < 1e-6:  # bone's Y axis points at the camera; nothing sensible to do
        return m
    z = [v / zl for v in z]
    x = [y[1] * z[2] - y[2] * z[1], y[2] * z[0] - y[0] * z[2], y[0] * z[1] - y[1] * z[0]]
    out = [row[:] for row in m]
    for r in range(3):
        out[r][0], out[r][1], out[r][2] = x[r] * sx, y[r] * sy, z[r] * sz
    return out


def pose(mesh, spin_angle=0.0, spin_node=None, billboard_nodes=()):
    """A copy of mesh with the spin node rotated about its own Y axis by spin_angle
    (radians) and billboard nodes turned to face the screen. Triangles, materials
    and the orbit centre are shared with the original."""
    world = {}
    bill = set(billboard_nodes)
    for ni in mesh.node_order:
        p = mesh.node_parents[ni]
        m = mesh.node_local[ni]
        if ni == spin_node:
            m = _mat_mul(m, _rot_y(spin_angle))
        m = _mat_mul(world[p], m) if p >= 0 else m
        if ni in bill:
            m = _billboard_y_axial(m)
        world[ni] = m
    verts = []
    for ni, (x, y, z) in mesh.vert_src:
        if ni < 0:
            verts.append((x, y, z))
            continue
        m = world[ni]
        verts.append((
            m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
        ))
    return Mesh(verts, mesh.tris, mesh.materials, mesh.center, mesh.radius, mesh.triangle_count,
                mesh.warnings, mesh.node_names, mesh.node_parents, mesh.node_local, mesh.node_order,
                mesh.vert_src)


# ---------------------------------------------------------------- rendering

def banner_camera():
    """Camera from processes/YANBF/pycgfx/banner-camera.gltf (fallback: same values)."""
    cam = dict(CAMERA_DEFAULT)
    try:
        with open(os.path.join(paths.PYCGFX_DIR, "banner-camera.gltf"), encoding="utf-8") as f:
            g = json.load(f)
        p = g["cameras"][0]["perspective"]
        cam.update(yfov=p["yfov"], aspect=p.get("aspectRatio", cam["aspect"]),
                   znear=p.get("znear", cam["znear"]), zfar=p.get("zfar", cam["zfar"]))
        node = next(n for n in g["nodes"] if "camera" in n)
        cam["pos"] = tuple(node.get("translation", cam["pos"]))
    except (OSError, ValueError, KeyError, IndexError, StopIteration):
        pass
    return cam


def _plane(pts, vals):
    """(a, b, c) with f(x, y) = a*x + b*y + c through the 3 points."""
    (x0, y0), (x1, y1), (x2, y2) = pts
    det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    f0, f1, f2 = vals
    a = ((f1 - f0) * (y2 - y0) - (f2 - f0) * (y1 - y0)) / det
    b = ((x1 - x0) * (f2 - f0) - (x2 - x0) * (f1 - f0)) / det
    return a, b, f0 - a * x0 - b * y0


def render(mesh, yaw=0.0, pitch=0.0, size=(300, 180), ss=1, camera=None, zoom=1.0, background=None,
           want_mask=False):
    """Render through the banner camera, with the model orbited about its centre.

    Scanline z-buffer with perspective-correct texturing. zoom scales the model
    about its centre (inspection only; 1.0 = true size). Back faces are culled
    unless the material is double-sided. ss > 1 supersamples for smoother edges.
    """
    cam = camera or banner_camera()
    W, H = size[0] * ss, size[1] * ss
    f = 1.0 / math.tan(cam["yfov"] / 2)
    aspect = cam["aspect"]
    znear, zfar = cam["znear"], cam["zfar"]
    cx, cy, cz = cam["pos"]
    px, py, pz = mesh.center
    ch_, sh_ = math.cos(yaw), math.sin(yaw)
    cp_, sp_ = math.cos(pitch), math.sin(pitch)

    world, screen, depth = [], [], []
    for x, y, z in mesh.verts:
        x, y, z = x - px, y - py, z - pz
        x, z = ch_ * x + sh_ * z, -sh_ * x + ch_ * z
        y, z = cp_ * y - sp_ * z, sp_ * y + cp_ * z
        x, y, z = x * zoom + px, y * zoom + py, z * zoom + pz
        world.append((x, y, z))
        d = cz - z
        depth.append(d)
        if d > 1e-6:
            screen.append(((f / aspect * (x - cx) / d + 1) * W / 2, (1 - f * (y - cy) / d) * H / 2))
        else:
            screen.append((0.0, 0.0))

    zbuf = [0.0] * (W * H)  # 1/depth; bigger = nearer
    if background is not None:  # an RGB image drawn behind the model
        start = background.convert("RGB").resize((W, H)).tobytes()
    else:
        start = bytes(BG) * (W * H)
    cbuf = bytearray(start)
    lx, ly, lz = -0.35, 0.55, 0.76
    blended = []

    for a, b, c, mi, uv, flat in mesh.tris:
        da, db, dc = depth[a], depth[b], depth[c]
        if min(da, db, dc) < znear or max(da, db, dc) > zfar:
            continue
        mat = mesh.materials[mi]
        pts = (screen[a], screen[b], screen[c])
        signed = ((pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1])
                  - (pts[2][0] - pts[0][0]) * (pts[1][1] - pts[0][1]))
        if abs(signed) < 1e-9:
            continue
        if signed > 0 and not mat.double_sided:  # screen y points down: CCW front faces are negative
            continue
        (ax, ay, az), (bx, by, bz), (qx, qy, qz) = world[a], world[b], world[c]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = qx - ax, qy - ay, qz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        shade = 0.45 + 0.55 * abs((nx * lx + ny * ly + nz * lz) / nl)
        job = (pts, (1 / da, 1 / db, 1 / dc), uv if mat.tex_data else None, mat, flat, shade)
        if mat.alpha_mode == "BLEND":
            blended.append(((da + db + dc) / 3, job))
        else:
            _fill(zbuf, cbuf, W, H, *job)

    blended.sort(key=lambda j: -j[0])  # far to near
    for _, job in blended:
        _fill(zbuf, cbuf, W, H, *job)

    img = Image.frombytes("RGB", (W, H), bytes(cbuf))
    if not want_mask:
        return img.resize(size, Image.LANCZOS) if ss != 1 else img
    # coverage: depth-written pixels, plus blended pixels that changed the backdrop
    mask = Image.frombytes("L", (W, H), bytes(255 if z > 0.0 else 0 for z in zbuf))
    if blended:
        changed = ImageChops.difference(img, Image.frombytes("RGB", (W, H), start)).convert("L")
        mask = ImageChops.lighter(mask, changed.point(lambda v: 255 if v else 0))
    if ss != 1:
        return img.resize(size, Image.LANCZOS), mask.resize(size, Image.LANCZOS)
    return img, mask


def _fill(zbuf, cbuf, W, H, pts, invd, uv, mat, flat, shade):
    """Rasterize one triangle into the z/colour buffers."""
    mode = mat.alpha_mode
    ys = [p[1] for p in pts]
    y_lo = max(0, math.ceil(min(ys) - 0.5))
    y_hi = min(H - 1, math.floor(max(ys) - 0.5))
    if y_hi < y_lo:
        return
    za, zb, zc = _plane(pts, invd)
    edges = ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0]))

    if uv is None:
        alpha = flat[3]
        if mode == "MASK" and alpha < mat.alpha_cutoff or mode == "BLEND" and alpha <= 0.0:
            return
        col = [min(255, int(flat[k] * shade * 255)) for k in range(3)]
        blend = mode == "BLEND" and alpha < 1.0
        ai = int(alpha * 256)
    else:
        tex, td = mat.texture, mat.tex_data
        TW, TH = tex.width, tex.height
        ua, ub, uc = _plane(pts, [uv[k][0] * invd[k] for k in range(3)])
        va, vb, vc = _plane(pts, [uv[k][1] * invd[k] for k in range(3)])
        tint = [int(min(1.0, mat.color[k] * shade) * 256) for k in range(3)]
        tr, tg, tb_ = tint
        cut = int(mat.alpha_cutoff * 255) if mode == "MASK" else 0
        amul = int(mat.color[3] * 256)

    for py in range(y_lo, y_hi + 1):
        yc = py + 0.5
        xs = []
        for (x0, y0), (x1, y1) in edges:
            if (y0 <= yc < y1) or (y1 <= yc < y0):
                xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
        if len(xs) < 2:
            continue
        xa = max(0, math.ceil(min(xs) - 0.5))
        xb = min(W - 1, math.floor(max(xs) - 0.5))
        if xb < xa:
            continue
        xc = xa + 0.5
        iz = za * xc + zb * yc + zc
        row = py * W
        if uv is None:
            r, g, b = col
            for i in range(row + xa, row + xb + 1):
                if iz > zbuf[i]:
                    j = i * 3
                    if blend:
                        cbuf[j] = (r * ai + cbuf[j] * (256 - ai)) >> 8
                        cbuf[j + 1] = (g * ai + cbuf[j + 1] * (256 - ai)) >> 8
                        cbuf[j + 2] = (b * ai + cbuf[j + 2] * (256 - ai)) >> 8
                    else:
                        zbuf[i] = iz
                        cbuf[j], cbuf[j + 1], cbuf[j + 2] = r, g, b
                iz += za
        else:
            uz = ua * xc + ub * yc + uc
            vz = va * xc + vb * yc + vc
            for i in range(row + xa, row + xb + 1):
                if iz > zbuf[i]:
                    p = ((int(vz / iz * TH) % TH) * TW + int(uz / iz * TW) % TW) * 4
                    j = i * 3
                    if mode == "OPAQUE":
                        zbuf[i] = iz
                        cbuf[j] = min(255, td[p] * tr >> 8)
                        cbuf[j + 1] = min(255, td[p + 1] * tg >> 8)
                        cbuf[j + 2] = min(255, td[p + 2] * tb_ >> 8)
                    elif mode == "MASK":
                        if td[p + 3] >= cut:
                            zbuf[i] = iz
                            cbuf[j] = min(255, td[p] * tr >> 8)
                            cbuf[j + 1] = min(255, td[p + 1] * tg >> 8)
                            cbuf[j + 2] = min(255, td[p + 2] * tb_ >> 8)
                    else:
                        ai = td[p + 3] * amul >> 8
                        if ai:
                            cbuf[j] = (min(255, td[p] * tr >> 8) * ai + cbuf[j] * (256 - ai)) >> 8
                            cbuf[j + 1] = (min(255, td[p + 1] * tg >> 8) * ai + cbuf[j + 1] * (256 - ai)) >> 8
                            cbuf[j + 2] = (min(255, td[p + 2] * tb_ >> 8) * ai + cbuf[j + 2] * (256 - ai)) >> 8
                iz += za
                uz += ua
                vz += va

