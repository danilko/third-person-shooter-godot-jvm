#!/usr/bin/env python3
"""
plateau_common.py -- PURE PYTHON (no bpy) parsing/reprojection helpers for pulling real PLATEAU
(Japan MLIT open 3D city model, CityGML/OBJ, CC BY 4.0 -- see plateau/ATTRIBUTION.md) data into the
project's world_grid.py local-metre coordinate space.

Used by plateau/extract_plateau.py (the CLI). Same "no bpy" convention as world_grid.py/road_network.py
so it can run outside Blender (e.g. a coverage-check pass) or inside Blender's bundled interpreter.

Coordinate pipeline (see BLENDER_CONVENTIONS.md, no rotation needed):
  PLATEAU tran (roads/rail) ships lat/lon/height in EPSG:6697 (JGD2011 geographic 3D).
  PLATEAU bldg/brid OBJ ships already-projected EPSG:6677 (JGD2011 Plane Rectangular CS IX) metres,
  with authority axis order (northing, easting) -- HENCE THE SWAP in reproject_6697_to_6677 below.
  EPSG:6677's +Y (northing) already matches this project's +Y=north=forward convention 1:1 -- no
  rotation, just a translation to the chosen reference point (the precinct's real-world anchor, e.g.
  Shibuya Scramble Crossing) so it lands at local (0,0), matching build_district.py's piece-at-origin
  convention.
"""
import math
import re
import xml.etree.ElementTree as ET

try:
    import pyproj
except ImportError:  # pyproj is only needed for the tran (lat/lon) path; OBJ (already-projected) works without it
    pyproj = None

TRAN_NS = {
    "tran": "http://www.opengis.net/citygml/transportation/2.0",
    "gml": "http://www.opengis.net/gml",
}


def reference_point(lon, lat, epsg=6677):
    """WGS84 (lon,lat) -> the given projected EPSG (default 6677, JGD2011 Plane Rectangular CS IX --
    Tokyo/Kanto). Osaka/Kansai precincts use EPSG:6674 (Plane Rectangular CS VI) instead -- match
    whatever the source OBJ tiles' filename suffix (`_bldg_<epsg>.obj`) says. This is the precinct's
    local-origin anchor."""
    if pyproj is None:
        raise RuntimeError("pyproj required for reference_point (pip install pyproj)")
    t = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = t.transform(lon, lat)
    return x, y


def _tran_transformer(epsg):
    return pyproj.Transformer.from_crs("EPSG:6697", f"EPSG:{epsg}", always_xy=False)


def parse_tran_roads(paths, ref_x, ref_y, radius_m, epsg=6677):
    """Parse CityGML tran:Road features from one or more *_tran_*.gml files, reproject each
    posList (lat,lon,height, EPSG:6697 -- confirmed true regardless of the file's own `_tran_NNNN_`
    filename suffix, which can be stale/misleading, e.g. Osaka's 2020 tran files are named `_6668_`
    but actually contain EPSG:6697 triples; always check srsName, not the filename, on a new region)
    to the given projected EPSG metres, translate relative to (ref_x, ref_y), and keep only roads whose
    ring-centroid falls within radius_m. Returns (roads, total_count)."""
    t = _tran_transformer(epsg)

    def parse_poslist(text):
        nums = [float(v) for v in text.split()]
        pts = []
        for i in range(0, len(nums), 3):
            lat, lon, h = nums[i], nums[i + 1], nums[i + 2]
            # Target projected CRS authority axis order is (northing, easting) for these JGD2011 Plane
            # Rectangular zones -- swap into (easting, northing).
            y, x, z = t.transform(lat, lon, h)
            pts.append((x - ref_x, y - ref_y, z))
        return pts

    all_roads = []
    for path in paths:
        root = ET.parse(path).getroot()
        for road in root.iter("{%s}Road" % TRAN_NS["tran"]):
            gid = road.get("{%s}id" % TRAN_NS["gml"], "road")
            rings = []
            ms = road.find("tran:lod1MultiSurface", TRAN_NS)
            if ms is None:
                continue
            for poslist in ms.iter("{%s}posList" % TRAN_NS["gml"]):
                rings.append(parse_poslist(poslist.text))
            if rings:
                all_roads.append({"id": gid, "rings": rings})

    def centroid_dist(rings):
        xs = [p[0] for ring in rings for p in ring]
        ys = [p[1] for ring in rings for p in ring]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        return math.hypot(cx, cy)

    near = [r for r in all_roads if centroid_dist(r["rings"]) <= radius_m]
    return near, len(all_roads)


_POSLIST_RE = re.compile(r"<gml:posList>([^<]+)</gml:posList>")


