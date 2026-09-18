"""Weapon models: the .blend IS the weapon, and the build only proves it and exports it.

    blender -b --python blender/tools/build_weapon.py -- [id ...]

For each weapon in `weapon_models.json` this opens `assets/weapons/<id>.blend`, refuses one that has
stopped conforming (naming the rule that broke), and writes `assets/weapons/<id>.glb` applying
NOTHING. There is no import/normalise step any more: a weapon is modelled (or fixed up) directly in
its .blend, next to every other weapon and the character, in `WeaponLibrary.blend`
(`build_weapon_library.py`) — see blender/WEAPON_AUTHORING.md.

THE STANDARD
  * 1 unit = 1 metre, and the model is its real-world length (`length_m`, taken from a reference)
  * -Z is the muzzle/blade direction, +Y up (Godot axes; Blender +Y forward, +Z up)
  * the ORIGIN is the GRIP — the centre of the firing hand's fist on the grip
  * every object has location 0 / rotation 0 / scale 1, and lives in ONE collection named <id>
  * EXCEPT a MOVING PART (a bolt, a cylinder, a pump — any mesh not named <id>): its origin is its
    PIVOT, so its location is that pivot; rotation 0 / scale 1 still. Its motion is a Blender ACTION on
    an NLA track (never the active action), exported as a glTF animation that Godot imports into the
    model's own `AnimationPlayer` — the weapon scene plays it by name (`fire_animation`,
    `reload_animation`, W13). Keys are sampled at the scene rate, so the .blend runs at 60 fps.

WHAT IS ASSERTED, AND WHY EACH ONE EXISTS
  * applied transforms — a surviving transform is something compensating for a model that is wrong;
    a part's LOCATION is its pivot, which is not compensation — its rotation and scale still are;
  * the clips — `WeaponItem.playMotion` is silent about a clip that does not exist (every weapon calls it
    on every shot), so a renamed action would stop a bolt from moving with nothing said anywhere. Each
    clip the weapon's scene names must be in the export, and an active action is refused (it exports
    twice and makes the rest pose a frame of the clip — the character pipeline's trap);
  * the collection — `WeaponLibrary.blend` links the weapon by that name, so a weapon outside it is
    silently missing from the library everyone cross-checks sizes in;
  * `length_m` — the size is a fact from the reference, not a free parameter;
  * `support_grip: "under"` — the SupportPoint is 2.5-6 cm BELOW the gun's underside, where a hand closing
    under a handguard puts its grip point; inside the gun buries the hand, and no probe sees it;
  * `grip_to_rear_m` — the origin really is the grip. The first standard only ASSERTED origin=grip
    and nothing measured it: every raw model's origin had in fact been left wherever a centring
    offset put it (SHG1's sat on the receiver, 0.48 m from the butt), and the character carried one
    socket per weapon to hide it. Measuring the distance from the origin to the rearmost point is
    what catches an origin that has walked off the grip again.
"""
import bpy, json, math, os, re, sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE = os.path.join(ROOT, "blender", "tools", "weapon_models.json")
OUT_DIR = os.path.join(ROOT, "assets", "weapons")
CATALOG = os.path.join(ROOT, "src", "main", "resources", "com", "openworld", "weapon", "weapon_catalog.json")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
wanted = set(a for a in argv if not a.startswith("--"))
cfg = json.load(open(TABLE))

LENGTH_TOL = 0.005      # 0.5% of the declared length
GRIP_TOL = 0.01         # 1 cm: the origin may not drift further than this off the grip
APPLIED_TOL = 1e-5
SUPPORT_UNDER_MIN, SUPPORT_UNDER_MAX = 0.025, 0.06      # location/rotation ~0 and scale ~1, i.e. "everything is applied"


def fail(wid, msg):
    raise SystemExit(f"[build_weapon] {wid}: {msg}")


