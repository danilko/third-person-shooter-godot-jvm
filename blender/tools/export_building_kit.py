"""Export a building kit's pieces FROM its .blend (PLAN.md 3.6b step 1: the kit .blend is the owner).

    blender -b assets/world_source/kits/<kit>/<kit>.blend --python-exit-code 1 \\
            --python blender/tools/export_building_kit.py [-- --out <dir>]

For every piece collection (a collection carrying `bk_piece_path`, laid out by build_building_kit_blend.py) this
writes `<out>/pieces/<category>/<Piece>.gltf + .bin` and then `<out>/pieces.json`; `<out>` defaults to the kit
folder, i.e. the pieces the game builds from.

* A piece sits at its grid spot in the file; the collection's `instance_offset` IS that spot, so the export moves
  the piece's top-level objects back by it -- a piece is exported about its own origin, exactly where it was
  authored before it was laid out. (The file is never saved; the move happens in memory only.)
* The model is the size (CLAUDE.md W19): nothing is scaled here. `module_scale` was baked in once, when the kit
  was first imported (`tools/building_kit/normalize_kit.py --init`), and from then on the .blend is at game size.
* Materials leave by NAME only as far as the game cares: every surface is re-resolved to
  `<kit>/materials/<name>.tres` by `tools/godot/build_building_scenes.gd`. Textures are referenced where they
  already are (`export_keep_originals`, a relative `../../textures/` uri), never copied.
* Every UV map and colour attribute is exported (the kit's COLOR_0 is a wear mask a material may read).
* `pieces.json` is measured by `normalize_kit.measure`, the same function that measured the downloaded pieces,
  so a size cannot differ depending on which tool wrote the file.
* THE BOUNDS ARE THE KIT'S CONTRACT WITH THE LAYOUT (`layout_buildings.py` places every piece from them), so an
  export whose piece bounds move more than `BOUNDS_TOL` from the `pieces.json` already there -- a wall nudged
  10 cm by accident, a piece renamed or deleted -- is REFUSED and nothing is written: the export goes to a
  temporary folder first and is installed only when it passes. A deliberate change is accepted with
  `-- --accept-bounds` (or `ACCEPT_BOUNDS=1 tools/building_kit/build_buildings.sh`); then re-run the layout
  self-test and `probe_buildings.gd`, which is what `build_buildings.sh` does next anyway.
"""
import json
import os
import shutil
import sys
import tempfile

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "building_kit"))
import normalize_kit as nk  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
KIT_DIR = os.path.dirname(bpy.data.filepath)
OUT = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else KIT_DIR
ACCEPT = "--accept-bounds" in argv or os.environ.get("ACCEPT_BOUNDS") == "1"
#: How far a piece's bounds may move before the export calls it a change to the kit (1 mm; Blender's re-export
#: of the downloaded pieces measured 0.1 mm at worst).
BOUNDS_TOL = 0.001
STAGE = tempfile.mkdtemp(prefix="building_kit_")
KIT = json.load(open(os.path.join(KIT_DIR, "kit.json")))
s = float(KIT["module_scale"])
manifest = {"kit": KIT["id"], "module_scale": s,
            "module_m": round(KIT["source_module_m"] * s, 4),
            "storey_m": round(KIT["source_storey_m"] * s, 4),
            "generated_by": "blender/tools/export_building_kit.py", "pieces": {}}

pieces = sorted((c for c in bpy.data.collections if c.get("bk_piece_path")), key=lambda c: c.name)
if not pieces:
    raise SystemExit("export_building_kit: no piece collections (bk_piece_path) in %s" % bpy.data.filepath)
