"""point_gltf.py -- a road piece as glTF, with no Blender (PLAN.md 3.1 B11).

`point_mesh.build` gives `{object: {material name: [triangle]}}` in the kit frame. This writes it as the `.gltf` +
`.bin` pair `export_world.py` used to write from a Blender session, so everything downstream is unchanged:
Godot imports it, `WorldBaker` bakes the piece scene (lanes from the lanekit sidecar), `NavBaker` bakes the
navmesh. What the file carries, and the rules for each:

  * ONE NODE PER OBJECT, named as `point_build` names it; a `-colonly` object stays a node with that suffix and a
    material-less mesh, which Godot's importer turns into a `StaticBody3D` + `ConcavePolygonShape3D` exactly as it
    did with Blender's proxies (`NavBaker` reads the `-noped` token off that name);
  * one primitive per material, materials as `road_kit.json` describes them (`point_kit.Kit.material`);
  * axes: kit Z-up to glTF Y-up, `(x, y, z) -> (x, z, -y)` -- a rotation, so winding survives (`point_export.godot`);
  * NORMALS ARE AUTO-SMOOTH (`SMOOTH_ANGLE_DEG`), computed here, not copied from anyone: a corner shared by faces
    within the angle is one vertex with their area-weighted normal, a sharper corner is split. It is the shading
    rule an artist sets by hand in Blender and industry tools default to. Blender's own export of these pieces
    was NOT a reference worth matching -- measured on DebugRoads, 88 vertex normals on one deck pointed INTO the
    prism (smooth shading across hard 90 degree edges, then an inverted extrude) -- so `normals_report` is the gate:
    every vertex normal within the angle of its face, none inverted.
"""
import json
import math
import os
import struct

#: Faces meeting at a corner within this angle share a normal; sharper corners are hard edges.
SMOOTH_ANGLE_DEG = 30.0
GENERATOR = "road_kit_authoring point_gltf"
_COS = math.cos(math.radians(SMOOTH_ANGLE_DEG))


def godot(p):
    """Kit Z-up -> glTF / Godot Y-up (`point_export.godot`)."""
    return (p[0], p[2], -p[1])


def _cross(u, v):
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _face(t):
    a, b, c = t
    return _cross((b[0] - a[0], b[1] - a[1], b[2] - a[2]), (c[0] - a[0], c[1] - a[1], c[2] - a[2]))


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else None


def _key(p):
    return (round(p[0], 5), round(p[1], 5), round(p[2], 5))


def indexed(tris, smooth_cos=_COS):
    """`(positions, normals, indices)` for triangles: degenerate faces dropped, corners welded by position AND by
    normal cluster (auto-smooth). Positions and normals in the frame given."""
    faces = []
    for t in tris:
        f = _face(t)
        u = _unit(f)
        if u is None:
            continue
        faces.append((t, f, u))
    at = {}
    for fi, (t, _f, _u) in enumerate(faces):
        for c in range(3):
            at.setdefault(_key(t[c]), []).append(fi)
    pos, nrm, idx, vid = [], [], [], {}
    cache = {}
    for fi, (t, _f, u) in enumerate(faces):
        for c in range(3):
            k = _key(t[c])
            ck = (k, fi)
            n = cache.get(ck)
            if n is None:
                ux, uy, uz = u
                sx = sy = sz = 0.0
                for g in at[k]:
                    gu = faces[g][2]
                    if ux * gu[0] + uy * gu[1] + uz * gu[2] >= smooth_cos:
                        gf = faces[g][1]
                        sx += gf[0]; sy += gf[1]; sz += gf[2]
                n = _unit((sx, sy, sz)) or u
                cache[ck] = n
            nk = (k, round(n[0], 3), round(n[1], 3), round(n[2], 3))
            v = vid.get(nk)
            if v is None:
                v = vid[nk] = len(pos)
                pos.append((float(t[c][0]), float(t[c][1]), float(t[c][2])))
                nrm.append(n)
            idx.append(v)
    return pos, nrm, idx


def normals_report(pos, nrm, idx, smooth_cos=_COS):
    """`(corners, worst_deg, inverted)`: how far any vertex normal sits from its face's normal, and how many point
    away from it (more than 90 degrees)."""
    worst, inverted, corners = 0.0, 0, 0
    lim = math.degrees(math.acos(max(-1.0, min(1.0, smooth_cos))))
    for k in range(0, len(idx), 3):
        u = _unit(_face((pos[idx[k]], pos[idx[k + 1]], pos[idx[k + 2]])))
        if u is None:
            continue
        for j in range(3):
            n = nrm[idx[k + j]]
            d = max(-1.0, min(1.0, sum(u[i] * n[i] for i in range(3))))
            ang = math.degrees(math.acos(d))
            corners += 1
            worst = max(worst, ang)
            inverted += ang > 90.0
    return corners, worst, inverted, lim


