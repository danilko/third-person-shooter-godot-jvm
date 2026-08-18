"""graph_attrs.py -- Mesh-Graph road authoring: per-EDGE and per-VERTEX road attributes.

THE ARCHITECTURE THIS SERVES. A road network is ONE mesh object: vertices are nodes (bends /
intersections / termini), edges are road segments. Every property that used to live as an
`rka_*` custom property on a per-piece Collection (see `custom_props.py`) becomes a generic
Blender ATTRIBUTE on the edge domain of that one mesh, so Geometry Nodes can read it with a
Named Attribute node and generate the whole network in one modifier evaluation.

WHY bmesh LAYERS AND NOT `mesh.attributes.new()`. The authoring gesture is "select some edges in
Edit Mode and stamp values on them". While an object is in Edit Mode the evaluated `Mesh`
datablock's `attributes[...].data` is NOT the live data -- the BMesh owns it, and writes there
are silently discarded on the next Edit-Mode round trip. `bm.edges.layers.int/float` IS the same
CustomData the generic attribute system exposes (same name, same domain, same type), so stamping
through bmesh and stamping through `mesh.attributes` produce a byte-identical result -- one just
works in Edit Mode and the other does not. `ensure_mesh_attributes()` is the Object-Mode twin,
used by the init/repair path and by headless tooling.

WHY `median_type` IS STORED AS AN INT. Mesh attributes have no string/enum type that Geometry
Nodes can branch on (`bm.edges.layers.string` exists but GN cannot read it). The enum is an
authoring-time affordance only; on disk it is an INT, and `MEDIAN_*` below is the single owner of
that mapping -- GN compares against these same integers, so keep the numbers stable forever
(appending new kinds is safe, renumbering existing ones silently re-skins every authored road).

SIGN CONVENTION. `sidewalk_left_width` / `sidewalk_right_width` are LEFT and RIGHT of the edge's
own direction (v0 -> v1), which is the same driving frame `lane_profile.py`'s module docstring
fixes: +s is the forward-lane side. An edge's direction is therefore load-bearing authoring data,
not an implementation detail -- flipping an edge swaps its sidewalks. `RKA_OT_graph_validate`
reports edges whose direction disagrees with their neighbours' so this stays visible.

THE ATTRIBUTES ARE THE INPUT TO `lane_profile.ProfileSet`, NOT A SECOND CROSS-SECTION MODEL.
`profile_from_scalars(lanes, lanes_backward, lane_width, median_width, sw_l, sw_r)` already turns
exactly this scalar set into the ordered slot list every existing consumer reads. Anything that
needs real geometry offsets (the Python node solver, the exporter) must go through that function
rather than re-deriving `half_width = lanes * lane_width` locally -- that duplicated-formula
divergence is the documented root cause of the three 2026-08 defects, and a mesh graph makes it
easier to reintroduce, not harder.
"""
import bmesh
import bpy

#: Set on every object this addon generates (carrier, corners, node pads); its VALUE is the name
#: of the graph mesh it was generated from. Defined here, the lowest module, because both the
#: solver and every operator poll need it.
GENERATED_TAG = "rka_generated_for"


def graph_object(context):
    """The road-graph mesh an operator should act on, resolved from whatever is selected.

    WHY THIS IS NOT JUST `context.active_object`. The graph is an edge-only wireframe with no
    faces, and it sits UNDERNEATH the road surface it generates. Clicking the road in the viewport
    -- the only thing there is to click -- selects the generated carrier, not the graph. Every
    operator used to poll `active_object` directly and reject anything carrying `GENERATED_TAG`,
    so selecting the road greyed out Build, Solve, Auto Aux, Preview and Export while leaving Init
    and Validate (the two without that check) enabled. That reads exactly like "the addon is
    broken": the buttons are there, most of them are dead, and nothing says why.

    A generated object knows the graph it came from, so resolve it instead of refusing. Selecting
    the road now acts on the road's graph, which is what the click meant."""
    return graph_object_from(context.active_object)


def graph_object_from(obj):
    """The graph `obj` belongs to: itself, or the owner it names in `GENERATED_TAG`.

    Split out from `graph_object` so the resolution is testable without a context."""
    if obj is None or obj.type != 'MESH':
        return None
    owner = obj.get(GENERATED_TAG)
    if not owner:
        return obj
    src = bpy.data.objects.get(owner)
    return src if src is not None and src.type == 'MESH' else None


# ------------------------------------------------------------------ enum <-> int (stable forever)

MEDIAN_NONE = 0
MEDIAN_PAINTED = 1
MEDIAN_RAISED_CONCRETE = 2
MEDIAN_GRASS = 3

MEDIAN_TYPE_ITEMS = (
    ('NONE', "None", "Forward and backward blocks meet at the divide, no separator",
     MEDIAN_NONE),
    ('PAINTED', "Painted", "Flat painted separator -- drivable surface, no curb, no height",
     MEDIAN_PAINTED),
    ('RAISED_CONCRETE', "Raised Concrete", "Kerbed concrete island, lifted to curb_height",
     MEDIAN_RAISED_CONCRETE),
    ('GRASS', "Grass", "Planted island -- kerbed like concrete, different material",
     MEDIAN_GRASS),
)

MEDIAN_TYPE_TO_INT = {it[0]: it[3] for it in MEDIAN_TYPE_ITEMS}
MEDIAN_INT_TO_TYPE = {it[3]: it[0] for it in MEDIAN_TYPE_ITEMS}

