#!/usr/bin/env python3
"""mirror_piece.py -- the RIGHT-HAND twin of a kerb-side piece, derived from the piece itself.

    python3 tools/mirror_piece.py            # every piece in PIECES below
    python3 tools/mirror_piece.py --check    # exit 1 when a twin is missing or older than its source

A traffic signal's mast arm and an expressway cantilever sign are modelled for a KEEP-LEFT kerb: the pole on the
left, the arm reaching right over the lanes. A right-hand network (user, 2026-10-12: "drive on the right";
`<stem>.network.json` traffic_side) stands the pole on the RIGHT kerb, so it needs the same piece mirrored. The
artist's piece stays the one owner -- this reflects its glTF in X (positions and normals negated, every triangle's
winding flipped so the faces still point out) and writes `<Piece>_R.gltf/.bin`; a `<Piece>.lamps.json` (the lens
meshes and name plates world.TrafficSignals lights) is reflected the same way. Re-run after the source piece is
rebuilt (blender/tools/build_street_poles.py, the library export).
"""
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
KITS = os.path.join(ROOT, "assets", "world_source", "kits")
PIECES = (os.path.join(KITS, "quaternius_zombie_apocalypse", "pieces", "props", "TrafficLight_JP.gltf"),
          os.path.join(KITS, "library", "pieces", "street", "Sign_ExpwyCantilever.gltf"))
FMT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
NUM = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def twin(path):
    return path[:-len(".gltf")] + "_R.gltf"


def mirror_gltf(src, dst):
    doc = json.load(open(src))
    base = os.path.dirname(src)
    bufs = [bytearray(open(os.path.join(base, b["uri"]), "rb").read()) for b in doc["buffers"]]

    def span(acc):
        a = doc["accessors"][acc]
        v = doc["bufferViews"][a["bufferView"]]
        n = NUM[a["type"]]
        f = FMT[a["componentType"]]
        size = struct.calcsize(f) * n
        stride = v.get("byteStride") or size
        off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        return bufs[v["buffer"]], off, stride, "<%d%s" % (n, f), a["count"], a

    done = set()
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            for name in ("POSITION", "NORMAL", "TANGENT"):
                acc = prim["attributes"].get(name)
                if acc is None or acc in done:
                    continue
                done.add(acc)
                buf, off, stride, fmt, count, a = span(acc)
                for i in range(count):
                    v = list(struct.unpack_from(fmt, buf, off + i * stride))
                    v[0] = -v[0]
                    if name == "TANGENT":
                        v[3] = -v[3]                     # the bitangent's hand flips with the reflection
                    struct.pack_into(fmt, buf, off + i * stride, *v)
                if name == "POSITION" and "min" in a:
                    a["min"][0], a["max"][0] = -a["max"][0], -a["min"][0]
            idx = prim.get("indices")
            if idx is not None and ("i", idx) not in done:
                done.add(("i", idx))
                buf, off, stride, fmt, count, _a = span(idx)
                for i in range(0, count - 2, 3):
                    b = struct.unpack_from(fmt, buf, off + (i + 1) * stride)
                    c = struct.unpack_from(fmt, buf, off + (i + 2) * stride)
                    struct.pack_into(fmt, buf, off + (i + 1) * stride, *c)
                    struct.pack_into(fmt, buf, off + (i + 2) * stride, *b)
    stem = os.path.splitext(os.path.basename(dst))[0]
    for k, b in enumerate(doc["buffers"]):
        b["uri"] = stem + (".bin" if k == 0 else "_%d.bin" % k)
        with open(os.path.join(os.path.dirname(dst), b["uri"]), "wb") as fh:
            fh.write(bytes(bufs[k]))
    for n in doc.get("nodes", ()):
        if n.get("name") and "mesh" in n:
            n["name"] = n["name"] + "_R"
    # Godot re-imports on the .gltf's own hash and never looks at the .bin (CLAUDE.md): carry the buffer's
    doc.setdefault("asset", {}).setdefault("extras", {})["bin_sha1"] = hashlib.sha1(bytes(bufs[0])).hexdigest()
    doc["asset"]["extras"]["mirrored_from"] = os.path.basename(src)
    with open(dst, "w") as fh:
        fh.write(json.dumps(doc, indent=1) + "\n")


def mirror_lamps(src, dst):
    d = json.load(open(src))

    def flip(v):
        return [-v[0] + 0.0, v[1], v[2]]

    for key in ("vehicle", "pedestrian", "plates"):
        for row in d.get(key, ()):
            for f in ("pos", "normal"):
                if f in row:
                    row[f] = flip(row[f])
            t = row.get("tris")
            if t:
                out = []
                for i in range(0, len(t) - 8, 9):
                    a, b, c = t[i:i + 3], t[i + 3:i + 6], t[i + 6:i + 9]
                    out += flip(a) + flip(c) + flip(b)
                row["tris"] = out
    d["notes"] = "The X mirror of %s (tools/mirror_piece.py): the right-hand twin's lenses and plates." % os.path.basename(src)
    with open(dst, "w") as fh:
        fh.write(json.dumps(d, indent=1) + "\n")


def main(argv):
    bad = 0
    for src in PIECES:
        dst = twin(src)
        lamps = src[:-len(".gltf")] + ".lamps.json"
        if "--check" in argv:
            stale = not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src)
            print("mirror_piece: %s %s" % (os.path.basename(dst), "STALE" if stale else "up to date"))
            bad |= stale
            continue
        mirror_gltf(src, dst)
        if os.path.exists(lamps):
            mirror_lamps(lamps, dst[:-len(".gltf")] + ".lamps.json")
        print("mirror_piece: %s -> %s" % (os.path.basename(src), os.path.basename(dst)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
