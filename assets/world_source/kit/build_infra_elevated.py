#!/usr/bin/env python3
"""
build_infra_elevated.py -> infra_elevated_kit.blend

Multi-level Tokyo infrastructure on the 7 m grid (pieces centred on origin):
  * Elevated EXPRESSWAY (Shuto-style): deck + tall pillar + ramp + guardrail.
  * Elevated RAIL viaduct: concrete deck + pier, and a red-brick ARCH span (mAAch ecute
    — a shopfront fits in the arch, track runs on top).
  * TRACKS: normal gauge + Shinkansen slab track (the bullet-vs-normal split starts here).
  * TRAINS: normal commuter (loco + car) and Shinkansen (long-nose + car).
  * STATION: platform + canopy roof + stairs.

Piers are authored 0..<layer height> so a deck dropped at that height meets them
(LAYER_RAIL=8 m, LAYER_EXPS=11 m — see lib/road_network.py). assemble.lay_overlay()
places decks at the layer height and auto-drops these piers to the ground.

RUN: blender --background --python kit/build_infra_elevated.py
"""
import bpy, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc
import road_network as rn

COLL = "INFRA"
H = kc.CELL / 2.0                 # 3.5
RAIL_Z = rn.LAYER_RAIL            # 8.0
EXPS_Z = rn.LAYER_EXPS            # 11.0