#: Median kinds that are physically raised (curbed island) rather than paint on the asphalt.
#: GN branches on this, and the node solver excludes them from the drivable intersection patch.
MEDIAN_RAISED = (MEDIAN_RAISED_CONCRETE, MEDIAN_GRASS)

NODE_AUTO = 0
NODE_BEND = 1
NODE_INTERSECTION = 2
NODE_CAP = 3

#: A SPLIT/MERGE (motorway gore). Not an intersection: branches leave tangentially, nothing
#: stops, so it gets a gore nose instead of a pad. `road_graph_solve._gore_trunk` auto-detects it.
NODE_GORE = 4

#: Not a junction at all -- a shape point. The road passes straight through it as one continuous
#: ribbon: no trim, no pad, no corner. This is the explicit "this vertex is NOT an intersection"
#: switch. Grade separation (an overpass) is a different thing entirely and needs no flag: two
#: roads that cross without SHARING a vertex are simply not connected, which is what the mesh
#: graph already means. `graph_validate` flags the dangerous case -- edges that cross in XY at the
#: same height without a shared vertex, i.e. an intersection the author forgot to make.
NODE_NONE = 5

NODE_TYPE_ITEMS = (
    ('AUTO', "Auto", "Classify from valency: 1 = cap, 2 = bend/taper, >= 3 = intersection or "
     "gore (detected by tangency)", NODE_AUTO),
    ('BEND', "Bend", "Force a smoothed pass-through even at valency >= 3 (rare)", NODE_BEND),
    ('INTERSECTION', "Intersection", "Force a trimmed + patched junction even at valency 2 -- "
     "use where the cross-section CHANGES across the node (lane count, median), which a smooth "
     "fillet cannot represent", NODE_INTERSECTION),
    ('CAP', "Cap", "Terminate the road here with an end cap", NODE_CAP),
    ('GORE', "Gore (split/merge)", "Force a tangential split -- ramp nose, Y-fork, lane drop. "
     "No pad, no stop line", NODE_GORE),
    ('NONE', "Shape point (no junction)", "Bend the road here but build NO junction: no trim, no "
     "pad, and the ribbon stays continuous through it. This is how a vertex is 'not an "
     "intersection' -- use it for curve control points", NODE_NONE),
)

NODE_TYPE_TO_INT = {it[0]: it[3] for it in NODE_TYPE_ITEMS}
NODE_INT_TO_TYPE = {it[3]: it[0] for it in NODE_TYPE_ITEMS}

# ------------------------------------------------------------------------------ attribute tables
# (attribute name, storage type, default). The name IS the GN contract -- a Named Attribute node
# in the GN tree spells it exactly like this, so these strings are load-bearing.

#: Roles that resolve a mesh through `graph_assets`. Each contributes a `<role>_asset_idx` INT
#: edge attribute; -1 means "no asset -- build this band parametrically from its numbers".
ASSET_ROLES = ("curb", "median", "sidewalk", "pillar", "rail", "prop")

ASSET_IDX = tuple("%s_asset_idx" % r for r in ASSET_ROLES)

EDGE_ATTRS = (
    # ---- carriageway
    ("lanes_fwd", 'INT', 2),
    ("lanes_bwd", 'INT', 2),
    ("lane_width", 'FLOAT', 3.5),
    # WHICH NAMED ROAD THIS EDGE BELONGS TO. Pure authoring metadata -- nothing in the solver or
    # the node tree reads it. It exists because a mesh graph's one real ergonomic loss against the
    # old per-piece model was that a road stopped being a thing you could click: 1600 identical
    # edges with no way to say "this one street". `rka.graph_select_road` gives that back.
    ("road_id", 'INT', -1),
    # Outermost extra lanes that belong to a ramp/auxiliary movement rather than the through
    # road. They widen the ribbon on that side and are what a GORE node splits off, so a merge
    # taper is authored as a short edge whose aux count differs from its neighbour's.
    ("aux_lanes_left", 'INT', 0),
    ("aux_lanes_right", 'INT', 0),
    # How long the aux lane takes to open. It is measured back along the chain from the GORE the
    # lane serves and reaches full width there, because that is the end where the ramp actually
    # attaches; away from the gore it closes to nothing. A merge whose aux lane simply APPEARS at
    # full width is the thing this replaces -- a driver cannot enter a lane that starts as a wall.
    ("aux_taper_length", 'FLOAT', 60.0),
    # WHICH END OF ITS OWN LANE GROUP the aux lane occupies: 0 = the KERB end (an ordinary
    # nearside exit/entry), 1 = the MEDIAN end (a left-hand exit, the real thing motorways build
    # where a ramp leaves on the offside). Without this the model could only express a nearside
    # ramp, so a ramp attaching on the other side of its own carriageway had no lane it could
    # legally connect to -- the generator either put the lane in the wrong group (orphaning it) or
    # refused to build one at all and left the ramp meeting a through lane. It is per SIDE because
    # the two carriageways are independent.
    ("aux_median_left", 'INT', 0),
    ("aux_median_right", 'INT', 0),
    # ---- median
    ("median_type", 'INT', MEDIAN_NONE),
    ("median_width", 'FLOAT', 0.0),
    # ---- kerb + footway
    # Per-SIDE, per-EDGE, so one side of a road can drop its kerb entirely (a ramp shoulder, a
    # bridge edge, a road that only has a footway on the town side). 0 = no kerb on that side;
    # `curb_height` still sizes the one that remains. A footway is removed by setting its own
    # width to 0 -- there is no second "sidewalk on/off" flag to disagree with the width.
    ("curb_left_on", 'INT', 1),
    ("curb_right_on", 'INT', 1),
    ("sidewalk_left_width", 'FLOAT', 2.5),
    ("sidewalk_right_width", 'FLOAT', 2.5),
    ("curb_height", 'FLOAT', 0.15),
    # ---- structure below the road surface
    # Thickness of the solid deck swept under the carriageway. 0 = the road is on grade and needs
    # none; > 0 gives it an underside, which is what an elevated section rests on.
    ("deck_thickness", 'FLOAT', 0.0),
    # Metres between pillar instances. 0 = no pillars (on-grade road).
    ("pillar_spacing", 'FLOAT', 0.0),
    # THE ELEVATION THE SUPPORTS LAND ON. A pillar's height is not a property of the pillar -- it
    # is `deck soffit - ground`, and that varies along every ramp -- so the ground is authored and
    # the column is derived from it. Per EDGE because a viaduct crosses water, then a quay, then a
    # street, and each stretch lands somewhere different.
    ("ground_z", 'FLOAT', 0.0),
    # Side of the square column. Its height comes from `ground_z`; only the section is authored.
    ("pillar_width", 'FLOAT', 1.4),
    # Metres between tiled asset instances for the curb/rail/prop rows.
    ("asset_spacing", 'FLOAT', 5.0),
) + tuple((n, 'INT', -1) for n in ASSET_IDX)

