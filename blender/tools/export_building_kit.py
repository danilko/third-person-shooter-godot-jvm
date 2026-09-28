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
* A kit may span SEVERAL .blend files (kit.json `blends`, the station kit: one file per station form). Each file
  writes only its own categories: the other files' pieces stay in `pieces.json` untouched, and only this file's
  categories are bounds-checked and pruned.
* What a piece carries besides its mesh is EMPTIES in its collection (the station kit's contract): `COL_*` (drawn as a
  cube; location = box centre, scale = half size) become `collide_boxes` ([cx, cy, cz, sx, sy, sz], Godot axes, the
  piece's own frame -- the shape `layout_buildings.place_props`' `collide: {boxes}` takes), and `GATE_*` (a ticket-gate
  lane; its local +Z is the unpaid side) become `gates` ({pos, out, w, h}), and `LIFT_*` (a lift's shaft floor at its
  low stop, props w/d/rise/door_w/door_h) become `lifts`, and `DOOR_*` (an INTERIOR door in a wall piece's hole: a
  single arrow on the floor at the doorway's centre pointing OUT of the room; props w, h, style "swing" | "slide",
  slide_dir +1 / -1 = the sliding leaf runs to the RIGHT / LEFT seen from where the arrow points) become `doors`.
  Empties never go into the glTF.
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
import math
import os
import shutil
import sys
import tempfile

import bpy
import mathutils

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
# The manifest header has ONE owner (normalize_kit), so the two writers of pieces.json cannot disagree about
# what a kit's header says -- including a props kit that has no module and no storey.
manifest = nk.manifest_header(KIT, "blender/tools/export_building_kit.py")

# a LINKED collection (another kit's piece, shown here by a PROP_ instance) is that kit's to export, never this one's
pieces = sorted((c for c in bpy.data.collections if c.get("bk_piece_path") and c.library is None),
                key=lambda c: c.name)
if not pieces:
    raise SystemExit("export_building_kit: no piece collections (bk_piece_path) in %s" % bpy.data.filepath)
MULTI = bool(KIT.get("blends"))
OWN_CATS = {c["bk_category"] for c in pieces}


def godot(v):
    """Blender (x, y, z) -> Godot (x, z, -y), rounded."""
    return [round(v[0], 5), round(v[2], 5), round(-v[1], 5)]


def markers(col):
    """The piece's COL_, GATE_ and LIFT_ Empties, in the piece's own frame (the grid offset removed), Godot axes."""
    boxes, gates, lifts, hulls, doors, props = [], [], [], [], [], []
    for o in sorted(col.all_objects, key=lambda o: o.name):
        if o.type != "EMPTY":
            continue
        loc = o.matrix_world.to_translation() - col.instance_offset
        if o.name.startswith("COL_"):
            sc = o.matrix_world.to_scale()
            half = [abs(sc[0]) * o.empty_display_size, abs(sc[1]) * o.empty_display_size,
                    abs(sc[2]) * o.empty_display_size]
            boxes.append(godot(loc) + [round(2 * half[0], 5), round(2 * half[2], 5), round(2 * half[1], 5)])
        elif o.name.startswith("GATE_"):
            z = o.matrix_world.to_3x3() @ mathutils.Vector((0.0, 0.0, 1.0))
            z.z = 0.0
            z = z.normalized() if z.length > 1e-6 else mathutils.Vector((1.0, 0.0, 0.0))
            gates.append({"pos": godot(loc), "out": godot(z), "w": float(o.get("w", 0.9)),
                          "h": float(o.get("h", 1.0))})
        elif o.name.startswith("DOOR_"):
            z = o.matrix_world.to_3x3() @ mathutils.Vector((0.0, 0.0, 1.0))
            z.z = 0.0
            z = z.normalized() if z.length > 1e-6 else mathutils.Vector((0.0, -1.0, 0.0))
            doors.append({"pos": godot(loc), "out": godot(z), "w": float(o.get("w", 0.85)),
                          "h": float(o.get("h", 2.0)), "style": str(o.get("style", "swing")),
                          "slide_dir": 1.0 if float(o.get("slide_dir", 1.0)) >= 0 else -1.0})
        elif o.name.startswith("PROP_"):
            # a LIBRARY fixture placed with the piece (a station restroom's washlet toilet, basin, ...): the game places
            # the library piece `piece` here, turned by the Empty's Z rotation (Blender's Z turn is Godot's yaw)
            yaw = math.degrees(o.matrix_world.to_euler().z)
            props.append({"piece": str(o["piece"]), "pos": godot(loc), "yaw": round(yaw % 360.0, 4),
                          "collide": str(o.get("collide", "none"))})
        elif o.name.startswith("HULL_"):
            # a CONVEX collider (a ramp's smooth slope): its points, relative to the Empty, in its custom property
            pts = list(o["pts"])
            hulls.append([godot(loc + mathutils.Vector(pts[i:i + 3])) for i in range(0, len(pts), 3)])
        elif o.name.startswith("LIFT_"):
            # a lift (world.Elevator): the shaft floor's centre at the low stop; w along the piece's X, d along its
            # Y (Godot Z), its doors on the two X faces
            lifts.append({"pos": godot(loc), "w": float(o["w"]), "d": float(o["d"]), "rise": float(o["rise"]),
                          "door_w": float(o.get("door_w", 1.1)), "door_h": float(o.get("door_h", 2.1))})
    return boxes, gates, lifts, hulls, doors, props
