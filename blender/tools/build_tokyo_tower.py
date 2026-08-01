#!/usr/bin/env python3
"""
build_tokyo_tower.py -- hand-modeled placeholder for Tokyo Tower, a building-tier asset
(assets/world_source/buildings/, same tier as build_example_building.py -> ExampleBuilding.blend).

WHY this exists instead of a PLATEAU extraction: Tokyo Tower is a tapering open-lattice steel
structure. PLATEAU's `bldg` module models solid footprint extrusions (LOD1/2), which has no
meaningful way to represent a lattice tower -- confirmed empirically this session (extracting the
"tokyotower" precinct found real surrounding buildings up to 94.8m, but nothing near the tower's
actual 332.9m). This script instead builds a simplified tapering-obelisk SILHOUETTE at the real
tower's real dimensions/colours/deck heights -- a placeholder good enough for scale/silhouette,
not a lattice-accurate model. Replace by hand later if a truss-accurate mesh is ever wanted.

Real reference dimensions (Tokyo Tower, public record):
  total height 332.9 m; base ~88 m square; Main Deck at 150 m; Top Deck at 249.6 m;
  International orange / white painted bands (aviation obstruction marking).

RUN:  blender --background --python build_tokyo_tower.py
Produces: assets/world_source/buildings/PLATEAU_TokyoTower.blend
"""
import bpy, os, sys

HERE_CODE = os.path.dirname(os.path.abspath(__file__))       # blender/buildings
BLENDER_SRC = os.path.dirname(HERE_CODE)                      # blender
HERE = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source", "buildings")  # data out dir
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import kit_common as kc

# ---- real reference dimensions (metres) ------------------------------------------------
BASE_HALF = 44.0       # base half-width (full base ~88m)
WAIST_Z = 90.0         # height where the legs have mostly converged
WAIST_HALF = 8.0
DECK_MAIN_Z = 150.0
DECK_MAIN_HALF_BEFORE = 6.0   # shaft half-width just below the main deck
DECK_MAIN_HALF = 15.0         # main deck platform half-width (overhangs the shaft)
DECK_TOP_Z = 249.6
DECK_TOP_HALF_BEFORE = 3.5
DECK_TOP_HALF = 8.0           # top deck platform half-width
ANTENNA_TOP_Z = 332.9
ANTENNA_HALF = 1.0

# Alternating international-orange / white bands (real tower's aviation-marking paint scheme).
BAND_HEIGHT = 24.0


def build():
    kc.setup_units()
    coll = kc.get_coll("TokyoTower")

    parts = []

    def taper_segment(z0, z1, h0, h1, matkey):
        # linear taper approximated by a handful of stacked sub-boxes (combine() only does
        # axis-aligned boxes, so a smooth taper is faceted into steps -- fine for a placeholder).
        steps = max(1, int((z1 - z0) / 6.0))
        for i in range(steps):
            a = i / steps
            b = (i + 1) / steps
            za, zb = z0 + (z1 - z0) * a, z0 + (z1 - z0) * b
            ha, hb = h0 + (h1 - h0) * a, h0 + (h1 - h0) * b
            h = (ha + hb) / 2.0   # one half-width per step (faceted, not a true linear taper)
            band_idx = int(za // BAND_HEIGHT)
            mk = "red" if band_idx % 2 == 0 else "line_w"
            parts.append(((-h, h, -h, h, za, zb), mk))

    # legs: base -> waist -> main deck shaft -> top deck shaft -> antenna base
    taper_segment(0.0, WAIST_Z, BASE_HALF, WAIST_HALF, "red")
    taper_segment(WAIST_Z, DECK_MAIN_Z, WAIST_HALF, DECK_MAIN_HALF_BEFORE, "red")
    taper_segment(DECK_MAIN_Z, DECK_TOP_Z, DECK_MAIN_HALF_BEFORE, DECK_TOP_HALF_BEFORE, "red")

    # main deck platform (disk approximated as a box -- placeholder)
    parts.append(((-DECK_MAIN_HALF, DECK_MAIN_HALF, -DECK_MAIN_HALF, DECK_MAIN_HALF,
                   DECK_MAIN_Z, DECK_MAIN_Z + 5.0), "glasscurtain"))
    # top deck platform
    parts.append(((-DECK_TOP_HALF, DECK_TOP_HALF, -DECK_TOP_HALF, DECK_TOP_HALF,
                   DECK_TOP_Z, DECK_TOP_Z + 4.0), "glasscurtain"))

    tower = kc.combine("PLATEAU_TokyoTower", parts, coll)

    # antenna mast (cylinder, separate object -- thin, no taper needed for a placeholder)
    kc.cyl("PLATEAU_TokyoTower_Antenna", ANTENNA_HALF, DECK_TOP_Z + 4.0, ANTENNA_TOP_Z, coll, "steel")

    # collision proxy spanning the widest (base) footprint up to the antenna tip
    kc.box("PLATEAU_TokyoTower-colonly", -BASE_HALF, BASE_HALF, -BASE_HALF, BASE_HALF,
           0.0, ANTENNA_TOP_Z, coll, "col")

    return tower


if __name__ == "__main__":
    kc.reset_scene(["TokyoTower"])
    build()
    kc.save_blend(HERE, "PLATEAU_TokyoTower.blend")
