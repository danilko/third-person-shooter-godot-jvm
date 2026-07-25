#!/usr/bin/env python3
"""save_roads.py — export hand-authored road_* centerline curves to the district's
git-diffable sidecar districts/<piece>.roads.json.

Authoring loop (PLATEAU districts have no solver grid, so internal traffic spines are
hand-drawn):
  1. Open districts/District_X.blend, draw poly/bezier curves named road_<name> over the
     PLATEAU road meshes (the rebuild re-imports previous ones into ROADS_SRC to continue).
  2. Per curve, set custom props: lanes (per direction, default 1), oneway (default False),
     class ('local'/'arterial'/'oneway', default 'local'), median (physical divider width
     in metres, default 0 — each direction's lane pack shifts out by median/2).
  3. Run:  blender districts/District_X.blend --background --python tools/save_roads.py
  4. Rebuild the district (tools/build_piece.sh <name>) — build_district.py reads the
     sidecar, regenerates the traffic layer (lib/road_graph.py) and re-imports the curves
     into ROADS_SRC. The .blend is disposable; the sidecar is the source of truth.

Curves are exported in WORLD space (object transforms applied). Bezier splines are sampled
BEZ_STEPS per segment; poly splines pass through verbatim. Only the first spline of each
curve object is used (one road per object — split multi-spline objects before saving).
"""
import bpy, json, os

BEZ_STEPS = 8   # samples per bezier segment (road_graph junction-splits on the polyline)


def _spline_points(ob):
    cu = ob.data
    if not cu.splines:
        return []
    sp = cu.splines[0]
    mw = ob.matrix_world
    pts = []
    if sp.type == 'BEZIER' and len(sp.bezier_points) >= 2:
        from mathutils.geometry import interpolate_bezier
        bps = sp.bezier_points
        for i in range(len(bps) - 1):
            seg = interpolate_bezier(bps[i].co, bps[i].handle_right,
                                     bps[i + 1].handle_left, bps[i + 1].co, BEZ_STEPS + 1)
            if i:
                seg = seg[1:]          # don't duplicate the shared knot
            pts.extend(seg)
    else:
        pts = [p.co.to_3d() for p in sp.points]
    return [list(mw @ p) for p in pts]


def main():
    blend = bpy.data.filepath
    if not blend:
        raise SystemExit("save_roads.py: open a district .blend first")
    piece = os.path.splitext(os.path.basename(blend))[0]
    out_path = os.path.join(os.path.dirname(blend), piece + ".roads.json")

    curves = []
    for ob in bpy.data.objects:
        if ob.type != 'CURVE' or not ob.name.startswith("road_"):
            continue
        points = _spline_points(ob)
        if len(points) < 2:
            print(f"  skipping {ob.name}: fewer than 2 points")
            continue
        curves.append({
            "name": ob.name.split(".")[0],   # strip any .001 duplicate suffix
            "lanes": int(ob.get("lanes", 1) or 1),
            "oneway": bool(ob.get("oneway", False)),
            "class": str(ob.get("class", "local") or "local"),
            "median": round(float(ob.get("median", 0.0) or 0.0), 3),
            "points": [[round(c, 3) for c in p] for p in points],
        })

    if not curves:
        raise SystemExit(f"save_roads.py: no road_* curve objects found in {piece}.blend")
    curves.sort(key=lambda c: c["name"])
    with open(out_path, "w") as f:
        json.dump({"piece": piece, "curves": curves}, f, indent=1)
    print(f"save_roads: wrote {len(curves)} curves -> {out_path}")


if __name__ == "__main__":
    main()