#: Written by `graph_solve`, read by the node tree. Separated from the authored table so a
#: re-solve can overwrite them wholesale without ever touching authored values.
EDGE_SOLVED = (
    ("trim_start", 'FLOAT', 0.0),
    ("trim_end", 'FLOAT', 0.0),
    # Lateral geometry, ALL computed by `lane_profile` in `graph_solve.write_solution` and merely
    # copied by the node tree. This is the "nodes never do slot math" rule made structural: there
    # is no lane count anywhere in the node graph to disagree with Python about.
    ("paved_half", 'FLOAT', 7.0),      # half the carriageway width (the sweep radius)
    ("paved_shift", 'FLOAT', 0.0),     # lateral shift of the carriageway centre off the spine
    ("curb_off_left", 'FLOAT', 7.0),   # signed offset of the left kerb line
    ("curb_off_right", 'FLOAT', -7.0),
    ("walk_w_left", 'FLOAT', 0.0),     # footway width outboard of that kerb line
    ("walk_w_right", 'FLOAT', 0.0),
    ("median_half", 'FLOAT', 0.0),
)

VERT_ATTRS = (
    ("node_type", 'INT', NODE_AUTO),
    # -1 = "solve it". A positive value is an artist override and is never recomputed.
    ("node_radius", 'FLOAT', -1.0),
    ("fillet_radius", 'FLOAT', 4.0),
    # Movement permission, not geometry. 1 = traffic may cross this node (turns across opposing
    # streams are legal); 0 = approaches only connect to their own side, which is what a ramp
    # terminal and a divided-road service opening need. Consumed by the lane/traffic export, not
    # by the sweep -- geometry and permission are deliberately separate, so a full pad can still
    # be built where only some movements are legal.
    ("allow_cross", 'INT', 1),
)

VERT_SOLVED = (
    ("solved_radius", 'FLOAT', 0.0),
    ("solved_kind", 'INT', 0),
    ("valency", 'INT', 0),
)

#: Edge attributes the BRUSH does not carry. `road_id` is authoring metadata with its own operator
#: (`rka.graph_tag_road`, which allocates ids); stamping it from the brush would let one careless
#: assign merge every selected road into one id.
BRUSH_EXCLUDED = ("road_id",)

EDGE_ATTR_NAMES = tuple(n for n, _t, _d in EDGE_ATTRS if n not in BRUSH_EXCLUDED)
VERT_ATTR_NAMES = tuple(n for n, _t, _d in VERT_ATTRS)
EDGE_SOLVED_NAMES = tuple(n for n, _t, _d in EDGE_SOLVED)
VERT_SOLVED_NAMES = tuple(n for n, _t, _d in VERT_SOLVED)

#: Everything `ensure_*` creates -- authored plus solved, so the node tree never reads a missing
#: name (a Named Attribute node that misses yields 0, which builds an invisible road rather than
#: erroring).
ALL_EDGE = EDGE_ATTRS + EDGE_SOLVED
ALL_VERT = VERT_ATTRS + VERT_SOLVED


# ------------------------------------------------------------------------------- bmesh (Edit Mode)

def _ensure_layers(layers_owner, table, elements, fill_defaults=True):
    """Get-or-create every layer in `table` on one bmesh domain.

    A freshly created CustomData layer is zero-filled, which is the WRONG default for
    `lane_width` (3.5) or `node_radius` (-1 = auto) -- a zero-width lane is not a neutral starting
    value, it is a degenerate road. So a layer this call had to CREATE is seeded across every
    existing element; a layer that already existed is never touched."""
    out = {}
    for name, dtype, default in table:
        coll = layers_owner.int if dtype == 'INT' else layers_owner.float
        lay = coll.get(name)
        if lay is None:
            lay = coll.new(name)
            if fill_defaults:
                for el in elements:
                    el[lay] = default
        out[name] = lay
    return out


