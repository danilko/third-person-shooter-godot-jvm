"""Build the animation REVIEW file: every body, side by side, playing the shared clip.

    blender -b --python-exit-code 1 --python blender/tools/build_animation_review.py
    blender assets/characters/animation_review.blend        # then open it and scrub

A clip is a fact about the SKELETON, not about a body (`blender/SKELETON_CONTRACT.md`), so there is
ONE clip library and every body plays it. That is right for the runtime and awkward for the ANIMATOR:
the clips live in Godot-chan's `.blend` and the other bodies have none, so a pose is authored while
looking at the body it suits LEAST -- Godot-chan is 1.49 m with a huge head and the longest hands,
and the bodies it has to serve are 1.65 m and 1.91 m.

This file is the fix, and it is a VIEW rather than a copy:

* every body is **library-LINKED** from its own `.blend` and then library-OVERRIDDEN, which is what
  lets a linked object take an action. Edit a body in its own file, reload here, and it updates.
* the actions are **library-LINKED** from the clip source and are therefore READ-ONLY here. That is
  the point, not a limitation: a clip has one owner, and a review file you could edit in would be a
  second one. Blender has no way to merge two edits of the same action, so it must not be possible
  to make two.

**The workflow is therefore: judge here, edit there.** Open this file, scrub a clip, see it on every
body at once; when something reads wrong, fix it in `shino.blend`, save, and come back
here with `File > External Data > Reload`.

**Judge it on SHINO** (user's call, 2026-09-20): she has the shortest effective reach of the three --
not the shortest arm, but the narrowest shoulders (0.218 m against 0.296), which is what puts an off
hand furthest from a weapon held on the right. A hold that works on her works on the others; the
reverse is measurably false (CLAUDE.md "W41": ASR1's support hand missed by 7.8 cm on Shino and
0.0 on the two wider bodies). So she stands in the middle, at the origin, facing the camera.

This file is GENERATED. Nothing reads it and nothing exports from it -- re-run this script rather
than editing it, the same contract `WeaponLibrary.blend` and `BuildingLibrary.blend` have.
"""
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets/characters/animation_review.blend")

# The clip source: the one file that owns the actions.
CLIP_SOURCE = "assets/characters/shino/shino.blend"

# The bodies, in the order they stand. SHINO IS FIRST, at the origin: she owns the clips and is
# the body the game ships, so a pose is judged on her.
BODIES = [
    {"blend": "assets/characters/shino/shino.blend", "armature": "shino",
     "label": "Shino 1.65 m  (the yardstick: narrowest shoulders, shortest reach)", "x": 0.0},
    {"blend": "assets/characters/godot_chan/merged_animation.blend", "armature": "Godot_Chan_Stealth",
     "label": "Godot-chan 1.49 m  (retired from the game; still the GEOMETRY reference)", "x": -1.3},
    {"blend": "assets/characters/fumiriya/fumiriya.blend", "armature": "fumiriya",
     "label": "Fumiriya 1.91 m", "x": 1.3},
]

# What the file opens on. Any of the 171 will do; this one is where a fit problem shows.
# Named as Godot sees it -- the importer strips a trailing `-loop`, which is what sets loop mode --
# so the lookup tries the suffixed form too rather than silently opening on whatever sorts first.
START_CLIP = "upright_aim_rifle"


def link_body(path, armature_name, scene):
    """Link a body's objects and return an editable OVERRIDE of its armature.

    A LINKED object cannot be given an `animation_data`, so it cannot be made to play a clip --
    which is the whole job here. `override_hierarchy_create` makes the local, editable proxy that
    can, and brings the meshes with it so they stay skinned to it. (Building local objects around
    the linked DATA instead does not work: vertex groups live on the OBJECT, so the meshes would
    come across unweighted and the armature would move nothing.)
    """
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(path, link=True, relative=True) as (src, dst):
        if armature_name not in src.objects:
            raise SystemExit("[anim-review] %s has no object %r" % (path, armature_name))
        dst.objects = list(src.objects)
    linked = [o for o in bpy.data.objects if o not in before and o is not None]
    for o in linked:
        scene.collection.objects.link(o)
    arm = bpy.data.objects.get(armature_name)
    if arm is None or arm.library is None:
        raise SystemExit("[anim-review] could not link the armature %r" % armature_name)

    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    override = arm.override_hierarchy_create(scene, bpy.context.view_layer, do_fully_editable=True)
    if override is None:
        raise SystemExit("[anim-review] override failed for %r" % armature_name)

    # The linked originals have served their purpose; the override carries the meshes.
    for o in linked:
        if o.name in scene.collection.objects:
            scene.collection.objects.unlink(o)
    return override


