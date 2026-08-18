#!/usr/bin/env python3
"""
build_curb_kit.py -> kit/curb_kit.blend

One Blender Collection per repeatable curb/barrier/fence piece (the same "one
Collection per reusable piece" convention `tools/build_lane_kit.py` established for
`lane_kit.blend`), each holding one visual mesh object + a `<Name>-colonly` collision
proxy (`kit_common.colonly`). Linked (`link=True`) into an authoring file via the
road_kit_authoring addon's "Link Curb Kit Library" button (`ops_placement.RKA_OT_
link_curb_kit_library`), then repeated along a segment/intersection-corner curb line
via `kit_common.curb_asset_row()` (Curb Style = 'Asset' on any build operator).

WORKED-EXAMPLE PIVOT CONVENTION (read this before authoring a new piece — REQUIRED
for a piece to tile correctly along a curved curb):
  * Origin at the piece's own local (0, 0, 0) — its "start corner", same ENDPOINT
    pivot every wall/fence module in walls_kit.blend already uses.
  * Length runs along local +X. `curb_asset_row()` samples the boundary curve at
    ~`spacing` m intervals and applies a per-instance rotation that maps local +X to
    the world tangent direction at each sample point — a piece authored any other
    way will point along the wrong axis the instant it's dropped on a curve.
  * Front/outward face on local +Y. After the heading rotation above, local +Y ends
    up pointing 90 degrees left of the direction of travel. For a road with curbs on
    both sides, ONE side needs `rot_offset_deg=180` (curb_asset_row's own parameter)
    to keep an asymmetric piece's decorated face pointing away from the road on
    both sides — see Kit_Curb_FencePost_L1 below, an intentionally asymmetric piece
    included specifically to demonstrate this (Kit_Curb_JerseyBarrier_L2 is
    symmetric, so its flip is a visual no-op — build/place that one first to
    confirm the repeat-along-curve mechanism works before debugging asymmetry).
  * Base at z=0 (sits directly on the curb boundary curve's own Z, which already
    includes `lane_surface_z` — see ops_segment.py/ops_intersection.py).
  * Tiling: a piece's own local-X bounding-box length should equal (or evenly
    divide) the `spacing` passed to `curb_asset_row()` for seamless tiling — the
    same "instance length == grid size" contract `ops_combine.py`'s Tier-1 lane-tile
    seam marking already documents. Each piece's Collection stores this length as
    `rka_curb_asset_length` so the addon can read it back and suggest a matching
    spacing instead of the user having to measure it by hand.
  * Each piece's Collection also stores `rka_curb_asset_object` = the mesh
    object name that IS the piece (the same `mesh_name` this table already
    carries) — `ops_intersection._resolve_curb_asset` reads this back so a
    multi-part piece (pole + arm + head, e.g. Kit_Curb_StreetLamp_L1) resolves
    to its intended decorated mesh, not whichever helper object (support pole,
    collision proxy) happened to link into the collection first (2026-08,
    user-reported: street lamps/traffic lights "never show up" — they DID
    place geometry, just the bare pole, easy to miss against a scene).

RUN: blender --background --python tools/build_curb_kit.py
"""
import bpy, os, sys

HERE_CODE = os.path.dirname(os.path.abspath(__file__))       # blender/kit
BLENDER_SRC = os.path.dirname(HERE_CODE)                      # blender
HERE = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source", "kit")  # data out dir
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import kit_common as kc

