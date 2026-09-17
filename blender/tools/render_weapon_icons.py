"""Weapon icons: one white silhouette per weapon, plus a review contact sheet.

    blender --background --python-exit-code 1 --python blender/tools/render_weapon_icons.py [-- ID ...]
            [-- --side=right --muzzle=right --scale=uniform --width=512 --height=128 --padding=6 --out=/tmp/icons]   (try a variant)

Every row of `src/main/resources/com/openworld/weapon/weapon_catalog.json` that has a model
(`assets/weapons/<id>.blend`) or a primitive (`weapon_models.json` `primitives`) is rendered with the
catalog's `icon` spec, so the tool, the weapon scenes and WeaponCatalogTest read one owner:

  * an ORTHOGRAPHIC side view (no perspective, no tilt: a tilt breaks the silhouette and makes two
    weapons of one length read as different lengths), `side` facing the viewer and the muzzle
    pointing `muzzle` on screen (shipped: the LEFT side, muzzle left — the natural view; mirrored only if the
    two disagree);
  * the whole model flat WHITE on a TRANSPARENT background — the UI tints it (modulate), so one PNG serves a
    kill feed, a greyed-out empty slot and a highlighted selection;
  * CENTRED in the `width` x `height` frame at ONE `pixels_per_metre` for every weapon (`scale` "uniform"),
    so the icons keep the weapons' real relative size and the UI scales every frame the same way; `scale`
    "fit" fills each frame instead (and `--scale=fit` tries it);
  * rendered at 4x and box-filtered down, so edges are anti-aliased from real coverage, not resampled.

Writes `<dir>/<id>.png` for each weapon and `review_sheet` (all icons on a dark background, catalog order,
never loaded by the game — its folder carries a .gdignore). A primitive-only weapon (no .blend) is rendered
from its primitive box/tube and reported as a PLACEHOLDER: its icon is a rectangle until it is modelled.
Fist has neither and gets no icon.
"""
import bpy, json, math, os, sys
import numpy as np
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG = os.path.join(ROOT, "src/main/resources/com/openworld/weapon/weapon_catalog.json")
MODELS = os.path.join(ROOT, "blender/tools/weapon_models.json")
SS = 4  # supersample factor


def res_path(p):
    return os.path.join(ROOT, p[len("res://"):]) if p.startswith("res://") else p


def weapon_objects(wid):
    """The weapon's meshes: its .blend's collection <id>, or a primitive built from weapon_models.json."""
    path = os.path.join(ROOT, "assets/weapons", wid + ".blend")
    if os.path.exists(path):
        bpy.ops.wm.open_mainfile(filepath=path)
        col = bpy.data.collections.get(wid)
        return [o for o in col.all_objects if o.type == 'MESH'], False
    prim = json.load(open(MODELS)).get("primitives", {}).get(wid)
    if not isinstance(prim, dict) or "size" not in prim:
        return [], False
    bpy.ops.wm.read_homefile(use_empty=True)
    sx, sy, sz = prim["size"]            # Godot axes: x right, y up, z back
    cx, cy, cz = prim["center"]
    # Godot (x, y, z) -> Blender (x, -z, y); the weapon's length (Godot z) is Blender y.
    if wid == "ATL1":
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=sx / 2, depth=sz, location=(cx, -cz, cy),
                                            rotation=(math.pi / 2, 0, 0))
    else:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, -cz, cy))
        bpy.context.object.scale = (sx, sz, sy)
    return [bpy.context.object], True


def render_icon(wid, spec):
    objs, placeholder = weapon_objects(wid)
    if not objs:
        return None
    W, H, pad = spec["width"], spec["height"], spec["padding"]
    scn = bpy.context.scene
    for o in scn.objects:
        o.hide_render = o not in objs
    deps = bpy.context.evaluated_depsgraph_get()
    ys, zs, xs = [], [], []
    for o in objs:
        ev = o.evaluated_get(deps)
        for v in ev.to_mesh().vertices:
            w = o.matrix_world @ v.co
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
        ev.to_mesh_clear()
    length, height = max(ys) - min(ys), max(zs) - min(zs)
    ctr = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (max(zs) + min(zs)) / 2))
    if spec.get("scale", "fit") == "uniform":
        # One scale for every weapon: real relative size, centred. A weapon too big for the frame is an error,
        # not a reason to shrink it — that would make it the one icon drawn at a different scale.
        px_per_m = float(spec["pixels_per_metre"])
        if length * px_per_m > W - 2 * pad or height * px_per_m > H - 2 * pad:
            raise SystemExit(f"[weapon_icons] {wid}: {length:.3f} x {height:.3f} m is "
                             f"{length * px_per_m:.0f} x {height * px_per_m:.0f} px at {px_per_m:g} px/m, which does "
                             f"not fit {W}x{H} less {pad} px padding. Lower pixels_per_metre (or widen the frame) "
                             f"in weapon_catalog.json and regenerate every icon.")
    else:
        px_per_m = min((W - 2 * pad) / length, (H - 2 * pad) / height)

    cam_data = bpy.data.cameras.new("icon_cam")
    cam_data.type = 'ORTHO'
    cam_data.sensor_fit = 'HORIZONTAL'
    cam_data.ortho_scale = W / px_per_m
    cam = bpy.data.objects.new("icon_cam", cam_data)
    scn.collection.objects.link(cam)
    right = spec.get("side", "left") == "right"
    # Blender: weapon forward +Y, up +Z, the weapon's right is +X. Looking at the right side from +X puts the
    # muzzle on screen-right; looking at the left side from -X puts it on screen-left. The image is mirrored
    # only when `muzzle` asks for the other direction than the side naturally gives.
    cam.location = ctr + Vector(((max(xs) - min(xs)) + 5.0) * (1 if right else -1) * Vector((1, 0, 0)))
    look = Vector((-1, 0, 0)) if right else Vector((1, 0, 0))
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    scn.camera = cam

    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.display.shading.light = 'FLAT'
    scn.display.shading.color_type = 'SINGLE'
    scn.display.shading.single_color = (1, 1, 1)
    scn.display.shading.show_object_outline = False
    scn.display.render_aa = '32'
    scn.render.film_transparent = True
    scn.render.resolution_x, scn.render.resolution_y = W * SS, H * SS
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format = 'PNG'
    scn.render.image_settings.color_mode = 'RGBA'
    raw = os.path.join(bpy.app.tempdir or "/tmp", f"icon_raw_{wid}.png")
    scn.render.filepath = raw
    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(raw, check_existing=False)
    a = np.array(img.pixels[:], dtype=np.float32).reshape(H * SS, W * SS, 4)[::-1, :, 3]   # bottom-up -> top-down
    bpy.data.images.remove(img)
    os.remove(raw)
    a = a.reshape(H, SS, W, SS).mean(axis=(1, 3))       # box filter: real coverage per output pixel
    natural = "right" if right else "left"
    if spec.get("muzzle", natural) != natural:
        a = a[:, ::-1]
    return a, length, height, placeholder


