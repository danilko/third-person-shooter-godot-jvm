"""Fill ARP Quick Rig's limb map from OUR 53-bone contract, and write it out for the UI.

    blender assets/characters/shino/shino.blend \
        --python blender/tools/arp/build_limb_map.py -- [--make-rig] [--save=<path>]

WHY THIS EXISTS. Auto-Rig Pro's Quick Rig asks which of your bones is the shoulder, the calf, the
neck. That is normally clicked in per limb -- but our bone NAMES are fixed by the skeleton contract
(`blender/SKELETON_CONTRACT.md`), so the answer is a TABLE, not a detection, and a table can be
right on every body instead of guessed per body.

`scene.limb_map` is a plain `CollectionProperty` of `LimbProp`, so it is filled directly here; the
map is then exported with ARP's own `arp.quick_export_mapping` so it can be loaded in the UI
(Quick Rig panel -> Import Mapping) and pressed by hand.

THREE TRAPS, each measured (2026-09-21):
  * `neck_bones_amount` DEFAULTS TO 2 and our rig has ONE neck bone, so Quick Rig took the "subneck"
    path and died on `KeyError: 'neck_ref'` at `_make_rig` line 5762. Every per-limb COUNT has to be
    stated, not left at its default.
  * `arp_ver_int` is computed in `show_error()`, a DRAW-TIME helper, so under `-b` it stays None and
    `_make_rig` dies on `None >= 36820`. It is a class attribute and is set here.
  * `base_armature_name` / `base_armature_pos` are set in `invoke()`, and a `bpy.ops` call from
    Python runs EXEC, which skips it -- so a cleanup step died on `None.location` AFTER building a
    381-bone rig. Hence the `'INVOKE_DEFAULT'` below. PRESSING THE BUTTON IN THE UI runs invoke and
    never had this problem; it is purely an artefact of driving the operator from a script.
  * ARP reaches for `bpy.context.space_data.overlay`, which is None even WITH a window, because a
    `--python` script does not run inside a viewport. It needs a VIEW_3D `temp_override`, so this
    CANNOT run headless -- it is an artist one-shot, never a build step.

The rig ARP generates must DRIVE our skeleton, never replace it: measured, 0 of its bone names match
our 53, so adopting it as the deform rig would re-mean every clip track, every MeshConfig path,
`Physical Bone head_2`, the bone-multiplier table and both VRoid conformations.
`export_character.py` already refuses an export in which anything drives the deform bones, which is
the safety net for forgetting to bake down.
"""
import bpy, sys, traceback