def assign(arm, action):
    """Put `action` on `arm` AND BIND ITS SLOT.

    **This is the whole reason another body looks like it "has no animation".** Since Blender 4.4 an
    action is SLOTTED: its channels belong to a slot that names the ID it was authored on, here
    `OBGodot_Chan_Stealth`. Assign that action to any other rig and `action_slot` comes up None --
    no error, no warning, the rig simply stands in its rest pose while the timeline runs. Binding
    the existing slot is what makes one clip play on every body.

    Measured on `upright_walk_forward`, once bound: the same rotation keys travel 0.53 m on Shino,
    0.47 m on Godot-chan and 0.65 m on Fumiriya -- longer legs, longer stride, one clip. That is the
    skeleton contract doing its job, and it is only visible once the slot is bound.
    """
    arm.animation_data.action = action
    if action.slots:
        arm.animation_data.action_slot = action.slots[0]


def label(text, at, size=0.06):
    t = bpy.data.curves.new(type="FONT", name="Label")
    t.body = text
    t.size = size
    t.align_x = "CENTER"
    o = bpy.data.objects.new("Label", t)
    o.location = at
    o.rotation_euler = (1.5707963, 0, 0)
    bpy.context.scene.collection.objects.link(o)
    return o


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    # Saved FIRST so every linked path below is written relative to this file.
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    scene = bpy.context.scene

    # The clips, linked and therefore read-only. One owner.
    with bpy.data.libraries.load(os.path.join(ROOT, CLIP_SOURCE), link=True, relative=True) as (src, dst):
        dst.actions = list(src.actions)
    clips = sorted(a.name for a in bpy.data.actions if a is not None)
    if not clips:
        raise SystemExit("[anim-review] no actions in " + CLIP_SOURCE)
    start = next((n for n in (START_CLIP, START_CLIP + "-loop") if n in clips), clips[0])
    if not start.startswith(START_CLIP):
        print("[anim-review] WARNING: no %r among the %d clips, opening on %s"
              % (START_CLIP, len(clips), start))

    rigs = []
    for spec in BODIES:
        arm = link_body(os.path.join(ROOT, spec["blend"]), spec["armature"], scene)
        arm.location = (spec["x"], 0.0, 0.0)
        arm.animation_data_create()
        assign(arm, bpy.data.actions[start])
        label(spec["label"], (spec["x"], 0.0, -0.12))
        rigs.append(arm)
        print("[anim-review] %-18s at x %+.1f" % (spec["armature"], spec["x"]))

    act = bpy.data.actions[start]
    scene.frame_start = int(act.frame_range[0])
    scene.frame_end = int(act.frame_range[1])

    note = bpy.data.texts.new("READ ME")
    note.write(
        "GENERATED by blender/tools/build_animation_review.py -- re-run it, do not edit this file.\n"
        "\n"
        "Bodies are LINKED + overridden; the %d clips are LINKED from\n"
        "  %s\n"
        "and are READ-ONLY here on purpose: a clip has ONE owner, and two editable copies could\n"
        "never be merged back.\n"
        "\n"
        "  judge here  ->  edit in shino.blend  ->  File > External Data > Reload\n"
        "\n"
        "Judge it on SHINO (centre, at the origin). She has the narrowest shoulders of the three,\n"
        "which is what decides whether an off hand reaches a weapon held on the right -- a hold\n"
        "that works on her works on the others, and the reverse is measurably false.\n"
        "\n"
        "To see another clip on all three: pick it in the Action editor for ONE armature, then\n"
        "assign the same action to the other two (they are ordinary local overrides).\n"
        "\n"
        "If a body stands in its REST pose while the timeline runs, its action SLOT is unbound.\n"
        "Since Blender 4.4 an action's channels belong to a slot named after the rig it was\n"
        "authored on (OBGodot_Chan_Stealth), and assigning the action to another rig leaves the\n"
        "slot empty with no error. Pick the slot next to the action name in the Action editor.\n"
        "\n"
        "What does NOT transfer between bodies, and is not a pose problem: Root/pelvis POSITION\n"
        "keys are absolute metres, so a crouch or a crawl authored here sits too high on a taller\n"
        "body (measured: Fumiriya's feet 5.8 cm off the ground in crouch_idle). That is runtime\n"
        "foot grounding, not something to fix by moving keys.\n"
        % (len(clips), CLIP_SOURCE)
    )

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("[anim-review] wrote %s -- %d bodies, %d clips, opens on %s"
          % (os.path.relpath(OUT, ROOT), len(rigs), len(clips), start))


main()
