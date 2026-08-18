"""graph_build.py -- turn a solved road graph into geometry: emit the swept CARRIER, then hang the
layer stack off it.

WHY PYTHON EMITS THE CARRIER INSTEAD OF THE NODE TREE SPLITTING EDGES. The obvious Geometry Nodes
route is `Split Edges -> capture edge attributes -> Mesh to Curve`, which works because the split
makes every edge its own two-point spline so the edge->point interpolation is exact. It has one
fatal limitation: it splits EVERYWHERE. A vertex the author marked as a shape point
(`NODE_NONE`) must NOT break the sweep -- the ribbon has to run through it continuously -- and no
selection on Split Edges can express "join these two edges but not those". Since the solver has to
run anyway (trims, patches, corners are not expressible in nodes at all), it also walks the graph
into CHAINS, and Python emits one polyline per chain with every number already resolved onto its
points. The node tree then never reasons about topology, only about sweeping.

WHAT A CHAIN IS. A maximal run of edges joined end-to-end through `NODE_NONE` vertices. Every
other node kind (junction, gore, bend, taper, cap) ends the chain, because those are exactly the
places the solver trimmed the ends back and a patch fills the gap. A single edge between two
junctions is a one-edge chain.

THE PARAMETRIC-OR-ASSET RULE LIVES HERE. `<role>_asset_idx >= 0` means "use the palette mesh", and
the matching parametric band is suppressed by writing its width to 0 -- so a kerb is never built
twice, and the choice is made in one Python line rather than by a branch in the node graph.

MATERIALS are left unassigned in this pass; the layer sockets exist (`Material`) and are wired,
so assigning them is a per-project decision rather than a code change.
"""
import bmesh
import bpy

from . import graph_assets as gas
from . import graph_attrs as ga
from . import graph_nodes as gn
from . import graph_solve as gsolve

SUFFIX_CARRIER = "_Carrier"

#: Per-point carrier attributes. FLOAT unless listed in `INT_ATTRS`.
INT_ATTRS = ("rka_ix_curb", "rka_ix_median", "rka_ix_sidewalk",
             "rka_ix_pillar", "rka_ix_rail", "rka_ix_prop")


def _point_values(attrs, offsets):
    """Every per-point number one edge contributes, already resolved. The single place the
    parametric-or-asset choice and the per-side kerb switch are applied."""
    ix = {r: int(attrs.get("%s_asset_idx" % r, -1)) for r in gas.ROLE_NAMES}
    curb_h = float(attrs.get("curb_height", 0.15))
    # A side with its kerb switched off, or one served by a palette asset, contributes no
    # parametric kerb -- width 0 rather than a second "build this?" flag in the node tree.
    hl = curb_h if int(attrs.get("curb_left_on", 1)) and ix["curb"] < 0 else 0.0
    hr = curb_h if int(attrs.get("curb_right_on", 1)) and ix["curb"] < 0 else 0.0
    med_raised = int(attrs.get("median_type", 0)) in ga.MEDIAN_RAISED
    med_h = 0.0 if ix["median"] >= 0 else offsets["median_half"]
    wl, wr = offsets["walk_w_left"], offsets["walk_w_right"]
    cl, cr = offsets["curb_off_left"], offsets["curb_off_right"]
    return {
        "rka_halfw": offsets["paved_half"],
        "rka_shift": offsets["paved_shift"],
        "rka_med_h": med_h,
        "rka_med_z": curb_h if med_raised else 0.0,
        # A footway is centred outboard of its kerb line; `curb_off_right` is already negative, so
        # outward is a further subtraction. Both are half-widths -- the band profile spans -1..1.
        "rka_walk_cl": cl + wl / 2.0,
        "rka_walk_hl": wl / 2.0,
        "rka_walk_cr": cr - wr / 2.0,
        "rka_walk_hr": wr / 2.0,
        "rka_curb_ol": cl,
        "rka_curb_or": cr,
        "rka_curb_hl": hl,
        "rka_curb_hr": hr,
        # Kerb thickness is half its height, so a taller kerb reads as a heavier one. The box is
        # swept as a narrow band extruded down, which is why this is a half-width.
        "rka_curb_tl": hl * 0.5,
        "rka_curb_tr": hr * 0.5,
        "rka_deck_h": float(attrs.get("deck_thickness", 0.0)),
        "rka_sp_asset": max(float(attrs.get("asset_spacing", 5.0)), 0.05),
        "rka_sp_pillar": max(float(attrs.get("pillar_spacing", 0.0)), 0.05),
        "rka_pillar_on": 1.0 if float(attrs.get("pillar_spacing", 0.0)) > 0.0 else 0.0,
        "rka_pillar_w": max(float(attrs.get("pillar_width", 1.4)), 0.1),
        # ONE ROW OR THE OTHER, never both. The parametric column runs only where no kit asset has
        # been picked; picking one hands the same points to the asset row instead.
        "rka_pillar_param": (1.0 if float(attrs.get("pillar_spacing", 0.0)) > 0.0
                             and ix["pillar"] < 0 else 0.0),
        # Carried per point so `build_carrier` can turn it into a column height once it knows the
        # point's own elevation -- the one number this cannot resolve from edge attributes alone.
        "rka_ground_z": float(attrs.get("ground_z", 0.0)),
        "rka_ix_curb": ix["curb"],
        "rka_ix_median": ix["median"],
        "rka_ix_sidewalk": ix["sidewalk"],
        # A pillar row with no spacing set is off, expressed by forcing its index negative so the
        # asset layer's own selection drops it -- no extra switch anywhere.
        "rka_ix_pillar": ix["pillar"] if float(attrs.get("pillar_spacing", 0.0)) > 0.0 else -1,
        "rka_ix_rail": ix["rail"],
        "rka_ix_prop": ix["prop"],
    }


