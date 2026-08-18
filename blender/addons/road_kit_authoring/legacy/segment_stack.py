"""segment_stack.py -- turn a segment's build parameters into a `road_stack` layer list.

This is the seam between "what the operator asked for" (lane counts, curb style, sidewalk widths,
prop assets) and "what the modifier stack needs" (a signed lateral offset and a profile/asset per
layer). It is deliberately the ONLY place that translation happens, for the reason the whole
redesign exists: the three 2026-08 defects were all two consumers deriving the same cross-section
with different conventions. Every offset below comes from `lane_profile`, and every one of them
reproduces the formula `intersection_kit.build_segment_from_spine` already uses for the same part,
so the stack and the exported lane data cannot drift.

THE OFFSETS, and where each matches the existing Python builder:

    pavement      centre shifted by (pos - neg) / 2, half-width (pos + neg) / 2
                  == `sweep_radius_and_shift(*paved_extents(profile))`
    curb L / R    +pos / -neg                     == `seg["curbs"] = [offset_line(pos_w),
                                                       offset_line(-neg_w)]`
    sidewalk L    +(pos + curb_clearance_l + w/2)  == `seg["sidewalks"]["L"]`
    sidewalk R    -(neg + curb_clearance_r + w/2)  == `seg["sidewalks"]["R"]`
    median         0        the spine IS the median centreline (both lane groups are offset
                            outward from it by median_half), so no offset line is needed
    props L / R   the sidewalk centre when that side has a sidewalk, else that side's curb line
                  -- the same "props sit on the sidewalk if there is one, else align to the
                  street" rule the sibling-object builder applied

SIGN. Offsets here are in `lane_profile`'s driving frame (`+s` = forward-lane side). The single
`traffic_side` flip is applied by `road_stack.write_layer_offset`, matching
`intersection_kit.lane_perp` -- so nothing in this module ever branches on traffic side, and the
flip cannot be applied twice.

PER-POINT, NOT PER-PIECE. Each offset is written as a per-vertex attribute sampled from the
`ProfileSet`, not as a constant, so a piece whose lane count changes along its length carries its
curb and sidewalk outward with it continuously. That is exactly what the old model could not do:
a varying cross-section had to become several pieces (`trunk_before` / `trunk_taper` /
`trunk_aux`), which is why a split had no lane data and could not be adjusted.
"""
import bpy

import lane_profile as lp
import road_stack as rs

# Attribute names for the per-point lateral offset of each layer. One per layer so each can vary
# independently along the piece; `road_stack` reads them by name through the layer's `OffsetAttr`.
ATTR_CURB_L = "rka_off_curb_l"
ATTR_CURB_R = "rka_off_curb_r"
ATTR_SW_L = "rka_off_sw_l"
ATTR_SW_R = "rka_off_sw_r"
ATTR_PROP_L = "rka_off_prop_l"
ATTR_PROP_R = "rka_off_prop_r"


_PROFILE_CACHE = {}


def _profile_obj(key, name, pts2d, cyclic=False):
    """A cached, un-linked 2D profile Curve for `GN_ProfileSweep`: local X = lateral, local Y = UP.

    NOTE THE SIGN, because there are two conventions in this file's neighbourhood and they differ.
    `GN_CurbLoop` maps a profile's local +Y to world -Z, so `kit_common._curb_profile_object`
    NEGATES its heights to compensate. `GN_ProfileSweep` (the stack's single sweep group) maps +Y
    to world +Z, so a profile authored for the old group arrives upside down and every curb hangs
    below the road. These builders therefore state heights positive-up and are deliberately NOT
    shared with the curb-loop path -- one object cannot satisfy both mappings, and quietly reusing
    it is how the "curb is under the road" defect happened the first time.

    Cached like `_curb_profile_object` (same reasons: live-edit rebuilds must not leak a datablock
    per rebuild, and a cross-file stale reference raises `ReferenceError` on any attribute access,
    so the staleness probe has to be guarded rather than a bare read). Not linked into any
    collection -- referenced only through an Object Info node, never rendered or exported."""
    obj = _PROFILE_CACHE.get(key)
    try:
        if obj is not None and obj.name in bpy.data.objects:
            return obj
    except ReferenceError:
        pass
    cu = bpy.data.curves.new(name + "_cu", 'CURVE')
    cu.dimensions = '3D'
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts2d) - 1)
    for i, (x, y) in enumerate(pts2d):
        sp.points[i].co = (x, y, 0.0, 1.0)
    sp.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, cu)
    _PROFILE_CACHE[key] = obj
    return obj