view_layer = bpy.context.view_layer
for col in pieces:
    cat = col["bk_category"]
    name = col.name
    objs = list(col.all_objects)
    if not objs:
        raise SystemExit("export_building_kit: piece %s has no objects" % name)
    off = col.instance_offset.copy()
    tops = [o for o in objs if o.parent is None or o.parent not in objs]
    for o in tops:
        o.location = o.location - off
    for o in view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    rel = os.path.join("pieces", cat)
    os.makedirs(os.path.join(STAGE, rel), exist_ok=True)
    path = os.path.join(STAGE, rel, name + ".gltf")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLTF_SEPARATE", use_selection=True, export_yup=True,
                              export_apply=False, export_keep_originals=True, export_vertex_color="ACTIVE",
                              export_all_vertex_colors=True, export_extras=True, export_cameras=False,
                              export_lights=False, export_animations=False)
    for o in tops:
        o.location = o.location + off
    # export_keep_originals writes the texture's path relative to where the FILE is; a --out elsewhere would
    # point at the wrong place, so the uri is always the kit's own textures folder.
    gltf = json.load(open(path))
    for img in gltf.get("images", []):
        img["uri"] = "../../textures/" + os.path.basename(img["uri"])
    gltf.setdefault("asset", {})["extras"] = {"exported_by": "blender/tools/export_building_kit.py",
                                              "module_scale": s}
    with open(path, "w") as fh:
        fh.write(json.dumps(gltf, indent=1) + "\n")
    lo, hi = nk.measure(gltf)
    manifest["pieces"][name] = nk.manifest_entry(name, cat, gltf, lo, hi)



def bounds_changes(old, new):
    """[(piece, what)] for every piece added, removed, re-categorised or moved more than BOUNDS_TOL."""
    out = []
    for n in sorted(set(old) | set(new)):
        if n not in new:
            out.append((n, "removed"))
        elif n not in old:
            out.append((n, "added"))
        elif old[n]["category"] != new[n]["category"]:
            out.append((n, "category %s -> %s" % (old[n]["category"], new[n]["category"])))
        else:
            d = max(abs(old[n][k][i] - new[n][k][i]) for k in ("min", "max") for i in range(3))
            if d > BOUNDS_TOL:
                out.append((n, "bounds moved %.4f m (min %s -> %s, max %s -> %s)"
                            % (d, old[n]["min"], new[n]["min"], old[n]["max"], new[n]["max"])))
    return out


old_path = os.path.join(OUT, "pieces.json")
if os.path.exists(old_path):
    changes = bounds_changes(json.load(open(old_path))["pieces"], manifest["pieces"])
    for n, what in changes:
        print("[export_building_kit] %s: %s" % (n, what))
    if changes and not ACCEPT:
        shutil.rmtree(STAGE)
        raise SystemExit("export_building_kit: %d piece(s) changed their bounds; nothing written. If that is "
                         "deliberate, re-run with -- --accept-bounds (ACCEPT_BOUNDS=1)." % len(changes))
with open(os.path.join(STAGE, "pieces.json"), "w") as fh:
    fh.write(json.dumps(manifest, indent=1) + "\n")
# install: a file is rewritten only if its bytes changed; a piece no longer in the file is removed
written = 0
for dirpath, _dirs, files in os.walk(STAGE):
    for f in files:
        src = os.path.join(dirpath, f)
        dst = os.path.join(OUT, os.path.relpath(src, STAGE))
        data = open(src, "rb").read()
        if not os.path.exists(dst) or open(dst, "rb").read() != data:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(data)
            written += 1
keep = {os.path.relpath(os.path.join(d, f), STAGE) for d, _x, fs in os.walk(STAGE) for f in fs}
for dirpath, _dirs, files in os.walk(os.path.join(OUT, "pieces")):
    for f in files:
        rel = os.path.relpath(os.path.join(dirpath, f), OUT)
        if f.endswith((".gltf", ".bin")) and rel not in keep:
            os.remove(os.path.join(OUT, rel))
            print("[export_building_kit] removed %s" % rel)
shutil.rmtree(STAGE)
print("[export_building_kit] %d pieces, %d files written -> %s" % (len(pieces), written, OUT))
