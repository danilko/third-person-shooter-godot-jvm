#!/usr/bin/env python3
"""
build_highrise.py -> highrise_kit.blend

Tall-massing + Tokyo-signage kit on the same 2 m bay / 3 m floor module as the
residential walls, so towers stack with `place_side` exactly like low-rise. Pieces:

  * Curtain wall:  SM_HR_Curtain_2x3 (glazed module), SM_HR_Spandrel_2x3 (solid band),
                   SM_HR_Corner_2x3 (mullion corner post).
  * Massing:       SM_HR_Podium_2x4 (retail base, 4 m), SM_HR_Setback_Cap (parapet step),
                   SM_HR_RoofMech (rooftop plant), SM_HR_Heli (helipad), SM_HR_Balcony_Tower
                   (tower-mansion balcony band).
  * Signage:       SM_Sign_Media_4x6 (emissive media facade — Shibuya),
                   SM_Sign_Vertical_1x6 (vertical neon column — Akihabara),
                   SM_Sign_Stack_2x3 (stacked signboards — Kabukicho),
                   SM_Gate_Arch (Kabukicho gate).

Authored front on +Y, base z=0, START corner at x=0 (endpoint pivot — same as walls),
so a tower face is a `place_side` grid of these modules. Solid massing gets a
`-colonly`; glass curtain + emissive signs are thin and carry no collision.

RUN: blender --background --python tools/build_highrise.py
"""
import bpy, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

COLL = "HIGHRISE"
BAY = kc.R_BAY            # 2.0
H = kc.R_H               # 3.0  floor height
T = kc.T                 # 0.20 wall thickness


def build_curtain(c):
    # Glazed curtain module: thin glass pane + mullion frame, front on +Y (y=0 face)
    kc.combine("SM_HR_Curtain_2x3", [
        ((0.0, BAY, 0.0, T, 0.0, H), "glasscurtain"),                 # glass infill
        ((0.0, 0.08, 0.0, T, 0.0, H), "steel"),                       # left mullion
        ((BAY-0.08, BAY, 0.0, T, 0.0, H), "steel"),                   # right mullion
        ((0.0, BAY, 0.0, T, 0.0, 0.12), "steel"),                     # transom bottom
        ((0.0, BAY, 0.0, T, H-0.12, H), "steel"),                     # transom top
    ], c)
    # Spandrel band (solid floor-edge panel between glazing runs)
    kc.combine("SM_HR_Spandrel_2x3", [
        ((0.0, BAY, 0.0, T, 0.0, H), "glasscurtain"),
        ((0.0, BAY, 0.0, T+0.02, 0.0, 0.9), "steel"),                 # solid lower band
    ], c)
    # Corner mullion post (joins two faces)
    kc.box("SM_HR_Corner_2x3", 0.0, T, 0.0, T, 0.0, H, c, "steel")


def build_facades(c):
    """Facade-mix modules so towers aren't all-glass: opaque wall, punched window,
    full-glass panel, and a half-wall/half-glass mixed panel. Front +Y, START at x=0."""
    # Opaque spandrel/wall panel (concrete with a slim trim band)
    kc.combine("SM_HR_Wall_Solid_2x3", [
        ((0.0, BAY, 0.0, T, 0.0, H), "concrete"),
        ((0.0, BAY, 0.0, T+0.02, H-0.15, H), "steel"),                # floor-edge trim
    ], c)
    # Window-punched wall (solid wall with a recessed glazed opening)
    kc.combine("SM_HR_Wall_Window_2x3", [
        ((0.0, BAY, 0.0, T, 0.0, H), "concrete"),
        ((0.35, BAY-0.35, T*0.4, T, 0.8, H-0.5), "glass"),            # window
    ], c)
    # Full frameless glass panel (clean glazed unit)
    kc.combine("SM_HR_Panel_Glass_2x3", [
        ((0.0, BAY, 0.0, T*0.6, 0.0, H), "glass"),
    ], c)
    # Mixed panel: solid lower half + glazed upper half (shop/office split)
    kc.combine("SM_HR_Mixed_2x3", [
        ((0.0, BAY, 0.0, T, 0.0, H*0.45), "concrete"),                # solid base
        ((0.0, BAY, 0.0, T*0.7, H*0.45, H), "glasscurtain"),          # glazed top
        ((0.0, BAY, 0.0, T+0.02, H*0.45-0.06, H*0.45), "steel"),      # split trim
    ], c)
    # Side-mounted projecting BLADE sign (vertical, juts off a building flank)
    kc.combine("SM_Sign_Blade_1x3", [
        ((0.0, 0.12, 0.0, 1.2, 0.0, 3.0), "neon"),                    # blade face
        ((0.0, 0.12, 0.0, 0.2, 0.0, 3.0), "steel"),                   # wall bracket
    ], c)


