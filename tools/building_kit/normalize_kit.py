#!/usr/bin/env python3
"""normalize_kit.py -- turn a NEWLY DOWNLOADED modular building kit into its first pieces (PLAN.md 3.6b step 1).

    python3 tools/building_kit/normalize_kit.py assets/world_source/kits/<kit_id> --init [--force]
    python3 tools/building_kit/normalize_kit.py assets/world_source/kits/<kit_id> --check   # read-only

ONE-TIME: the raw art makes the pieces once, then `blender/tools/build_building_kit_blend.py` lays them into the
kit's .blend, and from then on THE .BLEND OWNS THEM (`blender/tools/export_building_kit.py` writes `pieces/`, and
`tools/building_kit/build_buildings.sh` runs that export, not this). The weapon precedent (W19/W20). `--init`
refuses a kit that already has its .blend, because writing `pieces/` from `source/` would silently throw away every
edit made in that file; `--force` is for rebuilding a kit from scratch on purpose.

Reads `<kit>/kit.json` (authored: licence, source, module, `module_scale`, category rules) and every
`<kit>/source/*.gltf`, and writes

    <kit>/pieces/<category>/<Piece>.gltf + .bin   the piece, `module_scale` BAKED into its vertices
    <kit>/pieces.json                             generated manifest: category and measured size per piece

The rule is the weapon standard's (CLAUDE.md W19): the model IS the size. A piece is never scaled by a
transform on its instance, so a building scene places pieces on the scaled module and nothing else
has to know the number. Uniform scale only: normals and tangents are unchanged, textures keep their
proportions.

`material_prefix` (optional) renames every material on the way in, so a download whose materials are not
already `MI_*` still resolves to `<kit>/materials/MI_<name>.tres`, which is how the game finds a kit's look.

`module_scale` is the kit's one number and is what a MODULAR kit needs. A kit of unrelated props -- a nature
kit's trees, grass and stones -- has no module, and its families are downloaded at unrelated sizes, so
`category_scale` (optional: category -> scale) overrides it per category. The scale is still ONE number per
family, never one per model, so a family keeps its own variation; and it is still baked, so nothing downstream
holds it. `source_module_m` / `source_storey_m` are likewise optional: a kit with no module writes neither.

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
#: How far a declared POSITION box may sit from its own vertices before the bake says so (1 mm).
DECLARED_TOL = 0.001


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


def read_positions(gltf, blob, acc_index):
    """Every POSITION vertex of one accessor, from the buffer. glTF lets an accessor DECLARE its min/max, and
    the declaration is what `measure` used to trust -- but two models of the Stylized Nature download declare a
    box 1.6x and 3.2x larger than their own vertices, so a declared box is read as a hint, never as the truth,
    wherever the buffer is at hand."""
    acc = gltf["accessors"][acc_index]
    if acc["componentType"] != 5126 or acc["type"] != "VEC3" or acc.get("sparse"):
        raise SystemExit("POSITION must be dense float VEC3")
    view = gltf["bufferViews"][acc["bufferView"]]
    stride = view.get("byteStride", 12)
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    for k in range(acc["count"]):
        yield struct.unpack_from("<fff", blob, base + k * stride)


def measure(gltf, blob=None):
    """A piece's bounding box in its own frame, from every mesh node's TRS and its POSITION vertices (rounded
    to 0.1 mm). The ONE measure of a piece: `pieces.json` is written with it here and by
    `blender/tools/export_building_kit.py`, so a size cannot come out different depending on who wrote the piece.

    With `blob` the box comes from the VERTICES; without it, from each accessor's declared min/max, which is all
    a caller holding only the JSON can see. `declared_bounds_error` is how a caller checks the two agree."""
    lo, hi = [1e18] * 3, [-1e18] * 3
    for node in gltf.get("nodes", []):
        if "matrix" in node:
            raise SystemExit(f"node {node.get('name')} carries a matrix; export TRS instead")
        if "mesh" in node:
            t = node.get("translation", [0, 0, 0])
            q = node.get("rotation", [0, 0, 0, 1])
            ns = node.get("scale", [1, 1, 1])
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                ai = prim["attributes"]["POSITION"]
                acc = gltf["accessors"][ai]
                if blob is None:
                    # the box's corners, rotated: exact for axis turns, a bound otherwise
                    pts = ([acc["max" if c >> i & 1 else "min"][i] for i in range(3)] for c in range(8))
                else:
                    pts = read_positions(gltf, blob, ai)
                for p in pts:
                    p = rotate(q, [p[i] * ns[i] for i in range(3)])
                    for i in range(3):
                        lo[i] = min(lo[i], p[i] + t[i])
                        hi[i] = max(hi[i], p[i] + t[i])
    return [round(lo[i], 4) for i in range(3)], [round(hi[i], 4) for i in range(3)]


def declared_bounds_error(gltf, blob):
    """The worst distance, in metres, between an accessor's DECLARED min/max and its own vertices. 0 on a
    well-formed file; large on one whose exporter left a stale box behind."""
    worst = 0.0
    for mesh in gltf.get("meshes", []):
        for prim in mesh["primitives"]:
            ai = prim["attributes"]["POSITION"]
            acc = gltf["accessors"][ai]
            lo, hi = [1e18] * 3, [-1e18] * 3
            for p in read_positions(gltf, blob, ai):
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
            for i in range(3):
                worst = max(worst, abs(lo[i] - acc["min"][i]), abs(hi[i] - acc["max"][i]))
    return worst


def manifest_entry(name, cat, gltf, lo, hi):
    return {"category": cat, "path": f"pieces/{cat}/{name}.gltf", "min": lo, "max": hi,
            "size": [round(hi[i] - lo[i], 4) for i in range(3)],
            "materials": [m["name"] for m in gltf.get("materials", [])]}


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
            lo, hi = [1e18] * 3, [-1e18] * 3
            for k in range(acc["count"]):
                off = base + k * stride
                x, y, z = struct.unpack_from("<fff", blob, off)
                p = (x * s, y * s, z * s)
                struct.pack_into("<fff", blob, off, *p)
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
            # Written from the VERTICES, not scaled from the declaration: a source that declares a stale box
            # (two of this nature kit's models do) would otherwise hand the same lie to every later reader.
            acc["min"], acc["max"] = lo, hi
    for node in gltf.get("nodes", []):
        # A uniform scale commutes with a node's rotation and scale, so only its translation needs it.
        if "matrix" in node:
            raise SystemExit(f"node {node.get('name')} carries a matrix; export TRS instead")
        if "translation" in node:
            node["translation"] = [v * s for v in node["translation"]]
    lo, hi = measure(gltf, blob)
    for img in gltf.get("images", []):
        img["uri"] = texture_rel + "/" + os.path.basename(img["uri"])
    return gltf, bytes(blob), lo, hi


def manifest_header(kit, generated_by):
    """The manifest's header. Shared with `blender/tools/export_building_kit.py` so the two writers of
    `pieces.json` cannot disagree about what a kit's header says."""
    s = float(kit["module_scale"])
    head = {"kit": kit["id"], "module_scale": s}
    if "source_module_m" in kit:      # a kit of unrelated props (nature) has no module and writes neither
        head["module_m"] = round(kit["source_module_m"] * s, 4)
        head["storey_m"] = round(kit["source_storey_m"] * s, 4)
    if kit.get("category_scale"):
        head["category_scale"] = dict(sorted(kit["category_scale"].items()))
    head["generated_by"] = generated_by
    head["pieces"] = {}
    return head


