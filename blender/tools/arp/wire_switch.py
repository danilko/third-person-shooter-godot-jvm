"""Put the Auto-Rig Pro rig's hold on our skeleton behind ONE switch, stored at 0.

    blender assets/characters/shino/shino.blend --python blender/tools/arp/wire_switch.py -- [--save]

A ONE-SHOT, run after `build_limb_map.py --make-rig` (PLAN.md 6.17). Quick Rig in PRESERVE mode
leaves our 53-bone skeleton exactly as it is and makes it FOLLOW the ARP rig: every mapped bone gets
a COPY_TRANSFORMS + COPY_SCALE from `<bone>_qr_offset` (312 constraints on Shino, the hair and skirt
bones included). At full influence that is what lets ARP's controls pose the body -- and it is also
why, as generated, the shared clips do not play in the file and `export_character.py` refuses it
(measured: 0.876 m between constraints live and muted). An IK constraint at full influence
overrides the clip; this is the same fact at 312 bones.

So every one of those constraints' influence becomes a driver on ONE property,
`rig.pose.bones["c_pos"]["drive_game_rig"]` -- ARP's own root control, so it is found where an ARP
user looks (select c_pos, N-panel > Item > Properties):
    0 = the clips play and the file exports exactly as with no ARP rig at all
    1 = ARP's controls pose the body (Auto-Rig Pro's own IK/FK, snaps, picker)
Nothing is renamed, re-parented or re-rested. Idempotent.
"""
import bpy
import sys

PROP = "drive_game_rig"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    rig = next((o for o in bpy.data.objects if o.type == 'ARMATURE' and "arp_rig_type" in o.keys()), None)
    game = next((o for o in bpy.data.objects if o.type == 'ARMATURE' and o is not rig), None)
    if rig is None or game is None:
        raise SystemExit("[arp-switch] need an ARP rig and the game armature in the file")
    holder = rig.pose.bones["c_pos"]
    if PROP not in holder:
        holder[PROP] = 0.0
    holder.id_properties_ui(PROP).update(
        min=0.0, max=1.0,
        description="0 = the game clips play and export as-is; 1 = the Auto-Rig Pro controls pose the body")
    n = 0
    for pb in game.pose.bones:
        for con in pb.constraints:
            if getattr(con, "target", None) is not rig:
                continue
            try:
                con.driver_remove("influence")
            except Exception:
                pass
            d = con.driver_add("influence").driver
            d.type = 'AVERAGE'
            v = d.variables.new()
            v.name = "drive"
            v.type = 'SINGLE_PROP'
            v.targets[0].id = rig
            v.targets[0].data_path = 'pose.bones["c_pos"]["%s"]' % PROP
            n += 1
    holder[PROP] = 0.0
    # our old control layer's widget collection, emptied by `add_control_rig.py --remove`
    c = bpy.data.collections.get("CTRL_WIDGETS")
    if c is not None and not c.objects:
        bpy.data.collections.remove(c)
    print("[arp-switch] %d constraints on %r now follow %r pose.bones['c_pos']['%s'] = 0"
          % (n, game.name, rig.name, PROP))
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()
        print("[arp-switch] saved %s" % bpy.data.filepath)


main()