def write(objects, kit, path, node_order=None):
    """Write `objects` (`{name: {material name: [triangle]}}`, KIT frame) to `path` (`.gltf`) and its `.bin`.
    Material name `""` is a primitive with no material (a collision proxy). Returns a summary dict."""
    names = sorted(objects, key=lambda n: (n.lower(), n)) if node_order is None else list(node_order)
    blob = bytearray()
    buffer_views, accessors, meshes, nodes, materials, mat_index = [], [], [], [], [], {}
    summary = {"objects": 0, "triangles": 0, "vertices": 0, "worst_normal_deg": 0.0, "inverted_normals": 0}

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        buffer_views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(buffer_views) - 1

    for name in names:
        prims = []
        for mat in sorted(objects[name]):
            tris = [tuple(godot(p) for p in t) for t in objects[name][mat]]
            pos, nrm, idx = indexed(tris)
            if not idx:
                continue
            _c, worst, inv, _lim = normals_report(pos, nrm, idx)
            summary["worst_normal_deg"] = max(summary["worst_normal_deg"], worst)
            summary["inverted_normals"] += inv
            summary["triangles"] += len(idx) // 3
            summary["vertices"] += len(pos)
            pa = len(accessors)
            accessors.append({"bufferView": view(struct.pack("<%df" % (3 * len(pos)), *[c for p in pos for c in p]), 34962),
                              "componentType": 5126, "count": len(pos), "type": "VEC3",
                              "min": [min(p[i] for p in pos) for i in range(3)],
                              "max": [max(p[i] for p in pos) for i in range(3)]})
            accessors.append({"bufferView": view(struct.pack("<%df" % (3 * len(nrm)), *[c for n in nrm for c in n]), 34962),
                              "componentType": 5126, "count": len(nrm), "type": "VEC3"})
            wide = len(pos) > 65535
            accessors.append({"bufferView": view(struct.pack("<%d%s" % (len(idx), "I" if wide else "H"), *idx), 34963),
                              "componentType": 5125 if wide else 5123, "count": len(idx), "type": "SCALAR"})
            prim = {"attributes": {"POSITION": pa, "NORMAL": pa + 1}, "indices": pa + 2}
            if mat:
                if mat not in mat_index:
                    mat_index[mat] = len(materials)
                    materials.append(dict(kit.material(mat), name=mat))
                prim["material"] = mat_index[mat]
            prims.append(prim)
        if not prims:
            continue
        nodes.append({"name": name, "mesh": len(meshes)})
        meshes.append({"name": name, "primitives": prims})
        summary["objects"] += 1
    while len(blob) % 4:
        blob.append(0)
    bin_name = os.path.splitext(os.path.basename(path))[0] + ".bin"
    doc = {"asset": {"generator": GENERATOR, "version": "2.0"}, "scene": 0,
           "scenes": [{"name": "Scene", "nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
           "accessors": accessors, "bufferViews": buffer_views,
           "buffers": [{"byteLength": len(blob), "uri": bin_name}]}
    if materials:
        doc["materials"] = materials
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    for target, data, mode in ((os.path.join(os.path.dirname(os.path.abspath(path)), bin_name), bytes(blob), "wb"),
                               (path, json.dumps(doc, indent=1) + "\n", "w")):
        tmp = target + ".tmp"
        with open(tmp, mode) as fh:
            fh.write(data)
        os.replace(tmp, target)
    summary["worst_normal_deg"] = round(summary["worst_normal_deg"], 2)
    return summary


def self_test():
    import tempfile
    try:
        from . import point_kit as pk, point_mesh as pmsh
    except ImportError:
        import point_kit as pk                                               # noqa: E402
        import point_mesh as pmsh                                            # noqa: E402
    # A closed deck prism: 8 corners, but every corner is three hard edges -> 24 vertices, normals exactly the faces'.
    deck = pmsh.sweep([(0.0, 0.0, 5.0), (10.0, 0.0, 5.0)], [{"w": 3.0, "t": 1.0}] * 2, "deck", "", 0.0, "", "w", "t")
    pos, nrm, idx = indexed(deck)
    corners, worst, inverted, _lim = normals_report(pos, nrm, idx)
    assert len(pos) == 24 and worst < 1e-3 and inverted == 0, (len(pos), worst, inverted)
    print("OK: a box's hard edges split its corners (24 vertices, every normal on its face, none inverted)")
    # A gently curved band shares its vertices (smooth), a 90 degree fold does not.
    band = pmsh.sweep([(0.0, 0.0, 0.0), (10.0, 0.0, 0.3), (20.0, 0.0, 0.0)], [{"w": 2.0}] * 3, "band", "", 0.0, "", "w", "")
    pos, nrm, idx = indexed(band)
    assert len(pos) == 6, len(pos)
    print("OK: a 3 degree crease is smooth-shaded (6 vertices for 3 stations)")
    out = os.path.join(tempfile.mkdtemp(), "t.gltf")
    kit = pk.Kit({"M_Concrete": {"pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}})
    s = write({"a__surface": {"M_Concrete": deck}, "a_road-road-noped-colonly": {"": deck}}, kit, out)
    doc = json.load(open(out))
    assert s["objects"] == 2 and [n["name"] for n in doc["nodes"]] == ["a__surface", "a_road-road-noped-colonly"]
    assert doc["materials"][0]["name"] == "M_Concrete" and "material" not in doc["meshes"][1]["primitives"][0]
    assert os.path.getsize(os.path.join(os.path.dirname(out), "t.bin")) == doc["buffers"][0]["byteLength"]
    ys = [doc["accessors"][0]["min"][1], doc["accessors"][0]["max"][1]]
    assert ys == [4.0, 5.0], ys                               # kit Z became glTF Y
    print("OK: the file carries a node per object, the kit's material, a material-less proxy, and Y-up positions")
    return 3


if __name__ == "__main__":
    print("point_gltf.py: %d checks PASS" % self_test())
