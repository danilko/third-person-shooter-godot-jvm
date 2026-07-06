#!/usr/bin/env python3
"""
extract_plateau.py -- CLI: pull a real PLATEAU precinct (buildings + roads + bridges, real footprint
+ height, reprojected to local metres relative to a real-world anchor point) into a JSON consumed by
lib/plateau_import.py (a bpy helper build_district.py's `source="plateau"` CONFIG branch calls).

PURE PYTHON (no bpy) -- run with system python3, not Blender's interpreter (needs pyproj).

Usage:
    python3 extract_plateau.py --precinct shibuya --lon 139.70055 --lat 35.65950 --radius 260 \
        --tran <tran_*.gml> [<tran_*.gml> ...] \
        --bldg <tile_bldg_6677.obj> [<tile_bldg_6677.obj> ...] \
        [--brid <tile_brid_6677.obj> [...]] \
        --out data/shibuya.json

See AUTHORING_GUIDE.md for how to obtain the source PLATEAU tiles for a given real-world area (municipality
lookup on the G-Spatial Info Center catalog -> CityGML zip (tran) + Tokyo23kuOBJ-style zip (bldg/brid),
matched by JIS mesh code to the target lon/lat -- the Shibuya precinct's derivation is the worked example).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import plateau_common as pc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--precinct", required=True, help="precinct name, e.g. shibuya")
    ap.add_argument("--lon", type=float, required=True, help="real-world anchor longitude (WGS84)")
    ap.add_argument("--lat", type=float, required=True, help="real-world anchor latitude (WGS84)")
    ap.add_argument("--radius", type=float, default=260.0, help="clip radius in metres (default 260, fits a 504m district)")
    ap.add_argument("--epsg", type=int, default=6677, help="target projected CRS (6677=Tokyo/Kanto default, 6674=Osaka/Kansai -- match the source OBJ tiles' `_bldg_<epsg>.obj` filename suffix)")
    ap.add_argument("--tran", nargs="*", default=[], help="CityGML *_tran_*.gml file(s) (road polygons)")
    ap.add_argument("--bldg", nargs="*", default=[], help="PLATEAU OBJ *_bldg_6677.obj tile file(s) (LOD1/2 buildings)")
    ap.add_argument("--brid", nargs="*", default=[], help="PLATEAU OBJ *_brid_6677.obj tile file(s) (bridges)")
    ap.add_argument("--dem", nargs="*", default=[], help="CityGML *_dem_*.gml file(s) (real terrain elevation, dem:TINRelief -- these files are large, expect real processing time)")
    ap.add_argument("--out", required=True, help="output JSON path")
    args = ap.parse_args()

    ref_x, ref_y = pc.reference_point(args.lon, args.lat, epsg=args.epsg)
    print(f"[{args.precinct}] anchor EPSG:{args.epsg} = ({ref_x:.2f}, {ref_y:.2f})", file=sys.stderr)

    roads, roads_total = ([], 0)
    if args.tran:
        roads, roads_total = pc.parse_tran_roads(args.tran, ref_x, ref_y, args.radius, epsg=args.epsg)
        print(f"[{args.precinct}] roads: {len(roads)} kept / {roads_total} total in source tiles", file=sys.stderr)

    buildings_total = 0
    buildings = []
    ground_z = None
    for path in args.bldg:
        comps = pc.parse_obj_components(path, ref_x, ref_y)
        buildings_total += len(comps)
        buildings.extend(c for c in comps if c["dist"] <= args.radius)
    if buildings:
        close = [c for c in buildings if c["dist"] <= 60.0]
        ground_z = min((c["z0"] for c in close), default=min(c["z0"] for c in buildings))
        buildings.sort(key=lambda c: -c["height"])
        print(f"[{args.precinct}] buildings: {len(buildings)} kept / {buildings_total} total; "
              f"ground_z={ground_z:.2f}; tallest 5={[round(c['height'],1) for c in buildings[:5]]}",
              file=sys.stderr)

    bridges_total = 0
    bridges = []
    for path in args.brid:
        comps = pc.parse_obj_components(path, ref_x, ref_y)
        bridges_total += len(comps)
        bridges.extend(c for c in comps if c["dist"] <= args.radius)
    if bridges:
        print(f"[{args.precinct}] bridges: {len(bridges)} kept / {bridges_total} total", file=sys.stderr)

    terrain = []
    terrain_total = 0
    if args.dem:
        terrain, terrain_total = pc.parse_dem_triangles(args.dem, args.lon, args.lat, args.radius,
                                                         epsg=args.epsg, deg_pad=args.radius / 90000.0 + 0.002)
        if terrain:
            zs = [p[2] for tri in terrain for p in tri]
            print(f"[{args.precinct}] terrain: {len(terrain)} triangles kept / {terrain_total} scanned; "
                  f"elevation range {min(zs):.1f}-{max(zs):.1f}m", file=sys.stderr)
            if ground_z is None:
                # no buildings were found to derive a ground datum from (e.g. a road-only mountain
                # precinct) -- fall back to the terrain's own elevation nearest the anchor, so the
                # precinct's local Z=0 lands at "real ground here", not at 0m absolute (which would
                # otherwise place a ~1300m-elevation mountain precinct's ground ~1300m above the
                # world origin).
                near0 = min(((p[0] ** 2 + p[1] ** 2, p[2]) for tri in terrain for p in tri),
                            key=lambda t: t[0])
                ground_z = near0[1]
                print(f"[{args.precinct}] ground_z derived from terrain near anchor: {ground_z:.2f}",
                      file=sys.stderr)

    out = {
        "precinct": args.precinct,
        "reference_lonlat": [args.lon, args.lat],
        "reference_epsg6677": [ref_x, ref_y],
        "radius_m": args.radius,
        "ground_reference_elevation_m": ground_z,
        "roads": roads,
        "roads_total_in_tiles": roads_total,
        "buildings": [{"verts": c["verts"], "faces": c["faces"], "height": c["height"],
                        "cx": c["cx"], "cy": c["cy"]} for c in buildings],
        "buildings_total_in_tiles": buildings_total,
        "bridges": [{"verts": c["verts"], "faces": c["faces"], "height": c["height"],
                      "cx": c["cx"], "cy": c["cy"]} for c in bridges],
        "bridges_total_in_tiles": bridges_total,
        "terrain": terrain,
        "terrain_total_in_tiles": terrain_total,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f)
    print(f"[{args.precinct}] wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