def _chain_length(pts):
    return sum((pts[i + 1][0] - pts[i][0]).length for i in range(len(pts) - 1))


def _cut_front(pts, d):
    """Drop `d` metres off the FRONT of a `[(co, values), ...]` polyline, interpolating position
    and keeping the values of the segment the new endpoint lands in."""
    if d <= 1e-9:
        return pts
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i][0], pts[i + 1][0]
        seg = (b - a).length
        if seg < 1e-12:
            continue
        if acc + seg >= d:
            return [(a.lerp(b, (d - acc) / seg), pts[i + 1][1])] + pts[i + 1:]
        acc += seg
    return []


def _trim_chain(pts, t0, t1):
    """Trim both ends by arclength, or None if the two trims consume the whole chain."""
    if t0 + t1 >= _chain_length(pts) - 1e-6:
        return None
    out = _cut_front(pts, t0)
    if len(out) < 2:
        return None
    out = _cut_front(list(reversed(out)), t1)
    if len(out) < 2:
        return None
    return list(reversed(out))


def _mirror(values):
    """The same numbers for an edge walked BACKWARDS: left and right swap, and every signed
    lateral offset negates. Without this, a chain that happens to traverse one of its edges
    against its own direction would build that edge's footway on the wrong side."""
    m = dict(values)
    for a, b in (("rka_walk_cl", "rka_walk_cr"), ("rka_walk_hl", "rka_walk_hr"),
                 ("rka_curb_ol", "rka_curb_or"), ("rka_curb_hl", "rka_curb_hr"),
                 ("rka_curb_tl", "rka_curb_tr")):
        m[a], m[b] = values[b], values[a]
    for k in ("rka_shift", "rka_walk_cl", "rka_walk_cr", "rka_curb_ol", "rka_curb_or"):
        m[k] = -m[k]
    return m


def _chain_end_verts(bm, chain):
    """(first_vertex_index, last_vertex_index) of a chain, honouring each edge's walk direction."""
    bm.edges.ensure_lookup_table()
    e0, f0 = chain[0]
    e1, f1 = chain[-1]
    first = bm.edges[e0].verts[0 if f0 else 1].index
    last = bm.edges[e1].verts[1 if f1 else 0].index
    return first, last


def _arclengths(pts):
    cum, total = [0.0], 0.0
    for i in range(len(pts) - 1):
        total += (pts[i + 1][0] - pts[i][0]).length
        cum.append(total)
    return cum, total


