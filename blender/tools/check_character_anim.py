#!/usr/bin/env python3
"""Gate for the character animation export. Pure Python on the .glb — no Blender needed.

    python3 blender/tools/check_character_anim.py

Checks the facts that were each a shipped defect (`PLAN.archive.md`, "Crouch/crawl aiming, the crouch
'knock', and the 90-degree-off torso"), so a re-export cannot quietly reintroduce them:

  duplicate_clips   an action exported twice (active + stashed) comes back as ONE animation with
                    doubled channels; every clip must carry exactly BONES*3 channels.
  root_family       every clip in one stance family must agree on the Root bone. Root sits above
                    the pelvis, so a translation on it moves the whole skeleton -- and with it
                    WeaponAttachment (a BoneAttachment3D on hand_r, i.e. the gun, its Muzzle which
                    is FirearmItem.resolveShotOrigin's shot origin) and every PhysicalBone3D
                    hitbox. Points of one blendspace that disagree on Root translate the body,
                    the gun and the hitboxes together: the "knock".
  gun_travel        the same fact measured where it is felt -- hand_r world position across the
                    family, including idle->walk (a blendspace centre that disagrees with its own
                    corners) and the bob inside a single loop (a transition baked into a loop).
  gun_sway          the LATERAL half of that, which the vertical checks scored as PASS while the
                    gun swung 0.14 m side to side: the walk clips' spine_01/spine_02 counter-rotate
                    the pelvis twist, so an upper-body filter that replaces them with a static aim
                    pose lets the twist through into the gun. Asked of FORWARD/BACK clips only --
                    a strafe swings the body for real, a forward walk has nothing to swing about.
  feet_planted      a clip whose feet leave the floor is a Root offset applied without re-posing
                    the legs; the repair for a Root disagreement must not become this.
  tree_refs         every clip the reference visuals scene names must exist in the export.
  orphan_clips      and the reverse: a clip that exists and is named by no AnimationTree node is
                    unreachable, so authoring into it changes nothing while looking like a broken
                    animation. WARN — an unused clip is a normal work-in-progress state.

Exit code 1 on any ERROR. Thresholds are deliberately a little above the measured-good values,
so ordinary re-authoring passes and a structural regression does not.
"""
import json
import math
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
## The pelvis rest height the per-ring bob/foot limits below were calibrated on (the 1.52 m
## reference). Every body's limits scale by its own pelvis against this, so the reference scales to
## exactly 1.0 and a taller clip source is not failed for being tall.
REFERENCE_PELVIS_Y = 0.7671
HEIGHT_SCALE = 1.0
GLB = os.path.join(ROOT, "assets", "characters", "shino", "shino.glb")
if len(sys.argv) > 1:                      # optional: check some other export (e.g. a backup)
    GLB = sys.argv[1]
TSCN = os.path.join(ROOT, "src", "main", "resources", "com", "openworld",
                    "character", "CharacterVisuals_Shino.tscn")
# A second BODY is a second visuals scene with its own AnimationTree over its own export, and the
# clip names are the contract between them -- so the gate has to be pointable at either.
if len(sys.argv) > 2:
    TSCN = sys.argv[2]

