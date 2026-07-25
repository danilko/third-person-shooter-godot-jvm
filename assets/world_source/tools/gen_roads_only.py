#!/usr/bin/env python3
"""gen_roads_only.py — regenerate the traffic layer for a HAND-AUTHORED district blend.

The stem-form bake (`tools/build_piece.sh District_<...>`) deliberately skips the
build_district.py regen, so a district that was never generated from a CONFIG entry (a
road-kit demo, a fully hand-modeled piece) has nobody to turn its ROADS_SRC curves into
lane_/intersection_ markers. This tool is that missing step, run IN PLACE on the open blend:

  1. collect every LOCAL curve object named road_* (props: lanes / oneway / class / median —
     same table as save_roads.py; bezier splines sampled identically via
     save_roads._spline_points, world space);
  2. wipe ONLY this piece's previously generated markers (lane_<piece>__* /
     intersection_<piece>__*) from the local MARKERS collection — seam_/spawn_/water_ and
     anything else is never touched;
  3. run lib/road_graph.py via assemble.lay_road_graph under the piece's route prefix
     (identical to the generated-district path, so runtime naming matches);
  4. re-export the sidecar districts/<piece>.roads.json (save_roads.main(); skip with
     `-- --no-sidecar`) — the sidecar stays the source of truth either way;
  5. save the blend.

Loop for hand-authored districts:
    draw/edit road_* curves
    blender districts/<X>.blend --background --python tools/gen_roads_only.py
    tools/build_piece.sh <X>          # stem form, bake-only
    (SoloPiece walk-test, F4 = a car on every route)
"""
import bpy, os, sys

BP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # assets/world_source
sys.path.insert(0, os.path.join(BP, "lib"))
sys.path.insert(0, os.path.join(BP, "tools"))
import assemble as asm          # noqa: E402
import road_graph as rgm        # noqa: E402
import save_roads               # noqa: E402


def collect_curves():
    """[(stem, [(x,y,z)...], props)] for every local road_* curve — the road_ prefix is
    stripped from the route stem (same 63-char-name-cap rule as emit_authored_roads)."""
    curves = []
    for ob in bpy.data.objects:
        if ob.type != 'CURVE' or not ob.name.startswith("road_") or ob.library is not None:
            continue
        pts = save_roads._spline_points(ob)
        if len(pts) < 2:
            print(f"  skipping {ob.name}: fewer than 2 points")
            continue
        stem = ob.name.split(".")[0][len("road_"):]
        curves.append((stem, [tuple(p) for p in pts],
                       {"lanes": int(ob.get("lanes", 1) or 1),
                        "oneway": bool(ob.get("oneway", False)),
                        "class": str(ob.get("class", "local") or "local"),
                        "median": float(ob.get("median", 0.0) or 0.0)}))
    return curves


def clear_generated(piece):
    """Drop ONLY this piece's generated traffic markers (local objects); everything else in
    MARKERS (seam routes, spawns, water) survives."""
    lane_pfx = f"lane_{piece}__"
    ix_pfx = f"intersection_{piece}__"
    doomed = [o for o in bpy.data.objects if o.library is None
              and (o.name.startswith(lane_pfx) or o.name.startswith(ix_pfx))]
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)
    return len(doomed)


def generate(write_sidecar=True):
    """The reusable driver (build_kitdemo.py calls this in-process)."""
    blend = bpy.data.filepath
    if not blend:
        raise SystemExit("gen_roads_only.py: open (or save) a district .blend first")
    piece = os.path.splitext(os.path.basename(blend))[0]

    curves = collect_curves()
    if not curves:
        raise SystemExit(f"gen_roads_only.py: no road_* curves found in {piece}.blend")
    n_cleared = clear_generated(piece)
    asm.set_route_prefix(piece)
    n_lane, n_conn, n_ix = asm.lay_road_graph(rgm.from_curves(curves), z_off=0.3)
    if write_sidecar:
        save_roads.main()
    print(f"gen_roads_only: {piece} — cleared {n_cleared} old markers; "
          f"lanes={n_lane} connectors={n_conn} junctions={n_ix}"
          + ("" if write_sidecar else "  (sidecar not written)"))
    return n_lane, n_conn, n_ix


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    generate(write_sidecar="--no-sidecar" not in argv)
    # view-layer deselect guard (same None-slot idiom as build_district / export_world)
    for o in list(bpy.context.view_layer.objects):
        if o is not None:
            o.select_set(False)
    bpy.ops.wm.save_mainfile()


if __name__ == "__main__":
    main()
