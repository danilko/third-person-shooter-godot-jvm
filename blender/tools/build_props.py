#!/usr/bin/env python3
"""
build_props.py -> props_kit.blend

Street furniture & rooftop/forecourt props: utility pole, street light, vending
machine, guardrail, planter, traffic mirror, bollard, ATM, freezer, bins, water
tank, AC unit, konbini parking stall. Pivot: bottom CENTRE of footprint, base z=0
(drops onto the ground at a world point).

Collision: bulky props get a `<Name>-colonly` box proxy; thin/decorative bits
(rails, mirror disk, arms, glass) carry none.

RUN: blender --background --python tools/build_props.py
"""
import bpy, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

COLL = "PROPS"


def main():
    kc.setup_units()
    kc.reset_scene([COLL])
    c = kc.get_coll(COLL)

    # utility pole + crossarms
    pole = kc.cyl("SM_Env_Pole_8m", 0.09, 0, 8.0, c, "trim")
    kc.box("SM_Env_Pole_Arm1", -0.6, 0.6, -0.05, 0.05, 7.4, 7.5, c, "metal")
    kc.box("SM_Env_Pole_Arm2", -0.6, 0.6, -0.05, 0.05, 7.0, 7.1, c, "metal")
    kc.colonly(pole, c)

    # street light — tall COBRA, built as ONE mesh so the arm places with the pole when
    # instanced: boxy pole + long arm arching +X over the carriageway + lamp head at the
    # tip. ~7 m (taller than the 5.2 m signal). colonly = pole footprint only.
    COBRA = [
        ((-0.08, 0.08, -0.08, 0.08, 0.0, 7.0), "trim"),          # pole on the sidewalk
        ((0.0, 0.25, -0.05, 0.05, 6.70, 7.00), "metal"),         # short riser
        ((0.2, 4.6, -0.05, 0.05, 6.95, 7.05), "metal"),          # long cantilever arm (+X)
        ((4.4, 4.85, -0.16, 0.16, 6.78, 6.96), "accent"),        # lamp housing over the road
        ((4.48, 4.78, -0.13, 0.13, 6.70, 6.78), "line_y"),       # downward lens
    ]
    for nm in ("SM_Env_Light_Cobra", "SM_Env_Light_4m5"):        # 2nd = legacy alias
        kc.combine(nm, COBRA, c)
        kc.combine(nm + "-colonly", [((-0.08, 0.08, -0.08, 0.08, 0.0, 7.0), "col")], c)

    # vending machine
    vm = kc.box("SM_Env_Vendo_1x18", -0.5, 0.5, -0.4, 0.4, 0, 1.8, c, "accent")
    kc.box("SM_Env_Vendo_Glass", -0.4, 0.4, 0.40, 0.41, 0.9, 1.6, c, "glass")
    kc.colonly(vm, c)

    # guardrail (posts + 2 rails) — slim, proxy the whole span
    kc.box("SM_Env_Guard_PostL", -1.0, -0.94, -0.04, 0.04, 0, 0.8, c, "metal")
    kc.box("SM_Env_Guard_PostR", 0.94, 1.0, -0.04, 0.04, 0, 0.8, c, "metal")
    kc.box("SM_Env_Guard_Rail1", -1.0, 1.0, -0.03, 0.03, 0.72, 0.8, c, "metal")
    gr = kc.box("SM_Env_Guard_Rail2", -1.0, 1.0, -0.03, 0.03, 0.45, 0.51, c, "metal")
    kc.combine("SM_Env_Guard_PostL-colonly", [((-1.0, 1.0, -0.05, 0.05, 0, 0.8), "col")], c)

    # planter, traffic mirror
    pl = kc.box("SM_Env_Planter", -0.3, 0.3, -0.3, 0.3, 0, 0.6, c, "concrete"); kc.colonly(pl, c)
    kc.cyl("SM_Env_Mirror", 0.3, 2.0, 2.05, c, "metal", seg=24)
    kc.box("SM_Env_Mirror_Post", -0.04, 0.04, -0.04, 0.04, 0, 2.0, c, "trim")

    # forecourt / rooftop props
    atm = kc.box("SM_Kon_Prop_ATM", -0.35, 0.35, -0.35, 0.35, 0, 1.6, c, "metal"); kc.colonly(atm, c)
    fr = kc.box("SM_Kon_Prop_Freezer", -0.5, 0.5, -0.4, 0.4, 0, 1.2, c, "glass"); kc.colonly(fr, c)
    kc.cyl("SM_Kon_Prop_Bollard", 0.075, 0, 0.9, c, "accent")
    bn = kc.box("SM_Kon_Prop_Bins", -0.45, 0.45, -0.3, 0.3, 0, 1.0, c, "trim"); kc.colonly(bn, c)
    tk = kc.box("SM_Res_Prop_Tank", -0.6, 0.6, -0.6, 0.6, 0, 1.6, c, "metal"); kc.colonly(tk, c)
    ac = kc.box("SM_Res_Prop_AC", -0.4, 0.4, -0.15, 0.15, 0, 0.6, c, "metal"); kc.colonly(ac, c)

    # konbini parking stall (thin ground decal, corner pivot on grid)
    kc.box("SM_Kon_Stall_25x50", 0, 2.5, 0, 5.0, 0, 0.02, c, "asphalt")

    # traffic signal — Japanese HORIZONTAL signal (left-hand traffic), built as ONE mesh:
    # boxy pole on the kerb + cantilever arm reaching +X across the lanes + horizontal 3-lens
    # head (R/A/G) near the tip + a low pedestrian-signal box. Lenses are on the -Y face so
    # that placement (arm +X -> driver's right) leaves the head FACING the oncoming driver.
    # colonly = pole.
    kc.combine("SM_Env_TrafficLight", [
        ((-0.09, 0.09, -0.09, 0.09, 0.0, 5.2), "metal"),         # pole on the kerb
        ((0.0, 3.7, -0.05, 0.05, 5.05, 5.17), "metal"),          # cantilever arm (+X)
        ((2.55, 3.55, -0.16, 0.16, 4.62, 5.00), "trim"),         # horizontal head back box
        ((2.68, 2.98, -0.19, -0.16, 4.70, 4.94), "leaf"),        # green lens (-Y face)
        ((2.98, 3.28, -0.19, -0.16, 4.70, 4.94), "line_y"),      # amber lens
        ((3.28, 3.58, -0.19, -0.16, 4.70, 4.94), "red"),         # red lens
        ((-0.16, 0.16, -0.30, -0.16, 2.40, 3.00), "trim"),       # pedestrian-signal box (low)
    ], c)
    kc.combine("SM_Env_TrafficLight-colonly",
               [((-0.09, 0.09, -0.09, 0.09, 0.0, 5.2), "col")], c)

    # median twin-arm highway lamp — ONE mesh: tall boxy centre pole + symmetric arms ±X +
    # 2 lamp heads, for an expressway deck or an arterial median. colonly = pole.
    kc.combine("SM_Env_LampMedian",
        [((-0.11, 0.11, -0.11, 0.11, 0.0, 9.0), "trim"),         # centre pole
         ((-4.6, 4.6, -0.06, 0.06, 8.90, 9.00), "metal")]        # full cross arm ±X
      + [((s*4.35, s*4.75, -0.16, 0.16, 8.70, 8.92), "accent") for s in (-1, 1)]   # housings
      + [((s*4.43, s*4.67, -0.13, 0.13, 8.62, 8.70), "line_y") for s in (-1, 1)],  # lenses
        c)
    kc.combine("SM_Env_LampMedian-colonly",
               [((-0.11, 0.11, -0.11, 0.11, 0.0, 9.0), "col")], c)

    # overhead DIRECTION-SIGN TRUSS (Phase-2 demotion of the old lamp gantry): two posts +
    # cross-beam spanning ~17 m + two green direction-sign panels with a white legend bar
    # (front on -Y). Used over the expressway via assemble.place_corridor_signs. Posts colonly.
    kc.combine("SM_Env_LampGantry", [
        ((-8.6, -8.4, -0.10, 0.10, 0.0, 6.0), "metal"),          # left post
        ((8.4, 8.6, -0.10, 0.10, 0.0, 6.0), "metal"),            # right post
        ((-8.6, 8.6, -0.12, 0.12, 5.70, 5.96), "metal"),         # cross-beam
    ] + [((x0, x1, -0.05, 0.10, 4.40, 5.70), "leaf") for (x0, x1) in ((-7.6, -0.4), (0.4, 7.6))]
      + [((x0, x1, -0.07, -0.05, 4.60, 5.50), "line_w") for (x0, x1) in ((-6.6, -1.4), (1.4, 6.6))],
      c)                                                          # 2 green sign panels + legend
    kc.combine("SM_Env_LampGantry-colonly",
               [((-8.6, -8.4, -0.10, 0.10, 0.0, 6.0), "col"),
                ((8.4, 8.6, -0.10, 0.10, 0.0, 6.0), "col")], c)  # the two posts only

    vis = [o for o in c.objects if not o.name.endswith("-colonly")]
    print("PROPS kit: %d visual pieces, %d -colonly proxies"
          % (len(vis), len(c.objects) - len(vis)))
    if bpy.app.background:
        kc.save_blend(ROOT, "props_kit.blend")


if __name__ == "__main__":
    main()
