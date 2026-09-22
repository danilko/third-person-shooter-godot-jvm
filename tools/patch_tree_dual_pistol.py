#!/usr/bin/env python3
"""One-shot patch: the DUAL_PISTOL grip archetype (index 3) plays its own poses in the reference AnimationTree.

    python3 tools/patch_tree_dual_pistol.py        # idempotent; then regenerate the bodies:
    godot --headless --path . --script tools/godot/build_character_visuals.gd -- --body=shino   (and fumiriya)

Point 3 of the weapon blendspaces played the PISTOL's clips (a reserved archetype plays its base, W47). The
dual-pistol poses are the pistol poses with the right arm X-flipped onto the left
(blender/tools/make_dual_pistol_clips.py). Each point-3 node below is used by that point alone (counted), so it
is retargeted in place. The draw one-shot (WeaponChangeAnimation) keeps the pistol's.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn")
RETARGET = {   # node id -> clip
    "AnimationNodeAnimation_wa03": "upright_aim_dual_pistol",           # WeaponAim + WeaponAimTorso
    "AnimationNodeAnimation_kaim_dual_pistol": "crouch_aim_dual_pistol",  # WeaponAimCrouch
    "AnimationNodeAnimation_ktaim_dual_pistol": "crouch_aim_dual_pistol", # WeaponAimTorsoCrouch
    "AnimationNodeAnimation_caim_dual_pistol": "crawl_aim_dual_pistol",   # WeaponAimCrawl
    "AnimationNodeAnimation_wh03": "upright_hold_dual_pistol",          # WeaponHold
}


def main():
    s = open(SCENE).read()
    for node, clip in RETARGET.items():
        pat = r'(\[sub_resource type="AnimationNodeAnimation" id="%s"\]\nanimation = &")([^"]+)(")' % re.escape(node)
        m = re.search(pat, s)
        assert m, node
        if m.group(2) != clip:
            print("[patch-dual] %-42s %s -> %s" % (node, m.group(2), clip))
            s = s[:m.start(2)] + clip + s[m.end(2):]
    open(SCENE, "w").write(s)
    print("[patch-dual] done")


if __name__ == "__main__":
    main()