def build(kit_dir):
    kit = json.load(open(os.path.join(kit_dir, "kit.json")))
    s = float(kit["module_scale"])
    per_cat = kit.get("category_scale") or {}
    prefix = kit.get("material_prefix", "")
    src = os.path.join(kit_dir, "source")
    outputs = {}
    manifest = manifest_header(kit, "tools/building_kit/normalize_kit.py")
    for fname in sorted(os.listdir(src)):
        if not fname.endswith(".gltf"):
            continue
        name = fname[:-5]
        gltf = json.load(open(os.path.join(src, fname)))
        if len(gltf.get("buffers", [])) != 1:
            raise SystemExit(f"{fname}: expected one buffer")
        blob = open(os.path.join(src, gltf["buffers"][0]["uri"]), "rb").read()
        cat = category_of(name, kit["categories"])
        cs = float(per_cat.get(cat, s))
        for mat in gltf.get("materials", []):
            # The game resolves a surface to `<kit>/materials/<material name>.tres` by NAME
            # (tools/godot/build_building_scenes.gd), and every kit's materials are `MI_*`. A download whose
            # materials are named otherwise is prefixed here, once, so the kit file and the pieces agree.
            if prefix and not mat["name"].startswith(prefix):
                mat["name"] = prefix + mat["name"]
        err = declared_bounds_error(gltf, blob)
        if err > DECLARED_TOL:
            print(f"  note: {name} declares a POSITION box {err:.3f} m off its own vertices; measured from the "
                  f"vertices")
        gltf, blob, lo, hi = scale_gltf(gltf, blob, cs, "../../textures")
        gltf["buffers"][0]["uri"] = name + ".bin"
        gltf["buffers"][0]["byteLength"] = len(blob)
        gltf.setdefault("asset", {})["extras"] = {"normalized_by": "tools/building_kit/normalize_kit.py",
                                                  "module_scale": cs}
        rel = os.path.join("pieces", cat)
        outputs[os.path.join(rel, name + ".gltf")] = (json.dumps(gltf, indent=1) + "\n").encode()
        outputs[os.path.join(rel, name + ".bin")] = blob
        manifest["pieces"][name] = manifest_entry(name, cat, gltf, lo, hi)
    outputs["pieces.json"] = (json.dumps(manifest, indent=1) + "\n").encode()
    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kit_dir")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    kit_id = json.load(open(os.path.join(a.kit_dir, "kit.json")))["id"]
    owner = os.path.join(a.kit_dir, kit_id + ".blend")
    if not a.check and not a.init:
        raise SystemExit("normalize_kit: pass --init for a new kit (or --check). An existing kit's pieces come from "
                         "its .blend: blender/tools/export_building_kit.py")
    if a.init and os.path.exists(owner) and not a.force:
        raise SystemExit(f"normalize_kit: {owner} exists and owns this kit's pieces; --init would overwrite its "
                         "edits. Use export_building_kit.py, or --force to rebuild the kit from source/.")
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
