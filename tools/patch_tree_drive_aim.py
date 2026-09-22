#!/usr/bin/env python3
"""One-shot patch (PLAN.md 6.5): a SEATED aim branch in the reference AnimationTree.

    python3 tools/patch_tree_drive_aim.py      # idempotent: a scene already patched is left alone

`drive_aim_pistol` / `drive_aim_rifle` had been exported and orphaned since W7. This gives them a home:

    AimStanceTransition["Drive"] <- WeaponAimDrive   (the 11-point archetype blendspace, like WeaponAimCrouch)

A seat has two authored poses, not one per archetype, so each point plays its BASE's seated pose
(weapon_archetypes.json `base`) -- except where that would be wrong: dual pistols keep their own upright
pose (drive_aim_pistol's left arm is a single pistol's support hand), and the fist / melee / throwable
guards keep theirs (they are not drive-by weapons, and a pistol pose on an empty fist reads as a bug).
Those points play exactly what a seat played before, so nothing changes for them.

AnimationController selects "Drive" for both DriveCarrier and Passenger. The two rear-aim clips stay
unwired: the rear posture is the seat's continuous body turn (W9), not a separate pose.
Then run build_character_visuals.gd for every generated body.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn")
ARCH = os.path.join(ROOT, "blender/tools/weapon_archetypes.json")
SEATED = {"pistol": "drive_aim_pistol", "rifle": "drive_aim_rifle"}
OWN_POSE = {"dual_pistol", "melee", "fist", "throwable"}   # keep the upright archetype pose


def main():
    s = open(SCENE).read()
    if "WeaponAimDrive" in s:
        print("[drive-aim] already patched")
        return
    arch = sorted(json.load(open(ARCH))["archetypes"], key=lambda a: a["index"])
    clips = []
    for a in arch:
        if a["name"] in OWN_POSE:
            clips.append("upright_aim_" + a["name"])
        else:
            clips.append(SEATED[a["base"]])
    subs = [f'[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_daim{i}"]\n'
            f'animation = &"{c}"\n' for i, c in enumerate(clips)]
    bs = '[sub_resource type="AnimationNodeBlendSpace1D" id="AnimationNodeBlendSpace1D_aimdrive"]\n'
    for i in range(len(clips)):
        bs += (f'blend_point_{i}/node = SubResource("AnimationNodeAnimation_daim{i}")\n'
               f'blend_point_{i}/pos = {float(i)}\n')
    bs += f'max_space = {float(len(clips) - 1)}\nsnap = 1.0\nvalue_label = "weapon"\n'
    subs.append(bs)
    root_hdr = '[sub_resource type="AnimationNodeBlendTree" id="AnimationNodeBlendTree_jn40o"]'
    assert root_hdr in s
    s = s.replace(root_hdr, "\n".join(subs) + "\n" + root_hdr, 1)

    m = re.search(r'(\[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_aimstance"\]\n(?:[^\[]*?))\n\[', s)
    block = m.group(1)
    assert 'input_2/name = "Crouch"' in block and "input_3/" not in block
    add = ('input_3/name = "Drive"\ninput_3/auto_advance = false\n'
           'input_3/break_loop_at_end = false\ninput_3/reset = false')
    s = s.replace(block, block.rstrip("\n") + "\n" + add, 1)

    i = s.index("node_connections = [")
    s = (s[:i] + 'nodes/WeaponAimDrive/node = SubResource("AnimationNodeBlendSpace1D_aimdrive")\n'
         'nodes/WeaponAimDrive/position = Vector2(1020, 1500)\n' + s[i:])
    s = s.replace('node_connections = [',
                  'node_connections = [&"AimStanceTransition", 3, &"WeaponAimDrive", ', 1)
    open(SCENE, "w").write(s)
    print("[drive-aim] patched: " + ", ".join(f"{a['name']}={c}" for a, c in zip(arch, clips)))


if __name__ == "__main__":
    main()