def verify_and_export(w):
    wid = w["id"]
    path = os.path.join(OUT_DIR, wid + ".blend")
    if not os.path.exists(path):
        fail(wid, f"no {path}")
    bpy.ops.wm.open_mainfile(filepath=path)
    # Read the REST pose: before any clip starts. A clip that ends away from rest (a cylinder indexed one
    # chamber) would otherwise be read at its last frame if the file was saved past it.
    bpy.context.scene.frame_set(0)
    objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not objs:
        fail(wid, f"{path} has no mesh")

    # 1. nothing is compensating: every transform is applied (a moving part keeps its pivot as location)
    for o in objs:
        part = o.name != wid
        if ((not part and o.location.length > APPLIED_TOL)
                or max(abs(a) for a in o.rotation_euler) > APPLIED_TOL
                or max(abs(s - 1.0) for s in o.scale) > APPLIED_TOL):
            fail(wid, f"{o.name!r} still carries a transform "
                      f"(loc {tuple(round(v, 4) for v in o.location)}, "
                      f"rot {tuple(round(math.degrees(v), 2) for v in o.rotation_euler)}, "
                      f"scale {tuple(round(v, 4) for v in o.scale)}). "
                      f"Apply it (Object > Apply > All Transforms) — the model IS the weapon"
                      + (" (a moving part may keep only its pivot as a location)." if part else "."))
        if o.animation_data and o.animation_data.action is not None:
            fail(wid, f"{o.name!r} has an ACTIVE action {o.animation_data.action.name!r}. Push it down to an NLA "
                      f"track and clear the active action: an active action exports twice and its current "
                      f"frame becomes the part's rest pose.")
        for t in (o.animation_data.nla_tracks if o.animation_data else []):
            for st in t.strips:
                if st.extrapolation == 'NOTHING':
                    fail(wid, f"{o.name!r} clip {st.name!r} has extrapolation NOTHING: outside the strip Blender "
                              f"resets the animated channels to 0, so the part exports at the weapon's origin "
                              f"instead of its pivot. Set the strip's Extrapolation to Hold.")
    clips = sorted({s.action.name for o in objs if o.animation_data
                    for t in o.animation_data.nla_tracks for s in t.strips if s.action})
    # Godot's scene importer reads a `loop`/`cycle` prefix or suffix (`-` or `_`) as a LOOP hint: it loops the
    # clip AND strips the word, so `bolt_cycle` arrived as a looping `bolt` and the scene's name matched nothing.
    hinted = [c for c in clips if re.search(r'(^(loop|cycle)[-_])|([-_](loop|cycle)$)', c, re.I)]
    if hinted:
        fail(wid, f"clip(s) {hinted} start or end with loop/cycle: Godot's importer loops them and strips the word, "
                  f"so the scene's fire_animation/reload_animation would name nothing. A per-shot part motion "
                  f"plays once — rename the action (e.g. bolt_work).")
    if clips and bpy.context.scene.render.fps < 60:
        fail(wid, f"scene runs at {bpy.context.scene.render.fps} fps; clips {clips} are sampled at the scene rate, "
                  f"which is too coarse for a 0.1 s part motion. Set Output > Frame Rate to 60.")

    # 2. it is filed where the library looks for it
    col = bpy.data.collections.get(wid)
    stray = [o.name for o in objs if col is None or o.name not in col.all_objects]
    if stray:
        fail(wid, f"mesh(es) {stray} are not in a collection named {wid!r} — WeaponLibrary.blend "
                  f"links the weapon by that name, so they would be missing from it.")

    # 3. it is the size the reference says, and its origin is still on the grip
    vs = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo_y, hi_y = min(p.y for p in vs), max(p.y for p in vs)
    got, want = hi_y - lo_y, w["length_m"]
    if abs(got - want) / want > LENGTH_TOL:
        fail(wid, f"model measures {got:.3f} m but the table declares {want:.3f} m "
                  f"({w['reference']['based_on']}). Fix the model, or the table if the weapon changed.")
    rear, want_rear = -lo_y, w["grip_to_rear_m"]
    if abs(rear - want_rear) > GRIP_TOL:
        fail(wid, f"origin is {rear:.3f} m from the rearmost point but the table declares "
                  f"{want_rear:.3f} m — the origin has left the grip. Put it back on the centre of "
                  f"the firing hand's fist (Object > Set Origin, then Apply) and re-export.")

    out = os.path.join(OUT_DIR, wid + ".glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_yup=True,
                              export_apply=True, export_animations=bool(clips),
                              export_animation_mode='ACTIONS')
    # 4. every material carries a colour across glTF. Blender exports a base colour only from the ACTIVE
    # output's Principled BSDF as a constant or an image; a material whose exported output is anything else
    # (SNR1 shipped with a second, Cycles-only Material Output fed by a Diffuse BSDF) arrives in Godot as
    # plain white, with no warning on either side.
    import struct
    data = open(out, "rb").read()
    gltf = json.loads(data[20:20 + struct.unpack("<I", data[12:16])[0]])
    blank = [m.get("name", "?") for m in gltf.get("materials", [])
             if "baseColorFactor" not in m.get("pbrMetallicRoughness", {})
             and "baseColorTexture" not in m.get("pbrMetallicRoughness", {})]
    if blank:
        fail(wid, f"material(s) {blank} exported with NO base colour, so they render white in Godot. Give each "
                  f"one a single Material Output (target All) fed by a Principled BSDF whose Base Color is a "
                  f"constant or an image texture, then re-export.")

    # 5. every clip the weapon's scene plays is in the export
    exported = sorted(a.get("name", "?") for a in gltf.get("animations", []))
    scene_rel = next((r["scene"] for r in json.load(open(CATALOG))["weapons"] if r["id"] == wid), None)
    played, text = [], ""
    if scene_rel:
        text = open(os.path.join(ROOT, scene_rel.replace("res://", ""))).read()
        played = [c for c in re.findall(r'^(?:fire|reload)_animation = "([^"]*)"', text, re.M) if c]
    missing = [c for c in played if c not in exported]
    if missing:
        fail(wid, f"{scene_rel} plays {missing} but the export carries {exported or 'no clips'} — the part would "
                  f"never move, silently. Name the action after the clip (one NLA track per clip).")

    # 6. a support hand that closes UNDER a handguard/pump has its grip point below the gun, not inside it.
    # SupportHandIKModifier puts the hand's grip (75% of the way to middle_01) on SupportPoint, so a point inside
    # the forend buries the hand in it — SNR1 shipped with its point 2 cm inside, and every probe passed because
    # they measure the hand against the MARKER. The shipped long guns sit 3.4-4.6 cm under.
    support = ""
    if w.get("support_grip") == "under":
        m = scene_rel and re.search(r'\[node name="SupportPoint"[^\n]*\]\ntransform = Transform3D\((?:[-\d.e]+, ){9}'
                                    r'([-\d.e]+), ([-\d.e]+), ([-\d.e]+)\)', text)
        if not m:
            fail(wid, f"table says support_grip 'under' but {scene_rel} has no SupportPoint marker")
        gx, gy, gz = map(float, m.groups())
        px, py, pz = gx, -gz, gy                                   # Godot weapon frame -> Blender
        from mathutils.bvhtree import BVHTree
        verts, polys = [], []
        for o in objs:
            b = len(verts)
            verts += [o.matrix_world @ v.co for v in o.data.vertices]
            polys += [[b + i for i in p.vertices] for p in o.data.polygons]
        bvh = BVHTree.FromPolygons(verts, polys)
        bottom = None
        for dy in (0.0, 0.01, -0.01, 0.02, -0.02, 0.03, -0.03):   # nearest station along the bore with a surface
            hit = bvh.ray_cast(Vector((px, py + dy, -1.0)), Vector((0, 0, 1)), 3.0)[0]
            if hit is not None:
                bottom = hit.z
                break
        clearance = None if bottom is None else bottom - pz
        if clearance is None or not (SUPPORT_UNDER_MIN <= clearance <= SUPPORT_UNDER_MAX):
            fail(wid, f"SupportPoint is {'over no surface' if clearance is None else f'{clearance:+.3f} m under the gun'}; "
                      f"a hand closing under a handguard needs it {SUPPORT_UNDER_MIN:.3f}-{SUPPORT_UNDER_MAX:.3f} m below the "
                      f"underside (negative = inside the gun, the hand is buried). Move the marker in {scene_rel}.")
        support = f", SupportPoint {clearance:.3f} m under the gun"

    print(f"[build_weapon] {wid}: {got:.3f} m (declared {want:.3f}), grip->rear {rear:.3f} m, "
          f"clips {exported or '-'}{support}, wrote {os.path.basename(out)} ({os.path.getsize(out)} bytes)")


rows = [w for w in cfg["weapons"] if not wanted or w["id"] in wanted]
rows += [dict(v, id=k) for table in ("projectiles", "equipment") for k, v in cfg.get(table, {}).items()
         if k != "note" and (not wanted or k in wanted)]
for w in rows:
    verify_and_export(w)
print(f"[build_weapon] exported {len(rows)} weapon(s)")
