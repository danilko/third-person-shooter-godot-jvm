#!/usr/bin/env python3
"""One-shot patch (user, 2026-09-27): a RELAXED branch in front of the upright ring.

    python3 tools/patch_tree_relaxed.py      # idempotent: a scene already patched is left alone

    StanceTransition["Upright"] <- RelaxedTransition { Raised  <- UprightMovementBlend (the ring, as before)
                                                       Relaxed <- UprightRelaxedBlend }

UprightRelaxedBlend is a 1D blend by movement id -- idle 0, `upright_walk_relaxed` 1, run 2 -- because out
of combat the body faces its travel, so only forward exists. `upright_walk_relaxed` is a GAIT clip
(src/main/resources/com/openworld/character/anim/character_gaits.json): a male body strolls on the
ordinary walk, a female one on blender/tools/derive_gait.py's relaxed walk, which lets the upper body
move. Anything that faces the aim walks the steady ring, so that sway never reaches a gun.
AnimationController requests Relaxed / Raised. Then run build_character_visuals.gd for every generated body.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn")


def trans_input(i, name):
    return (f'input_{i}/name = "{name}"\ninput_{i}/auto_advance = false\n'
            f'input_{i}/break_loop_at_end = false\ninput_{i}/reset = false\n')


def main():
    s = open(SCENE).read()
    if "RelaxedTransition" in s:
        print("[relaxed] already patched")
        return
    pts = [(0.0, "upright_idle"), (1.0, "upright_walk_relaxed"), (2.0, "upright_run_forward")]
    subs = []
    for i, (_, clip) in enumerate(pts):
        subs.append(f'[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_rlx{i}"]\n'
                    f'animation = &"{clip}"\n')
    bs = ('[sub_resource type="AnimationNodeBlendSpace1D" id="AnimationNodeBlendSpace1D_rlx"]\n'
          'min_space = 0.0\nmax_space = 2.0\n')
    for i, (x, _) in enumerate(pts):
        bs += (f'blend_point_{i}/node = SubResource("AnimationNodeAnimation_rlx{i}")\n'
               f'blend_point_{i}/pos = {x}\n')
    subs.append(bs)
    subs.append('[sub_resource type="AnimationNodeTransition" id="AnimationNodeTransition_rlx"]\n'
                'xfade_time = 0.25\n' + trans_input(0, "Raised") + trans_input(1, "Relaxed"))
    root_hdr = '[sub_resource type="AnimationNodeBlendTree" id="AnimationNodeBlendTree_jn40o"]'
    assert root_hdr in s
    s = s.replace(root_hdr, "\n".join(subs) + "\n" + root_hdr, 1)

    nodes = [("RelaxedTransition", "AnimationNodeTransition_rlx", (-40, -120)),
             ("UprightRelaxedBlend", "AnimationNodeBlendSpace1D_rlx", (-260, -260))]
    txt = "".join(f'nodes/{n}/node = SubResource("{r}")\nnodes/{n}/position = Vector2({x}, {y})\n'
                  for n, r, (x, y) in nodes)
    i = s.index("node_connections = [")
    s = s[:i] + txt + s[i:]
    old = '&"StanceTransition", 0, &"UprightMovementBlend"'
    assert old in s
    s = s.replace(old, '&"StanceTransition", 0, &"RelaxedTransition", &"RelaxedTransition", 0, '
                       '&"UprightMovementBlend", &"RelaxedTransition", 1, &"UprightRelaxedBlend"', 1)
    open(SCENE, "w").write(s)
    print("[relaxed] patched", os.path.basename(SCENE))


if __name__ == "__main__":
    main()