# One entry per blendspace RING: the clips inside a ring are blended continuously, so they must
# share a Root baseline. A ring may legitimately sit at a different baseline from another ring
# (a sprint really does run lower than a walk), which is why sprint is its own entry.
#   aim      the stance's aim clip; the gun measurement composes it over the locomotion clip
#            exactly as the AnimationTree's filtered upper-body layer does.
#   bob/foot per-ring limits — a run bobs and lifts its feet far more than a walk, and saying so
#            here is honest, whereas one global number would either miss the walk defect or
#            reject every run.
FAMILIES = {
    "upright": dict(
        clips=["upright_idle", "upright_walk_forward", "upright_walk_back", "upright_walk_left",
               "upright_walk_right", "upright_walk_forward_left", "upright_walk_forward_right",
               "upright_walk_back_left", "upright_walk_back_right"],
        aim="upright_aim_pistol", bob=0.08, foot=0.30),
    "upright_sprint": dict(
        clips=["upright_run_forward", "upright_run_forward_rifle"],
        aim="upright_aim_rifle", bob=0.40, foot=0.85),
    "crouch": dict(
        clips=["crouch_idle", "crouch_walk_forward", "crouch_walk_back",
               "crouch_walk_left", "crouch_walk_right", "crouch_walk_forward_left",
               "crouch_walk_forward_right", "crouch_walk_back_left", "crouch_walk_back_right"],
        aim="crouch_aim_pistol", bob=0.08, foot=0.30),
    "crawl": dict(
        clips=["crawl_idle", "crawl_forward", "crawl_back", "crawl_left", "crawl_right"],
        aim="crawl_aim_pistol", bob=0.08, foot=0.30),
    # One clip, and that is the shape of the ring rather than an omission: a seated occupant does
    # not locomote (MovementController is switched off in the seat), so DriveCarrier's blendspace
    # plays the one pose at all five points. The ring checks still earn their keep on it -- a seated
    # placeholder must still close its loop and must not swing the gun.
    "drive": dict(
        clips=["drive_idle"],
        aim="drive_aim_pistol", bob=0.08, foot=0.30),
    # A seated PASSENGER (W35): the DriveCarrier stance, but the tree plays this ring instead of the
    # hands-on-wheel one. One clip, the same shape as drive.
    "passenger": dict(
        clips=["sit_idle"],
        aim="drive_aim_pistol", bob=0.08, foot=0.30),
    # SWIM has no AnimationTree state yet -- the stance ships with animationStanceKey = "Crawl" and
    # borrows that ring. Since the Universal Animation Library retarget (retarget_ual.py) swim is TWO
    # postures, and they are two rings on purpose: treading water is UPRIGHT (chest at the water
    # line; idle and the slow back/left/right drift share it) and the stroke is HORIZONTAL. Blending
    # one into the other across a blendspace moves the chest 0.4 m, which is a posture change, not a
    # "knock" -- wiring Swim needs a Transition between a tread ring and a stroke clip (the GTA
    # shape). A stroke also bobs the body more than a walk: 0.10-0.12 m measured, hence 0.15.
    "swim_tread": dict(
        clips=["swim_idle", "swim_back", "swim_left", "swim_right"],
        aim="swim_aim_pistol", bob=0.15, foot=0.30),
    "swim_stroke": dict(
        clips=["swim_forward"],
        aim="swim_aim_pistol", bob=0.15, foot=0.30),
}

ROOT_BASELINE_MAX = 0.06  # m, spread of per-clip MEAN Root.y inside one ring (good: <= 0.03)
LOOP_CLOSE_MAX    = 0.02  # m, |Root.y(first) - Root.y(last)| (good: <= 0.007)
GUN_STEP_MAX      = 0.07  # m, idle -> moving centre, composed pose (good: <= 0.064, the strafe
                          #    clips legitimately shift the hips; the crouch defect was 0.126)
GUN_SWAY_MAX      = 0.10  # m, LATERAL travel of the gun within one loop, FORWARD/BACK clips
                          #    only -- a strafe legitimately swings the body (walk_right measures
                          #    0.109 clean), while a forward walk has no lateral motion to justify
                          #    any. Clean, against the committed arms-only filter: 0.012-0.082.
                          #    With the upper-body filter widened to spine_01/spine_02 (a shipped
                          #    regression, reverted): 0.123-0.223. The limit separates the two.
                          #    Separate from the
                          #    vertical bob on purpose: widening the upper-body filter to
                          #    spine_01/spine_02 froze the counter-rotation those bones carry
                          #    against the pelvis twist and took upright walk from 0.015 m to
                          #    0.140 m of side-to-side gun swing -- a regression the height-only
                          #    checks scored as PASS.

## A PASS BY 2 mm IS NOT EVIDENCE, AND IT IS HOW THIS GATE WENT QUIET (2026-09-21).
## Every limit below is a distance in METRES measured on the clip source's own body, so the same
## clip keys measure differently on two bodies: crawl's placeholder ring (6.16) reads 0.110 m of
## gun bob on the 1.49 m reference and 0.078 m on Shino, against a 0.08 limit. Moving the library
## to Shino therefore turned four real ERRORs into silence, with nothing on either run to say the
## defect was still there. So a measurement that lands inside NEAR_FRACTION of its own limit is
## REPORTED as a warning rather than passing without a word -- the limit is not bent, the margin is
## made visible.
NEAR_FRACTION = 0.85