def _insert_at(pts, d):
    """Insert a point at arclength `d` from the front, unless one already sits there.

    A TAPER NEEDS A VERTEX AT ITS BREAKPOINT. The carrier only has points where the graph has
    them, so a 100 m taper on a chain whose last segment is 150 m long would otherwise be smeared
    linearly across that whole segment -- the authored taper length silently ignored. Splitting
    the segment is what makes the number mean something."""
    if d <= 1e-6:
        return pts
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i][0], pts[i + 1][0]
        seg = (b - a).length
        if seg < 1e-12:
            continue
        if acc + seg >= d - 1e-6:
            if abs(acc - d) < 1e-4 or abs(acc + seg - d) < 1e-4:
                return pts                       # a vertex is already close enough
            # The new point belongs to the segment it splits, same rule `_cut_front` uses.
            return pts[:i + 1] + [(a.lerp(b, (d - acc) / seg), pts[i + 1][1])] + pts[i + 1:]
        acc += seg
    return pts


def taper_breakpoints(pts, tap_s, tap_e):
    """Split the polyline where each taper begins, so the ramp has a vertex to pivot on."""
    _, total = _arclengths(pts)
    if 1e-6 < tap_s < total:
        pts = _insert_at(pts, tap_s)
        _, total = _arclengths(pts)
    if 1e-6 < tap_e < total:
        pts = _insert_at(pts, total - tap_e)
    return pts


def taper_scales(pts, tap_s, tap_e):
    """Per-point aux-lane openness, 0 (closed) .. 1 (full width).

    Shared by the CARRIER and the LANE EXPORT so a tapering ribbon and the routes drawn on it can
    never disagree -- a lane route computed against the untapered width would sit off the asphalt
    for the whole length of the taper, which is a car driving on air."""
    cum, total = _arclengths(pts)
    if tap_s <= 1e-6 and tap_e <= 1e-6:
        return [1.0] * len(pts)
    out = []
    for i in range(len(pts)):
        s = 0.0
        if tap_s > 1e-6:
            s = max(s, 1.0 - cum[i] / tap_s)
        if tap_e > 1e-6:
            s = max(s, 1.0 - (total - cum[i]) / tap_e)
        out.append(max(0.0, min(1.0, s)))
    return out


def chain_tapers(attrs_first, attrs_last, at_start, at_end):
    """(taper_at_start, taper_at_end) in metres -- 0 unless that end is a gore AND the edge there
    actually carries an aux lane. A road with nothing to taper must come out byte-identical to
    before, breakpoints included, or every ordinary chain pays for a feature it does not use."""
    def _t(attrs, live):
        if not live or not (int(attrs.get("aux_lanes_left", 0))
                            or int(attrs.get("aux_lanes_right", 0))):
            return 0.0
        return float(attrs.get("aux_taper_length", 0.0))

    return _t(attrs_first, at_start), _t(attrs_last, at_end)


def _resolve_points(trimmed, ends, gore_nodes):
    """Turn `[(co, (attrs, forward)), ...]` into `[(co, point_values), ...]`, opening any aux lane
    over its taper.

    THE TAPER IS ANCHORED AT THE GORE, because that is where the extra lane is actually used: the
    ramp attaches there, so the lane must be at full width there and close going away. Measured as
    arclength along the FINAL trimmed polyline, so it lines up with the geometry that gets built
    rather than with the untrimmed authoring graph.

    A chain with a gore at BOTH ends (a weaving section between an on-ramp and an off-ramp) takes
    the max of the two, which correctly leaves the lane full for its whole length when the chain
    is shorter than two tapers. A chain touching NO gore keeps its authored aux lanes at constant
    width -- exactly the previous behaviour, so nothing that is not a ramp changes.

    The taper LENGTH is read from the edge at the gore end, not per point: one ramp opens over one
    distance, and letting each edge along the chain contribute its own would kink the ramp."""
    tap_s, tap_e = chain_tapers(trimmed[0][1][0], trimmed[-1][1][0],
                                ends[0] in gore_nodes, ends[1] in gore_nodes)
    trimmed = taper_breakpoints(trimmed, tap_s, tap_e)
    scales = taper_scales(trimmed, tap_s, tap_e)

    out = []
    for (co, (attrs, forward)), scale in zip(trimmed, scales):
        pv = _point_values(attrs, gsolve.derived_offsets(attrs, aux_scale=scale))
        if not forward:
            pv = _mirror(pv)
        out.append((co, pv))
    return out


