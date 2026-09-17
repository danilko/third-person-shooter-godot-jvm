#!/usr/bin/env python3
"""normalize_kit.py -- turn a downloaded modular building kit into the pieces the game builds from.

    python3 tools/building_kit/normalize_kit.py assets/world_source/kits/<kit_id> [--check]

Reads `<kit>/kit.json` (authored: licence, source, module, `module_scale`, category rules) and every
`<kit>/source/*.gltf`, and writes

    <kit>/pieces/<category>/<Piece>.gltf + .bin   the piece, `module_scale` BAKED into its vertices
    <kit>/pieces.json                             generated manifest: category and measured size per piece

The rule is the weapon standard's (CLAUDE.md W19): the model IS the size. A piece is never scaled by a
transform on its instance, so a building scene places pieces on the scaled module and nothing else
has to know the number. Uniform scale only: normals and tangents are unchanged, textures keep their
proportions.

Images are shared: every piece points at `<kit>/textures/` by a relative uri, so 80 MB of PNGs exist once.
`--check` rebuilds into memory and fails if any written file differs (the pieces are stale).
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys

COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def category_of(name, rules):
    for cat, pattern in rules:
        if re.search(pattern, name):
            return cat
    raise SystemExit(f"{name}: no category rule matches (add one to kit.json)")


def rotate(q, v):
    """Rotate v by the unit quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return [v[0] + w * tx + y * tz - z * ty, v[1] + w * ty + z * tx - x * tz, v[2] + w * tz + x * ty - y * tx]


def scale_gltf(gltf, blob, s, texture_rel):
    """Return (gltf, blob, size) with POSITION data and node translations scaled by `s`."""
    blob = bytearray(blob)
    views_seen = {}
    for mesh in gltf.get("meshes", []):
        for prim in mesh["primitives"]:
            ai = prim["attributes"]["POSITION"]
            acc = gltf["accessors"][ai]
            if acc["componentType"] != 5126 or acc["type"] != "VEC3" or acc.get("sparse"):
                raise SystemExit("POSITION must be dense float VEC3")
            vi = acc["bufferView"]
            if vi in views_seen and views_seen[vi] != ai:
                raise SystemExit(f"bufferView {vi} is shared by two POSITION accessors")
            if vi in views_seen:
                continue
            views_seen[vi] = ai
            view = gltf["bufferViews"][vi]
            stride = view.get("byteStride", 12)
            base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            for k in range(acc["count"]):
                off = base + k * stride
                x, y, z = struct.unpack_from("<fff", blob, off)
                struct.pack_into("<fff", blob, off, x * s, y * s, z * s)
            acc["min"] = [v * s for v in acc["min"]]
            acc["max"] = [v * s for v in acc["max"]]
    lo, hi = [1e18] * 3, [-1e18] * 3
    for node in gltf.get("nodes", []):
        # A uniform scale commutes with a node's rotation and scale, so only its translation needs it.
        if "matrix" in node:
            raise SystemExit(f"node {node.get('name')} carries a matrix; export TRS instead")
        if "translation" in node:
            node["translation"] = [v * s for v in node["translation"]]
        if "mesh" in node:
            t = node.get("translation", [0, 0, 0])
            q = node.get("rotation", [0, 0, 0, 1])
            ns = node.get("scale", [1, 1, 1])
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                acc = gltf["accessors"][prim["attributes"]["POSITION"]]
                for c in range(8):    # the box's corners, rotated: exact for axis turns, a bound otherwise
                    p = [acc["max" if c >> i & 1 else "min"][i] for i in range(3)]
                    p = rotate(q, [p[i] * ns[i] for i in range(3)])
                    for i in range(3):
                        lo[i] = min(lo[i], p[i] + t[i])
                        hi[i] = max(hi[i], p[i] + t[i])
    for img in gltf.get("images", []):
        img["uri"] = texture_rel + "/" + os.path.basename(img["uri"])
    return gltf, bytes(blob), [round(lo[i], 4) for i in range(3)], [round(hi[i], 4) for i in range(3)]


def build(kit_dir):
    kit = json.load(open(os.path.join(kit_dir, "kit.json")))
    s = float(kit["module_scale"])
    src = os.path.join(kit_dir, "source")
    outputs = {}
    manifest = {"kit": kit["id"], "module_scale": s,
                "module_m": round(kit["source_module_m"] * s, 4),
                "storey_m": round(kit["source_storey_m"] * s, 4),
                "generated_by": "tools/building_kit/normalize_kit.py", "pieces": {}}
    for fname in sorted(os.listdir(src)):
        if not fname.endswith(".gltf"):
            continue
        name = fname[:-5]
        gltf = json.load(open(os.path.join(src, fname)))
        if len(gltf.get("buffers", [])) != 1:
            raise SystemExit(f"{fname}: expected one buffer")
        blob = open(os.path.join(src, gltf["buffers"][0]["uri"]), "rb").read()
        cat = category_of(name, kit["categories"])
        gltf, blob, lo, hi = scale_gltf(gltf, blob, s, "../../textures")
        gltf["buffers"][0]["uri"] = name + ".bin"
        gltf["buffers"][0]["byteLength"] = len(blob)
        gltf.setdefault("asset", {})["extras"] = {"normalized_by": "tools/building_kit/normalize_kit.py",
                                                  "module_scale": s}
        rel = os.path.join("pieces", cat)
        outputs[os.path.join(rel, name + ".gltf")] = (json.dumps(gltf, indent=1) + "\n").encode()
        outputs[os.path.join(rel, name + ".bin")] = blob
        manifest["pieces"][name] = {
            "category": cat, "path": f"{rel}/{name}.gltf",
            "min": lo, "max": hi, "size": [round(hi[i] - lo[i], 4) for i in range(3)],
            "materials": [m["name"] for m in gltf.get("materials", [])],
        }
    outputs["pieces.json"] = (json.dumps(manifest, indent=1) + "\n").encode()
    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kit_dir")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    outputs = build(a.kit_dir)
    stale = []
    for rel, data in outputs.items():
        path = os.path.join(a.kit_dir, rel)
        old = open(path, "rb").read() if os.path.exists(path) else None
        if old != data:
            stale.append(rel)
            if not a.check:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                open(path, "wb").write(data)
    pieces = [r for r in outputs if r.endswith(".gltf")]
    if a.check:
        print(f"normalize_kit --check: {len(pieces)} pieces, {len(stale)} stale")
        for r in stale[:10]:
            print("  stale", r)
        sys.exit(1 if stale else 0)
    digest = hashlib.sha1(b"".join(outputs[k] for k in sorted(outputs))).hexdigest()[:12]
    print(f"normalize_kit: {len(pieces)} pieces, {len(stale)} written, digest {digest}")


if __name__ == "__main__":
    main()