def ensure_edge_layers(bm, fill_defaults=True):
    return _ensure_layers(bm.edges.layers, ALL_EDGE, bm.edges, fill_defaults)


def ensure_vert_layers(bm, fill_defaults=True):
    return _ensure_layers(bm.verts.layers, ALL_VERT, bm.verts, fill_defaults)


def read_edge(bm, edge, layers=None):
    """This edge's road attributes as a plain dict (defaults for any layer that doesn't exist)."""
    layers = layers if layers is not None else ensure_edge_layers(bm, fill_defaults=False)
    return {n: edge[layers[n]] for n, _t, _d in ALL_EDGE if layers.get(n) is not None}


def read_vert(bm, vert, layers=None):
    layers = layers if layers is not None else ensure_vert_layers(bm, fill_defaults=False)
    return {n: vert[layers[n]] for n, _t, _d in ALL_VERT if layers.get(n) is not None}


# ---------------------------------------------------------------------------- mesh (Object Mode)

def ensure_mesh_attributes(mesh):
    """Object-Mode twin of `ensure_*_layers` -- used by init/repair and headless tooling.

    Same CustomData, reached through the generic attribute API instead of bmesh. Returns the list
    of attribute names this call had to create (so a caller can report "repaired 3 attributes")."""
    created = []
    for table, domain, count in ((ALL_EDGE, 'EDGE', len(mesh.edges)),
                                 (ALL_VERT, 'POINT', len(mesh.vertices))):
        for name, dtype, default in table:
            attr = mesh.attributes.get(name)
            if attr is not None and (attr.domain != domain or attr.data_type != dtype):
                # A name collision with a differently-shaped attribute would make GN read
                # garbage; drop and recreate rather than silently coexisting.
                mesh.attributes.remove(attr)
                attr = None
            if attr is None:
                attr = mesh.attributes.new(name=name, type=dtype, domain=domain)
                if count:
                    attr.data.foreach_set("value", [default] * count)
                created.append(name)
    mesh.update()
    return created


# -------------------------------------------------------------------------------------- settings

#: Dynamic-enum items must be kept alive on the Python side or Blender frees the strings it is
#: still displaying (the classic "garbled/crashing dynamic EnumProperty"). One cache per role.
_ENUM_CACHE = {}


def _role_items(role):
    def items(self, context):
        from . import graph_assets
        _ENUM_CACHE[role] = graph_assets.role_enum_items(role)
        return _ENUM_CACHE[role]
    return items


#: Brush fields whose stored value is an INT but whose UI is an enum of strings.
ENUM_BACKED = {"median_type": lambda v: MEDIAN_TYPE_TO_INT[v]}
ENUM_BACKED.update({n: int for n in ASSET_IDX})


def _overlay_modes():
    """Deferred so `graph_overlay` (which imports this module) is not needed at class-body time."""
    from . import graph_overlay
    return graph_overlay.MODES