def build_carrier(graph_obj, result):
    """Emit `<graph>_Carrier`: one polyline per chain, trimmed at both ends, with every per-point
    number already written."""
    me = graph_obj.data
    # Edit Mode owns the mesh: the datablock only reflects the live bmesh after an
    # `update_edit_mesh`. Reading the edit bmesh directly (rather than relying on `solve_object`
    # having just flushed) is what lets a rebuild run WITHOUT dropping the artist out of Edit Mode
    # and losing their selection -- see the auto-build in `graph_attrs`.
    own = graph_obj.mode != 'EDIT'
    bm = bmesh.new() if own else bmesh.from_edit_mesh(me)
    if own:
        bm.from_mesh(me)
    try:
        elayers = ga.ensure_edge_layers(bm, fill_defaults=False)
        verts, edges, per_point = [], [], []
        starved = []
        gore_nodes = {n.index for n in result.nodes if n.kind == gsolve.rgs().KIND_GORE}
        for chain in gsolve.chains(bm):
            # The chain's FULL polyline first -- one point per vertex, each carrying the ATTRS of
            # the edge it arrives on -- and only then trimmed by arclength at the two real ends.
            # Attributes rather than resolved numbers, because the aux-lane taper below needs to
            # re-resolve them per point once the final arclength is known.
            pts = []
            for n, (eidx, forward) in enumerate(chain):
                e = bm.edges[eidx]
                v0, v1 = (e.verts[0], e.verts[1]) if forward else (e.verts[1], e.verts[0])
                if (v1.co - v0.co).length < 1e-9:
                    continue
                attrs = ga.read_edge(bm, e, elayers)
                if not pts:
                    pts.append((v0.co.copy(), (attrs, forward)))
                pts.append((v1.co.copy(), (attrs, forward)))
            if len(pts) < 2:
                continue
            head_e, head_f = chain[0]
            tail_e, tail_f = chain[-1]
            ends = _chain_end_verts(bm, chain)
            t0 = result.trim_start[head_e] if head_f else result.trim_end[head_e]
            t1 = result.trim_end[tail_e] if tail_f else result.trim_start[tail_e]
            # TRIM THE CHAIN, NOT THE EDGE. A 40 m junction setback on a polyline resampled every
            # 12 m has to eat through several shape points; trimming each sample edge instead
            # (the first version of this) left 189 of the island's 1634 edges reporting
            # "too short" and shredded every road near a junction.
            trimmed = _trim_chain(pts, t0, t1)
            if trimmed is None:
                starved.append((chain[0][0], round(_chain_length(pts), 2),
                                round(t0 + t1, 2)))
                continue
            # May insert taper breakpoints, so the edge run is built from ITS length, not the
            # pre-resolve one.
            resolved = _resolve_points(trimmed, ends, gore_nodes)
            base = len(verts)
            for co, pv in resolved:
                verts.append((co.x, co.y, co.z))
                # THE COLUMN HEIGHT IS RESOLVED HERE, where the point's own elevation is known.
                # `soffit - ground` is the whole definition of a support, and it varies point by
                # point along a ramp; an edge attribute cannot express it and a fixed-height kit
                # asset cannot either. Clamped at 0 so a road on grade asks for no column rather
                # than a negative one.
                pv = dict(pv)
                soffit = co.z - float(pv.get("rka_deck_h", 0.0))
                pv["rka_pillar_h"] = max(soffit - float(pv.get("rka_ground_z", 0.0)), 0.0)
                per_point.append(pv)
            edges.extend((base + i, base + i + 1) for i in range(len(resolved) - 1))
        if starved:
            print("[graph_build] %d chain(s) fully consumed by their own junctions, skipped: %s"
                  % (len(starved), starved[:5]))
    finally:
        if own:
            bm.free()          # freeing an EDIT bmesh would pull it out from under Blender

    cme = bpy.data.meshes.new(graph_obj.name + SUFFIX_CARRIER)
    cme.from_pydata(verts, edges, [])
    cme.update()
    if verts:
        keys = sorted(per_point[0].keys())
        for name in keys:
            dtype = 'INT' if name in INT_ATTRS else 'FLOAT'
            attr = cme.attributes.new(name=name, type=dtype, domain='POINT')
            attr.data.foreach_set("value", [per_point[i][name] for i in range(len(verts))])
    return gsolve._generated_object(graph_obj, SUFFIX_CARRIER, cme)