def save_rgba(path, rgb, alpha):
    """rgb (H, W, 3) or a scalar, alpha (H, W); rows top-down."""
    H, W = alpha.shape
    px = np.ones((H, W, 4), dtype=np.float32)
    px[:, :, :3] = rgb
    px[:, :, 3] = alpha
    img = bpy.data.images.new(os.path.basename(path), W, H, alpha=True)
    img.pixels.foreach_set(px[::-1].ravel())            # Blender images are bottom-up
    img.filepath_raw = path
    img.file_format = 'PNG'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save()
    bpy.data.images.remove(img)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = dict(a[2:].split("=", 1) for a in args if a.startswith("--") and "=" in a)
    argv = [a for a in args if not a.startswith("--")]
    cat = json.load(open(CATALOG))
    spec = dict(cat["icon"])
    # Try a variant without touching the shipped icons: --side=left, --width= / --height= / --padding=,
    # --out=<dir> (the review sheet goes to <dir>/review/sheet.png).
    if "side" in opts: spec["side"] = opts["side"]
    if "muzzle" in opts: spec["muzzle"] = opts["muzzle"]
    for k in ("width", "height", "padding", "pixels_per_metre"):
        if k in opts: spec[k] = int(opts[k])
    if "scale" in opts: spec["scale"] = opts["scale"]
    if "out" in opts:
        spec["dir"] = os.path.abspath(opts["out"])
        spec["review_sheet"] = os.path.join(spec["dir"], "review", "sheet.png")
    out_dir = res_path(spec["dir"])
    rows = [r for r in cat["weapons"] if not argv or r["id"] in argv]
    icons = []
    for r in rows:
        got = render_icon(r["id"], spec)
        if got is None:
            print(f"[weapon_icons] {r['id']}: no model and no primitive — no icon")
            continue
        alpha, length, height, placeholder = got
        dst = os.path.join(out_dir, r["id"] + ".png")
        save_rgba(dst, 1.0, alpha)
        ys, xs = np.nonzero(alpha > 0.02)
        print(f"[weapon_icons] {r['id']}: {length:.3f} x {height:.3f} m ({length / height:.2f}:1, {spec.get('scale', 'fit')}) -> "
              f"{os.path.relpath(dst, ROOT)}, content {xs.max() - xs.min() + 1}x{ys.max() - ys.min() + 1} px"
              + ("  PLACEHOLDER (primitive, no model)" if placeholder else ""))
        icons.append(alpha)

    if icons and not argv:
        H, W = icons[0].shape
        cols, gap = 2, 16
        n_rows = math.ceil(len(icons) / cols)
        sheet_h, sheet_w = n_rows * (H + gap) + gap, cols * (W + gap) + gap
        rgb = np.full((sheet_h, sheet_w, 3), 0.12, dtype=np.float32)
        for i, a in enumerate(icons):
            y, x = gap + (i // cols) * (H + gap), gap + (i % cols) * (W + gap)
            rgb[y:y + H, x:x + W] = 0.18                   # the frame, so padding and centring are visible
            cell = rgb[y:y + H, x:x + W]
            rgb[y:y + H, x:x + W] = cell * (1 - a[:, :, None]) + a[:, :, None]
        sheet = res_path(spec["review_sheet"])
        save_rgba(sheet, rgb, np.ones((sheet_h, sheet_w), dtype=np.float32))
        ignore = os.path.join(os.path.dirname(sheet), ".gdignore")
        if not os.path.exists(ignore):
            open(ignore, "w").close()
        print(f"[weapon_icons] review sheet {os.path.relpath(sheet, ROOT)} ({len(icons)} icons, catalog order, "
              f"{cols} per row)")


main()