class RKA_GraphSettings(bpy.types.PropertyGroup):
    """The 'brush': values `RKA_OT_graph_assign_edges` stamps onto the selection.

    Every field is paired with a `use_*` toggle so a stamp can carry ONE property (widen the lane
    on 40 edges) without also resetting the seven the artist never touched -- the alternative,
    stamping the whole record every time, quietly destroys hand-tuned values and is the reason a
    'brush' UI needs per-field masking at all."""

    auto_build: bpy.props.BoolProperty(
        name="Auto Build", default=True,
        description="Rebuild the road geometry immediately after an Assign. Without this, "
                    "stamping an attribute changes nothing you can see -- the authored values "
                    "live on the graph edges, and only a Build sweeps them into the mesh, which "
                    "makes a correct assign look like a no-op. Turn off for very large graphs")

    overlay_on: bpy.props.BoolProperty(
        name="Graph Overlay", default=True,
        description="Colour the graph's edges by their authored values in the viewport")
    overlay_mode: bpy.props.EnumProperty(
        name="Show", items=lambda self, ctx: _overlay_modes(), default=None)
    overlay_width: bpy.props.FloatProperty(name="Line Width", default=4.0, min=1.0, max=16.0)

    use_lanes_fwd: bpy.props.BoolProperty(name="", default=True)
    lanes_fwd: bpy.props.IntProperty(
        name="Lanes Fwd", default=2, min=0, soft_max=6,
        description="Travel lanes in the edge's own direction (v0 -> v1)")

    use_lanes_bwd: bpy.props.BoolProperty(name="", default=True)
    lanes_bwd: bpy.props.IntProperty(
        name="Lanes Bwd", default=2, min=0, soft_max=6,
        description="Travel lanes against the edge's direction. 0 = one-way road")

    use_lane_width: bpy.props.BoolProperty(name="", default=True)
    lane_width: bpy.props.FloatProperty(
        name="Lane Width", default=3.5, min=0.5, soft_max=6.0, unit='LENGTH')

    use_median_type: bpy.props.BoolProperty(name="", default=True)
    median_type: bpy.props.EnumProperty(
        name="Median", items=MEDIAN_TYPE_ITEMS, default='NONE',
        description="Stored on the mesh as an INT -- see graph_attrs.MEDIAN_* ")

    use_median_width: bpy.props.BoolProperty(name="", default=True)
    median_width: bpy.props.FloatProperty(
        name="Median Width", default=0.0, min=0.0, soft_max=12.0, unit='LENGTH')

    use_sidewalk_left_width: bpy.props.BoolProperty(name="", default=True)
    sidewalk_left_width: bpy.props.FloatProperty(
        name="Sidewalk L", default=2.5, min=0.0, soft_max=10.0, unit='LENGTH',
        description="Left of the edge direction -- flipping the edge swaps L and R")

    use_sidewalk_right_width: bpy.props.BoolProperty(name="", default=True)
    sidewalk_right_width: bpy.props.FloatProperty(
        name="Sidewalk R", default=2.5, min=0.0, soft_max=10.0, unit='LENGTH')

    use_curb_left_on: bpy.props.BoolProperty(name="", default=False)
    curb_left_on: bpy.props.IntProperty(
        name="Curb Left", default=1, min=0, max=1,
        description="0 removes the kerb from the left side of this edge entirely")

    use_curb_right_on: bpy.props.BoolProperty(name="", default=False)
    curb_right_on: bpy.props.IntProperty(name="Curb Right", default=1, min=0, max=1)

    use_curb_height: bpy.props.BoolProperty(name="", default=True)
    curb_height: bpy.props.FloatProperty(
        name="Curb Height", default=0.15, min=0.0, soft_max=0.5, unit='LENGTH')

    use_aux_lanes_left: bpy.props.BoolProperty(name="", default=False)
    aux_lanes_left: bpy.props.IntProperty(
        name="Aux Lanes L", default=0, min=0, soft_max=3,
        description="Outermost lanes on the left that belong to a ramp/auxiliary movement -- "
                    "what a GORE node splits off")

    use_aux_lanes_right: bpy.props.BoolProperty(name="", default=False)
    aux_lanes_right: bpy.props.IntProperty(name="Aux Lanes R", default=0, min=0, soft_max=3)

    use_aux_median_left: bpy.props.BoolProperty(name="", default=False)
    aux_median_left: bpy.props.IntProperty(
        name="Aux At Median L", default=0, min=0, max=1,
        description="0 = the left group's aux lane is at its KERB (ordinary nearside ramp), "
                    "1 = at its MEDIAN (a left-hand / offside ramp)")

    use_aux_median_right: bpy.props.BoolProperty(name="", default=False)
    aux_median_right: bpy.props.IntProperty(
        name="Aux At Median R", default=0, min=0, max=1,
        description="Same for the right group")

    use_aux_taper_length: bpy.props.BoolProperty(name="", default=False)
    aux_taper_length: bpy.props.FloatProperty(
        name="Aux Taper", default=60.0, min=0.0, soft_max=250.0, unit='LENGTH',
        description="Length over which an aux lane opens, measured back from the gore it serves. "
                    "0 = no taper (the lane appears at full width)")

    use_deck_thickness: bpy.props.BoolProperty(name="", default=False)
    deck_thickness: bpy.props.FloatProperty(
        name="Deck Thickness", default=0.0, min=0.0, soft_max=3.0, unit='LENGTH',
        description="Solid structure swept UNDER the carriageway. 0 = on grade, no underside")

    use_ground_z: bpy.props.BoolProperty(name="", default=False)
    ground_z: bpy.props.FloatProperty(
        name="Ground Z", default=0.0, soft_min=-50.0, soft_max=200.0, unit='LENGTH',
        description="Elevation the support columns land on. Column height is the deck soffit "
                    "minus this, resolved per point")

    use_pillar_width: bpy.props.BoolProperty(name="", default=False)
    pillar_width: bpy.props.FloatProperty(
        name="Pillar Width", default=1.4, min=0.1, soft_max=6.0, unit='LENGTH',
        description="Side of the square support column")

    use_pillar_spacing: bpy.props.BoolProperty(name="", default=False)
    pillar_spacing: bpy.props.FloatProperty(
        name="Pillar Spacing", default=0.0, min=0.0, soft_max=80.0, unit='LENGTH',
        description="Metres between support pillars. 0 = none")

    use_asset_spacing: bpy.props.BoolProperty(name="", default=False)
    asset_spacing: bpy.props.FloatProperty(
        name="Asset Spacing", default=5.0, min=0.1, soft_max=40.0, unit='LENGTH',
        description="Metres between tiled instances in the curb / rail / prop rows")

    # ---- asset palette pickers. Identifier is the INDEX as a string -- that is what gets
    # stamped -- with the asset's name as the label, so the artist never sees a bare number.
    use_curb_asset_idx: bpy.props.BoolProperty(name="", default=False)
    curb_asset_idx: bpy.props.EnumProperty(name="Curb Asset", items=_role_items("curb"))
    use_median_asset_idx: bpy.props.BoolProperty(name="", default=False)
    median_asset_idx: bpy.props.EnumProperty(name="Median Asset", items=_role_items("median"))
    use_sidewalk_asset_idx: bpy.props.BoolProperty(name="", default=False)
    sidewalk_asset_idx: bpy.props.EnumProperty(name="Sidewalk Asset",
                                               items=_role_items("sidewalk"))
    use_pillar_asset_idx: bpy.props.BoolProperty(name="", default=False)
    pillar_asset_idx: bpy.props.EnumProperty(name="Pillar Asset", items=_role_items("pillar"))
    use_rail_asset_idx: bpy.props.BoolProperty(name="", default=False)
    rail_asset_idx: bpy.props.EnumProperty(name="Rail Asset", items=_role_items("rail"))
    use_prop_asset_idx: bpy.props.BoolProperty(name="", default=False)
    prop_asset_idx: bpy.props.EnumProperty(name="Prop Asset", items=_role_items("prop"))

    # ---- vertex brush
    node_type: bpy.props.EnumProperty(name="Node Type", items=NODE_TYPE_ITEMS, default='AUTO')
    allow_cross: bpy.props.IntProperty(
        name="Allow Crossing", default=1, min=0, max=1,
        description="0 = approaches only connect to their own side of this node (ramp terminal, "
                    "divided-road opening). Affects the traffic/lane export, not the geometry")
    node_radius: bpy.props.FloatProperty(
        name="Node Radius", default=-1.0, min=-1.0, soft_max=30.0, unit='LENGTH',
        description="Setback each incoming road is trimmed by at this node. -1 = solve it from "
                    "the incident roads' widths and angles")
    fillet_radius: bpy.props.FloatProperty(
        name="Fillet Radius", default=4.0, min=0.0, soft_max=30.0, unit='LENGTH',
        description="Kerb corner radius: bend smoothing at valency 2, corner arc at a junction")