# ------------------------------------------------------------------------------------ the stack

#: How far the structural deck's top face is sunk below the carriageway it carries. Big enough to
#: beat depth-buffer precision at world scale, small enough to be invisible. See the Deck layer.
DECK_Z_BIAS = -0.02

#: How far flush-with-the-road paint is lifted clear of the asphalt. Same reasoning, other sign.
PAINT_Z_BIAS = 0.01


def _layer(name, inner, offset=0.0, offset_attr="", z=0.0, z_attr="", require_attr="",
           **inputs):
    return {"name": name, "inner": inner, "offset": offset, "offset_attr": offset_attr,
            "z": z, "z_attr": z_attr, "require_attr": require_attr, "inputs": inputs}


#: Material slot per band, created on demand. Names only -- look and shader are a project
#: decision, and a road that ships with four flat colours is still four separable surfaces in the
#: glTF bake, which is what the downstream `-colonly` and material-key passes actually need.
MATERIALS = {
    "asphalt": (0.05, 0.05, 0.055, 1.0),
    "concrete": (0.55, 0.54, 0.52, 1.0),
    "footway": (0.42, 0.41, 0.40, 1.0),
    "median": (0.20, 0.30, 0.16, 1.0),
}


def material(key):
    """Get-or-create a flat material by key, so a rebuild reuses the same datablock and any
    hand-edited shading on it survives."""
    mat = bpy.data.materials.get("rka_%s" % key)
    if mat is None:
        mat = bpy.data.materials.new("rka_%s" % key)
        mat.use_nodes = True
        mat.diffuse_color = MATERIALS.get(key, (0.5, 0.5, 0.5, 1.0))
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = MATERIALS.get(key, (0.5, 0.5, 0.5, 1.0))
            bsdf.inputs["Roughness"].default_value = 0.9
    return mat


