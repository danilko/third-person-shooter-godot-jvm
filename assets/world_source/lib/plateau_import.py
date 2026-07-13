#!/usr/bin/env python3
"""
plateau_import.py -- bpy helper: turns a plateau/extract_plateau.py JSON (real building meshes,
bridge meshes, road footprint polygons, all pre-translated to local metres relative to the precinct's
real-world anchor point) into Blender objects, for build_district.py's `source="plateau"` CONFIG branch.

Placeholder scope (see PLAN.md's condensed-Tokyo-landmarks plan): buildings/bridges import the real
PLATEAU mesh as-is (a usable placeholder at real footprint+height); roads are extruded slabs from the
real footprint polygon at a placeholder thickness, intended for later hand-replacement with real kit
road tiles -- NOT a final art asset. PLATEAU's tran module carries no road elevation at LOD1, so
roads are FLAT unless real DEM terrain data was also extracted (`--dem`, see extract_plateau.py) --
when present, `TerrainSampler`/`import_terrain` build a real sloped ground mesh and roads are
draped onto it (their top face follows the real terrain height at each point, not a flat plane).
"""
import bpy
import json
import math

import kit_common as kc

ROAD_THICKNESS = 0.30


def load(json_path):
    with open(json_path) as f:
        return json.load(f)


def _mesh_object(name, coll, verts, faces, ox, oy, oz, rot_deg=0.0):
    """Build a mesh object from raw (verts, faces), translated by (ox,oy,oz) and optionally
    rotated about Z first (rot_deg) -- used when a real feature's own orientation (e.g. a bridge's
    real span direction) doesn't match the direction it needs to sit in the game world; this
    project is a compressed/rearranged "greatest hits" collage, not literal geography, so
    reorienting a landmark to fit its assigned game-world slot is expected, not a distortion."""
    if rot_deg:
        a = math.radians(rot_deg)
        ca, sa = math.cos(a), math.sin(a)
        verts = [(x * ca - y * sa, x * sa + y * ca, z) for (x, y, z) in verts]
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x + ox, y + oy, z - oz) for (x, y, z) in verts], [], faces)
    me.update()
    me.validate()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    return obj


def _extrude_polygon(name, coll, ring_xy, z0, z1, ox, oy, top_zs=None):
    """Extrude a footprint ring into a slab. `z0`/`z1` are the default flat bottom/top; if
    `top_zs` (one value per ring_xy point) is given, the TOP follows those per-point heights
    instead (draping onto real terrain -- see TerrainSampler) while the bottom stays `z0` below
    each point's own top (a constant-thickness slab following the slope, not a flat deck)."""
    n = len(ring_xy)
    if n < 3:
        return None
    if top_zs is not None:
        tops = top_zs
        bottoms = [t - (z1 - z0) for t in tops]
    else:
        tops = [z1] * n
        bottoms = [z0] * n
    verts = [(x + ox, y + oy, bz) for (x, y), bz in zip(ring_xy, bottoms)] + \
            [(x + ox, y + oy, tz) for (x, y), tz in zip(ring_xy, tops)]
    bottom = tuple(range(n))[::-1]
    top = tuple(range(n, 2 * n))
    sides = [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [bottom, top] + sides)
    me.update()
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    return obj