# our contract -> Quick Rig's slots. LEG: 1 thigh, 3 calf, 5 foot, 6 toes.
# ARM: 1 shoulder, 2 arm, 4 forearm, 6 hand.  SPINE: 1 pelvis then the spine.  HEAD: 1 neck, 2 head.
def limb_table(bones):
    head = "head_2" if "head_2" in bones else "head"
    spine = [n for n in ("spine_01", "spine_02", "spine_03") if n in bones]
    return [
        ("ARM", "LEFT",  {1: "clavicle_l", 2: "upperarm_l", 4: "lowerarm_l", 6: "hand_l"}, {}),
        ("ARM", "RIGHT", {1: "clavicle_r", 2: "upperarm_r", 4: "lowerarm_r", 6: "hand_r"}, {}),
        ("LEG", "LEFT",  {1: "thigh_l", 3: "calf_l", 5: "foot_l", 6: "ball_l"}, {}),
        ("LEG", "RIGHT", {1: "thigh_r", 3: "calf_r", 5: "foot_r", 6: "ball_r"}, {}),
        ("SPINE", "CENTER", dict([(1, "pelvis")] + [(i + 2, n) for i, n in enumerate(spine)]),
         {"spine_amount": len(spine) + 1}),
        # ONE neck bone on this skeleton -- the default of 2 is what broke it.
        ("HEAD", "CENTER", {1: "neck_01", 2: head}, {"neck_bones_amount": 1}),
    ]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    make_rig = "--make-rig" in argv
    save = next((a.split("=", 1)[1] for a in argv if a.startswith("--save=")), None)
    out_map = next((a.split("=", 1)[1] for a in argv if a.startswith("--map=")), None)

    sc = bpy.context.scene
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.name != "rig")
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bones = {b.name for b in arm.data.bones}
    print("[limb-map] armature %r, %d bones" % (arm.name, len(bones)))

    sc.limb_map.clear()
    for kind, side, slots, extra in limb_table(bones):
        missing = [n for n in slots.values() if n not in bones]
        if missing:
            print("[limb-map] SKIP %s %s -- missing %s" % (kind, side, missing))
            continue
        it = sc.limb_map.add()
        it.type, it.side = kind, side
        # `LimbProp.name` is written by an update callback on type/side, and a direct assignment
        # does not always fire it -- measured, the HEAD limb exported keyed '' while ARM came out
        # 'Arm.l'. The exported mapping is a dict KEYED BY NAME, so an unnamed limb collides.
        if not it.name:
            it.name = {"ARM": "Arm", "LEG": "Leg", "SPINE": "Spine",
                       "HEAD": "Head"}.get(kind, kind.title())
            if side != "CENTER":
                it.name += ".l" if side == "LEFT" else ".r"
        for i, n in slots.items():
            setattr(it, "bone_%02d" % i, n)
        for k, v in extra.items():
            setattr(it, k, v)
        print("[limb-map] %-6s %-6s %s %s" % (kind, side, {"bone_%02d" % i: n for i, n in slots.items()},
                                              extra if extra else ""))
    print("[limb-map] %d limbs" % len(sc.limb_map))

    if out_map:
        try:
            bpy.ops.arp.quick_export_mapping(filepath=out_map)
            print("[limb-map] wrote mapping %s  (load it with Quick Rig -> Import Mapping)" % out_map)
        except Exception as exc:
            print("[limb-map] mapping export failed: %s" % exc)

    if make_rig:
        import addon_utils
        ver = next(("".join(str(x) for x in m.bl_info["version"])
                    for m in addon_utils.modules() if m.bl_info.get("name") == "Auto-Rig Pro"), None)
        cls = getattr(bpy.types, "ARP_OT_quick_make_rig", None)
        if cls is not None and ver:
            cls.arp_ver_int = int(ver)                    # draw-time helper never runs here
        area = None
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'VIEW_3D':
                    area = (w, a)
                    break
            if area:
                break
        if area is None:
            print("[limb-map] NO VIEW_3D -- Quick Rig cannot run headless (it reads space_data).")
        else:
            w, a = area
            rgn = next((r for r in a.regions if r.type == 'WINDOW'), None)
            try:
                with bpy.context.temp_override(window=w, area=a, region=rgn, space_data=a.spaces.active):
                    # invoke() only validates, records the base armature and opens a confirm
                    # DIALOG -- which a script cannot press, so INVOKE came back RUNNING_MODAL and
                    # built nothing. Record what invoke records, then EXEC.
                    cls.base_armature_name = arm.name
                    cls.base_armature_pos = arm.location.copy()
                    cls.arp_light = False
                    print("[limb-map] quick_make_rig ->",
                          bpy.ops.arp.quick_make_rig('EXEC_DEFAULT', mode='PRESERVE',
                                                     match_to_rig=True, animation='NO_ANIM',
                                                     arm_ik_fk='IK', leg_ik_fk='IK',
                                                     remove_root=True, show_in_front=True,
                                                     orphan_bones_shape='NONE'))
            except Exception:
                print("[limb-map] quick_make_rig RAISED:")
                traceback.print_exc(file=sys.stdout)
        for o in bpy.data.objects:
            if o.type == 'ARMATURE':
                print("[limb-map]   armature %-8r %d bones, %d deform"
                      % (o.name, len(o.data.bones), sum(1 for b in o.data.bones if b.use_deform)))

    if save:
        bpy.ops.wm.save_as_mainfile(filepath=save)
        print("[limb-map] saved %s" % save)


main()