def build_expressway(c):
    # 2-lane elevated deck (7x7) with guardrail lips on the X edges; top at z=0
    kc.combine("SM_Exps_Deck_2L", [
        ((-H, H, -H, H, -0.4, 0.0), "asphalt"),
        ((-0.075, 0.075, -H, H, 0.0, 0.02), "line_y"),          # centre line
        ((-H, -H+0.2, -H, H, 0.0, 0.7), "steel"),               # guardrail -X
        ((H-0.2, H, -H, H, 0.0, 0.7), "steel"),                 # guardrail +X
    ], c)
    kc.box("SM_Exps_Pillar", -0.7, 0.7, -0.7, 0.7, 0, EXPS_Z, c, "concrete")
    kc.box("SM_Exps_Guardrail", -H, H, -0.08, 0.08, 0, 0.7, c, "steel")
    # Ramps are NO LONGER wedge tiles — they are curvilinear RampCurves swept by the GN
    # curve->road engine (lib/kit_common.road_from_curve). The only ramp leaf still needed is
    # the UNIT pier: a 0..1 m column scaled per-point (scl.z = height) by instancer_scaled, so
    # one source gives the TAPERED column line dropped under any ramp curve.
    kc.box("SM_Exps_RampPier", -0.45, 0.45, -0.45, 0.45, 0.0, 1.0, c, "concrete")
    # H-PIER / portal-frame straddle bent — two legs + a cap beam, unit 0..1 so instancer_scaled
    # (scl.z = height) grows it like the RampPier. The straddle GAP spans the LOCAL X axis, so when
    # yawed to the ramp heading the legs land on EITHER side of the lower road/deck the ramp crosses
    # — a higher ramp's support never plants a column in the lower carriageway (the reported "single
    # piller stuck in the middle of the lower ramp"). SPAN=4 m gives an 8 m clear straddle (a 7 m road
    # + kerbs). Cap sits in the top 8 % so it stays just under the deck soffit at any scaled height.
    HLEG, HSPAN = 0.45, 4.0
    kc.combine("SM_Exps_HPier", [
        ((-HSPAN - HLEG, -HSPAN + HLEG, -HLEG, HLEG, 0.0, 0.92), "concrete"),   # left leg
        (( HSPAN - HLEG,  HSPAN + HLEG, -HLEG, HLEG, 0.0, 0.92), "concrete"),   # right leg
        ((-HSPAN - HLEG,  HSPAN + HLEG, -HLEG, HLEG, 0.92, 1.0), "concrete"),   # cap beam
    ], c)
    # explicit two-leg collision proxy — NOT a filled bounds box (that would wall off the straddled
    # road). Legs only; the gap stays drivable. Named `<leaf>-colonly` so the exporter picks it up.
    kc.combine("SM_Exps_HPier-colonly", [
        ((-HSPAN - HLEG, -HSPAN + HLEG, -HLEG, HLEG, 0.0, 1.0), "col"),
        (( HSPAN - HLEG,  HSPAN + HLEG, -HLEG, HLEG, 0.0, 1.0), "col"),
    ], c)
    # 4-lane two-way deck — now widened to ~16.7 m so it carries a SHOULDER + shy gap outboard of
    # the outermost lane, and the edge BARRIER (placed by assemble at rn.barrier_offset) stands on
    # the deck, never in a travel lane (the old 14 m deck put the wall 0.1 m inside the outer lane).
    L2  = kc.LANE / 2.0                    # 1.75  half lane
    LO  = 4 * kc.LANE / 2.0                # 7.00  outer lane edge (4 lanes)
    EDG = rn.barrier_offset(4)             # 8.35  deck edge = lane edge + shoulder + shy
    kc.combine("SM_Exps_Deck_4L", [
        ((-EDG, EDG, -H, H, -0.45, 0.0), "asphalt"),
        ((-0.40, 0.40, -H, H, 0.0, 0.15), "concrete"),          # jersey median: wide base
        ((-0.30, 0.30, -H, H, 0.15, 0.35), "concrete"),         #   sloped face (step)
        ((-0.15, 0.15, -H, H, 0.35, 0.85), "concrete"),         #   narrow top
        ((-LO - 0.075, -LO + 0.075, -H, H, 0.0, 0.02), "line_w"),   # outer lane / shoulder edge -X
        ((LO - 0.075, LO + 0.075, -H, H, 0.0, 0.02), "line_w"),     # outer lane / shoulder edge +X
        ((-L2 - 0.075, -L2 + 0.075, -H, H, 0.0, 0.02), "line_w"),   # interior lane lines
        ((L2 - 0.075, L2 + 0.075, -H, H, 0.0, 0.02), "line_w"),
        ((-EDG, -EDG + 0.2, -H, H, 0.0, 0.4), "steel"),         # low edge kerb/guard -X
        ((EDG - 0.2, EDG, -H, H, 0.0, 0.4), "steel"),           # low edge kerb/guard +X
    ], c)
    # GRID-TILED highway leaves: a straight elevated mainline is "a continuation of the grid size
    # for each lane" — compose N lanes from these 3.5x7 tiles at z=LAYER_EXPS (assemble.lay_corridor
    # tiled path / lay_deck_tiled), reserving the swept curve engine for curved ramps only.
    kc.combine("SM_Exps_Lane_7", [((-L2, L2, -H, H, -0.45, 0.0), "asphalt"),
        ((L2 - 0.075, L2 + 0.075, -H, H, 0.0, 0.02), "line_w")], c)      # lane + right edge line
    kc.combine("SM_Exps_Median_7", [((-0.40, 0.40, -H, H, -0.45, 0.15), "concrete"),
        ((-0.30, 0.30, -H, H, 0.15, 0.35), "concrete"),
        ((-0.15, 0.15, -H, H, 0.35, 0.85), "concrete")], c)             # jersey median tile
    SW = rn.SHOULDER_W + rn.SHY                                          # 1.35 shoulder + shy strip
    kc.combine("SM_Exps_Shoulder_7", [((-SW/2, SW/2, -H, H, -0.45, 0.0), "asphalt"),
        ((-SW/2 - 0.075, -SW/2 + 0.075, -H, H, 0.0, 0.02), "line_w")], c)
    # NOISE/SOUND BARRIER (Shuto-style): a 7 m solid acoustic screen ~3 m tall for the deck
    # edges; instanced along both edges by assemble.place_corridor_barriers (not baked in).
    kc.combine("SM_Exps_NoiseBarrier",
        [((-0.10, 0.10, -H, H, 0.0, 3.0), "concrete"),          # solid screen panel
         ((-0.16, 0.16, -H, H, 2.80, 3.05), "steel")]           # top cap
      + [((-0.16, 0.16, y-0.1, y+0.1, 0.0, 3.0), "steel")       # posts
         for y in (-H + 0.3, 0.0, H - 0.3)], c)