findings = []


def err(check, msg):
    findings.append(("ERROR", check, msg))


def warn(check, msg):
    findings.append(("WARN", check, msg))


def gauge(check, value, limit, msg):
    """Report `value` against `limit`: an ERROR past it, a WARN inside NEAR_FRACTION of it."""
    if value > limit:
        err(check, msg + f" [{value:.3f} of {limit:.2f} m]")
    elif value > limit * NEAR_FRACTION:
        warn(check, msg + f" -- NOT over the limit, but only just inside it "
                          f"[{value:.3f} of {limit:.2f} m, {100.0 * value / limit:.0f}%]. "
                          f"A margin this thin is not evidence the fact is right; it is usually "
                          f"the same defect measured on a body it happens to suit.")


# ----------------------------------------------------------------- glTF reader
def load(path):
    d = open(path, "rb").read()
    _, _, length = struct.unpack("<III", d[:12])
    off, chunks = 12, {}
    while off < length:
        clen, ctype = struct.unpack("<II", d[off:off + 8])
        chunks[ctype] = d[off + 8:off + 8 + clen]
        off += 8 + clen + ((-clen) % 4)
    return json.loads(chunks[0x4E4F534A]), chunks[0x004E4942]


CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
      5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Rig:
    def __init__(self, J, BIN):
        self.J, self.BIN = J, BIN
        self.nodes = J["nodes"]
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.bone = {}
        for i in J["skins"][0]["joints"]:
            self.bone.setdefault(self.nodes[i].get("name"), i)
        self.anim = {a["name"]: a for a in J.get("animations", [])}

    def acc(self, i):
        a = self.J["accessors"][i]
        bv = self.J["bufferViews"][a["bufferView"]]
        fmt, sz = CT[a["componentType"]]
        n = NC[a["type"]]
        stride = bv.get("byteStride") or sz * n
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from("<" + fmt * n, self.BIN, base + k * stride)
                for k in range(a["count"])]

    def duration(self, name):
        d = 0.0
        for ch in self.anim[name]["channels"]:
            ts = [t[0] for t in self.acc(self.anim[name]["samplers"][ch["sampler"]]["input"])]
            if ts:
                d = max(d, ts[-1])
        return d

    def pose(self, name, t):
        out = {}
        for ch in self.anim[name]["channels"]:
            tgt = ch["target"]
            smp = self.anim[name]["samplers"][ch["sampler"]]
            times = [x[0] for x in self.acc(smp["input"])]
            vals = self.acc(smp["output"])
            k = 0
            for idx, tv in enumerate(times):
                if tv <= t + 1e-6:
                    k = idx
            out.setdefault(tgt.get("node"), {})[tgt["path"]] = vals[k]
        return out

    @staticmethod
    def _trs(t, r, s):
        x, y, z, w = r
        xx, yy, zz = x * x, y * y, z * z
        xy, xz, yz = x * y, x * z, y * z
        wx, wy, wz = w * x, w * y, w * z
        R = [[1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
             [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
             [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)]]
        return [[R[i][j] * s[j] for j in range(3)] + [t[i]] for i in range(3)] + [[0, 0, 0, 1]]

    def _rest(self, i):
        n = self.nodes[i]
        if "matrix" in n:
            m = n["matrix"]
            return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
        return self._trs(n.get("translation", [0, 0, 0]),
                         n.get("rotation", [0, 0, 0, 1]), n.get("scale", [1, 1, 1]))

    def world(self, bone, pose):
        i, chain = self.bone[bone], []
        while i is not None:
            chain.append(i)
            i = self.parent.get(i)
        M = [[1 if r == c else 0 for c in range(4)] for r in range(4)]
        for i in reversed(chain):
            p, n = pose.get(i), self.nodes[i]
            if p:
                L = self._trs(p.get("translation", n.get("translation", [0, 0, 0])),
                              p.get("rotation", n.get("rotation", [0, 0, 0, 1])),
                              p.get("scale", n.get("scale", [1, 1, 1])))
            else:
                L = self._rest(i)
            M = self.mm(M, L)
        return M

    @staticmethod
    def mm(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def samples(rig, clip, n=13):
    d = rig.duration(clip)
    return [rig.pose(clip, k / (n - 1) * d if d else 0.0) for k in range(n)]



def tscn_upper_body_filter():
    """Bones the AnimationTree's WeaponBlend layer takes from the aim clip.

    Read from the scene rather than restated here: this list IS the layer boundary, and a gate
    holding its own copy would be the second owner of it (CLAUDE.md's recurring defect).
    """
    if not os.path.exists(TSCN):
        return set()
    s = open(TSCN).read()
    m = re.search(r'^nodes/WeaponBlend/node = SubResource\("([^"]+)"\)', s, re.M)
    if not m:
        return set()
    blk = s.split(f'[sub_resource type="AnimationNodeBlend2" id="{m.group(1)}"]')[1].split("\n\n")[0]
    return {p.split(":")[-1] for p in re.findall(r'"([^"]*Skeleton3D:[^"]+)"', blk)}


def compose(rig, loco_pose, aim_clip, upper):
    """The pose the game actually shows: locomotion, with `upper` replaced by the aim clip."""
    if not aim_clip or not upper:
        return loco_pose
    out = dict(loco_pose)
    for ni, v in rig.pose(aim_clip, 0.0).items():
        if rig.nodes[ni].get("name") in upper:
            out[ni] = v
    return out


# ----------------------------------------------------------------- the checks
SHOULDER_BONES = ("clavicle_l", "clavicle_r")
## How far a hand may travel across an AIM or HOLD clip's own range. A pose clip is one pose; the
## allowance is for authored breathing, not for a second pose.
POSE_CLIP_STILL_MAX = 0.05
## How far a collarbone turns on its own channel in the AIM AND HOLD poses, from the shared table.
## It is a description of those poses, not a budget every clip must fit: the gate only WARNs on it,
## and the one place it is a hard limit is the control rig's IK solve, where it is what stops the
## solver answering "I cannot reach" with a dislocated shoulder.
SHOULDER_MAX_DEG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "character_anim_naming.json")))["limits"]["shoulder_channel_deg"]