# (new collection name, mesh object name, local-X length in meters)
PIECES = [
    ("Kit_Curb_JerseyBarrier_L2", "kit_curb_jersey_barrier_l2m", 2.0),
    ("Kit_Curb_FencePost_L1", "kit_curb_fence_post_l1m", 1.0),
    ("Kit_Median_YellowSeparator", "kit_median_yellow_separator_l2m", 2.0),
    ("Kit_Median_Island", "kit_median_island_l2m", 2.0),
    ("Kit_Curb_StreetLamp_L1", "kit_curb_street_lamp_l1m", 1.0),
    ("Kit_Curb_SidewalkTile_L2", "kit_curb_sidewalk_tile_l2m", 2.0),
    ("Kit_TrafficLight_L1", "kit_traffic_light_l1m", 1.0),
    ("Kit_TrafficGantry_L1", "kit_traffic_gantry_l1m", 9.0),
    # PIERS. The road graph's `pillar_spacing` has always driven a row of pillar instances, but
    # the kit shipped no `Kit_Pillar_*` collection, so `rka.graph_assets_link_kit` found nothing
    # for that role, every `pillar_asset_idx` stayed -1, and an elevated road showed its deck with
    # nothing holding it up (user-reported as "all the pillars seem to mess up").
    ("Kit_Pillar_Square_L2", "kit_pillar_square_l2m", 2.0),
    ("Kit_Pillar_Round_L2", "kit_pillar_round_l2m", 2.0),
]


def jersey_barrier(name, coll, length):
    """A simple trapezoidal jersey-barrier-like solid (two stacked boxes approximating the
    taper -- kit_common has no dedicated taper primitive; a real asset would sculpt this in
    bmesh). SYMMETRIC front/back, so the rot_offset_deg=180 flip on a road's far side is a
    visual no-op for this piece -- the simplest possible worked example."""
    base = kc.box(name, 0.0, length, -0.35, 0.35, 0.0, 0.5, coll, "concrete")
    kc.box(name + "_Cap", 0.0, length, -0.15, 0.15, 0.5, 0.8, coll, "concrete")
    kc.colonly(base, coll)
    return base


def fence_post(name, coll, length):
    """A single vertical post + one horizontal rail spanning `length` -- an ASYMMETRIC worked
    example (the rail sits only on local +Y, the piece's authored 'outward' face). Placed on
    the wrong curb side without a 180-degree rot_offset_deg flip, the rail would face the
    road instead of away from it."""
    kc.box(name + "_Post", 0.0, 0.1, 0.0, 0.1, 0.0, 1.1, coll, "wood")
    rail = kc.box(name, 0.0, length, 0.05, 0.1, 0.7, 0.85, coll, "wood")
    kc.colonly(rail, coll)
    return rail


def median_yellow_separator(name, coll, length):
    """A thin flat painted strip -- the 'single-mesh median' worked example for
    `ops_intersection.MEDIAN_STYLE_ITEMS`'s `ASSET_SINGLE` style (repeated along the median's own
    CENTERLINE, one row, replacing the old two-edge-wall styles). SYMMETRIC front/back (a flat
    strip has no 'outward face'), so `rot_offset_deg` is a no-op here same as the jersey barrier.
    No collision proxy -- flush paint on the pavement, nothing to drive INTO."""
    return kc.box(name, 0.0, length, -0.15, 0.15, 0.0, 0.02, coll, "line_y")


def median_island(name, coll, length):
    """A raised solid median island -- the 'barrier' worked example for `ASSET_SINGLE`, same
    trapezoidal-approximation technique as `jersey_barrier` (wider, so it visibly reads as a
    walkable/plantable island rather than a crash barrier). SYMMETRIC front/back."""
    base = kc.box(name, 0.0, length, -0.9, 0.9, 0.0, 0.15, coll, "concrete")
    kc.box(name + "_Cap", 0.0, length, -0.6, 0.6, 0.15, 0.35, coll, "concrete")
    kc.colonly(base, coll)
    return base


