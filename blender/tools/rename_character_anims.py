"""Apply the character clip naming pass to assets/characters/shino/shino.blend.

    blender -b assets/characters/shino/shino.blend --python <this> -- <map.json>

Reads the SAME map the scene patcher reads, so the .blend and the AnimationTree cannot end up
spelling a clip differently. Idempotent: a rename whose target already exists is skipped.

Scheme: <stance>_<action>[_<direction>][_<weapon>]-loop, stance first so a `sorted()` listing groups
by stance and a new stance is authored by copying a ring's names. Stance-agnostic one-shots (jump,
reload, roll, weapon_switch_*) stay bare, because prefixing them would claim a stance they do not
have.
"""
import bpy, json, sys

ARM = "Godot_Chan_Stealth"
cfg = json.load(open(sys.argv[sys.argv.index("--") + 1]))

arm = bpy.data.objects.get(ARM)
if arm is None:
    raise SystemExit(f"no armature object {ARM!r}")
if arm.animation_data is None:
    arm.animation_data_create()
ad = arm.animation_data
changed = 0


def track_for(action):
    for t in ad.nla_tracks:
        for st in t.strips:
            if st.action is action:
                return t
    return None


# 1. RENAME -- the action, its NLA track and its strip, so track name == clip name holds.
for old, new in cfg["renames"].items():
    act = bpy.data.actions.get(old)
    if act is None:
        print(f"[naming] rename {old!r}: not present (already applied?)")
        continue
    if bpy.data.actions.get(new) is not None:
        raise SystemExit(f"cannot rename {old!r} -> {new!r}: target already exists")
    trk = track_for(act)
    act.name = new
    if trk is not None:
        trk.name = new
        for st in trk.strips:
            if st.action is act:
                st.name = new
    print(f"[naming] renamed {old!r} -> {new!r}")
    changed += 1

# 2. DELETE -- import artefacts that duplicate a real clip under a machine-made name.
for name in cfg["delete"]:
    act = bpy.data.actions.get(name)
    if act is None:
        print(f"[naming] delete {name!r}: not present")
        continue
    trk = track_for(act)
    if trk is not None:
        ad.nla_tracks.remove(trk)
    bpy.data.actions.remove(act)
    print(f"[naming] deleted {name!r}")
    changed += 1

# 3. PLACEHOLDERS -- copies of the nearest real pose, named for what they must become.
#
# `--refresh-placeholders` re-copies one that is STILL a copy, because a placeholder is expected to
# track its source until somebody authors it and nothing here did: `upright_aim_sniper` was minted
# from `upright_aim_rifle` and then sat frozen while the rifle pose was re-authored twice, so the
# two had silently diverged (found 2026-09-20 -- the sniper was the only clip left laying the head
# 34 deg over). It is opt-in and it names what it overwrites, because once the sniper pose IS
# authored, refreshing it is exactly the wrong thing.
refresh = "--refresh-placeholders" in sys.argv
only = None
for a in sys.argv:
    if a.startswith("--refresh-only="):
        only = set(a.split("=", 1)[1].split(","))
for name, src_name in cfg["placeholders"].items():
    # A `_comment*` key is prose about the table, not a clip. This map has carried one since W45 and
    # nothing had re-run the tool since, so the very first placeholder pass after it died on
    # "source ... missing" -- the value is a sentence, and there is no action by that name.
    if name.startswith("_"):
        continue
    existing = bpy.data.actions.get(name)
    if existing is not None and not (refresh and (only is None or name in only)):
        print(f"[naming] placeholder {name!r} already present")
        continue
    if existing is not None:
        trk = track_for(existing)
        if trk is not None:
            ad.nla_tracks.remove(trk)
        bpy.data.actions.remove(existing)
        print(f"[naming] placeholder {name!r} REFRESHED from {src_name!r}")
    src = bpy.data.actions.get(src_name)
    if src is None:
        raise SystemExit(f"placeholder {name!r}: source {src_name!r} missing")
    act = src.copy()
    act.name = name
    trk = ad.nla_tracks.new()
    trk.name = name
    trk.strips.new(name, int(src.frame_range[0]), act)
    print(f"[naming] added {name!r} (copy of {src_name!r})")
    changed += 1

# One named NLA track per clip and NO active action.
ad.action = None
if changed:
    bpy.ops.wm.save_mainfile()
    print(f"[naming] saved {bpy.data.filepath} ({changed} change(s))")
else:
    print("[naming] nothing to do")