def _prism(name, verts, top_z, bot_z, coll, matkey):
    """A vertical prism: `verts`=[(x,y), ...] CCW plan polygon, extruded bot_z..top_z.
    Builds bottom + top + side faces. Origin stays at world (0,0,0)."""
    n = len(verts)
    vs = [(x, y, bot_z) for (x, y) in verts] + [(x, y, top_z) for (x, y) in verts]
    faces = [tuple(range(n - 1, -1, -1)),                       # bottom (CW)
             tuple(range(n, 2 * n))]                            # top
    for i in range(n):                                          # sides
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], faces); me.update(); kc.recalc_normals(me)
    obj = bpy.data.objects.new(name, me); coll.objects.link(obj)
    obj.data.materials.append(kc.mat(matkey))
    return obj


def _weld(keep, eaten):
    """Join `eaten` into `keep` as one leaf (deselect-all first so no stray object is
    swept in), keeping `keep`'s name."""
    bpy.ops.object.select_all(action='DESELECT')
    eaten.select_set(True); keep.select_set(True)
    bpy.context.view_layer.objects.active = keep
    bpy.ops.object.join()


def build_exps_connectors(c):
    """LANE-MERGE connector leaves (small, connectable pieces) for the new highway system:
      * SM_Exps_Deck_Taper — a 7 m deck tile that DROPS ONE LANE (3.5 m) across its length:
        full 4-lane width (-7..7) at the -Y end narrowing to 3 lanes (-7..3.5) at +Y, so two
        of them chain a 4->3->2 transition; rotate 180 to add a lane. Painted converging edge.
      * SM_Exps_Gore — the triangular GORE NOSE island where a ramp lane joins/leaves the
        mainline (the physical merge point): a low raised concrete wedge + chevron paint.
      * SM_Exps_Barrier_End — a sloped TERMINAL CAP so an opened noise barrier ends cleanly at
        the gore (top descends 3.0 -> 0.4 m) instead of a vertical face clipping the deck."""
    # --- taper deck: trapezoid asphalt slab, right (+X) edge pulls in by one lane ---
    WF, WN = 7.0, 3.5                                           # full / narrowed half-width
    plan = [(-WF, -H), (WF, -H), (WN, H), (-WF, H)]             # right edge tapers WF->WN
    _prism("SM_Exps_Deck_Taper", plan, 0.0, -0.45, c, "asphalt")
    tp = bpy.data.objects["SM_Exps_Deck_Taper"]
    # converging white edge line + jersey median, raised just above the slab
    line = kc.combine("SM_Exps_Deck_Taper_line", [
        ((-0.40, 0.40, -H, H, 0.0, 0.15), "concrete"),          # jersey median
    ], c)
    _weld(tp, line)                                            # median welded into the taper
    # --- gore nose: a low raised concrete island, 2 m wide narrowing to a point over 5 m ---
    g = _prism("SM_Exps_Gore", [(-1.0, -2.5), (1.0, -2.5), (0.0, 2.5)], 0.18, 0.0, c, "concrete")
    chev = kc.combine("SM_Exps_Gore_paint",
        [((-0.7 + 0.12*k, 0.7 - 0.12*k, -2.0 + 0.7*k, -1.7 + 0.7*k, 0.18, 0.20), "line_w")
         for k in range(5)], c)
    _weld(g, chev)                                             # chevrons welded into the gore
    # --- barrier end cap: thin wall (X), 1.5 m long (Y), top slopes 3.0 -> 0.4 m ---
    bm = bpy.data.meshes.new("SM_Exps_Barrier_End")
    bm.from_pydata(
        [(-0.10, -H + 5.5, 0.0), (0.10, -H + 5.5, 0.0), (0.10, H, 0.0), (-0.10, H, 0.0),
         (-0.10, -H + 5.5, 0.4), (0.10, -H + 5.5, 0.4), (0.10, H, 3.0), (-0.10, H, 3.0)],
        [], [(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
    bm.update(); kc.recalc_normals(bm)
    be = bpy.data.objects.new("SM_Exps_Barrier_End", bm); c.objects.link(be)
    be.data.materials.append(kc.mat("concrete"))


def build_ramp_segments(c):
    """MODULAR one-lane RAMP segments WITH SOLID WALLS (Tengenji / Hanshin entrance-ramp atom):
    a single 3.5 m lane bounded by concrete parapet walls on both edges. Array these along a
    descending straight (SM_Ramp_Grade_Wall_7, climbs CELL*MAX_GRADE over its length) or, later,
    along a gentle circular loop, to build a ramp from raised expressway down to the street — the
    'built from one lane segment' approach. Deck top at z=0 (grade tile rises along +Y).
    assemble.place_ramp_straight / place_ramp_loop array them."""
    LH = kc.LANE / 2.0                      # 1.75  half lane
    WW = 0.22                               # parapet wall thickness
    WH = 1.1                                # parapet wall height
    EW = LH + WW                            # 1.97  deck half-width (lane + wall footing)
    per = kc.CELL * rn.MAX_GRADE            # 0.56  rise per 7 m grade tile
    # FLAT walled lane tile
    kc.combine("SM_Ramp_Lane_Wall_7", [
        ((-EW, EW, -H, H, -0.45, 0.0), "asphalt"),          # deck slab (lane + wall footing)
        ((LH, EW, -H, H, 0.0, WH), "concrete"),             # +X parapet wall
        ((-EW, -LH, -H, H, 0.0, WH), "concrete"),           # -X parapet wall
    ], c)
    # SLOPED walled lane tile — deck + both walls rise `per` along +Y (walls ride the deck top)
    kc.wedge("SM_Ramp_Grade_Wall_7", [
        ((-EW, EW, -H, H, 0.0, per, 0.45), "asphalt"),      # sloped deck
        ((LH, EW, -H, H, WH, WH + per, WH), "concrete"),    # +X sloped parapet
        ((-EW, -LH, -H, H, WH, WH + per, WH), "concrete"),  # -X sloped parapet
    ], c)


def build_rail_viaduct(c):
    kc.combine("SM_Rail_Viaduct_Deck", [
        ((-2.5, 2.5, -H, H, -0.4, 0.0), "concrete"),
        ((-2.5, -2.3, -H, H, 0.0, 0.5), "concrete"),            # parapets
        ((2.3, 2.5, -H, H, 0.0, 0.5), "concrete"),
    ], c)
    # double-track deck (~9 m): two tracks side by side + centre divider + parapets
    kc.combine("SM_Rail_Viaduct_Deck_2T", [
        ((-4.5, 4.5, -H, H, -0.45, 0.0), "concrete"),
        ((-4.5, -4.3, -H, H, 0.0, 0.5), "concrete"),            # parapets
        ((4.3, 4.5, -H, H, 0.0, 0.5), "concrete"),
        ((-0.15, 0.15, -H, H, 0.0, 0.35), "concrete"),          # centre divider
    ], c)
    kc.box("SM_Rail_Pier", -0.6, 0.6, -0.6, 0.6, 0, RAIL_Z, c, "concrete")
    # red-brick arch bay (shop fits in the opening; track deck sits at z=RAIL_Z on top)
    kc.combine("SM_Rail_Arch_Brick", [
        ((-H, -2.4, -1.5, 1.5, 0, RAIL_Z), "brick"),            # left pier
        ((2.4, H, -1.5, 1.5, 0, RAIL_Z), "brick"),              # right pier
        ((-H, H, -1.5, 1.5, RAIL_Z-2.0, RAIL_Z), "brick"),      # spandrel over the bay
        ((-2.4, 2.4, -1.5, -1.3, 0, RAIL_Z-2.0), "brick"),      # arch back wall (thin)
    ], c)


def build_tracks(c):
    kc.combine("SM_Track_Std", [
        ((-1.2, 1.2, -H, H, 0.0, 0.08), "concrete"),            # ballast/slab
        ((-0.62, -0.5, -H, H, 0.08, 0.22), "rail"),
        ((0.5, 0.62, -H, H, 0.08, 0.22), "rail"),
    ], c)
    kc.combine("SM_Track_Shinkansen", [
        ((-1.7, 1.7, -H, H, 0.0, 0.10), "concrete"),            # wider slab track
        ((-0.79, -0.67, -H, H, 0.10, 0.24), "rail"),
        ((0.67, 0.79, -H, H, 0.10, 0.24), "rail"),
    ], c)


def _car(name, c, body_mat, stripe_mat, nose=False):
    """One ~6.6 m blockout rail car (length along Y). Window band + colour stripe."""
    L = 3.3
    parts = [
        ((-1.4, 1.4, -L, L, 0.2, 3.4), body_mat),               # body
        ((-1.42, 1.42, -L+0.3, L-0.3, 2.3, 3.0), "glass"),      # window band
        ((-1.4, 1.4, -L, L, 1.0, 1.3), stripe_mat),             # colour stripe
        ((-1.45, 1.45, -L, -L+0.1, 0.2, 3.4), "glass"),         # end window
    ]
    if nose:
        parts.append(((-1.0, 1.0, L-0.2, L+0.9, 0.4, 2.6), body_mat))   # tapered nose
    kc.combine(name, parts, c)


def build_trains(c):
    _car("SM_Train_Loco", c, "steel", "accent", nose=True)
    _car("SM_Train_Car", c, "steel", "accent")
    _car("SM_Shink_Nose", c, "shink", "accent", nose=True)
    _car("SM_Shink_Car", c, "shink", "accent")


def build_station(c):
    kc.combine("SM_Sta_Platform", [
        ((-1.6, 1.6, -H, H, 0.0, 1.1), "concrete"),
        ((-1.6, -1.4, -H, H, 1.1, 1.15), "line_y"),             # platform edge line
        ((1.4, 1.6, -H, H, 1.1, 1.15), "line_y"),
    ], c)
    kc.combine("SM_Sta_Roof", [
        ((-2.2, 2.2, -H, H, 3.0, 3.3), "steel"),                # canopy
        ((-2.0, -1.9, -H+0.3, -H+0.5, 1.1, 3.0), "steel"),      # posts
        ((1.9, 2.0, -H+0.3, -H+0.5, 1.1, 3.0), "steel"),
        ((-2.0, -1.9, H-0.5, H-0.3, 1.1, 3.0), "steel"),
        ((1.9, 2.0, H-0.5, H-0.3, 1.1, 3.0), "steel"),
    ], c)
    # stairs: 5 steps climbing toward +Y
    kc.combine("SM_Sta_Stairs", [((-1.4, 1.4, -H + k*1.2, -H + (k+1)*1.2, 0, (k+1)*0.55),
                                  "concrete") for k in range(5)], c)


SOLID = {
    "SM_Exps_Deck_2L", "SM_Exps_Deck_4L", "SM_Exps_Deck_Taper", "SM_Exps_Gore",
    "SM_Exps_Barrier_End", "SM_Exps_Pillar",
    "SM_Exps_RampPier", "SM_Exps_Guardrail", "SM_Exps_NoiseBarrier",
    "SM_Exps_Lane_7", "SM_Exps_Median_7", "SM_Exps_Shoulder_7",
    "SM_Ramp_Lane_Wall_7", "SM_Ramp_Grade_Wall_7",
    "SM_Rail_Viaduct_Deck", "SM_Rail_Viaduct_Deck_2T",
    "SM_Rail_Pier", "SM_Rail_Arch_Brick",
    "SM_Train_Loco", "SM_Train_Car", "SM_Shink_Nose", "SM_Shink_Car",
    "SM_Sta_Platform", "SM_Sta_Roof", "SM_Sta_Stairs",
}


def main():
    kc.setup_units()
    kc.reset_scene([COLL])
    c = kc.get_coll(COLL)
    build_expressway(c)
    build_exps_connectors(c)
    build_ramp_segments(c)
    build_rail_viaduct(c)
    build_tracks(c)
    build_trains(c)
    build_station(c)
    for name in list(SOLID):
        o = bpy.data.objects.get(name)
        if o:
            kc.colonly(o, c)
    vis = [o for o in c.objects if not o.name.endswith("-colonly")]
    print("INFRA kit: %d visual pieces, %d -colonly proxies"
          % (len(vis), len(c.objects) - len(vis)))
    for o in sorted(vis, key=lambda o: o.name):
        bb = o.bound_box; zs = [p[2] for p in bb]
        print("  %-24s Ztop=%.2f" % (o.name, max(zs)))
    if bpy.app.background:
        kc.save_blend(ROOT, "infra_elevated_kit.blend")


if __name__ == "__main__":
    main()