def street_lamp(name, coll, length):
    """A simple pole + cantilever arm + light head -- the street-lamp worked example for a
    segment/intersection's Prop Asset field (2026-08, user-reported: "the lamp/street lamp seem
    never show up... not able to use asset library for lamp" -- root cause was that NO lamp piece
    existed anywhere in `curb_kit.blend` at all, so there was nothing valid to reference). Base at
    z=0 (sits on the sidewalk/curb line), pole rises straight up, then the arm/head cantilever OUT
    on local +Y (an intentionally ASYMMETRIC piece, same convention as `fence_post` -- the arm must
    point away from the road, not into it, so it needs the R-side `rot_offset_deg=180` flip like
    any other asymmetric curb/prop asset)."""
    kc.cyl(name + "_Pole", 0.08, 0.0, 4.2, coll, "metal", seg=8)
    kc.box(name + "_Arm", -0.05, 0.05, 0.0, 1.0, 4.1, 4.2, coll, "metal")
    head = kc.box(name, -0.15, 0.15, 0.85, 1.15, 3.95, 4.15, coll, "neon")
    kc.colonly(bpy.data.objects.get(name + "_Pole"), coll)
    return head


def sidewalk_tile(name, coll, length):
    """A flat paving slab -- the sidewalk-asset worked example (2026-08, user-requested: sidewalks
    should be able to tile from the kit library the same way curbs/medians already can, instead of
    always being a procedurally swept BOX profile with its own material setup). SYMMETRIC (a flat
    slab has no 'outward face'). No collision proxy of its own -- a sidewalk is walkable, not a
    driving hazard; ground-plane collision under it is unaffected."""
    return kc.box(name, 0.0, length, -1.5, 1.5, 0.0, 0.1, coll, "concrete")


def traffic_light(name, coll, length):
    """A pole + signal head -- the traffic-light worked example for an intersection's per-arm
    Traffic Light toggle (2026-08, user-requested: "remove the lamp logic for intersection, but
    rather leave called 'traffic light'... will try to propose at the 45 degree outside of curb
    about 3 meter location"). Taller than `street_lamp` (5.0m vs 4.2m, real signal poles clear a
    truck) and a distinct "red" matkey head so it reads differently at a glance. SYMMETRIC (a
    plain box head has no 'outward face' to get wrong) -- `_populate_intersection_traffic_lights`
    places it once per enabled arm at a computed diagonal point, not tiled along a line, so there
    is no `rot_offset_deg` asymmetry concern the way `street_lamp`/`fence_post` have (its
    per-instance rotation only aims it along that diagonal, which any symmetric head looks fine
    from any angle)."""
    kc.cyl(name + "_Pole", 0.1, 0.0, 5.0, coll, "metal", seg=8)
    head = kc.box(name, -0.25, 0.25, -0.25, 0.25, 4.3, 4.9, coll, "red")
    kc.colonly(bpy.data.objects.get(name + "_Pole"), coll)
    return head


def traffic_gantry(name, coll, length):
    """A cantilever gantry -- vertical support pole + horizontal arm extending OUT OVER THE
    LANES, with a signal head hanging from the arm's far end. Used in place of a standalone
    `Kit_TrafficLight_L1` pole (`_populate_intersection_traffic_lights`'s 'Cantilever Rule') when
    the arm the signal is FOR has 2+ lanes in one direction -- the real-world reason a gantry
    exists at all (a pole-mounted signal at the curb is hard to see across multiple lanes; an
    overhead signal solves that).

    DELIBERATELY REVERSED pivot convention from every other curb/prop piece: the arm/head sit on
    local +Y just like `street_lamp`/`fence_post`, but here +Y means TOWARD the road (over the
    lanes), not away from it -- `_populate_intersection_traffic_lights`'s gantry placement rotates
    it 180 degrees from a standalone pole's own heading to compensate, documented at that call
    site. `length` (default 9.0m, unlike every OTHER piece's own physical-tiling length) is the
    arm's span -- long enough to clear ~2 lanes plus margin from a corner-mounted pole; a real
    per-road-width parametric span would need GN scaling or per-instance mesh generation, out of
    scope for this worked example (documented simplification, not a hidden bug)."""
    kc.cyl(name + "_Pole", 0.15, 0.0, 6.5, coll, "metal", seg=8)
    kc.box(name + "_Arm", -0.15, 0.15, 0.0, length, 6.3, 6.5, coll, "metal")
    head = kc.box(name, -0.25, 0.25, length - 0.6, length - 0.1, 5.6, 6.2, coll, "red")
    kc.colonly(bpy.data.objects.get(name + "_Pole"), coll)
    return head


