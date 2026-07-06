#!/usr/bin/env python3
"""
build_haneda_airport.py -- promotes the FULL real PLATEAU Haneda Airport extraction to its own
building-tier asset (same tier as buildings/PLATEAU_TokyoTower.blend), instead of being imported
inline into build_world.py's shared HARBOR collection every time the master rebuilds.

WHY this exists: same reason as build_rainbow_bridge.py -- build_harbor() used to call
plateau_import.import_components() directly against the master's own HARBOR collection, mixed in
with the hand-placed placeholder island/runway boxes, "scrambled together" with no clean
separation. This pulls the real terminal buildings + hangars/apron structures + real road/taxiway
polygons + connector bridges out into their own asset, appended once via kit_common.place_landmark()
-- the placeholder island footprint stays hand-modeled game-functional geometry in build_harbor()
(it's not PLATEAU data), everything ELSE real now comes from here.

Full extraction (plateau/data/haneda_full.json, anchor 139.7798E/35.5494N, 2500m radius -- covers
the ENTIRE airport, not just the terminal): 464 buildings, 85 roads, 57 bridges. Unlike the earlier
narrow 300m-radius/7-building pass, NO footprint-area outlier filtering is applied here -- the
"giant flat slab" components previously assumed to be misclassified junk (e.g. the 691x904m
idx=67 building) are, at this fuller extraction, revealed to plausibly be real apron/taxiway/hangar
complexes (Haneda's real apron areas legitimately span hundreds of metres) -- the biggest single
ROAD polygon alone is ~3230x2494m, matching the airport's own real overall footprint, i.e. the
extraction's own "road" classification is what carries the taxiway/apron pavement. Keeping
everything, unfiltered, is the deliberate choice here -- position/scale/cleanup happens by hand
afterward, not by guessing which large real feature is legitimate at extraction time.

RUN:  blender --background --python build_haneda_airport.py
Produces: assets/world_source/buildings/PLATEAU_HanedaTerminal.blend
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc
import plateau_import as pi

DATA_JSON = os.path.join(ROOT, "plateau", "data", "haneda_full.json")


def build():
    kc.setup_units()
    coll = kc.get_coll("HanedaTerminal")

    data = pi.load(DATA_JSON)
    ground_z = data.get("ground_reference_elevation_m") or 0.0

    b_count, b_tv, b_tf, b_skipped = pi.import_components(
        coll, data["buildings"], 0.0, 0.0, ground_z, 0.0, tag="Haneda_Bldg_Real")
    br_count, br_tv, br_tf, br_skipped = pi.import_components(
        coll, data["bridges"], 0.0, 0.0, ground_z, 0.0, tag="Haneda_Bridge_Real")

    r_count = 0
    for i, r in enumerate(data["roads"]):
        ring = r["rings"][0]
        xy = [(p[0], p[1]) for p in ring[:-1]] if ring[0] == ring[-1] else [(p[0], p[1]) for p in ring]
        obj = pi._extrude_polygon(f"Haneda_Road_Real_{i:03d}", coll, xy, -pi.ROAD_THICKNESS, 0.0, 0.0, 0.0)
        if obj:
            obj.data.materials.append(kc.mat("asphalt"))
            r_count += 1

    print(f"HanedaTerminal (full): {b_count} buildings, {br_count} bridges, {r_count} roads/taxiways "
          f"(anchor radius {data.get('radius_m')}m)")


if __name__ == "__main__":
    kc.reset_scene(["HanedaTerminal"])
    build()
    kc.save_blend(HERE, "PLATEAU_HanedaTerminal.blend")
