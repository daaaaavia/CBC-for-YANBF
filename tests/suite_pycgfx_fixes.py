"""pycgfx fixes 3 + 4 (app/pycgfx_fixes.py) for transparent (glTF
BLEND) materials. Shows the bug first (stock + 2 fixes: with a BLEND logo listed
before 'world', looking 'world' / 'COMMON' up by name lands on the logo's bone - the
HOME Menu crash), then that the fix makes every lookup right, marks BLEND materials
translucent, leaves opaque banners byte-identical, and that real builds work."""
import os

import gltflib

from _common import S, check, finish, isolate, skip
isolate("pycgfx_fixes")
import paths
import pipeline as pl

if paths.find_missing():
    skip("pycgfx and the tools must be set up")
import pycgfx_fixes as fixes  # noqa: E402

stock = pl.load_pycgfx()  # (not wrapped yet)
convert_stock = stock.convert_gltf
from cgfx import patricia  # noqa: E402  (pycgfx's own bit test)


def walk(d, name):
    """Look `name` up in a stored bone tree, like the 3DS does."""
    nodes = d.nodes
    length = max(len(n.get_name()) for n in nodes[1:])
    padded = name.ljust(length, "\0")
    cur, prev_bit, steps = nodes[nodes[0].left_index], 10 ** 9, 0
    while cur.refbit < prev_bit and steps < 64:
        prev_bit = cur.refbit
        cur = nodes[cur.right_index if patricia.get_bit(padded, cur.refbit) else cur.left_index]
        steps += 1
    return cur.name


def lookups(cgfx):
    d = cgfx.data.models["COMMON"].skeleton.bones.dict
    order = [n.name for n in d.nodes[1:]]
    return order, {n: walk(d, n) for n in order if walk(d, n) != n}


def model(blend_logo=False, blend_model=False, name_first=True):
    g = gltflib.GLTF.load(os.path.join(S, "banner_sibling.glb"))
    nodes = {n.name: i for i, n in enumerate(g.model.nodes)}
    if name_first:  # like your goldenEye banner: COMMON -> name before world
        g.model.nodes[nodes["COMMON"]].children = [nodes["name"], nodes["world"]]
    for m in g.model.materials:
        if (m.name == "logoMat" and blend_logo) or (m.name != "logoMat" and blend_model):
            m.alphaMode = "BLEND"
    return g


print("the bug, without the fixes")
order, wrong = lookups(convert_stock(model(blend_logo=True)))
check(order.index("nameModel") > order.index("world"), f"a BLEND logo's bone is moved last: {order}")
check(bool(wrong), f"... and lookups go wrong: {wrong}")
order, wrong = lookups(convert_stock(model()))
check(not wrong, "an opaque banner is fine without the fix")

print("with the fixes")
fixes.install()
fixes.install()  # (twice is harmless)
m = pl.load_pycgfx()
check(m is stock and m.convert_gltf is not convert_stock and m._cbc_fixes, "conversions now go through the fixes")
for label, g in (("BLEND logo, listed before world", model(blend_logo=True)),
                 ("BLEND logo, listed after world", model(blend_logo=True, name_first=False)),
                 ("BLEND model, opaque logo", model(blend_model=True)),
                 ("everything BLEND", model(blend_logo=True, blend_model=True))):
    cgfx = m.convert_gltf(g)
    order, wrong = lookups(cgfx)
    mats = cgfx.data.models["COMMON"].materials
    kinds = {n: mats[n].transluscency_kind for n in mats}
    blend = {mm.name for mm in g.model.materials if mm.alphaMode == "BLEND"}
    check(not wrong, f"{label}: every bone found by name ({order})")
    check(all(kinds[n] == (1 if n in blend else 0) for n in kinds), f"{label}: BLEND materials translucent, others not")

print("opaque banners are unchanged")
a = stock.write(convert_stock(model()))
b = stock.write(m.convert_gltf(model()))
check(a == b, f"byte-identical with and without the fixes ({len(a):,} bytes)")

print("real conversions and builds")
for blend in (False, True):
    g = model(blend_logo=blend)
    p = os.path.join(S, f"local_fix_{blend}.glb")
    g.export(p)
    ok, printed, tb = pl.convert_glb(p, os.path.join(S, f"local_fix_{blend}.cgfx"))
    check(ok and (("[pycgfx fix]" in printed) == blend), f"convert_glb ({'BLEND' if blend else 'opaque'} logo): "
          f"{'fix notes in the log' if blend else 'nothing to fix'}")
job = pl.BuildJob(icon_path="icon48.png", banner_mode=pl.MODE_GLB, banner_path=os.path.join(S, "local_fix_True.glb"),
                  audio_path="", rom_path="/roms/nds/Fix Test.nds", title="Fix Test", publisher="Test",
                  product_code="CTR-H-FIXT", unique_id="FF3D1", minor=0)
log = []
p = pl.Pipeline(job, lambda k, s: log.append((k, s)), output_root=os.path.join(S, "local_fix_out"),
                registry_path=paths.ID_REGISTRY)
check(p.run() and os.path.isfile(p.cia_path), "a CIA with a BLEND logo builds")
check(any("[pycgfx fix]" in s for k, s in log), "the build log says the fixes were applied")
finish()