def build_massing(c):
    # Retail podium: 2-bay wide x 4 m tall glazed base, raised storefront
    kc.combine("SM_HR_Podium_2x4", [
        ((0.0, BAY, 0.0, T, 0.0, 4.0), "glasscurtain"),
        ((0.0, BAY, 0.0, T+0.05, 0.0, 0.5), "concrete"),              # stall riser
        ((0.0, BAY, 0.0, T+0.05, 3.6, 4.0), "concrete"),              # fascia band
    ], c)
    # Setback parapet cap (a tower steps in; this caps the lower roof edge)
    kc.combine("SM_HR_Setback_Cap", [
        ((0.0, BAY, 0.0, 0.5, 0.0, 1.0), "concrete"),
        ((0.0, BAY, 0.0, 0.5, 1.0, 1.1), "steel"),                   # coping
    ], c)
    # Rooftop mechanical plant box (footprint sized to a bay grid)
    kc.combine("SM_HR_RoofMech", [
        ((-2.0, 2.0, -2.0, 2.0, 0.0, 2.2), "concrete"),
        ((-1.6, -0.4, -1.6, 1.6, 2.2, 3.0), "steel"),                # cooling units
        ((0.4, 1.6, -1.6, 1.6, 2.2, 3.0), "steel"),
    ], c)
    # Helipad (rooftop circle blockout + H mark)
    kc.combine("SM_HR_Heli", [
        ((-3.0, 3.0, -3.0, 3.0, 0.0, 0.2), "concrete"),
        ((-1.4, -0.9, -1.6, 1.6, 0.2, 0.24), "line_w"),
        ((0.9, 1.4, -1.6, 1.6, 0.2, 0.24), "line_w"),
        ((-1.4, 1.4, -0.25, 0.25, 0.2, 0.24), "line_w"),
    ], c)
    # Tower-mansion balcony band (deck + glass rail) for one bay
    kc.combine("SM_HR_Balcony_Tower", [
        ((0.0, BAY, T, 1.1, 0.0, 0.12), "concrete"),                 # deck cantilever
        ((0.0, BAY, 1.0, 1.1, 0.0, 1.05), "glass"),                  # glass balustrade
        ((0.0, 0.06, T, 1.1, 0.0, 1.05), "steel"),                   # rail posts
        ((BAY-0.06, BAY, T, 1.1, 0.0, 1.05), "steel"),
    ], c)


def build_signs(c):
    # Media facade screen — 4 m wide x 6 m tall emissive panel (Shibuya)
    kc.combine("SM_Sign_Media_4x6", [
        ((0.0, 4.0, 0.0, 0.15, 0.0, 6.0), "screen"),
        ((-0.1, 4.1, 0.0, 0.2, -0.15, 0.0), "steel"),               # bottom frame
        ((-0.1, 4.1, 0.0, 0.2, 6.0, 6.15), "steel"),                # top frame
    ], c)
    # Vertical neon column — 1 m wide x 6 m tall projecting sign (Akihabara)
    kc.combine("SM_Sign_Vertical_1x6", [
        ((0.0, 1.0, 0.0, 0.3, 0.0, 6.0), "neon"),
        ((0.0, 0.1, 0.0, 0.35, 0.0, 6.0), "steel"),                 # mounting spine
    ], c)
    # Stacked signboards — three offset boards (Kabukicho alley)
    kc.combine("SM_Sign_Stack_2x3", [
        ((0.0, 2.0, 0.0, 0.25, 0.0, 0.8), "neon"),
        ((0.2, 2.2, 0.0, 0.25, 1.0, 1.8), "screen"),
        ((-0.2, 1.8, 0.0, 0.25, 2.0, 2.8), "neon"),
        ((0.9, 1.1, 0.0, 0.3, 0.0, 2.8), "steel"),                  # post
    ], c)
    # District gate arch (Kabukicho) — spans a 7 m street
    kc.combine("SM_Gate_Arch", [
        ((-3.5, -3.2, -0.2, 0.2, 0.0, 5.0), "red"),                 # left post
        ((3.2, 3.5, -0.2, 0.2, 0.0, 5.0), "red"),                   # right post
        ((-3.5, 3.5, -0.3, 0.3, 5.0, 6.0), "red"),                  # beam
        ((-3.0, 3.0, -0.15, 0.15, 4.2, 4.9), "neon"),               # backlit sign band
    ], c)


SOLID = {
    "SM_HR_Spandrel_2x3", "SM_HR_Corner_2x3", "SM_HR_Podium_2x4",
    "SM_HR_Setback_Cap", "SM_HR_RoofMech", "SM_HR_Heli", "SM_HR_Balcony_Tower",
    "SM_Gate_Arch", "SM_HR_Wall_Solid_2x3", "SM_HR_Wall_Window_2x3", "SM_HR_Mixed_2x3",
}


def main():
    kc.setup_units()
    kc.reset_scene([COLL])
    c = kc.get_coll(COLL)
    build_curtain(c)
    build_facades(c)
    build_massing(c)
    build_signs(c)
    for name in list(SOLID):
        o = bpy.data.objects.get(name)
        if o:
            kc.colonly(o, c)
    vis = [o for o in c.objects if not o.name.endswith("-colonly")]
    print("HIGHRISE kit: %d visual pieces, %d -colonly proxies"
          % (len(vis), len(c.objects) - len(vis)))
    for o in sorted(vis, key=lambda o: o.name):
        bb = o.bound_box
        xs = [p[0] for p in bb]; ys = [p[1] for p in bb]; zs = [p[2] for p in bb]
        print("  %-22s X[%5.2f,%5.2f] Y[%5.2f,%5.2f] Z[%5.2f,%5.2f]"
              % (o.name, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    if bpy.app.background:
        kc.save_blend(ROOT, "highrise_kit.blend")


if __name__ == "__main__":
    main()