class TerrainSampler:
    """Grid-bucketed nearest-triangle-centroid height lookup over a list of real DEM triangles
    (see plateau_common.parse_dem_triangles) -- placeholder-quality (nearest centroid, not
    barycentric-interpolated), same idiom as the codebase's other spatial grids (SpatialEntityGrid
    etc). Triangles are already in the SAME local-metre frame as everything else in the JSON
    (relative to the precinct's real-world anchor)."""

    CELL = 10.0

    def __init__(self, triangles):
        self.buckets = {}
        self.centroids = []
        for tri in triangles:
            cx = sum(p[0] for p in tri) / 3.0
            cy = sum(p[1] for p in tri) / 3.0
            cz = sum(p[2] for p in tri) / 3.0
            idx = len(self.centroids)
            self.centroids.append((cx, cy, cz))
            key = (round(cx / self.CELL), round(cy / self.CELL))
            self.buckets.setdefault(key, []).append(idx)

    def height_at(self, x, y):
        if not self.centroids:
            return None
        kx, ky = round(x / self.CELL), round(y / self.CELL)
        best = None
        best_d2 = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for idx in self.buckets.get((kx + dx, ky + dy), ()):
                    cx, cy, cz = self.centroids[idx]
                    d2 = (cx - x) ** 2 + (cy - y) ** 2
                    if best_d2 is None or d2 < best_d2:
                        best_d2, best = d2, cz
        if best is not None:
            return best
        # fall back to a full scan if the point's 3x3 neighbourhood happened to be empty
        # (a sparse edge of the extracted patch) -- rare, so an O(n) scan here is fine.
        return min(self.centroids, key=lambda c: (c[0] - x) ** 2 + (c[1] - y) ** 2)[2]


def import_terrain(coll, triangles, ox, oy, ground_ref, tag="Terrain", edge_half=None):
    """Build ONE real terrain mesh (visual + collision, `-col` suffix per BLENDER_CONVENTIONS --
    the visual IS the collision proxy here, no separate box) from real DEM triangles, translated by
    (ox, oy) and by -ground_ref in Z (so it lands in the same locally-zeroed ground frame every
    other object in the precinct already uses). Returns the object, or None if no triangles.

    `edge_half`: if given, triangles whose centroid falls outside the +/-edge_half district square
    are dropped -- the DEM clip is RADIAL (extract_plateau.py), so a radius big enough to cover the
    square's corners (356+ m) also overhangs its edge midpoints (252 m) by ~100 m; unclipped, that
    overhang pokes into the NEIGHBOURING district's footprint at this district's own ground datum
    (wrong elevation there -- seam z-fighting, bumps under the boundary arterial deck)."""
    if not triangles:
        return None
    if edge_half is not None:
        triangles = [tri for tri in triangles
                     if abs(sum(p[0] for p in tri) / 3.0) <= edge_half
                     and abs(sum(p[1] for p in tri) / 3.0) <= edge_half]
        if not triangles:
            return None
    verts, faces = [], []
    for tri in triangles:
        base = len(verts)
        verts.extend((x + ox, y + oy, z - ground_ref) for (x, y, z) in tri)
        faces.append((base, base + 1, base + 2))
    me = bpy.data.meshes.new(f"{tag}-col")
    me.from_pydata(verts, [], faces)
    me.update()
    me.validate()
    obj = bpy.data.objects.new(f"{tag}-col", me)
    coll.objects.link(obj)
    obj.data.materials.append(kc.mat("dirt"))
    return obj


def _footprint_area(verts):
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def import_components(coll, components, ox, oy, ground_ref, world_z, tag, rot_deg=0.0, colonly=True,
                       max_footprint_area=None):
    """General-purpose version of the buildings/bridges half of import_precinct(), for placing a
    raw list of {verts, faces, height, ...} dicts (e.g. a loaded JSON's "buildings" or "bridges"
    list) at an ARBITRARY world position/rotation -- used by build_world.py to drop a landmark's
    real components into the master layout's own grid-space coordinates (which don't share a
    precinct's own at-origin convention), unlike import_precinct() which always places at a
    precinct's local origin.

    `ground_ref` = the JSON's own ground_reference_elevation_m (the raw absolute elevation that
    counts as "ground" for this extraction); `world_z` = the target world Z that ground level
    should land at (e.g. the harbor island's own surface height). Real height above ground is
    preserved; only the ground datum shifts.

    `max_footprint_area`: skip any component whose XY bounding-box footprint exceeds this (m^2).
    A real bridge's own extraction radius can sweep up unrelated large nearby structures (a big
    building, an elevated-highway interchange platform) tagged the same "bridge" module -- found
    for Rainbow Bridge via a rendered close-up: 2 of its 134 "bridge" components were ~750x300m
    slabs (nothing at real bridge scale is that wide), visually a giant flat plate burying the
    runway/island next to it. The genuine tower/cable/deck/pier components are all far smaller
    (the real tower is ~17x35m footprint at 124m tall) so a generous area cap cleanly drops the
    outliers without touching legitimate bridge structure. Returns (count, total_verts, total_faces,
    skipped_count)."""
    tv = tf = 0
    skipped = 0
    oz = ground_ref - world_z
    for i, c in enumerate(components):
        if max_footprint_area is not None and _footprint_area(c["verts"]) > max_footprint_area:
            skipped += 1
            continue
        name = f"{tag}_{i:03d}_h{c['height']:.0f}m"
        obj = _mesh_object(name, coll, c["verts"], c["faces"], ox, oy, oz, rot_deg=rot_deg)
        if colonly:
            kc.colonly_mesh(obj, coll=coll)
        tv += len(c["verts"]); tf += len(c["faces"])
    return len(components) - skipped, tv, tf, skipped