def brush_edge_values(s):
    """The brush's edge fields as an `{attr_name: value}` dict, MASKED by the `use_*` toggles.
    Storage-typed (median_type already an int), so callers write it straight into a layer."""
    out = {}
    for name in EDGE_ATTR_NAMES:
        if not getattr(s, "use_%s" % name):
            continue
        raw = getattr(s, name)
        conv = ENUM_BACKED.get(name)
        out[name] = conv(raw) if conv else raw
    return out


# ------------------------------------------------------------------------------------- operators

def auto_build(context, op):
    """Rebuild the geometry right after a stamp, so authoring has feedback.

    Imported LOCALLY on purpose: `graph_build` imports this module, so a module-level import would
    be a cycle. Runs IN Edit Mode -- `build_carrier` and `solve_object` both read the edit bmesh --
    which is the point, since bouncing through Object Mode would drop the artist's selection and
    the active-edge readout after every single assign.

    A build failure must not swallow the stamp: the attributes are already written, so this
    reports and returns rather than raising, and the artist can still press Build."""
    if not context.scene.rka_graph.auto_build:
        return
    obj = context.edit_object or context.active_object
    from . import graph_solve as gsolve
    if obj is None or obj.type != 'MESH' or gsolve.GENERATED_TAG in obj.keys():
        return
    from . import graph_build as gbuild
    try:
        gbuild.build_object(obj)
    except Exception as exc:                                  # noqa: BLE001 -- see docstring
        op.report({'WARNING'}, "Assigned, but the rebuild failed: %s" % exc)


def _edit_bmesh(context):
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        return None, None
    return obj, bmesh.from_edit_mesh(obj.data)


def reject_generated(context, op):
    """True (and reported) when Edit Mode is on a GENERATED object, where a stamp is meaningless.

    Build, Solve and the rest resolve a generated object back to its graph (`graph_object`), but a
    STAMP cannot be redirected that way -- it writes to the selected edges, and the selected edges
    of `<graph>_Carrier` are swept output that the next Build overwrites wholesale. Without this
    the operator happily reports "Assigned 8 field(s) to 214 edge(s)" and nothing whatsoever
    changes, which is indistinguishable from the addon being broken. Say where the edit has to
    happen instead."""
    obj = context.edit_object
    owner = obj.get(GENERATED_TAG) if obj is not None else None
    if not owner:
        return False
    op.report({'ERROR'}, "'%s' is generated from '%s' and is rebuilt from scratch -- leave Edit "
                         "Mode, select '%s' and stamp its edges instead"
              % (obj.name, owner, owner))
    return True


class RKA_OT_graph_init_attrs(bpy.types.Operator):
    """Create (or repair) every road attribute on this mesh, seeded with defaults.

    Run once on a fresh graph mesh so GN never reads a missing attribute -- a Named Attribute node
    pointed at a name that doesn't exist yields 0, which silently builds zero-width roads rather
    than erroring."""
    bl_idname = "rka.graph_init_attrs"
    bl_label = "Init / Repair Road Attributes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return graph_object(context) is not None

    def execute(self, context):
        obj = graph_object(context)
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        created = ensure_mesh_attributes(obj.data)
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, "Road attributes ready (%d created: %s)"
                    % (len(created), ", ".join(created) if created else "none"))
        return {'FINISHED'}


class RKA_OT_graph_assign_edges(bpy.types.Operator):
    """Stamp the brush's enabled fields onto every selected edge."""
    bl_idname = "rka.graph_assign_edges"
    bl_label = "Assign To Selected Edges"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        if reject_generated(context, self):
            return {'CANCELLED'}
        obj, bm = _edit_bmesh(context)
        layers = ensure_edge_layers(bm)
        values = brush_edge_values(context.scene.rka_graph)
        if not values:
            self.report({'WARNING'}, "No fields enabled -- nothing to assign")
            return {'CANCELLED'}
        n = 0
        for e in bm.edges:
            if not e.select or e.hide:
                continue
            for name, v in values.items():
                e[layers[name]] = v
            n += 1
        bmesh.update_edit_mesh(obj.data)
        if not n:
            self.report({'WARNING'}, "No edges selected")
            return {'CANCELLED'}
        auto_build(context, self)
        self.report({'INFO'}, "Assigned %d field(s) to %d edge(s)" % (len(values), n))
        return {'FINISHED'}


