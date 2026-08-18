"""road_stack.py -- a road piece as ONE object carrying a LAYERED MODIFIER STACK, all layers
driven off the same spine curve.

    spine object (MESH polyline + per-vertex attributes)
      [Spine]        mesh -> curve, and compute the lateral frame ONCE
      [Pavement]     asymmetric swept carriageway
      [Curb L] [Curb R]        offset copies of the same curve, swept with a 2D profile object
      [Sidewalk L] [Sidewalk R]
      [Median]
      [CurbAssets L/R] [Props L/R] [Streetlights]   offset copies, tiled with an asset object
      [Support]      piers/embankment underneath, raycast against the terrain
      [Finish]       drop the carrier curve, leave the mesh

WHY A STACK, AND WHY IT REPLACES THE SIBLING-OBJECT MODEL. Until now a segment was a Collection
of SIBLING OBJECTS -- `spine_X`, `curb_X_L/R`, `sidewalk_X_*`, `median_X`, `mark_X_*`, prop rows
-- each built by its own Python call from its own offset point list, and each DELETED AND
RECREATED whenever anything changed. A whole category of machinery exists only to manage that:
`clear_generated_mesh_objects`, the `_rka_touched` tagging, `ops_intersection.
sweep_untouched_boundaries`, the update-in-place conventions on `swept_wall`/`flat_ribbon`, and
most of `rebuild_segment_gn_in_place`. None of it is about roads; all of it is about Python owning
object lifetimes. A modifier stack has no object-lifetime problem at all: every layer re-derives
live from the spine on every dependency-graph update, so dragging one control point moves the
pavement, both curbs, both sidewalks, the median, every streetlight and every pier together.

It is also the only structure in which the parts genuinely ARE one operation. Curb, sidewalk,
median and barrier already all go through the same `Curve to Mesh with a caller-supplied 2D
profile object` -- they differ ONLY in lateral offset, vertical offset and which profile. So they
are one group instantiated N times, not N node trees. Same for every asset row (curb pieces,
streetlights, props): one `tile an object along the curve` group, different offsets and objects.

THE DISCIPLINE THAT KEEPS THIS HONEST. Every lateral offset in the stack is a number computed by
`lane_profile.slot_offset` in Python and handed to the layer. Nodes NEVER re-derive where a slot
is. That rule is the whole point: the three 2026-08 defects all came from two consumers deriving
the same cross-section with different conventions, and re-implementing slot math inside the node
tree would recreate exactly that bug where it is far harder to see. The node graph knows how to
OFFSET and SWEEP; it does not know what a lane is.

THE LATERAL FRAME IS COMPUTED ONCE, IN `GN_SpineCurve`, and stored as the point attribute
`rka_lat` = `normalize(cross(+Z, tangent))`. Layers read that attribute rather than taking their
own tangent, for two reasons: an offset curve's own tangent differs slightly from the spine's on
any bend (so per-layer tangents would fan out instead of staying parallel), and one stored vector
cannot disagree with itself. Its sign matches `intersection_kit.offset_spine_line(+x)` under
`traffic_side='LEFT'` -- i.e. `+rka_lat` is the FORWARD-lane side, the same `+s` direction
`lane_profile` measures in. The `traffic_side` flip stays in Python, where
`intersection_kit.lane_perp` already owns it; a layer receives a plain signed distance.

WHY THE CARRIER IS A MESH, NOT A CURVE. A legacy `bpy.types.Curve` datablock has no
`.attributes` collection at all (verified: `AttributeError`), so it can hold exactly two
per-point floats -- the built-in `radius` and `tilt` -- and nothing else. A Mesh can hold as many
named per-vertex attributes as we like, and `Mesh to Curve` preserves them into the curve domain.
That is what makes the cross-section PER-POINT data instead of per-piece constants: a ramp
opening, a lane dropping, a median widening are all just attribute values varying along the
spine, rather than the separate collections `ops_split.py` had to emit. A branching road is
likewise legal -- several edge chains in one mesh become several splines, all swept by one stack.
"""
import bpy

import kit_common as kc

# Per-vertex attributes. `rka_lat` is the only one the NODES produce (a pure frame vector, no
# cross-section meaning); every other attribute is written by Python from `lane_profile`, because
# nodes must never derive where a slot is -- see "THE DISCIPLINE" above.
ATTR_LAT = "rka_lat"          # FLOAT_VECTOR, unit lateral vector on the +s side (GN_SpineCurve)
ATTR_HALFW = "rka_halfw"      # FLOAT, half the paved width at this point = (neg + pos) / 2
ATTR_SHIFT = "rka_shift"      # FLOAT, lateral shift of the paved centre off the spine
                              #        = (pos - neg) / 2; nonzero exactly when the carriageway is
                              #        asymmetric, which is what a one-way road or an opening ramp
                              #        is. This is `intersection_kit.sweep_radius_and_shift`,
                              #        per point instead of per piece.

_UP = (0.0, 0.0, 1.0)


