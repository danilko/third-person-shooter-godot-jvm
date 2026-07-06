#!/usr/bin/env python3
"""
build_walls.py -> walls_kit.blend

All facade modules: residential walls, konbini (commercial) walls, shotengai shop
fronts, garage, plus slabs / corners / parapets / balcony / stoop / canopy / sign.

Endpoint pivot: origin at base START corner (x=0), front face +Y, length +X,
base z=0 — so modules abut by stepping +BAY in X. Slabs pivot at the TOP corner.

Collision: every solid module gets a combined `<Name>-colonly` proxy. Walls WITH
an opening get a proxy of the SOLID parts only (jambs + sill + header) so doors
and windows stay passable. Thin glass panes carry no collision.

RUN: blender --background --python kit/build_walls.py
"""
import bpy, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

COLL = "WALLS"
BAY, T, R_H, K_H, SLAB = kc.R_BAY, kc.T, kc.R_H, kc.K_H, kc.SLAB


def wall_colonly(name, c, w, h, opening):
    """Combined collision proxy. opening=(x0,x1,z0,z1) cut from the wall, or None."""
    if opening is None:
        parts = [((0, w, -T, 0, 0, h), "col")]
    else:
        ox0, ox1, oz0, oz1 = opening
        parts = []
        if ox0 > 0:           parts.append(((0, ox0, -T, 0, 0, h), "col"))      # left jamb
        if ox1 < w:           parts.append(((ox1, w, -T, 0, 0, h), "col"))      # right jamb
        if oz0 > 0:           parts.append(((ox0, ox1, -T, 0, 0, oz0), "col"))  # sill
        if oz1 < h:           parts.append(((ox0, ox1, -T, 0, oz1, h), "col"))  # header
    kc.combine(name + "-colonly", parts, c)


def wall(name, c, h, opening=None, pane=None, matkey="concrete", w=None):
    w = w or BAY
    o = kc.box(name, 0, w, -T, 0, 0, h, c, matkey)
    if opening:
        ox0, ox1, oz0, oz1 = opening
        kc.cut(o, ox0, ox1, -T, 0, oz0, oz1)
    if pane:
        px0, px1, pz0, pz1 = pane
        kc.box(name + "_Pane", px0, px1, -0.11, -0.09, pz0, pz1, c, "glass")
    wall_colonly(name, c, w, h, opening)
    return o


def build_residential(c):
    wall("SM_Res_Wall_Solid_2x3", c, R_H)
    wall("SM_Res_Wall_Window_2x3", c, R_H, opening=(0.4, 1.6, 0.9, 2.3),
         pane=(0.4, 1.6, 0.9, 2.3))
    wall("SM_Res_Wall_Door_2x3", c, R_H, opening=(0.5, 1.5, 0.0, 2.1),
         pane=(0.5, 1.5, 2.1, 2.5))                      # transom glass above door
    wall("SM_Res_Wall_Slider_2x3", c, R_H, opening=(0.1, 1.9, 0.2, 2.4),
         pane=(0.1, 1.9, 0.2, 2.4))
    # corner trim post (solid)
    p = kc.box("SM_Res_Corner_02x02x3", 0, T, -T, 0, 0, R_H, c, "trim")
    kc.colonly(p, c)
    # slab — TOP face at datum (pivot top corner)
    s = kc.box("SM_Res_Slab_2x2x03", 0, BAY, -BAY, 0, -SLAB, 0, c, "trim")
    kc.colonly(s, c)
    # balcony deck + rails
    d = kc.box("SM_Res_Balcony_Deck", 0, BAY, 0, 1.0, -0.2, 0, c, "trim"); kc.colonly(d, c)
    kc.box("SM_Res_Balcony_RailL", 0.0, 0.06, 0.0, 0.06, 0, 1.1, c, "metal")
    kc.box("SM_Res_Balcony_RailR", BAY - 0.06, BAY, 0.0, 0.06, 0, 1.1, c, "metal")
    kc.box("SM_Res_Balcony_RailTop", 0, BAY, 0.0, 0.06, 1.04, 1.1, c, "metal")
    # parapet cap
    kc.box("SM_Res_Parapet_Slab", 0, BAY, -BAY, 0, -0.2, 0, c, "trim")
    kc.box("SM_Res_Parapet_UpL", 0, T, -T, 0, 0, 0.6, c, "metal")
    kc.box("SM_Res_Parapet_UpR", BAY - T, BAY, -T, 0, 0, 0.6, c, "metal")
    pw = kc.box("SM_Res_Parapet_Wall", 0, BAY, -T, 0, 0, 0.6, c, "concrete"); kc.colonly(pw, c)
    # entry stoop
    for i in range(3):
        wdt = 1.6 - i * 0.4
        kc.box(f"SM_Res_Stoop_Step{i+1}", -wdt/2, wdt/2, 0, 0.6, i*0.15, (i+1)*0.15, c, "trim")