class RKA_OT_graph_assign_verts(bpy.types.Operator):
    """Stamp node_type / node_radius / fillet_radius onto every selected vertex."""
    bl_idname = "rka.graph_assign_verts"
    bl_label = "Assign To Selected Nodes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        if reject_generated(context, self):
            return {'CANCELLED'}
        obj, bm = _edit_bmesh(context)
        layers = ensure_vert_layers(bm)
        s = context.scene.rka_graph
        n = 0
        for v in bm.verts:
            if not v.select or v.hide:
                continue
            v[layers["node_type"]] = NODE_TYPE_TO_INT[s.node_type]
            v[layers["node_radius"]] = s.node_radius
            v[layers["fillet_radius"]] = s.fillet_radius
            v[layers["allow_cross"]] = s.allow_cross
            n += 1
        bmesh.update_edit_mesh(obj.data)
        if not n:
            self.report({'WARNING'}, "No vertices selected")
            return {'CANCELLED'}
        auto_build(context, self)
        self.report({'INFO'}, "Assigned node settings to %d vertex/vertices" % n)
        return {'FINISHED'}


class RKA_OT_graph_tag_road(bpy.types.Operator):
    """Give every selected edge the same road id, so it can be reselected as one road later."""
    bl_idname = "rka.graph_tag_road"
    bl_label = "Tag As Road"
    bl_options = {'REGISTER', 'UNDO'}

    road_id: bpy.props.IntProperty(
        name="Road Id", default=-1, min=-1,
        description="-1 = allocate the next free id")

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        obj, bm = _edit_bmesh(context)
        layers = ensure_edge_layers(bm)
        rid = self.road_id
        if rid < 0:
            used = {int(e[layers["road_id"]]) for e in bm.edges}
            rid = max([i for i in used if i >= 0] or [-1]) + 1
        n = 0
        for e in bm.edges:
            if e.select and not e.hide:
                e[layers["road_id"]] = rid
                n += 1
        bmesh.update_edit_mesh(obj.data)
        if not n:
            self.report({'WARNING'}, "No edges selected")
            return {'CANCELLED'}
        self.report({'INFO'}, "Tagged %d edge(s) as road %d" % (n, rid))
        return {'FINISHED'}


class RKA_OT_graph_select_road(bpy.types.Operator):
    """Select every edge sharing the active edge's road id, or its whole chain if it has none."""
    bl_idname = "rka.graph_select_road"
    bl_label = "Select Whole Road"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        obj, bm = _edit_bmesh(context)
        layers = ensure_edge_layers(bm)
        active = next((el for el in reversed(bm.select_history)
                       if isinstance(el, bmesh.types.BMEdge)), None)
        if active is None:
            active = next((e for e in bm.edges if e.select), None)
        if active is None:
            self.report({'WARNING'}, "Select an edge first")
            return {'CANCELLED'}

        rid = int(active[layers["road_id"]])
        if rid >= 0:
            picked = [e for e in bm.edges if int(e[layers["road_id"]]) == rid]
            what = "road %d" % rid
        else:
            # UNTAGGED FALLS BACK TO THE CHAIN, which is the same unit the builder trims and
            # sweeps as one ribbon -- so "select whole road" does something useful on a graph
            # nobody has tagged yet, which is every graph until someone starts tagging.
            from . import graph_solve as gsolve
            picked, what = [], "chain"
            for chain in gsolve.chains(bm):
                if any(eidx == active.index for eidx, _f in chain):
                    picked = [bm.edges[eidx] for eidx, _f in chain]
                    break
        for e in picked:
            e.select_set(True)
        bm.select_flush(True)
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, "Selected %d edge(s) of %s" % (len(picked), what))
        return {'FINISHED'}


class RKA_OT_graph_select_similar(bpy.types.Operator):
    """Select every edge whose cross-section matches the active edge's."""
    bl_idname = "rka.graph_select_similar"
    bl_label = "Select Similar Cross-Section"
    bl_options = {'REGISTER', 'UNDO'}

    #: The fields that make two edges "the same kind of road". Deliberately not every attribute:
    #: matching on deck thickness or asset indices would split one street into a dozen groups.
    KEYS = ("lanes_fwd", "lanes_bwd", "lane_width", "median_type", "median_width",
            "sidewalk_left_width", "sidewalk_right_width")

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        obj, bm = _edit_bmesh(context)
        layers = ensure_edge_layers(bm)
        active = next((el for el in reversed(bm.select_history)
                       if isinstance(el, bmesh.types.BMEdge)), None)
        if active is None:
            active = next((e for e in bm.edges if e.select), None)
        if active is None:
            self.report({'WARNING'}, "Select an edge first")
            return {'CANCELLED'}

        def key(e):
            return tuple(round(float(e[layers[k]]), 4) for k in self.KEYS)

        want, n = key(active), 0
        for e in bm.edges:
            if not e.hide and key(e) == want:
                e.select_set(True)
                n += 1
        bm.select_flush(True)
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, "Selected %d edge(s) with the same cross-section" % n)
        return {'FINISHED'}


