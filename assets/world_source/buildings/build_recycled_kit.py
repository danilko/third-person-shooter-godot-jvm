#!/usr/bin/env python3
"""
build_recycled_kit.py -- curates a small, hand-editable library of REAL PLATEAU buildings recycled
from data already extracted for the 10 real precincts (assets/world_source/plateau/data/*.json), for
placement across the 26 generic filler districts (see lib/recycled_buildings.py) INSTEAD OF the
synthetic procedural building generator (lib/buildings.py's fill_frontage/tower_preset). No new
PLATEAU downloads needed -- 2,828 real buildings are already committed and unused beyond their own
precinct's ~260m extraction radius.

Picks a stratified sample across height buckets (low/mid/high/tower) AND across source precincts
(for facade variety), re-centers each building to its OWN footprint-bbox centre sitting on local
z=0 (a normal origin-pivoted placeable asset, unlike the precinct-anchor-relative coordinates the
raw JSON ships), and saves each as its own top-level Blender collection in ONE
buildings/RecycledBuildingKit.blend -- individually hand-editable later, same tier as
buildings/PLATEAU_TokyoTower.blend. Keeps original vertex data as-is (already low-poly LOD1
extrusions, per plan) -- no decimation/retopo.

Two manifests are written alongside the .blend:
  - RecycledBuildingKit.json  (machine-readable: collection name / bucket / footprint w,d / height)
    -- lib/recycled_buildings.py reads this to best-fit a candidate WITHOUT opening the .blend.
  - RECYCLED_KIT_MANIFEST.md  (human-readable table, traces each asset back to its source JSON +
    building index for future manual refinement).

RUN:
  blender --background --python assets/world_source/buildings/build_recycled_kit.py
"""
import bpy, json, glob, os, sys, random

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                        # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import plateau_import as pi
import kit_common as kc

DATA_DIR = os.path.join(ROOT, "plateau", "data")
OUT_BLEND = os.path.join(HERE, "RecycledBuildingKit.blend")
OUT_JSON = os.path.join(HERE, "RecycledBuildingKit.json")
OUT_MD = os.path.join(HERE, "RECYCLED_KIT_MANIFEST.md")

# (bucket, hmin, hmax, target_count). "tower" target is generous -- there are only ~10 real
# buildings >90m across every extracted precinct combined, so "take all" in practice.
BUCKETS = [
    ("low", 0.0, 15.0, 25),
    ("mid", 15.0, 40.0, 12),
    ("high", 40.0, 90.0, 8),
    ("tower", 90.0, 100000.0, 10),
]
SEED = 20260705


def _footprint_bbox(verts):
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, max(xs) - min(xs), max(ys) - min(ys)


def main():
    rng = random.Random(SEED)

    # 1. Load every extracted precinct's buildings, tagged with source + index.
    entries = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        src = os.path.splitext(os.path.basename(path))[0]
        data = pi.load(path)
        ground_z = data.get("ground_reference_elevation_m") or 0.0
        for i, b in enumerate(data.get("buildings", [])):
            entries.append(dict(src=src, idx=i, height=b["height"], verts=b["verts"],
                                 faces=b["faces"], ground_z=ground_z))

    # 2. Bucket by height, then pick `target_count` per bucket spread across as many DIFFERENT
    #    source precincts as possible (round-robin by source) before repeating a source, so the
    #    library isn't dominated by one dense precinct (e.g. Ueno's 867 buildings).
    picked = []
    for bucket, hmin, hmax, target in BUCKETS:
        in_bucket = [e for e in entries if hmin <= e["height"] < hmax]
        by_src = {}
        for e in in_bucket:
            by_src.setdefault(e["src"], []).append(e)
        for lst in by_src.values():
            rng.shuffle(lst)
        srcs = sorted(by_src.keys())
        rng.shuffle(srcs)
        chosen = []
        round_i = 0
        while len(chosen) < target and any(by_src[s] for s in srcs):
            for s in srcs:
                if len(chosen) >= target:
                    break
                if round_i < len(by_src[s]):
                    chosen.append(by_src[s][round_i])
            round_i += 1
        for e in chosen:
            picked.append((bucket, e))

    # 3. Build a fresh .blend: one mesh + one -colonly proxy + one top-level collection per
    #    picked building, re-centred to its own footprint-bbox centre (local origin) at z=0.
    bpy.ops.wm.read_homefile(use_empty=True)
    scene_coll = bpy.context.scene.collection
    manifest_rows = []
    kit_index = {}
    counts = {}
    for bucket, e in picked:
        n = counts.get(bucket, 0)
        counts[bucket] = n + 1
        name = f"RB_{bucket}_{n:02d}"
        cx, cy, w, d = _footprint_bbox(e["verts"])
        coll = bpy.data.collections.new(name)
        scene_coll.children.link(coll)
        obj = pi._mesh_object(name, coll, e["verts"], e["faces"], -cx, -cy, e["ground_z"])
        kc.colonly(obj, coll=coll)
        kit_index[name] = dict(bucket=bucket, height=round(e["height"], 1),
                                footprint_w=round(w, 1), footprint_d=round(d, 1),
                                source=e["src"], source_index=e["idx"])
        manifest_rows.append((name, bucket, round(e["height"], 1), round(w, 1), round(d, 1),
                               e["src"], e["idx"]))

    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)

    with open(OUT_JSON, "w") as f:
        json.dump(kit_index, f, indent=2, sort_keys=True)

    with open(OUT_MD, "w") as f:
        f.write("# RecycledBuildingKit manifest\n\n")
        f.write("Each row = one collection in `RecycledBuildingKit.blend`, real PLATEAU geometry\n")
        f.write("recycled from an already-extracted precinct. Edit the collection directly in\n")
        f.write("Blender to hand-refine; this table just traces it back to its source for reference.\n\n")
        f.write("| asset | bucket | height (m) | footprint w x d (m) | source | source index |\n")
        f.write("|---|---|---|---|---|---|\n")
        for name, bucket, h, w, d, src, idx in manifest_rows:
            f.write(f"| {name} | {bucket} | {h} | {w} x {d} | {src} | {idx} |\n")

    counts_str = ", ".join(f"{b}={c}" for b, c in counts.items())
    print(f"RECYCLED_KIT: {len(picked)} buildings ({counts_str}) -> {OUT_BLEND}")


main()