def quat_angle_from_rest(rest, pose):
    """Degrees of `rest^-1 * pose` -- the bone's own rotation, which is what a shoulder articulates.

    NOT the bone's world direction: a clip that rolls or dashes turns every bone in the body, and
    measured that way a perfectly ordinary sword clip reads 160 deg at the collarbone while its own
    channel moves 10 (measured -- it is what makes the direction a useless metric here).
    """
    rx, ry, rz, rw = rest
    px, py, pz, pw = pose
    # conjugate of rest, times pose
    w = rw * pw + rx * px + ry * py + rz * pz
    return math.degrees(2.0 * math.acos(min(1.0, abs(w))))


def main():
    if not os.path.exists(GLB):
        print(f"check_character_anim: missing {GLB}", file=sys.stderr)
        return 2
    J, BIN = load(GLB)
    rig = Rig(J, BIN)
    nbones = len(J["skins"][0]["joints"])
    expect = nbones * 3

    # THE BOB AND FOOT LIMITS ARE METRES, SO THEY SCALE WITH THE BODY. They were calibrated on the
    # 1.52 m reference; the clip source is Shino now (1.645 m) and a taller body lifts its foot
    # further for the same motion -- measured, `upright_run_forward` reads 0.905 m on her against a
    # limit of 0.85 that she was never measured under. Scaled by this body's own pelvis rest (the
    # leg, which is what a foot lift is a function of) rather than total height, since a head does
    # not lift a foot. The reference scales to exactly 1.0.
    global HEIGHT_SCALE
    HEIGHT_SCALE = rig.world("pelvis", {})[1][3] / REFERENCE_PELVIS_Y

    # A MORPH ANIMATION IS NOT A BODY CLIP, and the library skips it for the same reason
    # (`build_character_anims.gd`): a VRoid body's ~40 facial shape keys export as one extra
    # animation named after the MESH, so Shino's export carries a 168th called `Face`. Checking it
    # as a body clip reports a channel-count "duplicate" that is nothing of the sort.
    def is_body_clip(a):
        for c in a["channels"]:
            if c.get("target", {}).get("path") == "weights":
                return False
        return True

    body_clips = [a for a in J["animations"] if is_body_clip(a)]
    skipped_morph = [a["name"] for a in J["animations"] if not is_body_clip(a)]
    if skipped_morph:
        print(f"  morph_clips: {len(skipped_morph)} shape-key animation(s) not checked as body "
              f"clips: {', '.join(skipped_morph)}")

    # -- duplicate_clips ----------------------------------------------------
    for a in body_clips:
        if len(a["channels"]) != expect:
            err("duplicate_clips",
                f"{a['name']!r} has {len(a['channels'])} channels, expected {expect} "
                f"({nbones} bones x 3). A count that is an exact multiple means the action was "
                f"exported more than once (active action + stash); keep one NLA track per clip "
                f"and no active action.")

    def clip(name):  # importer strips -loop
        return name + "-loop" if name + "-loop" in rig.anim else name

    # -- pose_clip_moves ----------------------------------------------------
    # AN AIM OR HOLD CLIP IS ONE POSE. A blendspace point PLAYS its clip, so a pose clip holding two
    # different poses alternates between them every frame -- which is what "the arm moves in and out
    # constantly" was: the authored crawl aim clips carried the new prone pose on frame 0 and the
    # placeholder they replaced on frame 1, 0.49 m apart at the hand, and the game flipped between
    # them at a ~2.5 frame cycle. Every upright aim clip is a single frame, which is why this had
    # never bitten and why nothing was watching for it.
    # Only clips the AnimationTree actually PLAYS: an orphan pose clip cannot alternate in game, and
    # failing the export over one would be reporting a fact about the .blend as a defect in the game.
    played = set(re.findall(r'^animation = &"([^"]+)"', open(TSCN).read(), re.M)) if os.path.exists(TSCN) else set()
    for name in sorted(rig.anim):
        base = name[:-5] if name.endswith("-loop") else name
        if base not in played:
            continue
        if "_aim_" not in base and "_hold_" not in base:
            continue
        ps = samples(rig, name, 9)
        if len(ps) < 2:
            continue
        worst, at = 0.0, None
        for b in ("hand_l", "hand_r"):
            if b not in rig.bone:
                continue
            pts = [rig.world(b, p) for p in ps]
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    d = sum((pts[i][k][3] - pts[j][k][3]) ** 2 for k in range(3)) ** 0.5
                    if d > worst:
                        worst, at = d, b
        if worst > POSE_CLIP_STILL_MAX:
            err("pose_clip_moves",
                f"{name!r} is a POSE clip but {at} travels {worst:.3f} m across it (limit "
                f"{POSE_CLIP_STILL_MAX:.2f}). A blendspace point plays its clip, so two poses in one "
                f"pose clip alternate every frame. Keep the authored frame and delete the rest.")

    # -- shoulder_overbend --------------------------------------------------
    # A WARN, deliberately, and the limit is DESCRIPTIVE rather than universal (user, 2026-09-20).
    # 60 deg is what the aim and hold poses measure -- it is a description of how those are built in
    # the .blend, not a rule every clip owes: an attack, a throw or a prone reach legitimately swings
    # the collarbone further, and the big prone rotation is in the SHOULDER JOINT anyway
    # (`upperarm_l` 134.5 deg on the authored crawl rifle pose, against clavicles of 39.7/34.9).
    # So this reports and does not fail: it is here to SAY when a clip has gone somewhere unusual,
    # which is what caught the five ARMS-ONLY retargeted attacks at 73-171 deg (W34/W45), not to
    # decide what a pose is allowed to be.
    for name in sorted(rig.anim):
        worst = {}
        for b in SHOULDER_BONES:
            i = rig.bone.get(b)
            if i is None:
                continue
            rest = rig.nodes[i].get("rotation", [0, 0, 0, 1])
            for p in samples(rig, name, 17):
                q = p.get(i, {}).get("rotation")
                if q is None:
                    continue
                d = quat_angle_from_rest(rest, q)
                if d > worst.get(b, 0.0):
                    worst[b] = d
        over = {b: d for b, d in worst.items() if d > SHOULDER_MAX_DEG + 0.5}
        if over:
            warn("shoulder_overbend",
                 f"{name!r} turns " + ", ".join(f"{b} {d:.1f} deg" for b, d in sorted(over.items()))
                 + f" on its own channel, past the {SHOULDER_MAX_DEG:.0f} deg the aim and hold poses "
                   f"use. Fine if the clip means it; `blender/tools/fix_shoulder_overbend.py` clamps "
                   f"the shoulder and re-solves the arm so the hand stays put if it does not.")

    # -- root_baseline / loop_transition / gun_travel / feet_planted --------
    # The upper-body layer boundary, read off the scene so the gate and the
    # AnimationTree cannot disagree about which bones the aim clip supplies.
    upper = tscn_upper_body_filter()
    ri = rig.bone["Root"]

    for fam, spec in FAMILIES.items():
        present = [(m, clip(m)) for m in spec["clips"] if clip(m) in rig.anim]
        for m in spec["clips"]:
            if clip(m) not in rig.anim:
                warn("root_baseline", f"{fam}: clip {m!r} is not in the export")
        if not present:
            continue
        aim = clip(spec["aim"]) if clip(spec["aim"]) in rig.anim else None
        if aim is None:
            warn("gun_travel", f"{fam}: aim clip {spec['aim']!r} missing; gun check skipped")

        stats = {}
        for label, c in present:
            ps = samples(rig, c, 17)
            ys = [p.get(ri, {}).get("translation", [0, 0, 0])[1] for p in ps]
            composed = [compose(rig, p, aim, upper) for p in ps] if aim else ps
            stats[label] = dict(
                mean=sum(ys) / len(ys),
                close=abs(ys[0] - ys[-1]),
                gun=[rig.world("hand_r", p)[1][3] for p in composed],
                gun_x=[rig.world("hand_r", p)[0][3] for p in composed],
                gun_z=[rig.world("hand_r", p)[2][3] for p in composed],
                foot=max(max(rig.world(b, p)[1][3] for p in ps) for b in ("ball_l", "ball_r")),
            )

        # a ring must share one Root baseline -- a per-clip offset translates the whole
        # skeleton, and with it the gun, its Muzzle and every PhysicalBone3D hitbox
        lo = min(stats, key=lambda k: stats[k]["mean"])
        hi = max(stats, key=lambda k: stats[k]["mean"])
        spread = stats[hi]["mean"] - stats[lo]["mean"]
        gauge("root_baseline", spread, ROOT_BASELINE_MAX,
              f"{fam}: Root.y baseline spans {spread:.3f} m inside one blendspace ring "
              f"-- {lo!r} at {stats[lo]['mean']:.3f} vs {hi!r} at {stats[hi]['mean']:.3f}.")

        # a loop whose first frame is not its last is a stance TRANSITION baked into a
        # looping clip; it then plays that transition forever
        for label, st in stats.items():
            gauge("loop_transition", st["close"], LOOP_CLOSE_MAX,
                  f"{fam}: {label!r} does not close -- Root.y differs by {st['close']:.3f} m "
                  f"between its first and last frame. Find the frame that matches the last one "
                  f"and trim everything before it.")

        # the same fact where it is felt: the gun, on the pose that actually ships
        # Compare CENTRES, not floors: a gait legitimately bobs, and the idle clip does not,
        # so a floor-to-floor comparison just reports half the walk's own bob. What must not
        # differ is where the gun sits on average -- that is the step you feel on the first
        # frame of movement (the shipped crouch defect measured 0.126 m here).
        idle = present[0][0]
        centre = lambda l: sum(stats[l]["gun"]) / len(stats[l]["gun"])
        base = centre(idle)
        for label in stats:
            step = abs(centre(label) - base)
            if label != idle:
                gauge("gun_travel", step, GUN_STEP_MAX,
                      f"{fam}: gun centre shifts {step:.3f} m from {idle!r} to {label!r}.")
            bob = max(stats[label]["gun"]) - min(stats[label]["gun"])
            gauge("gun_travel", bob, spec["bob"],
                  f"{fam}: gun travels {bob:.3f} m inside {label!r} alone.")
            sway = max(max(stats[label]["gun_x"]) - min(stats[label]["gun_x"]),
                       max(stats[label]["gun_z"]) - min(stats[label]["gun_z"]))
            lateral = "left" in label or "right" in label
            if not lateral:
                gauge("gun_sway", sway, GUN_SWAY_MAX,
                      f"{fam}: gun swings {sway:.3f} m sideways inside {label!r} -- the torso "
                      f"is not absorbing the pelvis twist. Check what the upper-body filter takes "
                      f"from the aim clip: a STATIC spine_01/spine_02 replaces the "
                      f"counter-rotation the walk clip animates.")
            gauge("feet_planted", stats[label]["foot"], spec["foot"] * HEIGHT_SCALE,
                  f"{fam}: {label!r} lifts a foot to {stats[label]['foot']:.3f} m "
                  f"-- a Root offset applied without re-posing the legs.")

    # -- tree_refs ----------------------------------------------------------
    if os.path.exists(TSCN):
        imported = {a[:-5] if a.endswith("-loop") else a for a in rig.anim}
        refs = sorted(set(re.findall(r'^animation = &"([^"]+)"',
                                     open(TSCN).read(), re.M)))
        for r in refs:
            if r not in imported:
                err("tree_refs", f"AnimationTree references clip {r!r}, absent from the export.")
        print(f"  tree_refs: {len(refs)} clips referenced by the AnimationTree")

        # -- aim_coverage: THE ARTIST'S LIST -------------------------------
        # A grip archetype's index is APPEND-ONLY (W12), so an archetype no weapon uses cannot be
        # deleted -- but its CLIPS can, and they were: a copy of another pose that nothing can reach
        # is a clip that silently goes stale (the sniper set diverged twice, W45). Those indices now
        # point at their base clip, so the render is unchanged and there is one pose to keep right
        # instead of two. What is left is exactly the set an artist can change something with, and
        # this prints it per stance so nobody has to work that out from a blendspace.
        try:
            arch = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "weapon_archetypes.json")))
            cat = json.load(open(os.path.join(ROOT, "src/main/resources/com/openworld/weapon/"
                                                    "weapon_catalog.json")))
        except OSError:
            arch = cat = None
        if arch and cat:
            weapons = {}
            for row in cat["weapons"]:
                weapons.setdefault(row["archetype"], []).append(row["id"])
            print("  aim_coverage: the poses an artist can change something with")
            for fam, what in (("upright_aim_%s", "aim, standing"), ("crouch_aim_%s", "aim, kneeling"),
                              ("crawl_aim_%s", "aim, prone"), ("upright_hold_%s", "hold, non-combat"),
                              ("weapon_switch_%s", "draw")):
                own, shared = [], []
                for a in arch["archetypes"]:
                    if a["name"] not in weapons:
                        continue
                    (own if (fam % a["name"]) in imported else shared).append(a["name"])
                line = "    %-18s own: %s" % (what, ", ".join(own) if own else "-")
                if shared:
                    line += "   |  SHARED (no clip of their own): " + ", ".join(shared)
                print(line)
            idle = [a["name"] for a in arch["archetypes"] if a["name"] not in weapons]
            print("    %-18s %s -- no shipped weapon; their blendspace points play their base pose"
                  % ("reserved:", ", ".join(idle) if idle else "-"))

        # -- orphan_clips ---------------------------------------------------
        # The other direction, which cost a whole investigation: a clip that exists, exports, and
        # is named by NOTHING. Authoring into one changes the game by exactly zero, and it looks
        # like the animation is broken rather than unused. That is what aim_pistol_crouch-loop and
        # its three siblings are today -- real crouch/prone poses whose arms (the only bones
        # WeaponBlend's filter takes from the aim branch) are bit-identical to the upright clip's,
        # so the AnimationTree's single upright WeaponAim blendspace loses nothing by ignoring
        # them. WARN, not ERROR: an unused clip is a normal state for work in progress.
        orphans = sorted(imported - set(refs))
        if orphans:
            warn("orphan_clips",
                 f"{len(orphans)} exported clip(s) referenced by no AnimationTree node, so "
                 f"editing them cannot change the game: {', '.join(orphans)}")

    # -- report -------------------------------------------------------------
    print(f"check_character_anim: {len(J['animations'])} clips, {nbones} bones, "
          f"{len(FAMILIES)} blendspace rings")
    for level, check, msg in findings:
        print(f"  {level} [{check}] {msg}")
    bad = sum(1 for f in findings if f[0] == "ERROR")
    print(f"  {'FAIL' if bad else 'PASS'} — {bad} error(s), "
          f"{len(findings) - bad} warning(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
