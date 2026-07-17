#!/usr/bin/env python3
"""
build_rainbow_bridge_overlay.py -> overlays/Overlay_RainbowBridge.blend

The FIRST overlay blend (AUTHORING_GUIDE §5): a long-span connective structure authored in its
own .blend OUTSIDE any district, in WORLD coordinates, exported + baked to its own always-resident
.tscn (tools/build_overlay.sh) and instanced as a permanent node in hosts/WorldMaster.tscn — the
same residency model as the master's ARTDECK. Replaces the old preview-only HARBOR blockout
boxes (RainbowBridgeDeck/Rail/BridgePier_*, removed from build_world.build_harbor — HARBOR is
dropped at export, so this is the first Rainbow Bridge that actually ships).

Collections (regen-in-place, the build_district idiom):
  OVERLAY — generated here, wiped + rebuilt on every run:
            * the real PLATEAU span (buildings/PLATEAU_RainbowBridge.blend, 231 components
              JOINED into one visual mesh — separate objects would sit always-resident as
              hundreds of nodes), seated at the slot_rainbowbridge anchor.
            * the DRIVABLE CONTRACT: `-colonly` road deck at BR_DECK_Z + rail deck at BR_RAIL_Z
              (PLATEAU visuals carry no collision) + visual pier cylinders.
  MANUAL  — yours, PRESERVED across regens: hand-tune the span's seat/scale, add ramps,
            retaining walls, extra piers (with their own -colonly proxies) here.

The seat constants (BR_X, ISL_Y0, BR_DECK_Z, BR_RAIL_Z) come from lib/world_grid.py — the ONE
source build_world.py's harbor blockout + slot anchors use, so overlay and master agree.

NO traffic layer yet (lane_* routes over the deck join the arterial graph in Roads-v2 Phase 3);
the deck is walkable/drivable off the collision alone.

RUN:  blender --background --python overlays/build_rainbow_bridge_overlay.py
      (or the full loop: tools/build_overlay.sh rainbow_bridge)
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc
import plateau_import as pi
from world_grid import ISL_Y0, BR_X, BR_DECK_Z, BR_RAIL_Z, to_world

BLEND = os.path.join(HERE, "Overlay_RainbowBridge.blend")
LANDMARK_BLEND = os.path.join(ROOT, "buildings", "PLATEAU_RainbowBridge.blend")

# Span footprint: same seat the old HARBOR blockout used — from the island's south edge (ISL_Y0)
# out across the bay band, centreline at BR_X. The real extraction is ~1700x1100 m (collage
# world: final fit is MANUAL hand-tuning, per the extraction's own header).
SPAN_LEN = 260.0                                  # deck strip length (blockout-derived, v1)
DECK_HALF = 15.0                                  # road deck half-width
RAIL_HALF = 6.0                                   # rail deck half-width


def _clear_local_coll(name):
    """Wipe a LOCAL collection's objects (library-linked same-named collections untouched —
    the pipeline-wide local-only lookup rule)."""
    c = next((c for c in bpy.data.collections if c.name == name and c.library is None), None)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def build():
    kc.setup_units()
    coll = kc.get_coll("OVERLAY")
    kc.get_coll("MANUAL")                          # ensure the hand-tuning channel exists

    # ── real PLATEAU span, joined to one visual mesh ─────────────────────────────
    before = set(coll.objects)
    kc.place_landmark(coll, LANDMARK_BLEND, "RainbowBridge",
                      (to_world(BR_X), to_world(ISL_Y0 - SPAN_LEN / 2.0), 0.0))
    appended = [o for o in coll.objects if o not in before and o.type == 'MESH']
    if appended:
        # join needs the objects selectable in the view layer
        bpy.context.view_layer.update()
        joined = pi._join_all(appended, "Overlay_RainbowBridge_Span")
        print(f"RainbowBridge overlay: joined {len(appended)} components -> 1 visual mesh")
    else:
        print("WARNING: no components appended from", LANDMARK_BLEND)

    # ── drivable contract: colonly decks + visual piers (blockout-derived, v1) ──
    y0, y1 = ISL_Y0 - SPAN_LEN, ISL_Y0
    kc.box("Overlay_RB_Deck-colonly", to_world(BR_X - DECK_HALF), to_world(BR_X + DECK_HALF),
           to_world(y0), to_world(y1), BR_DECK_Z - 0.6, BR_DECK_Z, coll, "col")
    kc.box("Overlay_RB_Rail-colonly", to_world(BR_X - RAIL_HALF), to_world(BR_X + RAIL_HALF),
           to_world(y0), to_world(y1), BR_RAIL_Z - 0.4, BR_RAIL_Z, coll, "col")
    n_pier = 0
    y = ISL_Y0 - 20.0
    while y > y0:
        p = kc.cyl(f"Overlay_RB_Pier_{n_pier}", 4.0, -2.0, BR_DECK_Z - 0.6, coll, "metal")
        p.location = (to_world(BR_X), to_world(y), 0.0)
        n_pier += 1
        y -= 40.0
    print(f"RainbowBridge overlay: 2 colonly decks + {n_pier} piers at "
          f"({to_world(BR_X):.0f}, {to_world(y0):.0f}..{to_world(y1):.0f})")


if __name__ == "__main__":
    if os.path.exists(BLEND):
        bpy.ops.wm.open_mainfile(filepath=BLEND)   # regen-in-place: MANUAL survives
        _clear_local_coll("OVERLAY")
    else:
        import assemble as asm
        asm.wipe_scene()
    build()
    kc.save_blend(HERE, "Overlay_RainbowBridge.blend")
    print("OVERLAY=Overlay_RainbowBridge")