def parse_dem_triangles(paths, ref_lon, ref_lat, radius_m, epsg=6677, deg_pad=0.01):
    """Parse PLATEAU `dem:TINRelief` (terrain, real elevation) GML files -- a real elevation mesh,
    unlike tran (roads, no elevation at LOD1). These files are HUGE (a whole secondary-mesh
    quadrant can be 100s of MB of one-triangle-per-posList XML), so this deliberately does NOT use
    a DOM parser (ET.parse would hold the whole tree in memory) -- instead a regex scan over the
    raw text plus a cheap LAT/LON bounding-box pre-filter (in degrees, before any reprojection)
    keeps only candidate triangles near the target point, and pyproj only runs on those survivors.
    Each posList is 4 points (3 triangle corners + the first point repeated to close the ring) of
    (lat, lon, elevation) triples. Returns a list of triangles, each
    [(x, y, z), (x, y, z), (x, y, z)] in local metres relative to the reference point (same
    convention as parse_tran_roads/parse_obj_components)."""
    t = _tran_transformer(epsg)
    ref_x, ref_y = 0.0, 0.0  # filled by caller's own reference_point() call normally; here we
    # reproject the anchor itself once, the same way, so triangle coords land relative to it.
    ry, rx, _ = t.transform(ref_lat, ref_lon, 0.0)
    lat_pad = deg_pad
    lon_pad = deg_pad / max(0.1, math.cos(math.radians(ref_lat)))
    lat_lo, lat_hi = ref_lat - lat_pad, ref_lat + lat_pad
    lon_lo, lon_hi = ref_lon - lon_pad, ref_lon + lon_pad

    triangles = []
    total = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for m in _POSLIST_RE.finditer(text):
            total += 1
            nums = m.group(1).split()
            # 4 points x 3 numbers; the 4th duplicates the 1st (closed ring) -- keep the first 3.
            lat0, lon0 = float(nums[0]), float(nums[1])
            if not (lat_lo <= lat0 <= lat_hi and lon_lo <= lon0 <= lon_hi):
                continue  # cheap reject before touching pyproj
            pts = []
            for i in range(0, 9, 3):
                lat, lon, h = float(nums[i]), float(nums[i + 1]), float(nums[i + 2])
                y, x, z = t.transform(lat, lon, h)
                pts.append((x - rx, y - ry, z))
            cx = sum(p[0] for p in pts) / 3.0
            cy = sum(p[1] for p in pts) / 3.0
            if math.hypot(cx, cy) <= radius_m:
                triangles.append(pts)
    return triangles, total


def parse_obj(path):
    """Minimal Wavefront OBJ reader -- vertices + faces (0-based), no materials/groups (PLATEAU's
    OBJ export has neither; see connected_components() to recover per-building/per-bridge grouping)."""
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()
                verts.append((float(x), float(y), float(z)))
            elif line.startswith("f "):
                idx = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
                faces.append(tuple(idx))
    return verts, faces


def connected_components(verts, faces):
    """Union-find over faces sharing vertex indices -> list of {verts, faces, cx, cy, z0, z1, height}
    dicts, one per disjoint mesh island (PLATEAU's OBJ export has no per-building/per-bridge grouping,
    so this is how individual buildings/bridge-pieces are recovered from one merged tile mesh)."""
    parent = list(range(len(verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for f in faces:
        for v in f[1:]:
            union(f[0], v)

    groups = {}
    for fi, f in enumerate(faces):
        groups.setdefault(find(f[0]), []).append(fi)

    comps = []
    for face_idxs in groups.values():
        vset = sorted({vi for fi in face_idxs for vi in faces[fi]})
        remap = {vi: k for k, vi in enumerate(vset)}
        cverts = [verts[vi] for vi in vset]
        cfaces = [tuple(remap[vi] for vi in faces[fi]) for fi in face_idxs]
        xs = [v[0] for v in cverts]
        ys = [v[1] for v in cverts]
        zs = [v[2] for v in cverts]
        comps.append({
            "verts": cverts, "faces": cfaces,
            "cx": (min(xs) + max(xs)) / 2, "cy": (min(ys) + max(ys)) / 2,
            "z0": min(zs), "z1": max(zs), "height": max(zs) - min(zs),
        })
    return comps


def parse_obj_components(path, ref_x, ref_y):
    """parse_obj + connected_components, translated relative to (ref_x, ref_y). dist = XY distance
    from the reference point (post-translation), for radius filtering by the caller."""
    verts, faces = parse_obj(path)
    comps = connected_components(verts, faces)
    for c in comps:
        c["verts"] = [(x - ref_x, y - ref_y, z) for (x, y, z) in c["verts"]]
        c["cx"] -= ref_x
        c["cy"] -= ref_y
        c["dist"] = math.hypot(c["cx"], c["cy"])
    return comps
