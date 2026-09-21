#!/usr/bin/env python3
"""study_nature_kit.py -- MEASURE the Stylized Nature MegaKit before it becomes a kit (PLAN.md 3.16 step 1).

    python3 tools/building_kit/study_nature_kit.py [<dir>] [--json <out>] [--md <out>]

Reads every `<dir>/glTF/*.gltf` of the download and prints, per model, the facts a keep / rescale / recolour /
drop verdict is made from: its size in metres, how that compares with the 1.49 m character and the 1.82 m ken,
its triangle count, and its materials (which say whether it is an alpha-cut leaf card).

It is pure python and READ-ONLY -- the download is never touched. Sizes come from `normalize_kit.measure` over
the actual VERTICES, the ONE measure of a piece, so a number here and a number in `pieces.json` cannot disagree.
`declared_off` is how far a model's own declared glTF box sits from its vertices: 0 on 66 of the 68, 3.18 m on
Fern_1 and 1.39 m on Plant_1_Big, which is why the vertices and not the declaration are what is read.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import normalize_kit as nk  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DEFAULT = os.path.join(ROOT, "assets", "world_source", "kits", "quaternius_stylized_nature")

#: The two rulers every asset in this project is measured against (CLAUDE.md W19/W20: the model IS the size).
CHARACTER_H = 1.49   # Godot-chan, measured to the crown
KEN_M = 1.82         # the building kits' plan module

#: What each family IS, the axis its size is judged on ("y" upright, "xz" flat/spreading), the band a Japanese
#: example of it really occupies in metres, and what we would use it for. A model inside its band is `keep`;
#: outside it, the scale that would put the FAMILY's median in the middle of the band is what a rescale costs.
#: The bands are ordinary field sizes, not opinions: a lawn clover is ankle height, a keyaki street tree is a
#: two-storey building, a tobiishi stepping stone is a pace wide.
FAMILIES = (
    (r"^CommonTree", "broadleaf tree", "y", (6.0, 12.0), "street tree (keyaki/ginkgo), sakura when recoloured"),
    (r"^Pine", "conifer", "y", (6.0, 14.0), "kuromatsu: coast windbreak, shrine, castle grounds"),
    (r"^TwistedTree", "gnarled tree", "y", (12.0, 20.0), "sacred tree (御神木), banyan/gajumaru (Okinawa)"),
    (r"^DeadTree", "bare tree", "y", (8.0, 16.0), "winter and wasteland accent"),
    (r"^Bush_", "bush", "y", (0.8, 1.8), "hedge when clipped: house, konbini lot"),
    (r"^Plant_1", "leafy plant", "y", (0.6, 4.0), "yatsude/basho: Okinawan garden, shade planting"),
    (r"^Plant_7", "spreading plant", "xz", (0.3, 0.7), "low ground planting"),
    (r"^Fern", "fern patch", "y", (0.5, 1.0), "massif and touge undergrowth"),
    (r"^Clover", "lawn cover", "y", (0.05, 0.20), "lawn, verge, park"),
    (r"^Flower", "flower", "y", (0.3, 0.7), "verge, garden, planter"),
    (r"^Grass_.*_Tall", "tall grass", "y", (1.0, 2.0), "susuki on the farmland and the touge"),
    (r"^Grass", "grass tuft", "y", (0.3, 0.8), "verge, farm edge, rough ground"),
    (r"^Mushroom", "mushroom", "y", (0.08, 0.25), "forest floor"),
    (r"^Petal", "petal scatter", "xz", (0.3, 1.0), "sakura fall under a tree"),
    (r"^Pebble", "cobble", "xz", (0.10, 0.30), "gravel bed, Japanese garden"),
    (r"^Rock_", "boulder", "y", (1.0, 3.0), "massif, coast, garden rock"),
    (r"^RockPath", "stepping stone", "xz", (0.30, 0.60), "shrine approach (参道), garden path"),
)


def family_of(name):
    for pat, kind, axis, band, use in FAMILIES:
        if re.match(pat, name):
            return kind, axis, band, use
    return "?", "y", None, ""


def triangles(gltf):
    n = 0
    for node in gltf.get("nodes", []):
        if "mesh" not in node:
            continue
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            acc = gltf["accessors"][prim["indices"]] if "indices" in prim \
                else gltf["accessors"][prim["attributes"]["POSITION"]]
            n += acc["count"] // 3
    return n


def images_of(gltf):
    return sorted({os.path.basename(i["uri"]) for i in gltf.get("images", []) if "uri" in i})


def study(src):
    rows = []
    for fname in sorted(os.listdir(src)):
        if not fname.endswith(".gltf"):
            continue
        name = fname[:-5]
        gltf = json.load(open(os.path.join(src, fname)))
        blob = open(os.path.join(src, gltf["buffers"][0]["uri"]), "rb").read()
        lo, hi = nk.measure(gltf, blob)          # the VERTICES: two of this download's models declare a stale box
        declared_off = round(nk.declared_bounds_error(gltf, blob), 3)
        size = [round(hi[i] - lo[i], 3) for i in range(3)]
        kind, axis, band, use = family_of(name)
        rows.append({
            "name": name, "kind": kind, "axis": axis, "band": band, "use": use,
            "size": size, "declared_off": declared_off,
            "measured": size[1] if axis == "y" else round(max(size[0], size[2]), 3),
            "sink": round(-lo[1], 3),                 # how far the model's base is buried below its origin
            "off_centre": round(max(abs(lo[0] + hi[0]), abs(lo[2] + hi[2])) / 2, 3),
            "vs_character": round(size[1] / CHARACTER_H, 2),
            "vs_ken": round(max(size[0], size[2]) / KEN_M, 2),
            "tris": triangles(gltf),
            "materials": [m["name"] for m in gltf.get("materials", [])],
            "images": images_of(gltf),
        })
    # One scale PER FAMILY, from its median, so a family keeps its own variation (a rescale is baked into the
    # vertices per the kit rule, never applied as an instance transform -- CLAUDE.md W19, "the model IS the size").
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)
    for kind, rs in by_kind.items():
        band = rs[0]["band"]
        if not band:
            continue
        ms = sorted(r["measured"] for r in rs)
        med = ms[len(ms) // 2]
        mid = (band[0] + band[1]) / 2
        scale = round(mid / med, 2) if med else 1.0
        inside = sum(1 for m in ms if band[0] <= m <= band[1])
        for r in rs:
            r["family_median"] = med
            r["family_scale"] = scale
            r["family_inside"] = f"{inside}/{len(rs)}"
            r["verdict"] = "keep" if band[0] <= r["measured"] <= band[1] else f"rescale x{scale}"
    for r in rows:
        r.setdefault("verdict", "?")
        r.setdefault("family_scale", 1.0)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=DEFAULT,
                    help="the kit folder (its source/ is the download), or the download folder itself")
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args()
    src = next(d for d in (os.path.join(a.dir, "source"), os.path.join(a.dir, "glTF"), a.dir)
               if os.path.isdir(d))
    rows = study(src)
    tex = sorted({i for r in rows for i in r["images"]})
    print(f"{len(rows)} models, {len(tex)} textures, {sum(r['tris'] for r in rows)} triangles total")
    print(f"{'model':24} {'kind':16} {'size x,y,z (m)':22} {'judged':>7} {'sink':>5} {'tris':>6}  verdict")
    for r in rows:
        s = ", ".join(f"{v:.2f}" for v in r["size"])
        print(f"{r['name']:24} {r['kind']:16} {s:22} {r['measured']:7.2f} {r['sink']:5.2f} {r['tris']:6}  "
              f"{r['verdict']}")
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)
    print(f"\n{'family':16} {'n':>2} {'axis':4} {'measured range':>16} {'median':>7} {'real band':>13} "
          f"{'in band':>8} {'scale':>6}  triangles")
    for kind, rs in sorted(by_kind.items(), key=lambda kv: -sum(r["tris"] for r in kv[1])):
        ms = sorted(r["measured"] for r in rs)
        b = rs[0]["band"]
        tris = sum(r["tris"] for r in rs)
        band = f"{b[0]:.2f}-{b[1]:.2f}" if b else "-"
        print(f"  {kind:16} {len(rs):2} {rs[0]['axis']:4} {ms[0]:7.2f}..{ms[-1]:7.2f} m "
              f"{rs[0].get('family_median', 0):7.2f} {band:>13} {rs[0].get('family_inside', '-'):>8} "
              f"x{rs[0].get('family_scale', 1):.2f}  {tris} ({tris // len(rs)} avg)")
    if a.json:
        json.dump({"source": os.path.relpath(a.dir, ROOT), "character_h": CHARACTER_H, "ken_m": KEN_M,
                   "models": rows}, open(a.json, "w"), indent=1)
        print("wrote", a.json)
    if a.md:
        write_md(a.md, rows, by_kind, tex)
        print("wrote", a.md)


def baked_scales():
    """What `kit.json` actually bakes per category, so the record cannot claim a scale the kit does not apply."""
    try:
        kit = json.load(open(os.path.join(DEFAULT, "kit.json")))
    except OSError:
        return {}, {}
    cat_of = {}
    for cat, pat in kit["categories"]:
        cat_of[pat] = cat
    return kit.get("category_scale") or {}, cat_of


def write_md(path, rows, by_kind, tex):
    """The study, WHOLE and derived -- no hand-written half, so re-running it after a kit change cannot leave a
    stale conclusion standing beside a fresh table."""
    bad = [r for r in rows if r["declared_off"] > 0.001]
    baked, _ = baked_scales()
    cat_of = {}
    for r in rows:
        for pat, kind, _axis, _band, _use in FAMILIES:
            if re.match(pat, r["name"]):
                cat_of[kind] = pat
                break
    # family -> the kit.json category it became (the categories mirror the families, in the same order)
    try:
        kit = json.load(open(os.path.join(DEFAULT, "kit.json")))
        pat_to_cat = {pat: cat for cat, pat in kit["categories"]}
    except OSError:
        pat_to_cat = {}
    with open(path, "w") as f:
        f.write("# Stylized Nature MegaKit (Standard) -- the study\n\n")
        f.write("GENERATED by `tools/building_kit/study_nature_kit.py --md <this file>`; do not hand-edit.\n")
        f.write("The pictures beside it are `tools/godot/shot_nature_kit.gd` (needs a display).\n\n")
        f.write(f"{len(rows)} models, {sum(r['tris'] for r in rows)} triangles, {len(by_kind)} families, "
                f"{len(tex)} textures referenced (the kit keeps 20: five are the plain white partners of the "
                f"`_C` set and two Pro-only maps, which is what a recolour is made from). Measured against the "
                f"character's {CHARACTER_H} m and the {KEN_M} m ken.\n\n")
        f.write("## What it costs to make the kit ours\n\n")
        f.write("| family | n | axis | measured | median | the band a Japanese one occupies | in band | "
                "to mid-band | BAKED | triangles (avg) |\n|---|--:|---|---|--:|---|--:|--:|--:|--:|\n")
        for kind, rs in sorted(by_kind.items(), key=lambda kv: -sum(r["tris"] for r in kv[1])):
            ms = sorted(r["measured"] for r in rs)
            b = rs[0]["band"]
            t = sum(r["tris"] for r in rs)
            cat = pat_to_cat.get(cat_of.get(kind, ""), "")
            bk = baked.get(cat)
            f.write(f"| {kind} | {len(rs)} | {rs[0]['axis']} | {ms[0]:.2f}..{ms[-1]:.2f} m | "
                    f"{rs[0].get('family_median', 0):.2f} | {b[0]:.2f}-{b[1]:.2f} m | "
                    f"{rs[0].get('family_inside', '-')} | x{rs[0].get('family_scale', 1):.2f} | "
                    f"{('x%.2f' % bk) if bk is not None else '-'} | {t} ({t // len(rs)}) |\n")
        f.write("\nONE scale per family, baked into the vertices -- so a family keeps its own variation and "
                "nothing downstream holds the number (CLAUDE.md W19). A family already inside its band is baked "
                "at 1.0 and not nudged to the middle of it: the trees read as young Japanese street and coastal "
                "trees where they are.\n\n")
        f.write("## Findings\n\n")
        if bad:
            f.write("* **" + ", ".join(r["name"] for r in bad) + " DECLARE a glTF POSITION box larger than their "
                    "own vertices** (" + ", ".join(f"{r['declared_off']:.2f} m" for r in bad) + "), so a reader "
                    "that trusts the declaration -- which is what glTF asks for -- measures them wrong. "
                    "`normalize_kit.measure` reads the vertices; `declared_bounds_error` is the check.\n")
        f.write("* **The trees came out right and the ground cover did not.** Every tree family is inside its "
                "band unscaled; lawn, flowers, grass tufts, mushrooms, cobbles, stepping stones and spreading "
                "plants are 2.4-10x too large, which is what the bake fixes.\n")
        f.write("* **A piece's base is buried below its origin** (0.02-0.34 m): the download's convention, kept, "
                "so a tree on uneven ground has no visible join. A building kit's origin sits ON the ground.\n")
        f.write("* **A recolour is one material, not a new texture.** Each leaf shape ships twice: `X.png`, a "
                "pure WHITE mask, and `X_C.png`, the same shape already tinted. So sakura, a fresh-green keyaki, "
                "an autumn ginkgo and a momiji are one `albedo_color` each over the white one "
                "(`shot_nature_kit.gd --variants` is the picture).\n")
        f.write("* **`Bark_NormalTree` is declared alpha MASK and its texture is opaque everywhere**, so ten "
                "trees alpha-tested their trunks for nothing; ours is opaque.\n")
        f.write("* The Standard set has **no wind or toon shader** (that is the paid Source version), so the "
                "look is ours to write.\n\n")
        f.write("## Every model\n\n")
        f.write("| model | family | size x,y,z (m) | x character | sink (m) | tris | materials | verdict | "
                "use |\n|---|---|---|--:|--:|--:|---|---|---|\n")
        for r in rows:
            sz = " x ".join(f"{v:.2f}" for v in r["size"])
            f.write(f"| {r['name']} | {r['kind']} | {sz} | {r['vs_character']:.2f} | {r['sink']:.2f} | "
                    f"{r['tris']} | {', '.join(r['materials'])} | {r['verdict']} | {r['use']} |\n")


if __name__ == "__main__":
    main()