def stack_spec():
    """The whole road, as data. Adding a band is one entry here, not a node tree."""
    band, deck, assets = gn.make_band_group(), gn.make_deck_group(), gn.make_assets_group()
    pillars = gn.make_pillars_group()
    reg = gas.registry
    return [
        _layer("Carriageway", band, offset_attr="rka_shift", WidthAttr="rka_halfw",
               Material=material("asphalt")),
        # A PAINTED median is deliberately flush with the road (`rka_med_z` = 0 for it), which is
        # the same coplanar-surface trap the deck fell into, just narrower -- so lift the paint by
        # the same kind of bias. A raised median already clears the asphalt and is unaffected.
        _layer("Median", band, WidthAttr="rka_med_h", z=PAINT_Z_BIAS, z_attr="rka_med_z",
               Material=material("median")),
        _layer("SidewalkL", band, offset_attr="rka_walk_cl", z_attr="rka_curb_hl",
               WidthAttr="rka_walk_hl", Material=material("footway")),
        _layer("SidewalkR", band, offset_attr="rka_walk_cr", z_attr="rka_curb_hr",
               WidthAttr="rka_walk_hr", Material=material("footway")),
        # A kerb is a narrow band at kerb-top height extruded back DOWN to the road surface, so
        # its box comes from the same two groups every other band uses.
        _layer("CurbL", deck, offset_attr="rka_curb_ol", z_attr="rka_curb_hl",
               WidthAttr="rka_curb_tl", ThicknessAttr="rka_curb_hl",
               Material=material("concrete")),
        _layer("CurbR", deck, offset_attr="rka_curb_or", z_attr="rka_curb_hr",
               WidthAttr="rka_curb_tr", ThicknessAttr="rka_curb_hr",
               Material=material("concrete")),
        # THE DECK TOP MUST SIT BELOW THE ROAD, NOT ON IT. The slab spans the same width as the
        # carriageway, so a top face at z = 0 is coplanar with the asphalt over the entire road --
        # measured by vertical ray sampling, 73.7% of the road surface had asphalt and concrete
        # within 5 mm, which is z-fighting across the whole network. It is worst where
        # `rka_deck_h` is 0 (every non-bridge edge): a zero-thickness deck is a bare concrete
        # sheet lying exactly on the asphalt. Dropping the slab by `DECK_Z_BIAS` is invisible --
        # it is buried under the road it carries -- and leaves the asphalt unambiguously on top.
        _layer("Deck", deck, offset_attr="rka_shift", z=DECK_Z_BIAS,
               WidthAttr="rka_halfw", ThicknessAttr="rka_deck_h",
               Material=material("concrete")),
        _layer("CurbAssetL", assets, offset_attr="rka_curb_ol", Palette=reg(gas.ROLE_CURB),
               IndexAttr="rka_ix_curb", SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
        _layer("MedianAsset", assets, Palette=reg(gas.ROLE_MEDIAN), IndexAttr="rka_ix_median",
               SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
        # Two pillar layers, and only one of them ever builds for a given edge: the parametric
        # column whenever `pillar_asset_idx` is -1 (the default), the instanced kit piece when an
        # author has picked one. That is the same "-1 = build this band from its numbers instead"
        # convention every other band already uses, so choosing a decorative column is one stamp
        # and needs no switch.
        _layer("Pillars", pillars, offset_attr="rka_shift", SpacingAttr="rka_sp_pillar",
               Material=material("concrete"), require_attr="rka_pillar_param"),
        _layer("PillarAssets", assets, offset_attr="rka_shift", Palette=reg(gas.ROLE_PILLAR),
               IndexAttr="rka_ix_pillar", SpacingAttr="rka_sp_pillar"),
        _layer("RailL", assets, offset_attr="rka_curb_ol", z_attr="rka_curb_hl",
               Palette=reg(gas.ROLE_RAIL), IndexAttr="rka_ix_rail",
               SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
        _layer("PropsL", assets, offset_attr="rka_walk_cl", z_attr="rka_curb_hl",
               Palette=reg(gas.ROLE_PROP), IndexAttr="rka_ix_prop",
               SpacingAttr="rka_sp_asset", **{"Align To Curve": True}),
    ]


def _attr_values(mesh, name):
    """Every value of a point-domain attribute, or None if the mesh does not carry it."""
    att = mesh.attributes.get(name)
    if att is None or not hasattr(att, "data"):
        return None
    try:
        return [d.value for d in att.data]
    except AttributeError:                          # not a scalar attribute
        return None


def layer_has_content(mesh, entry):
    """Would this layer build anything on THIS mesh?

    A layer whose width (or asset index) is zero everywhere still gets swept: Geometry Nodes
    happily extrudes a zero-width band and emits the polygons anyway, and a Named Attribute node
    pointed at a name the mesh does not carry reads 0 rather than erroring. So the junction
    corners -- which carry no `rka_halfw`, no median, no deck and no right-hand side at all --
    were being swept by the full 13-layer road stack, producing 11,400 concrete polygons totalling
    392 m2 of actual area plus two entirely empty bands. Every asset layer was in the same
    position on the main carrier, since every `rka_ix_*` is -1 ("parametric, no asset").

    Asking the mesh is better than hand-listing which layers a corner gets: it stays correct when
    a layer is added, and it also drops asset layers automatically until someone actually stamps
    an asset index."""
    inputs = entry.get("inputs") or {}
    # An explicit "this layer needs this attribute to be set somewhere" declaration, for a layer
    # whose switch is not a width or an asset index (the parametric pillar row).
    req = entry.get("require_attr")
    if req:
        vals = _attr_values(mesh, req)
        if vals is None or not any(abs(v) > 1e-6 for v in vals):
            return False
    idx = inputs.get("IndexAttr")
    if idx:
        vals = _attr_values(mesh, idx)
        return bool(vals) and max(vals) >= 0
    for key in ("WidthAttr", "ThicknessAttr"):
        name = inputs.get(key)
        if not name:
            continue
        vals = _attr_values(mesh, name)
        if vals is None or not any(abs(v) > 1e-6 for v in vals):
            return False
    return True


def build_stack(carrier_obj, spec=None):
    """(Re)build the carrier's modifier stack: head, every layer that has content, finish.

    Rebuilt wholesale rather than reconciled, because the stack is DERIVED from the spec -- and
    reconciling a live stack against a spec is exactly the bookkeeping this design exists to
    delete. It is cheap: modifiers hold no geometry, so this is a few dozen property writes."""
    for m in list(carrier_obj.modifiers):
        carrier_obj.modifiers.remove(m)
    head = carrier_obj.modifiers.new("Spine", 'NODES')
    head.node_group = gn.make_spine_group()

    for s in (spec if spec is not None else stack_spec()):
        if not layer_has_content(carrier_obj.data, s):
            continue
        wrapper, ids = gn.wrap_layer(s["inner"], "GN_Layer_" + s["inner"].name)
        mod = carrier_obj.modifiers.new(s["name"], 'NODES')
        mod.node_group = wrapper
        _set(mod, ids, "Offset", float(s.get("offset", 0.0)))
        _set(mod, ids, "OffsetAttr", s.get("offset_attr", "") or "")
        _set(mod, ids, "ZOffset", float(s.get("z", 0.0)))
        _set(mod, ids, "ZOffsetAttr", s.get("z_attr", "") or "")
        for k, v in (s.get("inputs") or {}).items():
            if v is not None:
                _set(mod, ids, k, v)

    tail = carrier_obj.modifiers.new("Finish", 'NODES')
    tail.node_group = gn.make_finish_group()
    return carrier_obj


def _set(mod, ids, name, value):
    """Set one Geometry Nodes modifier input by interface-socket identifier.

    NOT `mod[socket_id] = value`. Older Blenders exposed GN modifier inputs as plain ID-properties
    and that is what most examples still show; this one's `NodesModifier` does not support
    IDProperties at all (`mod["Socket_1"] = 1.0` raises "id properties not supported for this
    type" for EVERY socket, including plain floats -- so it fails loudly rather than silently, at
    least). Inputs live on a structured `mod.properties.inputs`, whose per-socket attributes are
    read-only pointers to a struct carrying the mutable `.value`. `kit_common.set_mod_input`
    records the same finding from the previous time this API moved."""
    if name in ids:
        getattr(mod.properties.inputs, ids[name]).value = value


def build_object(graph_obj, arc_segments=8):
    """Solve, emit the carrier, hang the stack. The whole build, in the order it must happen.

    The junction CORNERS get the very same stack. `graph_solve.build_corner_mesh` writes the same
    per-point attribute names, with every band it does not want set to zero -- so a corner's kerb
    and footway are swept by the identical layers a straight road uses, and there is no second
    description of what a footway looks like to drift out of sync."""
    result = gsolve.solve_object(graph_obj, arc_segments)
    carrier = build_carrier(graph_obj, result)
    build_stack(carrier)
    corners = bpy.data.objects.get(graph_obj.name + gsolve.SUFFIX_CORNERS)
    if corners is not None and len(corners.data.vertices):
        build_stack(corners)
    nodes = bpy.data.objects.get(graph_obj.name + gsolve.SUFFIX_NODES)
    if nodes is not None and len(nodes.data.polygons) and not nodes.data.materials:
        nodes.data.materials.append(material("asphalt"))
    return result, carrier


class RKA_OT_graph_build(bpy.types.Operator):
    """Solve and build the active road graph: carrier, layer stack, node patches, kerb corners."""
    bl_idname = "rka.graph_build"
    bl_label = "Build Road Graph"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return ga.graph_object(context) is not None

    def execute(self, context):
        obj = ga.graph_object(context)
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        result, carrier = build_object(obj)
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, "Built %d carrier polyline(s) from %d node(s)"
                    % (len(carrier.data.vertices), len(result.nodes)))
        return {'FINISHED'}


CLASSES = (RKA_OT_graph_build,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