def curb_profile_object(style, height, thickness):
    """A curb cross-section for the stack. `NONE` yields None, which `layers_for_segment` treats
    as "no such layer" -- so a curb-less road simply has no curb modifier, rather than a modifier
    producing nothing."""
    if not style or style == 'NONE' or height <= 0.0 or thickness <= 0.0:
        return None
    half = thickness / 2.0
    return _profile_obj(("curb", style, round(height, 4), round(thickness, 4)),
                        "RKA_StackCurb_%s" % style,
                        [(-half, 0.0), (half, 0.0), (half, height), (-half, height)],
                        cyclic=True)


def sidewalk_profile_object(width, height):
    """A sidewalk slab: `width` across, `height` proud of the carriageway."""
    if width <= 0.0 or height <= 0.0:
        return None
    half = width / 2.0
    return _profile_obj(("sw", round(width, 4), round(height, 4)), "RKA_StackSidewalk",
                        [(-half, 0.0), (half, 0.0), (half, height), (-half, height)],
                        cyclic=True)


def median_profile_object(width, height):
    """A raised median island, centred on the spine (which IS the median centreline)."""
    if width <= 0.0 or height <= 0.0:
        return None
    half = width / 2.0
    return _profile_obj(("med", round(width, 4), round(height, 4)), "RKA_StackMedian",
                        [(-half, 0.0), (half, 0.0), (half, height), (-half, height)],
                        cyclic=True)


def _edge(profile, side):
    neg, pos = lp.paved_extents(profile)
    return pos if side == "L" else -neg


def _sidewalk_centre(profile, side, width, clearance):
    """Centre of the sidewalk strip on `side`: just outside the paved edge, past whatever the curb
    itself occupies (`clearance`), then half its own width. `curb_outer_clearance` is what stops a
    BOX curb's outer half or an asset curb's real footprint overlapping the sidewalk -- the same
    quantity `build_segment_from_spine` takes as `curb_clearance_l`/`_r`."""
    if width <= 0.0:
        return _edge(profile, side)
    e = _edge(profile, side)
    out = clearance + width / 2.0
    return e + out if side == "L" else e - out