#: How far a pier reaches below the road it carries. A pillar row is instanced AT THE ROAD
#: SURFACE -- the graph knows the deck's thickness but not the ground's height -- so the piece is
#: built HANGING DOWN from its own origin and is expected to bury its foot. Built the other way up
#: (anchored at the foot, growing +Z) every pier stands on top of the carriageway, which is what
#: the first version of these did.
PILLAR_DROP = 9.0


def pillar_square(name, coll, length):
    """A square pier with a head that spreads under the deck. Hangs from z=0 down to
    `-PILLAR_DROP`; see that constant for why it is anchored at the top."""
    shaft = kc.box(name, 0.0, length, -0.55, 0.55, -PILLAR_DROP, -0.4, coll, "concrete")
    kc.box(name + "_Head", -0.25, length + 0.25, -0.85, 0.85, -0.4, 0.0, coll, "concrete")
    kc.colonly(shaft, coll)
    return shaft


def pillar_round(name, coll, length):
    """A slimmer stepped pier -- the visual alternative to `pillar_square` for lighter viaducts.
    Stepped boxes rather than a true cylinder: `kit_common` has no cylinder primitive, and a
    three-step taper reads as round enough at the distance a pier is ever seen from."""
    shaft = kc.box(name, 0.15, length - 0.15, -0.45, 0.45, -PILLAR_DROP, -0.6, coll, "concrete")
    kc.box(name + "_Mid", 0.05, length - 0.05, -0.6, 0.6, -0.6, -0.3, coll, "concrete")
    kc.box(name + "_Head", -0.2, length + 0.2, -0.8, 0.8, -0.3, 0.0, coll, "concrete")
    kc.colonly(shaft, coll)
    return shaft


BUILDERS = {
    "kit_pillar_square_l2m": pillar_square,
    "kit_pillar_round_l2m": pillar_round,
    "kit_curb_jersey_barrier_l2m": jersey_barrier,
    "kit_curb_fence_post_l1m": fence_post,
    "kit_median_yellow_separator_l2m": median_yellow_separator,
    "kit_median_island_l2m": median_island,
    "kit_curb_street_lamp_l1m": street_lamp,
    "kit_curb_sidewalk_tile_l2m": sidewalk_tile,
    "kit_traffic_light_l1m": traffic_light,
    "kit_traffic_gantry_l1m": traffic_gantry,
}


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    kc.setup_units()
    scene_coll = bpy.context.scene.collection

    for coll_name, mesh_name, length in PIECES:
        coll = bpy.data.collections.new(coll_name)
        scene_coll.children.link(coll)
        BUILDERS[mesh_name](mesh_name, coll, length)
        coll["rka_curb_asset_length"] = length
        coll["rka_curb_asset_object"] = mesh_name

    # A pier is instanced at the ROAD SURFACE and must hang below it (see PILLAR_DROP). Built the
    # other way up it stands on the carriageway -- visible immediately, but only if someone looks,
    # so assert it here instead.
    for coll_name, _mesh, _len in PIECES:
        if not coll_name.startswith("Kit_Pillar_"):
            continue
        top = max((obj.matrix_world @ v.co).z
                  for obj in bpy.data.collections[coll_name].objects
                  if obj.type == 'MESH' for v in obj.data.vertices)
        if top > 1e-6:
            raise AssertionError("%s reaches to z=%.2f: a pier must hang BELOW its origin, or it "
                                 "is instanced standing on top of the road" % (coll_name, top))

    print("CURB_KIT: %d collections" % len(PIECES))
    if bpy.app.background:
        kc.save_blend(HERE, "curb_kit.blend")


if __name__ == "__main__":
    main()
