#!/usr/bin/env python3
"""One-shot patch: the SHOTGUN grip archetype (index 10) in the reference AnimationTree.

    python3 tools/patch_tree_shotgun.py        # idempotent; then regenerate the bodies:
    godot --headless --path . --script tools/godot/build_character_visuals.gd -- --body=shino   (and fumiriya)

A pump shotgun's support hand sits far forward of a rifle's (on the pump), so it gets its own AIM pose,
`upright_aim_shotgun` -- authored on the Auto-Rig Pro controls as `ARP_upright_aim_shotgun-loop`
(PLAN.md 6.17) and baked into the game clip at export. Every other family (hold, draw, crouch and crawl
aim) plays the rifle's clip at the new point, exactly as the reserved archetypes play their base
(`weapon_archetypes.json` "base": "rifle"). The index list is APPEND-ONLY (W12), so shotgun is 10.

Blendspaces touched, all seven weapon-index ones: WeaponAim, WeaponAimTorso (the new aim node),
WeaponAimCrouch, WeaponAimCrawl, WeaponAimTorsoCrouch, WeaponHold, WeaponChangeAnimation (the rifle's).
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(ROOT, "src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn")
INDEX = 10
NEW_ID = "AnimationNodeAnimation_aim_shotgun"
NEW_CLIP = "upright_aim_shotgun"
OWN_POSE = {"WeaponAim", "WeaponAimTorso"}          # these take the new clip; the rest reuse the rifle's
SPACES = ["WeaponAim", "WeaponAimTorso", "WeaponAimCrouch", "WeaponAimCrawl", "WeaponAimTorsoCrouch",
          "WeaponHold", "WeaponChangeAnimation"]


def main():
    s = open(SCENE).read()
    if NEW_ID in s:
        print("[patch-shotgun] already patched")
        return
    # the node, defined before any blendspace that uses it: right after the sniper aim node
    anchor = re.search(r'\[sub_resource type="AnimationNodeAnimation" id="AnimationNodeAnimation_aim_sniper"\]\n'
                       r'animation = &"[^"]+"\n\n', s)
    s = s[:anchor.end()] + ('[sub_resource type="AnimationNodeAnimation" id="%s"]\nanimation = &"%s"\n\n'
                            % (NEW_ID, NEW_CLIP)) + s[anchor.end():]
    for space in SPACES:
        sub = re.search(r'nodes/%s/node = SubResource\("([^"]+)"\)' % space, s).group(1)
        head = '[sub_resource type="AnimationNodeBlendSpace1D" id="%s"]\n' % sub
        a = s.index(head)
        b = s.find("\n[", a + len(head))
        block = s[a:b]
        rifle = re.search(r'blend_point_1/node = SubResource\("([^"]+)"\)', block).group(1)
        node = NEW_ID if space in OWN_POSE else rifle
        named = "blend_point_9/name" in block
        add = 'blend_point_%d/node = SubResource("%s")\nblend_point_%d/pos = %d.0\n' % (INDEX, node, INDEX, INDEX)
        if named:
            add += 'blend_point_%d/name = &"%d"\n' % (INDEX, INDEX)
        block = block.replace("max_space = 9.0", "max_space = %d.0" % INDEX)
        last = re.search(r'blend_point_9/[^\n]*\n(?!blend_point_9)', block)
        # append after the final blend_point_9 line
        lines = block.split("\n")
        idx = max(i for i, l in enumerate(lines) if l.startswith("blend_point_9/"))
        lines.insert(idx + 1, add.rstrip("\n"))
        block = "\n".join(lines)
        s = s[:a] + block + s[b:]
        print("[patch-shotgun] %-22s point %d -> %s" % (space, INDEX, node))
    open(SCENE, "w").write(s)
    print("[patch-shotgun] wrote %s" % os.path.relpath(SCENE, ROOT))


if __name__ == "__main__":
    main()
