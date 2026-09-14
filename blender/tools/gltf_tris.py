"""gltf_tris.py -- read a .gltf (+ .bin) into {node: {material: [triangles]}}, node transforms applied. Used by
roadkit_mesh_parity.py to compare a baked road piece with the pure-Python sweep (PLAN.md 3.1 B10.7)."""
import json, struct, os, math, sys
COMP = {5126: ("f", 4), 5123: ("H", 2), 5125: ("I", 4), 5121: ("B", 1)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
def _acc(g, buf, i):
    a = g["accessors"][i]; bv = g["bufferViews"][a["bufferView"]]
    fmt, size = COMP[a["componentType"]]; n = NCOMP[a["type"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", size * n)
    out = []
    for k in range(a["count"]):
        vals = struct.unpack_from("<" + fmt * n, buf, off + k * stride)
        out.append(vals if n > 1 else vals[0])
    return out
def _mat(q, t, s):
    x, y, z, w = q
    r = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],[2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],[2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    return [[r[i][j]*s[j] for j in range(3)] + [t[i]] for i in range(3)]
def load(path):
    """{node_name: {material_name: [(a,b,c), ...]}} in the glTF (Godot, Y-up) frame, node transforms applied (1 level + parents)."""
    g = json.load(open(path)); buf = open(os.path.join(os.path.dirname(path), g["buffers"][0]["uri"]), "rb").read()
    parent = {}
    for i, n in enumerate(g["nodes"]):
        for c in n.get("children", []): parent[c] = i
    def world(i):
        n = g["nodes"][i]
        m = _mat(n.get("rotation", (0,0,0,1)), n.get("translation", (0,0,0)), n.get("scale", (1,1,1)))
        if i in parent:
            p = world(parent[i])
            m = [[sum(p[r][k]*m[k][c] for k in range(3)) + (p[r][3] if c == 3 else 0) for c in range(4)] for r in range(3)]
        return m
    out = {}
    for i, n in enumerate(g["nodes"]):
        if "mesh" not in n: continue
        W = world(i)
        for prim in g["meshes"][n["mesh"]]["primitives"]:
            pos = _acc(g, buf, prim["attributes"]["POSITION"])
            idx = _acc(g, buf, prim["indices"]) if "indices" in prim else list(range(len(pos)))
            mname = g["materials"][prim["material"]]["name"] if "material" in prim else "-"
            P = [tuple(sum(W[r][k]*p[k] for k in range(3)) + W[r][3] for r in range(3)) for p in pos]
            tris = [(P[idx[k]], P[idx[k+1]], P[idx[k+2]]) for k in range(0, len(idx) - 2, 3)]
            out.setdefault(n["name"], {}).setdefault(mname, []).extend(tris)
    return out
if __name__ == "__main__":
    m = load(sys.argv[1])
    obj = m[sys.argv[2]]
    for mat, tris in obj.items():
        horiz = [t for t in tris if abs(((t[1][0]-t[0][0])*(t[2][2]-t[0][2]) - (t[2][0]-t[0][0])*(t[1][2]-t[0][2]))) > 1e-6]
        ups = downs = verts = 0
        for a,b,c in tris:
            u=(b[0]-a[0],b[1]-a[1],b[2]-a[2]); v=(c[0]-a[0],c[1]-a[1],c[2]-a[2])
            ny = u[2]*v[0]-u[0]*v[2]
            nl = math.sqrt((u[1]*v[2]-u[2]*v[1])**2 + ny**2 + (u[0]*v[1]-u[1]*v[0])**2) or 1
            if ny/nl > 0.7: ups += 1
            elif ny/nl < -0.7: downs += 1
            else: verts += 1
        print(mat, len(tris), "up", ups, "down", downs, "vertical", verts)
