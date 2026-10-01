"""Two fixes to pycgfx for transparent (glTF alphaMode BLEND) materials, on top of the
two in patches/pycgfx.patch (so they're called fixes 3 and 4).

They're applied while the program runs, to the banner pycgfx has just built, so the
pycgfx files on disk stay exactly as the setup window checks them. yanbf_cbc.py calls
install() at startup; every .glb conversion after that - builds and the CIA editor -
gets them.

Fix 3 - the bone lookup tree (the crash).
  Bones are stored in a name-lookup table (a patricia tree: each entry records the
  positions of the next entries to check). When a model has a BLEND material, pycgfx
  re-orders the bones so transparent ones are drawn last - by moving the table's
  entries - but doesn't rebuild the tree, so its stored positions point at the wrong
  entries. Looking up 'world' or 'COMMON' then finds the transparent bone instead,
  and the HOME Menu crashes. Fix: rebuild every skeleton's tree after conversion. The
  bone order (and everything that refers to bones by number) is unchanged; only the
  tree's positions are recomputed. Models with no BLEND material are byte-identical.

Fix 4 - translucency kind.
  pycgfx sets up blending for BLEND materials but leaves the material's translucency
  kind at 0 (opaque), so the 3DS may draw it in the opaque pass. Fix: set it to 1
  (translucent) for BLEND materials.
"""

import pipeline as pl

TRANSLUCENT = 1  # NW4C TranslucencyKind: 0 opaque, 1 translucent, 2 subtractive, 3 additive
_installed = False


def apply(cgfx, gltf):
    """Fix a converted CGFX in place. Returns a list of what was changed."""
    notes = []
    models = cgfx.data.models
    for name in models:
        cmdl = models[name]
        bones = cmdl.skeleton.bones.dict
        before = [(n.left_index, n.right_index, n.refbit) for n in bones.nodes]
        bones.regenerate()
        if [(n.left_index, n.right_index, n.refbit) for n in bones.nodes] != before:
            notes.append(f"rebuilt the bone lookup tree of {name}")
        blend = {m.name for m in (gltf.model.materials or []) if m.alphaMode == "BLEND"}
        for mat_name in cmdl.materials:
            mtob = cmdl.materials[mat_name]
            if mat_name in blend and mtob.transluscency_kind != TRANSLUCENT:
                mtob.transluscency_kind = TRANSLUCENT
                notes.append(f"marked material {mat_name!r} as translucent")
    return notes


def install():
    """Make every pycgfx conversion from now on go through apply()."""
    global _installed
    if _installed:
        return
    load = pl.load_pycgfx

    def load_with_fixes(*args, **kwargs):
        module = load(*args, **kwargs)
        if not getattr(module, "_cbc_fixes", False):
            convert = module.convert_gltf

            def convert_gltf(gltf, *a, **kw):
                cgfx = convert(gltf, *a, **kw)
                for note in apply(cgfx, gltf):
                    print(f"[pycgfx fix] {note}")  # shown in the build log
                return cgfx

            module.convert_gltf = convert_gltf
            module._cbc_fixes = True
        return module

    pl.load_pycgfx = load_with_fixes
    _installed = True
