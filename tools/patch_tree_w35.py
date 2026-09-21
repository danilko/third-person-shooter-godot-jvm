#!/usr/bin/env python3
"""One-shot patch (W35): wire the retargeted library clips into both bodies' AnimationTree.

    python3 tools/patch_tree_w35.py      # idempotent: a scene already patched is left alone

Adds, in CharacterVisuals_GodotChan*.tscn:
  * a "Passenger" input on StanceTransition -> PassengerMovementBlend (sit_idle at all five points,
    the DriveCarrier ring's shape) -- AnimationController picks it for a seated non-driver;
  * "attack_throw" on AttackClip (the grenade throw rides the arms-only Attack one-shot);
  * HitReact: a OneShot filtered to spine_01/02/03, neck_01, head_2, fed by HitReactClip
    (hit_chest | hit_head);
The chain's end becomes  output <- HitReact(NeckFront). (A Climb one-shot was here and was removed in
W39 with the ledge climb.)
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES = ["CharacterVisuals_GodotChan.tscn"]
# Body-independent since the shared animation library landed: the AnimationTree resolves
# against the ARMATURE node, so a filter names the skeleton and the bone, nothing else.
SK = "Skeleton3D:"
FLINCH = ["spine_01", "spine_02", "spine_03", "neck_01", "head_2"]


def trans_input(i, name):
    return (f'input_{i}/name = "{name}"\ninput_{i}/auto_advance = false\n'
            f'input_{i}/break_loop_at_end = false\ninput_{i}/reset = true\n')


def patch(path):
    s = open(path).read()
    if "PassengerMovementBlend" in s:
        print(f"[w35] {os.path.basename(path)}: already patched")
        return
    # -- new sub-resources, placed before the root BlendTree (sub-resources must precede their user)
    subs = []
    for i in range(5):
        subs.append(f'[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_psg{i}"]\n'
                    f'animation = &"sit_idle"\n')
    pts = [(0, 0), (0, 1), (-1, 0), (0, -1), (1, 0)]
    bs = '[sub_resource type="AnimationNodeBlendSpace2D" id="AnimationNodeBlendSpace2D_psg"]\n'
    for i, (x, y) in enumerate(pts):
        bs += (f'blend_point_{i}/node = SubResource("AnimationNodeAnimation_psg{i}")\n'
               f'blend_point_{i}/pos = Vector2({x}, {y})\nblend_point_{i}/name = &"{i}"\n')
    subs.append(bs)
    subs.append('[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_atk6"]\n'
                'animation = &"attack_throw"\n')
    subs.append('[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_hrc"]\n'
                'animation = &"hit_chest"\n')
    subs.append('[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_hrh"]\n'
                'animation = &"hit_head"\n')
    subs.append('[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_hr"]\n'
                + trans_input(0, "hit_chest") + trans_input(1, "hit_head"))
    subs.append('[sub_resource type="AnimationNodeOneShot" id="AnimationNodeOneShot_hr"]\n'
                'filter_enabled = true\nfilters = [' + ", ".join(f'"{SK}{b}"' for b in FLINCH) + ']\n'
                'fadein_time = 0.05\nfadeout_time = 0.15\n')
    root_hdr = '[sub_resource type="AnimationNodeBlendTree" id="AnimationNodeBlendTree_jn40o"]'
    assert root_hdr in s
    s = s.replace(root_hdr, "\n".join(subs) + "\n" + root_hdr, 1)

    # -- transitions gain an input
    m = re.search(r'(\[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_jn40o"\]\n(?:[^\[]*?))\n\[', s)
    block = m.group(1)
    s = s.replace(block, block.rstrip("\n") + "\n" + trans_input(4, "Passenger").rstrip("\n"), 1)
    m = re.search(r'(\[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_atk"\]\n(?:[^\[]*?))\n\[', s)
    block = m.group(1)
    s = s.replace(block, block.rstrip("\n") + "\n" + trans_input(6, "attack_throw").rstrip("\n"), 1)

    # -- nodes, before node_connections
    nodes = [
        ("PassengerMovementBlend", "AnimationNodeBlendSpace2D_psg", (-320, 800)),
        ("attack_throw", "AnimationNodeAnimation_atk6", (1600, -1180)),
        ("HitReact", "AnimationNodeOneShot_hr", (2480, 140)),
        ("HitReactClip", "AnimationNodeTransition_hr", (2260, 360)),
        ("hit_chest", "AnimationNodeAnimation_hrc", (2020, 340)),
        ("hit_head", "AnimationNodeAnimation_hrh", (2020, 460)),
    ]
    txt = "".join(f'nodes/{n}/node = SubResource("{r}")\nnodes/{n}/position = Vector2({x}, {y})\n'
                  for n, r, (x, y) in nodes)
    i = s.index("node_connections = [")
    s = s[:i] + txt + s[i:]

    # -- connections: the chain's end, plus every new input
    old = '&"output", 0, &"NeckFront", '
    assert old in s
    new = ('&"output", 0, &"HitReact", &"HitReact", 0, &"NeckFront", &"HitReact", 1, &"HitReactClip", '
           '&"HitReactClip", 0, &"hit_chest", &"HitReactClip", 1, &"hit_head", '
           '&"StanceTransition", 4, &"PassengerMovementBlend", &"AttackClip", 6, &"attack_throw", ')
    s = s.replace(old, new, 1)
    s = s.replace("parameters/DriveCarrierMovementBlend/blend_position = Vector2(0, 0)\n",
                  "parameters/DriveCarrierMovementBlend/blend_position = Vector2(0, 0)\n"
                  "parameters/PassengerMovementBlend/blend_position = Vector2(0, 0)\n", 1)
    open(path, "w").write(s)
    print(f"[w35] {os.path.basename(path)}: patched")


for sc in SCENES:
    patch(os.path.join(ROOT, "src", "main", "resources", "com", "openworld", "character", sc))