class RKA_OT_graph_pick_edge(bpy.types.Operator):
    """Eyedropper: load the active (or first selected) edge's values back into the brush."""
    bl_idname = "rka.graph_pick_edge"
    bl_label = "Pick From Active Edge"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.edit_object is not None and context.edit_object.type == 'MESH'

    def execute(self, context):
        obj, bm = _edit_bmesh(context)
        edge = next((el for el in reversed(bm.select_history)
                     if isinstance(el, bmesh.types.BMEdge)), None)
        if edge is None:
            edge = next((e for e in bm.edges if e.select and not e.hide), None)
        if edge is None:
            self.report({'WARNING'}, "No edge selected")
            return {'CANCELLED'}
        vals = read_edge(bm, edge, ensure_edge_layers(bm))
        s = context.scene.rka_graph
        for name, v in vals.items():
            if name not in EDGE_ATTR_NAMES:
                continue          # solved attributes (trim_*) are outputs, not brush fields
            if name == "median_type":
                s.median_type = MEDIAN_INT_TO_TYPE.get(int(v), 'NONE')
            elif name in ASSET_IDX:
                # An index that no longer exists in the palette (asset removed) falls back to
                # "None" rather than raising -- the stamp is stale data, not a program error.
                try:
                    setattr(s, name, str(int(v)))
                except TypeError:
                    setattr(s, name, "-1")
            else:
                setattr(s, name, v)
        self.report({'INFO'}, "Picked edge attributes into the brush")
        return {'FINISHED'}


class RKA_OT_graph_validate(bpy.types.Operator):
    """Report the graph's topology and flag what would generate broken geometry.

    Checks, in the order they bite: missing attributes (GN reads 0 -> zero-width road), zero-length
    edges (no tangent -> the sweep frame is undefined), a valency histogram (so the node counts are
    visible before a heavy GN evaluation), and roads too WIDE for their own segment length -- an
    edge shorter than the setbacks its two end nodes demand trims to nothing and produces a hole,
    which is the single most common mesh-graph authoring failure."""
    bl_idname = "rka.graph_validate"
    bl_label = "Validate Road Graph"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return graph_object(context) is not None

    def execute(self, context):
        obj = graph_object(context)
        own_bm = obj.mode != 'EDIT'
        bm = bmesh.new() if own_bm else bmesh.from_edit_mesh(obj.data)
        if own_bm:
            bm.from_mesh(obj.data)
        try:
            missing = [n for n in EDGE_ATTR_NAMES if bm.edges.layers.int.get(n) is None
                       and bm.edges.layers.float.get(n) is None]
            layers = ensure_edge_layers(bm, fill_defaults=False)
            valency = {}
            for v in bm.verts:
                valency[len(v.link_edges)] = valency.get(len(v.link_edges), 0) + 1
            degenerate = [e.index for e in bm.edges if e.calc_length() < 1e-4]
            # Half-width of the widest thing this edge carries, used for the length sanity check.
            short = []
            for e in bm.edges:
                a = read_edge(bm, e, layers)
                half = (a.get("median_width", 0.0) * 0.5
                        + max(a.get("lanes_fwd", 0), a.get("lanes_bwd", 0))
                        * a.get("lane_width", 3.5)
                        + max(a.get("sidewalk_left_width", 0.0),
                              a.get("sidewalk_right_width", 0.0)))
                if e.calc_length() < half * 2.0 and e.calc_length() > 1e-4:
                    short.append((e.index, round(e.calc_length(), 2), round(half * 2.0, 2)))
            lines = ["valency: %s" % ", ".join("%d->%dx" % kv for kv in sorted(valency.items()))]
            if missing:
                lines.append("MISSING ATTRS: %s (run Init/Repair)" % ", ".join(missing))
            if degenerate:
                lines.append("ZERO-LENGTH edges: %s" % degenerate[:10])
            if short:
                lines.append("TOO SHORT for their own width (edge, len, needs): %s" % short[:10])
            # THE MOVEMENTS, not just the graph. A ramp fed across a motorway's median is a
            # perfectly well-formed graph -- nothing about the mesh is wrong -- so it can only be
            # caught by asking what the routes mean. Imported here rather than at module level:
            # `graph_export` imports this module, so a top-level import would be a cycle.
            try:
                from . import graph_export as gx
                bad_moves = gx.audit_movements(obj)
            except Exception as exc:                          # noqa: BLE001 -- report, never block
                bad_moves = ["movement audit failed: %s" % exc]
            lines.extend("ILLEGAL MOVEMENT: %s" % m for m in bad_moves[:10])
            for ln in lines:
                print("[rka.graph_validate] %s" % ln)
            self.report({'WARNING'} if (missing or degenerate or short or bad_moves)
                        else {'INFO'}, " | ".join(lines))
        finally:
            if own_bm:
                bm.free()
        return {'FINISHED'}


CLASSES = (RKA_GraphSettings, RKA_OT_graph_init_attrs, RKA_OT_graph_assign_edges,
           RKA_OT_graph_assign_verts, RKA_OT_graph_pick_edge, RKA_OT_graph_validate,
           RKA_OT_graph_tag_road, RKA_OT_graph_select_road, RKA_OT_graph_select_similar)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rka_graph = bpy.props.PointerProperty(type=RKA_GraphSettings)


def unregister():
    del bpy.types.Scene.rka_graph
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