def build_konbini(c):
    wall("SM_Kon_Glass_2x36", c, K_H, opening=(0.1, 1.9, 0.6, 3.0),
         pane=(0.1, 1.9, 0.6, 3.0))
    wall("SM_Kon_Door_2x36", c, K_H, opening=(0.1, 1.9, 0.0, 3.0),
         pane=(0.1, 1.9, 0.0, 3.0))
    wall("SM_Kon_Wall_2x36", c, K_H)
    p = kc.box("SM_Kon_Corner_03x36", 0, 0.3, -0.3, 0, 0, K_H, c, "trim"); kc.colonly(p, c)
    kc.box("SM_Kon_Sign_2x07", 0, BAY, -T, 0, 0, 0.7, c, "accent")
    kc.box("SM_Kon_Parapet_Slab", 0, BAY, -BAY, 0, -0.2, 0, c, "trim")
    kc.box("SM_Kon_Parapet_UpL", 0, 0.15, -0.15, 0, 0, 0.5, c, "metal")
    kc.box("SM_Kon_Parapet_UpR", BAY-0.15, BAY, -0.15, 0, 0, 0.5, c, "metal")
    pw = kc.box("SM_Kon_Parapet_Wall", 0, BAY, -T, 0, 0, 0.5, c, "concrete"); kc.colonly(pw, c)
    cn = kc.box("SM_Kon_Canopy_3x26", 0, 3.0, 0, 2.6, 2.4, 2.6, c, "metal"); kc.colonly(cn, c)
    s = kc.box("SM_Kon_Slab_2x2x03", 0, BAY, -BAY, 0, -SLAB, 0, c, "trim"); kc.colonly(s, c)


def build_shop(c):
    # shotengai shopfront: big glazing + recessed door, residence floors stack above
    wall("SM_Shop_Glass_2x3", c, R_H, opening=(0.2, 1.8, 0.4, 2.4), pane=(0.2, 1.8, 0.4, 2.4))
    wall("SM_Shop_Door_2x3", c, R_H, opening=(0.5, 1.5, 0.0, 2.2), pane=(0.5, 1.5, 0.0, 2.2))
    # flat awning projecting over the shopfront
    a = kc.combine("SM_Shop_Awning_2", [((0, BAY, -1.2, 0, 2.4, 2.5), "red"),
                                        ((0, BAY, -1.25, -1.15, 2.0, 2.5), "red")], c)
    kc.colonly(a, c)


def build_house_parts(c):
    g = kc.box("SM_House_Garage_2x3", 0, BAY, -T, 0, 0, R_H, c, "concrete")
    kc.cut(g, 0.1, 1.9, -T, 0, 0.0, 2.0)
    kc.box("SM_House_Garage_Door", 0.1, 1.9, -0.06, -0.04, 0.0, 2.0, c, "metal")
    wall_colonly("SM_House_Garage_2x3", c, BAY, R_H, (0.1, 1.9, 0.0, 2.0))


def main():
    kc.setup_units()
    kc.reset_scene([COLL])
    c = kc.get_coll(COLL)
    build_residential(c)
    build_konbini(c)
    build_shop(c)
    build_house_parts(c)
    vis = [o for o in c.objects if not o.name.endswith("-colonly")]
    print("WALLS kit: %d visual pieces, %d -colonly proxies"
          % (len(vis), len(c.objects) - len(vis)))
    if bpy.app.background:
        kc.save_blend(ROOT, "walls_kit.blend")


if __name__ == "__main__":
    main()
