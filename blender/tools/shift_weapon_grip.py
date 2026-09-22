"""Move a weapon's GRIP POINT down its grip by DZ metres, i.e. the model up by DZ in its own frame. A one-shot
(the import_melee_pack.py contract): the record of what was done, not a build step. NOT idempotent -- run once.

    blender -b --python-exit-code 1 --python blender/tools/shift_weapon_grip.py -- DZ ID [ID ...]

The weapon standard puts the model's origin on the centre of the firing fist (WEAPON_AUTHORING.md), and the
character's socket holds that origin -- so "the hand holds the gun lower" and "the gun sits higher in the hand"
are the same change, made in the MODEL (SNR1 took the same +0.02 m in W33). For each ID:
  * assets/weapons/<ID>.blend: the main mesh's data moves +DZ in Blender Z; a moving part (origin = its pivot,
    e.g. REV1's Cylinder) moves by its LOCATION instead, so its pivot stays on its axis; transforms stay applied;
  * src/main/resources/com/openworld/weapon/<ID>.tscn: every Marker3D (Muzzle, SupportPoint, StockPoint,
    MuzzleLeft) and CollisionShape3D moves +DZ in Godot Y (Blender Z up = Godot Y up). The muzzle flashes ride
    their markers; ModelLeft (DUP1's second gun) instances the shifted .glb itself.
A PISTOL's SupportPoint is the support hand cupped round the firing FIST, not a point on the gun, so it belongs
to the fist and must NOT move with the model: after this tool, put PIS1/PIS2/REV1's SupportPoint back (it was done
by hand, 2026-09-21). SMG1's is its vertical foregrip, a point on the gun, and moves with it.
Then `build_weapon.py <ID>` verifies (length and grip->rear are unchanged by a vertical move) and exports.

2026-09-21 (user: "shift the grip point down ~5 cm so the pistol is held higher"): PIS1, PIS2, DUP1, REV1, SMG1
by 0.03 m. 5 cm was measured first and rejected: the grips reach only 5.3-6.4 cm below the old fist centre, so a
5 cm move leaves the lower half of the fist (pinky, ring finger) closing on air below the grip.
Then (user: align the fist with the trigger) PIS1, PIS2, DUP1 by -0.015 m: pistols net +0.015, REV1 and SMG1 +0.03.
"""
import os
import re
import sys

import bpy
from mathutils import Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def shift_blend(wid, dz):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "assets/weapons/%s.blend" % wid))
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        if ob.name == wid:
            ob.data.transform(Matrix.Translation((0.0, 0.0, dz)))
        else:
            ob.location.z += dz            # a moving part: its origin is its pivot
    bpy.ops.wm.save_mainfile(compress=True)
    bak = bpy.data.filepath + "1"
    if os.path.exists(bak):
        os.remove(bak)


def shift_tscn(wid, dz):
    p = os.path.join(ROOT, "src/main/resources/com/openworld/weapon/%s.tscn" % wid)
    lines = open(p).read().split("\n")
    moved = 0
    for i, line in enumerate(lines):
        if not re.match(r'\[node name="[^"]+" type="(Marker3D|CollisionShape3D)"', line):
            continue
        if i + 1 < len(lines) and lines[i + 1].startswith("transform = Transform3D("):
            v = [float(x) for x in lines[i + 1][len("transform = Transform3D("):-1].split(",")]
            v[10] = round(v[10] + dz, 5)
            lines[i + 1] = "transform = Transform3D(%s)" % ", ".join(("%g" % x) for x in v)
            moved += 1
    open(p, "w").write("\n".join(lines))
    return moved


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    dz, ids = float(argv[0]), argv[1:]
    for wid in ids:
        shift_blend(wid, dz)
        n = shift_tscn(wid, dz)
        print("[shift-grip] %s: model +%.3f m in its .blend, %d markers/colliders +%.3f m in its scene" % (wid, dz, n, dz))


main()
