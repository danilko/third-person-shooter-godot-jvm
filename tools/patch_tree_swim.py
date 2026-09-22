#!/usr/bin/env python3
"""One-shot patch (PLAN.md 6.4): give Swim its own animation branch in the reference AnimationTree.

    python3 tools/patch_tree_swim.py      # idempotent: a scene already patched is left alone

Swim used to borrow Crawl's ring (Stance.animationStanceKey = "Crawl"). The UAL retarget (W34) gave it
real clips, and measured that swimming is TWO postures -- treading water UPRIGHT and the stroke
HORIZONTAL -- which one blendspace cannot hold (blending between them moved the gun centre 0.41 m).
So it is a Transition, the shape check_character_anim's swim_tread / swim_stroke rings already expect:

    StanceTransition["Swim"] <- SwimTransition { Tread <- SwimMovementBlend ; Stroke <- swim_forward }

SwimMovementBlend is the tread ring (swim_idle / _back / _left / _right, with the idle ahead too:
moving forward while treading -- i.e. while aiming -- stays upright). AnimationController picks
Tread or Stroke. Then run build_character_visuals.gd for every generated body.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn")


def trans_input(i, name):
    return (f'input_{i}/name = "{name}"\ninput_{i}/auto_advance = false\n'
            f'input_{i}/break_loop_at_end = false\ninput_{i}/reset = true\n')


def main():
    s = open(SCENE).read()
    if "SwimTransition" in s:
        print("[swim] already patched")
        return
    ring = [((0, 0), "swim_idle"), ((0, 1), "swim_idle"), ((0, -1), "swim_back"),
            ((-1, 0), "swim_left"), ((1, 0), "swim_right")]
    subs = []
    for i, (_, clip) in enumerate(ring):
        subs.append(f'[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_swm{i}"]\n'
                    f'animation = &"{clip}"\n')
    bs = '[sub_resource type="AnimationNodeBlendSpace2D" id="AnimationNodeBlendSpace2D_swm"]\n'
    for i, ((x, y), _) in enumerate(ring):
        bs += (f'blend_point_{i}/node = SubResource("AnimationNodeAnimation_swm{i}")\n'
               f'blend_point_{i}/pos = Vector2({x}, {y})\nblend_point_{i}/name = &"{i}"\n')
    subs.append(bs)
    subs.append('[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_swmf"]\n'
                'animation = &"swim_forward"\n')
    subs.append('[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_swm"]\n'
                'xfade_time = 0.4\n' + trans_input(0, "Tread") + trans_input(1, "Stroke"))
    root_hdr = '[sub_resource type="AnimationNodeBlendTree" id="AnimationNodeBlendTree_jn40o"]'
    assert root_hdr in s
    s = s.replace(root_hdr, "\n".join(subs) + "\n" + root_hdr, 1)

    m = re.search(r'(\[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_jn40o"\]\n(?:[^\[]*?))\n\[', s)
    block = m.group(1)
    assert 'input_4/name = "Passenger"' in block and "input_5/" not in block
    s = s.replace(block, block.rstrip("\n") + "\n" + trans_input(5, "Swim").rstrip("\n"), 1)

    nodes = [
        ("SwimTransition", "AnimationNodeTransition_swm", (-120, 1000)),
        ("SwimMovementBlend", "AnimationNodeBlendSpace2D_swm", (-360, 960)),
        ("swim_stroke", "AnimationNodeAnimation_swmf", (-360, 1100)),
    ]
    txt = "".join(f'nodes/{n}/node = SubResource("{r}")\nnodes/{n}/position = Vector2({x}, {y})\n'
                  for n, r, (x, y) in nodes)
    i = s.index("node_connections = [")
    s = s[:i] + txt + s[i:]
    s = s.replace('node_connections = [',
                  'node_connections = [&"StanceTransition", 5, &"SwimTransition", '
                  '&"SwimTransition", 0, &"SwimMovementBlend", &"SwimTransition", 1, &"swim_stroke", ', 1)
    open(SCENE, "w").write(s)
    print("[swim] patched", os.path.basename(SCENE))


if __name__ == "__main__":
    main()
