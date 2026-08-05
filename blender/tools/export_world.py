#!/usr/bin/env python3
"""
export_world.py — export the master world-layout .blend into res:// as glTF for the baker.

Unlike export_kit.py (per-leaf .glb library), this exports the WHOLE open scene — every
district plate, arterial ribbon, harbor blockout, and (crucially) every named marker empty
with its Custom Properties as glTF `extras` — so the Java WorldBaker can turn region_/lane_/
intersection_/water_/slot_ nodes into gameplay nodes (BLENDER_CONVENTIONS.md I6a).

The one flag that matters vs. the kit export: `export_extras=True` (marker params ride along)
and empties are kept as nodes. Cameras/lights are dropped (preview-only).

RUN (with the master .blend open):
  blender --background world_master.blend --python tools/export_world.py
Then bake it: point BakeWorldMaster.tscn (or BakeWorld.tscn) at the emitted glTF and run it
(headless CLI / editor F6 / DebugHarness F5) — see BLENDER_CONVENTIONS "Three ways to trigger".

Also reused by tools/build_piece.sh for a per-district PIECE export (not just the master) —
optionally scoped to ONE top-level content collection via `--only <CollName>`, e.g.
`--only STREET_LOD_LOW` exports JUST the low-detail placeholder tier (see lib/lod_low.py) as
its own standalone glTF/`.tscn`, dropping STREET/MARKERS/MANUAL entirely so the two LOD tiers
bake to two independent scenes a runtime LOD switch can pick between
(WorldZoneMarker.instantiateLodLow/removeLodLow) instead of one merged scene:
  blender --background District_X.blend --python tools/export_world.py -- --only STREET_LOD_LOW out.gltf
"""
import bpy, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # blender
sys.path.insert(0, os.path.join(ROOT, "lib"))       # kit_common.bake_colonly_proxies
import kit_common as kc
# res:// world dir the baker reads from.
PROJECT = os.path.dirname(ROOT)                    # repo root (…/third-person-shooter)
OUT_DIR = os.path.join(PROJECT, "src", "main", "resources", "com", "openworld", "world")
OUT = os.path.join(OUT_DIR, "master", "World_master.gltf")

def _local_coll(name):
    """Local (non-library) collection by name — a district .blend with neighbours linked in
    (tools/link_neighbors.py) holds several same-named linked STREET collections, and a bare
    bpy.data.collections.get() may return one of those instead of the piece's own."""
    return next((c for c in bpy.data.collections
                 if c.name == name and c.library is None), None)


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
only_coll = None
if argv and argv[0] == "--only":
    only_coll = argv[1]
    argv = argv[2:]
if argv:
    OUT = argv[0]
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# Scoped export: keep ONLY `only_coll`'s objects among the piece's content collections (kit
# SOURCE collections are untouched here — the existing drop-sources pass below removes them
# regardless of scope). Runs on a throwaway load, same as the rest of this script.
if only_coll:
    _dropped_scope = 0
    for cname in ("STREET", "STREET_LOD_LOW", "MARKERS", "MANUAL"):
        if cname == only_coll:
            continue
        c = _local_coll(cname)
        if not c:
            continue
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
            _dropped_scope += 1
    print("--only %s: dropped %d objects from other content collections" % (only_coll, _dropped_scope))
    kept = _local_coll(only_coll)
    if not kept or not kept.objects:
        print("--only %s: collection missing or empty -- nothing to export" % only_coll)
        sys.exit(3)

# Realize Geometry-Nodes instances into real mesh BEFORE export. Blender's glTF exporter does NOT
# export bare GN 'Instance on Points' instances — they collapse to the source at origin — so every
# kc.instancer / kc.Batch layer (fill_frontage streetwall, road/sidewalk tiling, trees, poles) would
# pile up at center. Converting each GN-modified object to mesh bakes the placement into real,
# positioned geometry. (Runs on a throwaway load — the .blend keeps its GN; only the export is baked.)
_gn = [o for o in bpy.context.scene.objects
       if o.type == 'MESH' and any(m.type == 'NODES' for m in o.modifiers)]
if _gn:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in _gn:
        o.hide_set(False)
        o.hide_viewport = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = _gn[0]
    bpy.ops.object.convert(target='MESH')     # applies GN + realizes instances into real mesh
    print("realized %d GN-instanced layers into mesh for export" % len(_gn))

