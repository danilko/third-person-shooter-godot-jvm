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

WHAT IS ASSERTED, AND WHY EACH ONE EXISTS
  * applied transforms — a surviving transform is something compensating for a model that is wrong;
  * the collection — `WeaponLibrary.blend` links the weapon by that name, so a weapon outside it is
    silently missing from the library everyone cross-checks sizes in;
  * `length_m` — the size is a fact from the reference, not a free parameter;
  * `grip_to_rear_m` — the origin really is the grip. The first standard only ASSERTED origin=grip
    and nothing measured it: every raw model's origin had in fact been left wherever a centring
    offset put it (SG1's sat on the receiver, 0.48 m from the butt), and the character carried one
    socket per weapon to hide it. Measuring the distance from the origin to the rearmost point is
    what catches an origin that has walked off the grip again.
"""
import bpy, json, math, os, sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE = os.path.join(ROOT, "blender", "tools", "weapon_models.json")
OUT_DIR = os.path.join(ROOT, "assets", "weapons")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
wanted = set(a for a in argv if not a.startswith("--"))
cfg = json.load(open(TABLE))

LENGTH_TOL = 0.005      # 0.5% of the declared length
GRIP_TOL = 0.01         # 1 cm: the origin may not drift further than this off the grip
APPLIED_TOL = 1e-5      # location/rotation ~0 and scale ~1, i.e. "everything is applied"


def fail(wid, msg):
    raise SystemExit(f"[build_weapon] {wid}: {msg}")


def verify_and_export(w):
    wid = w["id"]
    path = os.path.join(OUT_DIR, wid + ".blend")
    if not os.path.exists(path):
        fail(wid, f"no {path}")
    bpy.ops.wm.open_mainfile(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not objs:
        fail(wid, f"{path} has no mesh")

    # 1. nothing is compensating: every transform is applied
    for o in objs:
        if (o.location.length > APPLIED_TOL
                or max(abs(a) for a in o.rotation_euler) > APPLIED_TOL
                or max(abs(s - 1.0) for s in o.scale) > APPLIED_TOL):
            fail(wid, f"{o.name!r} still carries a transform "
                      f"(loc {tuple(round(v, 4) for v in o.location)}, "
                      f"rot {tuple(round(math.degrees(v), 2) for v in o.rotation_euler)}, "
                      f"scale {tuple(round(v, 4) for v in o.scale)}). "
                      f"Apply it (Object > Apply > All Transforms) — the model IS the weapon.")

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
                              export_apply=True, export_animations=False)
    print(f"[build_weapon] {wid}: {got:.3f} m (declared {want:.3f}), grip->rear {rear:.3f} m, "
          f"wrote {os.path.basename(out)} ({os.path.getsize(out)} bytes)")


rows = [w for w in cfg["weapons"] if not wanted or w["id"] in wanted]
for w in rows:
    verify_and_export(w)
print(f"[build_weapon] exported {len(rows)} weapon(s)")