def _join_all(objs, name):
    """Join every object in `objs` into ONE mesh object named `name` (single-object case just
    renames -- no join needed). Same select/active/join idiom as build_infra_elevated.py's
    `_weld()`. Used to collapse a district's many per-polygon road slabs into one mesh."""
    if not objs:
        return None
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def _crosses_edge_margin(verts, half, margin):
    """True if any vertex of a building/bridge footprint falls within `margin` metres of the true
    +/-half district boundary on either the X or Y axis (in the SAME pre-offset, anchor-centred
    frame the raw JSON verts are already in). Used to hold real buildings back from the district
    edge so a neighbouring piece's connector-stub road always finds clear ground to enter through
    -- real PLATEAU buildings are placed at their true extraction position with no awareness of
    where a neighbour's connector needs to land, and were found (via a rendered close-up of the
    Shibuya/resid_0_1 seam) to form a solid wall right across the boundary with no gap at all."""
    if half is None:
        return False
    limit = half - margin
    for (x, y, _z) in verts:
        if abs(x) > limit or abs(y) > limit:
            return True
    return False


def import_precinct(coll, data, offset_x, offset_y, tag="PLATEAU", edge_half=None, edge_margin=20.0):
    """Build every building/bridge/road object from a loaded extract_plateau.py JSON into `coll`,
    shifted by (offset_x, offset_y) -- the piece's own pre-recenter half-extent, so the real-world
    anchor point lands at local (offset_x, offset_y) and recenter() brings it to true origin exactly
    like every procedurally-built object in build_district.py. Returns a stats dict for the caller's
    build-summary print.

    `edge_half`/`edge_margin`: if `edge_half` is given (the true district half-extent, e.g. 252 for
    a full-footprint real precinct), any building/bridge whose footprint comes within `edge_margin`
    metres of that boundary on either axis is SKIPPED -- reserving a clear perimeter strip so
    ANY neighbouring piece's connector-stub (procedural or another real precinct) has open ground
    to route through, regardless of which specific edge/heading it enters at."""
    ground_z = data.get("ground_reference_elevation_m") or 0.0

    b_verts = b_faces = 0
    b_skipped = 0
    for i, b in enumerate(data["buildings"]):
        if _crosses_edge_margin(b["verts"], edge_half, edge_margin):
            b_skipped += 1
            continue
        tag_kind = "Landmark" if i < 3 else "Bldg"
        name = f"{tag}_{tag_kind}_{i:03d}_h{b['height']:.0f}m"
        obj = _mesh_object(name, coll, b["verts"], b["faces"], offset_x, offset_y, ground_z)
        kc.colonly_mesh(obj, coll=coll)
        b_verts += len(b["verts"]); b_faces += len(b["faces"])

    br_verts = br_faces = 0
    br_skipped = 0
    for i, br in enumerate(data["bridges"]):
        if _crosses_edge_margin(br["verts"], edge_half, edge_margin):
            br_skipped += 1
            continue
        name = f"{tag}_Bridge_{i:03d}_h{br['height']:.0f}m"
        obj = _mesh_object(name, coll, br["verts"], br["faces"], offset_x, offset_y, ground_z)
        kc.colonly_mesh(obj, coll=coll)
        br_verts += len(br["verts"]); br_faces += len(br["faces"])

    terrain_tris = data.get("terrain") or []
    sampler = TerrainSampler(terrain_tris) if terrain_tris else None
    terrain_obj = None
    if sampler:
        # NB: the sampler above keeps the FULL (unclipped) triangle set so road draping still has
        # height data right up to the district edge; only the built mesh is clipped to the square.
        terrain_obj = import_terrain(coll, terrain_tris, offset_x, offset_y, ground_z,
                                     tag=f"{tag}_Terrain", edge_half=edge_half)

    r_count = 0
    road_objs = []
    for i, r in enumerate(data["roads"]):
        ring = r["rings"][0]
        xy = [(p[0], p[1]) for p in ring[:-1]] if ring[0] == ring[-1] else [(p[0], p[1]) for p in ring]
        top_zs = [sampler.height_at(x, y) - ground_z for x, y in xy] if sampler else None
        obj = _extrude_polygon(f"{tag}_Road_{i:03d}", coll, xy, -ROAD_THICKNESS, 0.0, offset_x, offset_y,
                               top_zs=top_zs)
        if obj:
            obj.data.materials.append(kc.mat("asphalt"))
            road_objs.append(obj)
            r_count += 1

    # Combine every per-polygon road slab into ONE mesh -- one object/node per district instead
    # of (often) dozens, all sharing the same "asphalt" material and carrying no per-object
    # collision of their own (what's walkable is the real terrain mesh when DEM was extracted,
    # else the district's flat GroundSafety box).
    _join_all(road_objs, f"{tag}_Road")

    # Does the (radial) DEM clip cover the whole district square, corners included? If so the
    # terrain mesh IS the district ground and the caller can skip the flat GroundSafety plane
    # (which would otherwise poke above real terrain anywhere the ground dips below its own
    # elev-1.0 slab level -- an invisible floor hovering over every real valley).
    terrain_radius = data.get("terrain_radius_m", data.get("radius_m", 0.0)) if terrain_tris else 0.0
    covers = terrain_obj is not None and edge_half is not None and \
        terrain_radius >= math.hypot(edge_half, edge_half) - 1e-6

    return {
        "buildings": len(data["buildings"]) - b_skipped, "buildings_total": data.get("buildings_total_in_tiles", 0),
        "bridges": len(data["bridges"]) - br_skipped, "roads": r_count,
        "roads_total": data.get("roads_total_in_tiles", 0),
        "building_verts": b_verts, "building_faces": b_faces,
        "terrain_triangles": len(terrain_tris), "has_terrain": terrain_obj is not None,
        "terrain_covers_square": covers,
        "edge_clipped": b_skipped + br_skipped,
    }


