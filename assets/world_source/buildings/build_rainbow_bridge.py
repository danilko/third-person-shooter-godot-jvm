#!/usr/bin/env python3
"""
build_rainbow_bridge.py -- promotes the FULL real PLATEAU Rainbow Bridge extraction to its own
building-tier asset (same tier as buildings/PLATEAU_TokyoTower.blend), instead of being imported
inline into build_world.py's shared HARBOR collection every time the master rebuilds.

WHY a bigger re-extraction: the original 260m-radius/single-anchor extraction only reached ONE of
the bridge's two main towers (the anchor point sits right at that radius's edge relative to the
tower) -- a single 260m radius physically cannot span a ~800m real bridge. Re-extracted with a
900m radius from the same anchor (139.7631E/35.6367N): now captures BOTH towers (confirmed --
two real ~124m-tall components ~530m apart, matching the real main span almost exactly) plus much
more of the surrounding structure. 231 components kept (up from 130), overall extent ~1700x1100m.

NO footprint-area outlier filtering is applied here (unlike the original pass) -- per the same
reasoning as build_haneda_airport.py's full re-extraction: several of the largest components
(e.g. a matched symmetric pair at height 58.5m, ~529x208m each) are plausibly real deck/girder or
approach-viaduct structure, not junk, and this world is a compressed collage anyway (placement/
scale/cleanup happens by hand afterward, not by guessing at extraction time). The 90-degree
rotation to fit the game's N-S harbor gap is still baked in here so build_harbor() just appends
and translates like every other landmark.

RUN:  blender --background --python build_rainbow_bridge.py
Produces: assets/world_source/buildings/PLATEAU_RainbowBridge.blend
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc
import plateau_import as pi

DATA_JSON = os.path.join(ROOT, "plateau", "data", "rainbowbridge_full.json")


def build():
    kc.setup_units()
    coll = kc.get_coll("RainbowBridge")

    data = pi.load(DATA_JSON)
    ground_z = data.get("ground_reference_elevation_m") or 0.0
    count, tv, tf, skipped = pi.import_components(
        coll, data["bridges"], 0.0, 0.0, ground_z, 0.0,
        tag="RainbowBridge_Real", rot_deg=90.0)
    print(f"RainbowBridge (full): {count} components placed, {tv} verts / {tf} faces "
          f"(anchor radius {data.get('radius_m')}m)")


if __name__ == "__main__":
    kc.reset_scene(["RainbowBridge"])
    build()
    kc.save_blend(HERE, "PLATEAU_RainbowBridge.blend")