def _mirror_inputs(dst_ifc, src_ng, skip_geometry=True):
    """Copy `src_ng`'s INPUT sockets onto `dst_ifc`, returning `{name: (src_id, dst_id)}`.

    This is what lets `wrap_layer` turn ANY existing "curve in -> mesh out" node group into a
    stack layer without hand-transcribing its interface: `GN_RoadSupport`'s dozen pier/fill
    settings, `GN_CurbAssetRow`'s spacing/rotation, a future barrier group's height -- all appear
    on the wrapper automatically and stay in step if the inner group gains an input."""
    mapping = {}
    first_geo_skipped = not skip_geometry
    for item in src_ng.interface.items_tree:
        if getattr(item, "item_type", "SOCKET") != "SOCKET" or item.in_out != "INPUT":
            continue
        if item.socket_type == "NodeSocketGeometry" and not first_geo_skipped:
            first_geo_skipped = True
            continue
        s = dst_ifc.new_socket(item.name, in_out="INPUT", socket_type=item.socket_type)
        if hasattr(item, "default_value") and hasattr(s, "default_value"):
            try:
                s.default_value = item.default_value
            except (TypeError, ValueError):
                pass
        mapping[item.name] = (item.identifier, s.identifier)
    return mapping


def make_spine_curve_group():
    """GN_SpineCurve -- the stack's first modifier. Converts the MESH carrier to a curve (which
    preserves every per-vertex attribute into the curve's point domain) and stores the lateral
    frame `rka_lat` on it, once, for every layer above to share.

    Nothing else happens here on purpose: this layer emits a CURVE and no mesh, so the geometry
    flowing up the stack starts as pure curve and each layer joins its own mesh to it. The curve
    component rides along the whole way (a Blender geometry holds mesh/curve/instance components
    side by side) and is dropped by `GN_StackFinish` at the top -- that is how every layer can
    still see the spine after earlier layers have added meshes."""
    ng = bpy.data.node_groups.get("GN_SpineCurve")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("GN_SpineCurve", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-700, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (700, 0)
    L = ng.links.new

    m2c = ng.nodes.new("GeometryNodeMeshToCurve"); m2c.location = (-460, 0)
    L(nin.outputs["Geometry"], m2c.inputs["Mesh"])

    # A carrier that is ALREADY a curve (legacy content, built before the mesh carrier) has to
    # pass through too -- phases 1-5 read both types, see the plan. This is a JOIN rather than a
    # Switch on purpose: `GeometryNodeSwitch` has no GEOMETRY mode in this Blender (verified --
    # its `input_type` enum is FLOAT/INT/BOOLEAN/VECTOR/RGBA/ROTATION/MATRIX/STRING/MENU/SHADER/
    # OBJECT/IMAGE), and a join needs no predicate anyway: exactly one branch is ever non-empty.
    # A mesh carrier yields nothing from Separate Components' Curve output, and a curve carrier
    # yields nothing from Mesh to Curve.
    sep = ng.nodes.new("GeometryNodeSeparateComponents"); sep.location = (-460, -220)
    L(nin.outputs["Geometry"], sep.inputs["Geometry"])
    sw = ng.nodes.new("GeometryNodeJoinGeometry"); sw.location = (-240, -100)
    L(m2c.outputs["Curve"], sw.inputs["Geometry"])
    L(sep.outputs["Curve"], sw.inputs["Geometry"])

    # rka_lat = normalize(cross(+Z, tangent)). For a spine running +X this is +Y, which is the
    # side `intersection_kit.offset_spine_line(+x)` displaces to under traffic_side='LEFT' -- the
    # `+s` side `lane_profile` measures in. Verified by measurement, not by reading the docs.
    tan = ng.nodes.new("GeometryNodeInputTangent"); tan.location = (-240, 260)
    cross = ng.nodes.new("ShaderNodeVectorMath"); cross.operation = 'CROSS_PRODUCT'
    cross.location = (-80, 260)
    cross.inputs[0].default_value = _UP
    L(tan.outputs["Tangent"], cross.inputs[1])
    norm = ng.nodes.new("ShaderNodeVectorMath"); norm.operation = 'NORMALIZE'
    norm.location = (80, 260)
    L(cross.outputs["Vector"], norm.inputs[0])

    store = ng.nodes.new("GeometryNodeStoreNamedAttribute"); store.location = (300, 0)
    store.data_type = 'FLOAT_VECTOR'; store.domain = 'POINT'
    store.inputs["Name"].default_value = ATTR_LAT
    L(sw.outputs["Geometry"], store.inputs["Geometry"])
    L(norm.outputs["Vector"], store.inputs["Value"])
    L(store.outputs["Geometry"], nout.inputs["Geometry"])
    return ng


def make_stack_finish_group():
    """GN_StackFinish -- the stack's LAST modifier: drop the carrier curve and keep the meshes.

    The curve has to survive the whole stack (every layer re-derives from it), but it must not
    reach the exported/collided result: a stray curve component is invisible in the viewport yet
    is real geometry to anything that walks the evaluated object, and it would silently ride into
    the glTF bake and the `-colonly` proxy pass. Dropping it is one node, done once, at the top --
    rather than every layer having to remember not to pass it on."""
    ng = bpy.data.node_groups.get("GN_StackFinish")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("GN_StackFinish", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-300, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (300, 0)
    sep = ng.nodes.new("GeometryNodeSeparateComponents"); sep.location = (-80, 0)
    ng.links.new(nin.outputs["Geometry"], sep.inputs["Geometry"])
    ng.links.new(sep.outputs["Mesh"], nout.inputs["Geometry"])
    return ng


def _offset_stage(ng, L, geo_socket, nin, x=-100):
    """Build the shared "take the spine curve and shift it sideways" sub-chain, and return the
    resulting curve socket. THE one place a lateral offset happens, so every layer in the stack
    is displaced by the same rule and cannot drift from the pavement.

    Offset = `Offset` (a plain float input) + the per-point value of the named attribute
    `OffsetAttr`, if that attribute exists. The constant covers a fixed-width layer (a curb at a
    known lane edge); the attribute covers a layer whose offset VARIES along the piece (the outer
    curb of a road whose lane count changes, the edge of an opening ramp) -- which is the whole
    reason the carrier is a mesh. When `OffsetAttr` is left blank, or names an attribute that is
    not present, `Input Named Attribute`'s own `Exists` output selects 0 and only the constant
    applies, so a caller that does not need per-point variation simply omits it.

    Direction is `rka_lat`, read -- never recomputed -- from what `GN_SpineCurve` stored. `ZOffset`
    lifts the layer vertically (a sidewalk sits above the carriageway; a soffit sits below)."""
    lat = ng.nodes.new("GeometryNodeInputNamedAttribute"); lat.location = (x - 380, 240)
    lat.data_type = 'FLOAT_VECTOR'
    lat.inputs["Name"].default_value = ATTR_LAT

    off_a = ng.nodes.new("GeometryNodeInputNamedAttribute"); off_a.location = (x - 380, 80)
    off_a.data_type = 'FLOAT'
    L(nin.outputs["OffsetAttr"], off_a.inputs["Name"])
    pick = ng.nodes.new("GeometryNodeSwitch"); pick.input_type = 'FLOAT'
    pick.location = (x - 220, 80)
    pick.inputs["False"].default_value = 0.0
    L(off_a.outputs["Exists"], pick.inputs["Switch"])
    L(off_a.outputs["Attribute"], pick.inputs["True"])
    total = ng.nodes.new("ShaderNodeMath"); total.operation = 'ADD'; total.location = (x - 80, 80)
    L(pick.outputs["Output"], total.inputs[0])
    L(nin.outputs["Offset"], total.inputs[1])

    scale = ng.nodes.new("ShaderNodeVectorMath"); scale.operation = 'SCALE'
    scale.location = (x + 60, 200)
    L(lat.outputs["Attribute"], scale.inputs[0])
    L(total.outputs["Value"], scale.inputs["Scale"])

    zvec = ng.nodes.new("ShaderNodeCombineXYZ"); zvec.location = (x + 60, 20)
    L(nin.outputs["ZOffset"], zvec.inputs["Z"])
    add = ng.nodes.new("ShaderNodeVectorMath"); add.operation = 'ADD'; add.location = (x + 220, 120)
    L(scale.outputs["Vector"], add.inputs[0])
    L(zvec.outputs["Vector"], add.inputs[1])

    setpos = ng.nodes.new("GeometryNodeSetPosition"); setpos.location = (x + 400, 0)
    L(geo_socket, setpos.inputs["Geometry"])
    L(add.outputs["Vector"], setpos.inputs["Offset"])
    return setpos.outputs["Geometry"]


def wrap_layer(inner_ng, name):
    """Turn ANY "curve in -> geometry out" node group into a stack layer, and cache it by `name`.

    The wrapper does the three things every layer has in common and nothing else: pull the spine
    curve back out of the accumulated geometry, shift it sideways/vertically (`_offset_stage`),
    and JOIN whatever the inner group produced onto what was already there. The inner group stays
    completely unaware of the stack -- it just sweeps or tiles along the curve it is handed.

    Its inputs are mirrored onto the wrapper automatically (`_mirror_inputs`), so wrapping
    `GN_RoadSupport` exposes all of its pier/fill settings, wrapping `GN_CurbAssetRow` exposes
    spacing and rotation, and a future group's new input appears without editing this function.
    That is what makes "add another layer" a one-line change rather than a new node tree."""
    wrapped = bpy.data.node_groups.get(name)
    if wrapped:
        return wrapped, dict(wrapped["sock_ids"].to_dict()
                             if hasattr(wrapped["sock_ids"], "to_dict") else wrapped["sock_ids"])
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    off_s = ifc.new_socket("Offset", in_out="INPUT", socket_type="NodeSocketFloat")
    offa_s = ifc.new_socket("OffsetAttr", in_out="INPUT", socket_type="NodeSocketString")
    z_s = ifc.new_socket("ZOffset", in_out="INPUT", socket_type="NodeSocketFloat")
    inner_map = _mirror_inputs(ifc, inner_ng)
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-900, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (900, 0)
    L = ng.links.new

    sep = ng.nodes.new("GeometryNodeSeparateComponents"); sep.location = (-700, -160)
    L(nin.outputs["Geometry"], sep.inputs["Geometry"])
    curve = _offset_stage(ng, L, sep.outputs["Curve"], nin, x=-380)

    # NB `node_tree`, not `node_group` -- the group NODE and the NodesModifier spell this
    # differently (`mod.node_group` vs `node.node_tree`), and the node raises AttributeError for
    # the modifier's spelling.
    grp = ng.nodes.new("GeometryNodeGroup"); grp.node_tree = inner_ng; grp.location = (300, -80)
    # The inner group's first (geometry) input takes the offset curve; every other input is fed
    # straight from the mirrored wrapper socket of the same name.
    geo_in = next(s for s in grp.inputs if s.type == 'GEOMETRY')
    L(curve, geo_in)
    for sock_name in inner_map:
        if sock_name in nin.outputs and sock_name in grp.inputs:
            L(nin.outputs[sock_name], grp.inputs[sock_name])

    join = ng.nodes.new("GeometryNodeJoinGeometry"); join.location = (620, 0)
    L(nin.outputs["Geometry"], join.inputs["Geometry"])
    L(next(o for o in grp.outputs if o.type == 'GEOMETRY'), join.inputs["Geometry"])
    L(join.outputs["Geometry"], nout.inputs["Geometry"])

    ids = {"Offset": off_s.identifier, "OffsetAttr": offa_s.identifier, "ZOffset": z_s.identifier}
    ids.update({k: v[1] for k, v in inner_map.items()})
    ng["sock_ids"] = ids
    return ng, ids


# ------------------------------------------------------------------- inner content node groups
# Each takes a CURVE and returns geometry. None of them knows it is in a stack, and none knows
# what a lane is -- `wrap_layer` supplies the offset, Python supplies the numbers.

def make_pavement_group():
    """GN_PaveSweep: the carriageway. Sweeps a UNIT line scaled per point by `rka_halfw`.

    The asymmetry that caused the "one-way roads are built double-width" defect is handled
    entirely by the wrapper's offset stage (`OffsetAttr = rka_shift`), NOT here -- so this group
    stays a plain symmetric sweep and there is no second place where a left extent and a right
    extent can disagree. That is a deliberate simplification of the Phase-0 fix: `GN_RoadProfile`
    took `Neg Frac`/`Pos Frac` as MODIFIER inputs, i.e. one asymmetry ratio for the whole piece,
    so a road whose asymmetry changes ALONG its length -- a ramp, a taper, a gore, the exact cases
    this redesign exists for -- could not be expressed and had to be cut into separate pieces.
    Per-point `rka_shift` + `rka_halfw` express all of them continuously.

    Flat, zero-thickness, no end caps -- see `kit_common.make_road_profile_group`'s docstring for
    why a road surface is a plane and not a slab; that reasoning is unchanged and still applies."""
    ng = bpy.data.node_groups.get("GN_PaveSweep")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("GN_PaveSweep", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ifc.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-700, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (700, 0)
    L = ng.links.new

    halfw = ng.nodes.new("GeometryNodeInputNamedAttribute"); halfw.location = (-700, -220)
    halfw.data_type = 'FLOAT'
    halfw.inputs["Name"].default_value = ATTR_HALFW

    line = ng.nodes.new("GeometryNodeCurvePrimitiveLine"); line.location = (-460, -400)
    line.inputs["Start"].default_value = (-1.0, 0.0, 0.0)
    line.inputs["End"].default_value = (1.0, 0.0, 0.0)

    # "Z Up" for the same reason `make_profile_sweep_group` pins it -- see there. On the
    # carriageway it additionally guarantees the ribbon stays horizontal instead of rolling with
    # the curve's incidental twist.
    setn = ng.nodes.new("GeometryNodeSetCurveNormal"); setn.location = (-320, 0)
    setn.inputs["Mode"].default_value = 'Z Up'
    L(nin.outputs["Geometry"], setn.inputs["Curve"])

    c2m = ng.nodes.new("GeometryNodeCurveToMesh"); c2m.location = (-180, 0)
    c2m.inputs["Fill Caps"].default_value = False
    L(setn.outputs["Curve"], c2m.inputs["Curve"])
    L(line.outputs["Curve"], c2m.inputs["Profile Curve"])
    # Per-point half-width goes into Curve to Mesh's own `Scale` FIELD, not into the curve's
    # `radius` attribute. This Blender no longer scales the profile by radius implicitly (measured:
    # a Set Curve Radius of 5.25 still swept a unit-wide ribbon, +-1.0 -- the shift landed
    # correctly at 5.25 while the width stayed 2.0, which is what made the cause obvious). The old
    # `kit_common.GN_RoadProfile` relies on the radius path and is unchanged; new stack layers use
    # Scale.
    L(halfw.outputs["Attribute"], c2m.inputs["Scale"])

    setm = ng.nodes.new("GeometryNodeSetMaterial"); setm.location = (60, 0)
    L(c2m.outputs["Mesh"], setm.inputs["Geometry"])
    L(nin.outputs["Material"], setm.inputs["Material"])
    ss = ng.nodes.new("GeometryNodeSetShadeSmooth"); ss.location = (300, 0)
    L(setm.outputs["Geometry"], ss.inputs["Geometry"])
    L(ss.outputs["Geometry"], nout.inputs["Geometry"])
    return ng


def make_profile_sweep_group():
    """GN_ProfileSweep: sweep a caller-supplied 2D PROFILE OBJECT along the curve -- the single
    group behind curb L, curb R, sidewalk L, sidewalk R, median, and any barrier or kerb-line
    added later. They differ only in offset, height and which profile object, all of which are
    inputs, which is why this is instantiated N times rather than written N times.

    `Profile` is a `NodeSocketObject`, not Geometry: assigning an Object straight to a
    Geometry-typed modifier input silently no-ops in this Blender, and routing it through an
    Object socket into an internal Object Info node is what actually works (the same finding
    `make_curb_loop_group` records). So the "2D plane / profile asset" convention the rest of the
    kit already uses -- `_curb_profile_object`, `gutter_curb_profile`, a sidewalk cross-section --
    plugs straight in with no new authoring rule.

    Radius is forced to 1 so the profile sweeps at its AUTHORED size. Without this the profile
    would inherit whatever radius the pavement layer set (Curve to Mesh always scales its profile
    by the curve's radius), and every curb would silently grow with the road's width."""
    ng = bpy.data.node_groups.get("GN_ProfileSweep")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("GN_ProfileSweep", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ifc.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    ifc.new_socket("Profile", in_out="INPUT", socket_type="NodeSocketObject")
    sc = ifc.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat")
    sc.default_value = 1.0
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-700, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (700, 0)
    L = ng.links.new

    oi = ng.nodes.new("GeometryNodeObjectInfo"); oi.location = (-620, -280)
    oi.transform_space = "ORIGINAL"
    L(nin.outputs["Profile"], oi.inputs["Object"])

    # PROFILE ORIENTATION. Curve to Mesh's profile plane is rotated 180 degrees about the sweep
    # axis relative to the convention every profile asset in this kit is authored in. Measured on
    # a +X spine (all four normal modes agree): an authored point at local X=+1 sweeps to world
    # y = -1, and one at local Y=+0.5 sweeps to world z = -0.5. So a curb drawn "outward and up"
    # comes out "inward and down" -- which is why the first version of this layer produced a curb
    # hanging under the road.
    #
    # Undo it as a ROTATION (0, 0, pi) about the profile's own Z, not a (1,-1,1) mirror: the two
    # move the geometry identically here, but a rotation has determinant +1 and preserves face
    # winding, whereas a mirror inverts it and would leave every curb and sidewalk inside-out --
    # invisible from the street under backface culling, and wrong in the glTF bake.
    prot = ng.nodes.new("GeometryNodeTransform"); prot.location = (-460, -280)
    prot.inputs["Rotation"].default_value = (0.0, 0.0, 3.141592653589793)
    L(oi.outputs["Geometry"], prot.inputs["Geometry"])

    # PIN THE SWEEP FRAME. Curve to Mesh orients the profile with the curve's own normal, which
    # by default is "Minimum Twist" -- derived from the curve's shape, so the profile's idea of
    # "up" depends on where the road happens to bend. Measured on a plain +X spine with the
    # default frame: an authored profile point at local +Y (which every profile asset in this kit
    # means as UP -- see `kit_common._curb_profile_object`) swept to world Z = -0.5, i.e. the curb
    # was built pointing DOWN. "Z Up" makes the frame deterministic and world-referenced, so
    # authored profiles sweep the way they were drawn on every piece regardless of its curvature,
    # and two layers on the same spine can never disagree about which way is up.
    setn = ng.nodes.new("GeometryNodeSetCurveNormal"); setn.location = (-320, 0)
    setn.inputs["Mode"].default_value = 'Z Up'
    L(nin.outputs["Geometry"], setn.inputs["Curve"])

    c2m = ng.nodes.new("GeometryNodeCurveToMesh"); c2m.location = (-180, 0)
    # False for the same reason `make_curb_loop_group` sets it: an open (segment) curb otherwise
    # gets a solid end wall exactly where it meets the next piece.
    c2m.inputs["Fill Caps"].default_value = False
    L(setn.outputs["Curve"], c2m.inputs["Curve"])
    L(prot.outputs["Geometry"], c2m.inputs["Profile Curve"])
    # `Scale` defaults to 1.0, so the profile sweeps at its AUTHORED size and does NOT inherit the
    # pavement layer's width -- see `make_pavement_group` for why this is Curve to Mesh's Scale
    # field rather than the curve's radius attribute.
    L(nin.outputs["Scale"], c2m.inputs["Scale"])

    setm = ng.nodes.new("GeometryNodeSetMaterial"); setm.location = (60, 0)
    L(c2m.outputs["Mesh"], setm.inputs["Geometry"])
    L(nin.outputs["Material"], setm.inputs["Material"])
    ss = ng.nodes.new("GeometryNodeSetShadeSmooth"); ss.location = (300, 0)
    L(setm.outputs["Geometry"], ss.inputs["Geometry"])
    L(ss.outputs["Geometry"], nout.inputs["Geometry"])
    return ng


def make_asset_row_group():
    """GN_AssetRow: tile an ASSET OBJECT along the curve -- streetlights, curb kit pieces,
    bollards, trees, signs. One group for every prop row in the stack.

    THIS REPLACES THE PYTHON TILING PATH, which is what the user asked for ("take the asset of
    light lamp/curb editor as modifier rather than python script, so can more easily follow the
    curve and seem better perform than call each"). Both halves of that are real:

      * FOLLOWS THE CURVE. The Python row (`kit_common.curb_asset_row`'s baked path) sampled the
        boundary polyline ONCE at build time and wrote out fixed instances. Edit the spine
        afterwards and the lamps stay where they were until something re-ran the operator. Here
        the count, the positions and the headings are all NODES, re-evaluated by the dependency
        graph on every spine edit -- drag a control point and the whole row slides with it.
      * PERFORMS BETTER. Per-instance Python meant a `bpy.data.objects.new` + collection link per
        lamp, i.e. real datablocks, undo-stack pressure and .blend size proportional to prop
        count. Instance-on-Points keeps ONE evaluated instance reference per point and only
        realizes at export time.

    Count is `max(1, round(Length / Spacing))` computed as a Math chain, and Curve To Points is
    asked for Count+1 points with the last one deleted -- COUNT mode always places a point at the
    far end INCLUSIVE, so the raw output would put a redundant overlapping instance right on the
    joint with the next piece. That subtlety is inherited deliberately from
    `make_curb_asset_row_group`, where it was found by measurement.

    `Phase` (0..1) trims the head of the curve before sampling, which is how two rows on opposite
    sides get STAGGERED instead of marching in lockstep -- previously called out as needing a Trim
    Curve node that "does not appear anywhere in the codebase today", which was true of the
    codebase but not of Blender: the node exists and is used here.

    `Skip` + `SkipRadius` delete any point within `SkipRadius` of the `Skip` object's geometry --
    the intersection-exclusion rule (no lamp post standing in the middle of a junction mouth),
    live instead of precomputed. Leaving `Skip` empty disables it: Geometry Proximity reports
    `Is Valid = False` with no target, and the delete selection is ANDed with that."""
    ng = bpy.data.node_groups.get("GN_AssetRow")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("GN_AssetRow", "GeometryNodeTree")
    ifc = ng.interface
    ifc.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ifc.new_socket("Object", in_out="INPUT", socket_type="NodeSocketObject")
    sp = ifc.new_socket("Spacing", in_out="INPUT", socket_type="NodeSocketFloat")
    sp.default_value = 30.0
    ifc.new_socket("RotOffset", in_out="INPUT", socket_type="NodeSocketFloat")
    scl = ifc.new_socket("ScaleY", in_out="INPUT", socket_type="NodeSocketFloat")
    scl.default_value = 1.0
    ifc.new_socket("Phase", in_out="INPUT", socket_type="NodeSocketFloat")
    ifc.new_socket("Skip", in_out="INPUT", socket_type="NodeSocketObject")
    skr = ifc.new_socket("SkipRadius", in_out="INPUT", socket_type="NodeSocketFloat")
    skr.default_value = 0.0
    ifc.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nin = ng.nodes.new("NodeGroupInput"); nin.location = (-1200, 0)
    nout = ng.nodes.new("NodeGroupOutput"); nout.location = (1500, 0)
    L = ng.links.new

    # ---- Phase: trim the head of the curve so opposite rows stagger instead of pairing up.
    trim = ng.nodes.new("GeometryNodeTrimCurve"); trim.location = (-1000, 0)
    trim.mode = 'FACTOR'
    L(nin.outputs["Geometry"], trim.inputs["Curve"])
    L(nin.outputs["Phase"], trim.inputs[2])          # Start (factor)

    # ---- Count = max(1, round(length / spacing)); +1 because COUNT mode is end-inclusive.
    clen = ng.nodes.new("GeometryNodeCurveLength"); clen.location = (-820, 300)
    div = ng.nodes.new("ShaderNodeMath"); div.operation = 'DIVIDE'; div.location = (-660, 300)
    rnd = ng.nodes.new("ShaderNodeMath"); rnd.operation = 'ROUND'; rnd.location = (-500, 300)
    mx = ng.nodes.new("ShaderNodeMath"); mx.operation = 'MAXIMUM'; mx.location = (-340, 300)
    mx.inputs[1].default_value = 1.0
    p1 = ng.nodes.new("ShaderNodeMath"); p1.operation = 'ADD'; p1.location = (-180, 300)
    p1.inputs[1].default_value = 1.0
    L(trim.outputs["Curve"], clen.inputs["Curve"])
    L(clen.outputs["Length"], div.inputs[0])
    L(nin.outputs["Spacing"], div.inputs[1])
    L(div.outputs["Value"], rnd.inputs[0])
    L(rnd.outputs["Value"], mx.inputs[0])
    L(mx.outputs["Value"], p1.inputs[0])

    c2p = ng.nodes.new("GeometryNodeCurveToPoints"); c2p.mode = 'COUNT'; c2p.location = (-180, 0)
    L(trim.outputs["Curve"], c2p.inputs["Curve"])
    L(p1.outputs["Value"], c2p.inputs["Count"])

    # ---- Heading: Z-only, from the tangent. Props never lean with a sloped road -- the same
    # convention every other heading in this addon uses.
    sep = ng.nodes.new("ShaderNodeSeparateXYZ"); sep.location = (-180, -200)
    at2 = ng.nodes.new("ShaderNodeMath"); at2.operation = 'ARCTAN2'; at2.location = (-20, -200)
    addr = ng.nodes.new("ShaderNodeMath"); addr.operation = 'ADD'; addr.location = (140, -200)
    cmb = ng.nodes.new("ShaderNodeCombineXYZ"); cmb.location = (300, -200)
    L(c2p.outputs["Tangent"], sep.inputs["Vector"])
    L(sep.outputs["Y"], at2.inputs[0])
    L(sep.outputs["X"], at2.inputs[1])
    L(at2.outputs["Value"], addr.inputs[0])
    L(nin.outputs["RotOffset"], addr.inputs[1])
    L(addr.outputs["Value"], cmb.inputs["Z"])
    strot = ng.nodes.new("GeometryNodeStoreNamedAttribute"); strot.location = (460, 0)
    strot.data_type = 'FLOAT_VECTOR'; strot.domain = 'POINT'
    strot.inputs["Name"].default_value = "rowrot"
    L(c2p.outputs["Points"], strot.inputs["Geometry"])
    L(cmb.outputs["Vector"], strot.inputs["Value"])

    # ---- Drop the end-inclusive overshoot point, OR any point inside the Skip object.
    idx = ng.nodes.new("GeometryNodeInputIndex"); idx.location = (300, -420)
    idxf = ng.nodes.new("ShaderNodeMath"); idxf.operation = 'ADD'; idxf.location = (440, -420)
    idxf.inputs[1].default_value = 0.0
    eq = ng.nodes.new("FunctionNodeCompare"); eq.data_type = 'FLOAT'; eq.operation = 'EQUAL'
    eq.location = (580, -420)
    L(idx.outputs["Index"], idxf.inputs[0])
    L(idxf.outputs["Value"], eq.inputs[0])
    L(mx.outputs["Value"], eq.inputs[1])

    skoi = ng.nodes.new("GeometryNodeObjectInfo"); skoi.location = (300, -640)
    skoi.transform_space = "RELATIVE"
    L(nin.outputs["Skip"], skoi.inputs["Object"])
    prox = ng.nodes.new("GeometryNodeProximity"); prox.location = (460, -640)
    L(skoi.outputs["Geometry"], prox.inputs["Geometry"])
    near = ng.nodes.new("FunctionNodeCompare"); near.data_type = 'FLOAT'; near.operation = 'LESS_THAN'
    near.location = (620, -640)
    L(prox.outputs["Distance"], near.inputs[0])
    L(nin.outputs["SkipRadius"], near.inputs[1])
    valid = ng.nodes.new("FunctionNodeBooleanMath"); valid.operation = 'AND'
    valid.location = (760, -640)
    L(near.outputs["Result"], valid.inputs[0])
    L(prox.outputs["Is Valid"], valid.inputs[1])

    anyd = ng.nodes.new("FunctionNodeBooleanMath"); anyd.operation = 'OR'; anyd.location = (900, -500)
    L(eq.outputs["Result"], anyd.inputs[0])
    L(valid.outputs["Boolean"], anyd.inputs[1])

    dele = ng.nodes.new("GeometryNodeDeleteGeometry"); dele.domain = 'POINT'; dele.location = (900, 0)
    L(strot.outputs["Geometry"], dele.inputs["Geometry"])
    L(anyd.outputs["Boolean"], dele.inputs["Selection"])

    rdrot = ng.nodes.new("GeometryNodeInputNamedAttribute"); rdrot.location = (900, -200)
    rdrot.data_type = 'FLOAT_VECTOR'
    rdrot.inputs["Name"].default_value = "rowrot"

    oi = ng.nodes.new("GeometryNodeObjectInfo"); oi.location = (900, -300)
    oi.transform_space = "ORIGINAL"
    if "As Instance" in oi.inputs:
        oi.inputs["As Instance"].default_value = True
    L(nin.outputs["Object"], oi.inputs["Object"])

    sclv = ng.nodes.new("ShaderNodeCombineXYZ"); sclv.location = (900, -380)
    sclv.inputs["X"].default_value = 1.0
    sclv.inputs["Z"].default_value = 1.0
    L(nin.outputs["ScaleY"], sclv.inputs["Y"])

    iop = ng.nodes.new("GeometryNodeInstanceOnPoints"); iop.location = (1120, 0)
    L(dele.outputs["Geometry"], iop.inputs["Points"])
    L(oi.outputs["Geometry"], iop.inputs["Instance"])
    L(rdrot.outputs["Attribute"], iop.inputs["Rotation"])
    L(sclv.outputs["Vector"], iop.inputs["Scale"])

    # Realize is required for glTF export -- bare un-realized instances export empty/at origin
    # (see `kit_common.make_gn_group`'s docstring, found the hard way).
    real = ng.nodes.new("GeometryNodeRealizeInstances"); real.location = (1320, 0)
    L(iop.outputs["Instances"], real.inputs["Geometry"])
    L(real.outputs["Geometry"], nout.inputs["Geometry"])
    return ng


# ------------------------------------------------------------------------- the carrier and stack

def make_spine_mesh(name, pts, coll):
    """The spine CARRIER: a mesh polyline through `pts` -- one vertex per control point, one edge
    between consecutive points. This object IS the piece: the whole road is its modifier stack, so
    entering Edit Mode and dragging a vertex reshapes pavement, curbs, sidewalks, median, props
    and piers together, live, with no Python rebuild step.

    Mesh rather than Curve because a Curve datablock cannot carry custom per-point attributes at
    all (see the module docstring) -- and those attributes are what make the cross-section vary
    ALONG the piece instead of being one constant per piece."""
    me = bpy.data.meshes.new(name + "_spine")
    me.from_pydata([(p[0], p[1], p[2]) for p in pts],
                   [(i, i + 1) for i in range(len(pts) - 1)], [])
    me.update()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    return obj


def write_spine_attributes(spine_obj, values):
    """Write `{attr_name: [per-vertex floats]}` onto the carrier mesh, creating each attribute if
    needed. This is the ONLY way cross-section numbers reach the node stack, and every number in
    it comes from `lane_profile` -- keeping the "nodes never derive slot math" rule enforceable by
    inspection: if a value is wrong it is wrong in one Python function, not somewhere in a graph.

    Lists shorter than the vertex count hold their last value (a constant-width road can pass a
    single-element list); longer ones are truncated."""
    me = spine_obj.data
    n = len(me.vertices)
    for name, vals in values.items():
        if not vals:
            continue
        attr = me.attributes.get(name)
        if attr is None or attr.data_type != 'FLOAT' or attr.domain != 'POINT':
            if attr is not None:
                me.attributes.remove(attr)
            attr = me.attributes.new(name=name, type='FLOAT', domain='POINT')
        seq = [float(vals[min(i, len(vals) - 1)]) for i in range(n)]
        attr.data.foreach_set("value", seq)
    me.update()


def spine_attributes_for(profile_set, n_points, traffic_side='LEFT'):
    """`{ATTR_HALFW: [...], ATTR_SHIFT: [...]}` sampled at `n_points` stations of `profile_set` --
    the bridge from the cross-section description to the node stack, and the single owner of the
    `traffic_side` flip on the way in.

    `paved_extents` (not `extents`) because sidewalks ride their own layers and must not widen the
    carriageway sweep. The pair is turned into (half-width, centre shift) exactly as
    `intersection_kit.sweep_radius_and_shift` defines it, per point rather than per piece."""
    import lane_profile as lp
    sign = 1.0 if traffic_side == 'LEFT' else -1.0
    halfw, shift = [], []
    for prof in profile_set.sample(max(n_points, 2)):
        neg, pos = lp.paved_extents(prof)
        halfw.append((neg + pos) / 2.0)
        shift.append(sign * (pos - neg) / 2.0)
    return {ATTR_HALFW: halfw, ATTR_SHIFT: shift}


def layer(name, inner_ng, offset=0.0, offset_attr="", z=0.0, **inputs):
    """One entry in a stack spec. `inner_ng` is any curve-in/geometry-out group (the ones above,
    or an existing one like `GN_RoadSupport`); `offset`/`offset_attr`/`z` place it; `inputs` are
    forwarded by NAME to the inner group's own sockets."""
    return {"name": name, "inner": inner_ng, "offset": offset,
            "offset_attr": offset_attr, "z": z, "inputs": inputs}


def build_stack(spine_obj, layers):
    """(Re)build the whole modifier stack on `spine_obj`, in order: `GN_SpineCurve`, every layer,
    `GN_StackFinish`.

    Rebuilt wholesale rather than patched, because the stack is DERIVED from the piece's settings
    -- a piece that loses its median should lose that layer, and reconciling a live stack against
    a spec is exactly the object-lifetime bookkeeping this design exists to delete. It is cheap:
    modifiers hold no geometry, so this is a few dozen property writes, not a rebuild of anything.

    The spine's own control points and its per-vertex attributes are untouched -- they are the
    authored state and never regenerated from a spec."""
    for m in list(spine_obj.modifiers):
        spine_obj.modifiers.remove(m)

    head = spine_obj.modifiers.new("Spine", 'NODES')
    head.node_group = make_spine_curve_group()

    for spec in layers:
        wrapper, ids = wrap_layer(spec["inner"], "GN_Layer_" + spec["inner"].name)
        mod = spine_obj.modifiers.new(spec["name"], 'NODES')
        mod.node_group = wrapper
        kc.set_mod_input(mod, ids["Offset"], float(spec.get("offset", 0.0)))
        kc.set_mod_input(mod, ids["OffsetAttr"], spec.get("offset_attr", "") or "")
        kc.set_mod_input(mod, ids["ZOffset"], float(spec.get("z", 0.0)))
        for k, v in (spec.get("inputs") or {}).items():
            if k in ids and v is not None:
                kc.set_mod_input(mod, ids[k], v)

    tail = spine_obj.modifiers.new("Finish", 'NODES')
    tail.node_group = make_stack_finish_group()
    return spine_obj


def write_layer_offset(spine_obj, attr_name, profile_set, fn, traffic_side='LEFT'):
    """Write a per-point lateral offset attribute for ONE layer: `fn(profile)` is evaluated at
    every spine station and stored under `attr_name`, with the `traffic_side` flip applied here
    and nowhere else.

    `fn` returns an offset in `lane_profile`'s driving frame (`+s` = forward-lane side). The stack
    measures along `rka_lat`, which is `cross(+Z, tangent)` -- always the same geometric side
    regardless of which side of the road traffic keeps to -- so the flip belongs at exactly one
    boundary, this one. Applying it inside `fn` as well would cancel it out for keep-right
    content, which is precisely the shape of the Phase-0 sign bug (invisible while everything was
    symmetric, because a symmetric sweep is sign-invariant)."""
    n = max(len(spine_obj.data.vertices), 2)
    sign = 1.0 if traffic_side == 'LEFT' else -1.0
    vals = [sign * float(fn(prof)) for prof in profile_set.sample(n)]
    write_spine_attributes(spine_obj, {attr_name: vals})
    return attr_name