# Bake road_kit_authoring's collision proxies (-colonly) for every pad_/curb_/spine_ GN boundary
# object. 2026-08: this used to be baked LIVE in Blender during authoring/rebuild -- moved here
# because a -colonly proxy is invisible/has zero authoring-time value while being the single
# most expensive+crash-prone live rebuild operation (a to_mesh() depsgraph bake); same exact
# bake (kit_common.colonly_mesh_evaluated, unchanged), just deferred to when it's actually
# needed. Runs BEFORE export, same throwaway-load convention as the GN-realize step above --
# these proxies never touch the source .blend, they only exist for this export.
_colonly = kc.bake_colonly_proxies(bpy.context.scene.objects, bpy.context.scene.collection)
if _colonly:
    print("baked %d road_kit_authoring -colonly collision proxies for export" % len(_colonly))

# Drop kit SOURCE objects before export. load_kits appends every kit piece (SM_*, Road_*, Deco_*, +
# their -colonly proxies) at ORIGIN; hide_sources only hides them from RENDER, but the exporter takes
# the whole scene regardless — so they baked as a redundant geometry+collision PILE at the district
# centre that blocks movement. They're not needed in the export: mmesh visuals load from the res://
# kit glbs and towers are already realized above. Remove them from this throwaway load (the .blend is
# untouched). NOTE: this runs AFTER the GN realize so tower geometry (which referenced these sources)
# is already baked to mesh. LANDMARK_PREVIEW (tools/link_landmark_preview.py) is dropped for the same
# reason — a real district's STREET content linked in purely so opening world_master.blend shows it
# beside the harbor/ring; it must never reach the baked master (that district already streams in on
# its own via the normal region_ zone mechanism — this would double it up). LAYOUT (build_world.py's
# linked-district Piece_* Collection-Instances — every built piece library-linked at its world
# position — plus fallback Plate_* boxes for unbuilt districts) and HARBOR (its harbor/Haneda/bridge
# blockout boxes) are the master's own preview layer: each district already streams in on its own at
# runtime, so exporting the linked instances would double every piece (the glTF exporter expands
# Collection-Instances into real nodes) — every gameplay marker built alongside (region_/lane_/
# intersection_/slot_) already lands in MARKERS/LANDMARKS instead, so dropping these two collections
# loses no gameplay data. Left in, they baked hundreds of raw MeshInstance3D/StaticBody3D/
# ConcavePolygonShape3D nodes straight into World_master.tscn (never collapsed to MultiMesh — that
# only applies to `mmesh_`-tagged markers) — real geometry with no runtime purpose, heavy enough to
# make the Godot editor slow to open/render the baked master scene.
_dropped = 0
# NEIGHBOR_REF = tools/link_neighbors.py's linked neighbour-district/master references (the
# in-context seam-editing aid) — read-only Blender-side context that must never reach the game
# (each neighbour already streams in on its own; exporting it would double the geometry), same
# rationale as LANDMARK_PREVIEW on the master.
for cname in ("ROADS", "WALLS", "PROPS", "EXTRAS", "HIGHRISE", "INFRA", "LANDMARK_PREVIEW",
              "LAYOUT", "HARBOR", "ROADS_SRC", "NEIGHBOR_REF"):
    c = _local_coll(cname)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
            _dropped += 1
if _dropped:
    print("dropped %d kit source objects (kept out of the export)" % _dropped)

# view-layer objects only: bpy.data.objects also holds library-linked datablocks (neighbour
# refs), and select_set raises on an object that is not in the view layer. Snapshot the list and
# skip None entries: the removals above leave stale None slots in view_layer.objects until the
# next depsgraph update (Blender 5.x), and select_set on that None crashed the whole export.
for o in list(bpy.context.view_layer.objects):
    if o is not None:
        o.select_set(False)

bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format='GLTF_SEPARATE',   # text .gltf + .bin (inspectable; matches WorldExample.gltf)
    use_selection=False,             # whole scene
    export_apply=True,
    export_extras=True,              # Custom Properties -> glTF extras -> node metadata (the marker params)
    export_cameras=False,
    export_lights=False,
    export_yup=True,                 # Blender Z-up -> glTF Y-up (Godot importer expects this)
)
print("EXPORTED world master ->", OUT)