view_layer = bpy.context.view_layer
for col in pieces:
    cat = col["bk_category"]
    name = col.name
    objs = [o for o in col.all_objects if o.type != "EMPTY"]
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
    blob = open(os.path.join(os.path.dirname(path), gltf["buffers"][0]["uri"]), "rb").read()
    for img in gltf.get("images", []):
        img["uri"] = "../../textures/" + os.path.basename(img["uri"])
    gltf.setdefault("asset", {})["extras"] = {"exported_by": "blender/tools/export_building_kit.py",
                                              "module_scale": s}
    with open(path, "w") as fh:
        fh.write(json.dumps(gltf, indent=1) + "\n")
    lo, hi = nk.measure(gltf, blob)
    manifest["pieces"][name] = nk.manifest_entry(name, cat, gltf, lo, hi)
    boxes, gates, lifts, hulls, doors, props = markers(col)
    if props:
        manifest["pieces"][name]["props"] = props
    if doors:
        manifest["pieces"][name]["doors"] = doors
    if hulls:
        manifest["pieces"][name]["collide_hulls"] = hulls
    if lifts:
        manifest["pieces"][name]["lifts"] = lifts
    if boxes:
        manifest["pieces"][name]["collide_boxes"] = boxes
    if gates:
        manifest["pieces"][name]["gates"] = gates



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
    old_pieces = json.load(open(old_path))["pieces"]
    if MULTI:
        # another .blend's pieces are that file's to export: keep them, and judge only this file's categories
        for n, e in old_pieces.items():
            if e["category"] not in OWN_CATS and n not in manifest["pieces"]:
                manifest["pieces"][n] = e
        old_pieces = {n: e for n, e in old_pieces.items() if e["category"] in OWN_CATS}
    changes = bounds_changes(old_pieces, {n: e for n, e in manifest["pieces"].items()
                                          if not MULTI or e["category"] in OWN_CATS})
    for n, what in changes:
        print("[export_building_kit] %s: %s" % (n, what))
    if changes and not ACCEPT:
        shutil.rmtree(STAGE)
        raise SystemExit("export_building_kit: %d piece(s) changed their bounds; nothing written. If that is "
                         "deliberate, re-run with -- --accept-bounds (ACCEPT_BOUNDS=1)." % len(changes))
manifest["pieces"] = dict(sorted(manifest["pieces"].items()))
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
        if MULTI and os.path.basename(os.path.dirname(os.path.join(dirpath, f))) not in OWN_CATS:
            continue
        if f.endswith((".gltf", ".bin")) and rel not in keep:
            os.remove(os.path.join(OUT, rel))
            print("[export_building_kit] removed %s" % rel)
        elif f.endswith(".gltf.import") and rel[:-len(".import")] not in keep:
            os.remove(os.path.join(OUT, rel))     # Godot's import record of a piece that is gone
            print("[export_building_kit] removed %s" % rel)
shutil.rmtree(STAGE)
print("[export_building_kit] %d pieces, %d files written -> %s" % (len(pieces), written, OUT))