def layers_for_segment(spine_obj, profile_set, traffic_side='LEFT',
                       curb_l_profile=None, curb_r_profile=None, curb_matkey="concrete",
                       median_profile=None,
                       sidewalk_l_width=0.0, sidewalk_r_width=0.0,
                       sidewalk_l_profile=None, sidewalk_r_profile=None,
                       curb_clearance_l=0.0, curb_clearance_r=0.0,
                       prop_l_asset=None, prop_l_spacing=30.0,
                       prop_r_asset=None, prop_r_spacing=30.0,
                       skip_object=None, skip_radius=0.0,
                       pave_matkey="asphalt", mat=None):
    """Write every per-point offset attribute onto `spine_obj` and return the layer list to hand
    `road_stack.build_stack`. `mat` is `kit_common.mat` (passed in so this module stays free of a
    `kit_common` import and therefore trivially unit-testable).

    A layer whose asset/profile does not resolve is simply OMITTED -- the same "no piece = no
    geometry" convention `curb_loop` already has, and the reason `curb_style='NONE'` needs no
    special case here: the caller passes no profile and the layer never exists."""
    attrs = rs.spine_attributes_for(profile_set, len(spine_obj.data.vertices), traffic_side)
    rs.write_spine_attributes(spine_obj, attrs)

    def off(attr, fn):
        rs.write_layer_offset(spine_obj, attr, profile_set, fn, traffic_side)
        return attr

    layers = [rs.layer("Pavement", rs.make_pavement_group(), offset_attr=rs.ATTR_SHIFT,
                       Material=mat(pave_matkey))]

    for side, prof, attr in (("L", curb_l_profile, ATTR_CURB_L),
                             ("R", curb_r_profile, ATTR_CURB_R)):
        if prof is None:
            continue
        layers.append(rs.layer(
            "Curb" + side, rs.make_profile_sweep_group(),
            offset_attr=off(attr, lambda p, s=side: _edge(p, s)),
            Profile=prof, Material=mat(curb_matkey)))

    # The median rides the spine itself -- offset 0, no attribute needed.
    if median_profile is not None:
        layers.append(rs.layer("Median", rs.make_profile_sweep_group(),
                               Profile=median_profile, Material=mat(curb_matkey)))

    for side, w, prof, clear, attr in (
            ("L", sidewalk_l_width, sidewalk_l_profile, curb_clearance_l, ATTR_SW_L),
            ("R", sidewalk_r_width, sidewalk_r_profile, curb_clearance_r, ATTR_SW_R)):
        if w <= 0.0 or prof is None:
            continue
        layers.append(rs.layer(
            "Sidewalk" + side, rs.make_profile_sweep_group(),
            offset_attr=off(attr, lambda p, s=side, ww=w, c=clear: _sidewalk_centre(p, s, ww, c)),
            Profile=prof, Material=mat(curb_matkey)))

    for side, asset, spacing, w, clear, attr in (
            ("L", prop_l_asset, prop_l_spacing, sidewalk_l_width, curb_clearance_l, ATTR_PROP_L),
            ("R", prop_r_asset, prop_r_spacing, sidewalk_r_width, curb_clearance_r, ATTR_PROP_R)):
        if asset is None:
            continue
        has_sw = w > 0.0 and (sidewalk_l_profile if side == "L" else sidewalk_r_profile) is not None
        layers.append(rs.layer(
            "Prop" + side, rs.make_asset_row_group(),
            offset_attr=off(attr, (lambda p, s=side, ww=w, c=clear: _sidewalk_centre(p, s, ww, c))
                            if has_sw else (lambda p, s=side: _edge(p, s))),
            Object=asset, Spacing=spacing,
            # R is rotated 180 deg to face the street from the far side, and STAGGERED half a
            # spacing so poles do not line up straight across from each other -- the real-world
            # alternating-sides convention the sibling-object builder already applied via
            # `curb_asset_row(phase_offset=...)`. `Phase` here is a 0..1 curve fraction, so the
            # half-spacing is expressed relative to the piece, not in metres.
            RotOffset=3.141592653589793 if side == "R" else 0.0,
            Phase=0.0 if side == "L" else _half_spacing_fraction(spine_obj, spacing),
            Skip=skip_object, SkipRadius=skip_radius))

    return layers


def _half_spacing_fraction(spine_obj, spacing):
    """Half a spacing expressed as a fraction of the piece's length, for `GN_AssetRow`'s `Phase`
    (a Trim Curve factor). Uses the straight-line control-point length, which is exact for the
    POLY spines this addon builds. Clamped below 0.5 so a very short piece cannot trim itself to
    nothing and end up with no props at all."""
    from mathutils import Vector
    vs = [Vector(v.co) for v in spine_obj.data.vertices]
    total = sum((vs[i + 1] - vs[i]).length for i in range(len(vs) - 1)) if len(vs) > 1 else 0.0
    if total <= 0.0 or spacing <= 0.0:
        return 0.0
    return min(0.49, (spacing / 2.0) / total)