def nearest_edge_point(data, edge, ax, reach):
    """Find the extracted road ring-vertex closest to district edge `edge` ('N'/'S'/'E'/'W') at
    arterial-centreline coordinate `ax`, `reach` from the precinct's own local origin (pre-offset,
    i.e. still in extract_plateau.py's reference-point-centred coordinates). Returns (x, y, heading_rad)
    of the nearest ring vertex + the direction along the ring at that point, or None if no roads are
    close enough (caller falls back to the generic connector heading).
    Placeholder scope: nearest-point only -- does not yet snap the connector stub to the exact road
    width/lane count, see PLAN.md section 3."""
    target = {
        "N": (ax, reach), "S": (ax, -reach),
        "E": (reach, ax), "W": (-reach, ax),
    }[edge]
    best = None
    best_d2 = None
    for r in data["roads"]:
        for ring in r["rings"]:
            for i, p in enumerate(ring):
                dx, dy = p[0] - target[0], p[1] - target[1]
                d2 = dx * dx + dy * dy
                if best_d2 is None or d2 < best_d2:
                    nxt = ring[(i + 1) % len(ring)]
                    heading = math.atan2(nxt[1] - p[1], nxt[0] - p[0])
                    best = (p[0], p[1], heading)
                    best_d2 = d2
    return best
