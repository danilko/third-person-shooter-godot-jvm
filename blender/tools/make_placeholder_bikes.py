"""Placeholder MOTORCYCLES, generated from real Japanese dimensions, in the component form (PLAN.md 3.1b / 2c.7).

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/make_placeholder_bikes.py -- [ID ...] [--force]

The bike set (user, 2026-10-15): fictional names, no logos, a Japanese class as the SIZE reference only. Each bike is a
BLOCK MODEL of the right size written to `assets/vehicles/<ID>.blend` in component form, the same contract as
make_placeholder_cars.py (+Y forward, origin on the ground at mid-wheelbase, named parts, `seat_*` Empties), so
`build_vehicle.py` measures it and `tools/build_vehicle_scenes.py` builds its scene. A bike's parts:

  chassis      frame, engine, tank, seat, bars, forks, mudguards, lamps (never comes off)
  wheel_f / wheel_b   the two wheels (the runtime drives FOUR narrow rays under them: Motorcycle.java)
  fairing      the front cowl / leg shield (comes loose and off; damage slot bump_front)
  top_box      the rear box: scooter delivery box, the postal box, the police pannier box (slot bump_rear)
  mirror_l/r   the mirrors on their stalks (slots door_lr / door_rr: a bike has no rear doors)
  windscreen   the screen of the sport bike and the 白バイ

Seats: `seat_front_l` = the rider (on the cushion's top), `seat_rear_l` = the pillion.
Grips: `grip_l` / `grip_r` = where the rider's hands close on the bars (the knuckle line, a hand's width in from each
bar end). They export as nodes in the .glb and the runtime puts the hands on them (character.RiderPoseModifier), so an
artist who moves a bar moves these with it and the hands follow, no code.

Sizes (L x W x H, wheelbase, seat height, tyre radius f/r); maker figures where a spec sheet was found (2026-10-16):
  SCT1  原付 scooter, Dio AF68 class (Honda JP: 1.72 x 0.65 x 1.02, wb 1.18, seat 0.69, 84 kg)
  POB1  postal Cub, Super Cub 110 class (Honda 2017: 1.86 x 0.695 x 1.04, wb 1.205, seat 0.735, 99 kg), 郵便 red,
        front basket + the rear postal box
  TRB1  rural trail, Serow 250 / CRF250L class (from memory: 2.23 x 0.82 x 1.20, wb 1.44, seat 0.86, ~135 kg)
  SSB1  racing supersport, YZF-R1 class (from memory: 2.06 x 0.70 x 1.16, wb 1.42, seat 0.85, ~200 kg)
  PMB1  police 白バイ, CB1300 class (CB1300SF factbook 2.20 x 0.78-0.79 x 1.12-1.17, wb 1.515-1.545, ~270 kg; the
        police kit -- crash bars, tall screen, the red lamps on their posts, the pannier box -- makes it 0.90 wide,
        1.45 high)
"""
import importlib.util
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("make_placeholder_cars", os.path.join(HERE, "make_placeholder_cars.py"))
cars = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cars)
Part, DIR = cars.Part, cars.DIR
cars.COLOURS.update({"seat": (0.06, 0.06, 0.07), "engine": (0.28, 0.28, 0.30), "chrome": (0.70, 0.71, 0.73),
                     "post_box": (0.80, 0.06, 0.05)})

# a grip's centre this far in from the bar end (m): half a gloved hand's width plus the bar-end weight
GRIP_IN = 0.06
# THE RIDER TRIANGLE (3.1b hands on the bars, 2026-10-16): the seat Empty is the rider's HIP, HIP_BEHIND_FRONT behind the
# cushion's front edge (right behind the tank / the scooter's leg shield, where a rider sits, not halfway to the
# pillion), and the grips RISE above the seat and REACH ahead of that hip by a riding position per kind -- upright on a
# scooter / Cub / trail / 白バイ, the sport bike's clip-ons low and far (the tuck). MY PICKS from the usual rider-triangle
# figures (from memory, not measured off a bike): an upright bike's grips ~0.30 m over the seat and ~0.5 m ahead of the
# hip. Before this the bars were placed from the stated height as if it were the mirror tops: 0.09-0.10 m over the
# seat, out of reach of both bodies by 0.15-0.4 m (probe_rider_pose).
HIP_BEHIND_FRONT = {"scooter": 0.20, "cub": 0.20, "trail": 0.18, "sport": 0.18, "police": 0.18}
GRIP_RISE = {"scooter": 0.30, "cub": 0.30, "trail": 0.32, "sport": 0.06, "police": 0.32}
GRIP_REACH = {"scooter": 0.48, "cub": 0.48, "trail": 0.52, "sport": 0.58, "police": 0.52}

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORCE = "--force" in argv

# kind: scooter | cub | trail | sport | police. paint "car" is repainted per bike at runtime.
BIKES = {
    "SCT1": dict(L=1.72, W=0.65, H=1.02, wb=1.18, seat=0.69, rf=0.24, rb=0.24, tw=0.10, kind="scooter",
                 body="car", box=True, box_mat="trim"),
    "POB1": dict(L=1.86, W=0.695, H=1.04, wb=1.205, seat=0.735, rf=0.29, rb=0.29, tw=0.08, kind="cub",
                 body="post_red", box=True, box_mat="post_box", basket=True),
    "TRB1": dict(L=2.23, W=0.82, H=1.20, wb=1.44, seat=0.86, rf=0.36, rb=0.34, tw=0.10, kind="trail",
                 body="car"),
    "SSB1": dict(L=2.06, W=0.70, H=1.16, wb=1.42, seat=0.85, rf=0.30, rb=0.31, tw=0.18, kind="sport",
                 body="car", screen=True),
    "PMB1": dict(L=2.20, W=0.90, H=1.45, wb=1.52, seat=0.79, rf=0.31, rb=0.32, tw=0.17, kind="police",
                 body="police_white", screen=True, box=True, box_mat="police_white", bar="lamp_red"),
}


def build(vid, c):
    L, W, H, wb, seat, rf, rb, tw = c["L"], c["W"], c["H"], c["wb"], c["seat"], c["rf"], c["rb"], c["tw"]
    kind, body = c["kind"], c["body"]
    hl, hw = L / 2, W / 2
    yf, yb = wb / 2, -wb / 2                       # the axles
    parts = {}
    P = lambda n: parts.setdefault(n, Part(n))
    ch = P("chassis")
    low = kind in ("scooter", "cub")               # step-through: a floorboard between the knees, the engine low
    # the cushion: its top is the seat height, over the middle-to-rear of the wheelbase
    s_front = 0.10 if low else 0.05
    s_rear = yb - (0.05 if low else 0.10)
    ch.box((-0.14, s_rear, seat - 0.09), (0.14, s_front, seat), "seat")
    # the body under the seat (scooter / cub shell) or the tank in front of it
    if low:
        ch.box((-0.15, yb + 0.05, max(rb + 0.05, 0.30)), (0.15, s_front, seat - 0.09), body)
        ch.box((-0.17, yb - 0.10, 0.20), (0.17, yb + 0.25, rb + 0.12), "engine")      # the swing-arm unit
        ch.box((-0.16, s_front, 0.18), (0.16, yf - 0.32, 0.28), body)                 # the floorboard
    else:
        ch.box((-0.15, s_front, seat - 0.12), (0.15, s_front + 0.45, seat + 0.10), body)   # the tank
        ch.box((-0.17, -0.05, 0.22), (0.17, s_front + 0.40, seat - 0.15), "engine")
        ch.box((-0.10, s_rear - 0.25, seat - 0.12), (0.10, s_rear, seat + (0.12 if kind == "sport" else 0.02)), body)
    # the frame spine, steering head, forks and bars
    head_y = yf - (0.28 if low else 0.30)
    # the bars are where the rider's hands go (the rider triangle above); the stated height is the body's, mirrors over it
    hip_y = s_front - HIP_BEHIND_FRONT[kind]
    bar_z = seat + GRIP_RISE[kind]
    grip_y = min(hip_y + GRIP_REACH[kind], head_y - 0.02)
    ch.box((-0.04, s_front - 0.05, 0.30), (0.04, head_y, 0.40 if low else seat - 0.05), "frame")
    ch.box((-0.05, head_y - 0.05, 0.40), (0.05, head_y + 0.05, bar_z), "frame")
    for sx in (-1, 1):
        ch.box((sx * 0.07 - 0.02, head_y, rf), (sx * 0.07 + 0.02, yf, bar_z - 0.10), "chrome")
    bar_half = {"scooter": 0.30, "cub": 0.31, "trail": 0.40, "sport": 0.33, "police": 0.40}[kind]
    ch.box((-bar_half, head_y - 0.06, bar_z - 0.03), (bar_half, head_y + 0.02, bar_z + 0.03), "trim")
    if grip_y < head_y - 0.06:                     # the bar ends sweep back to the grips
        for sx in (-1, 1):
            x0, x1 = sorted((sx * (bar_half - 2 * GRIP_IN), sx * bar_half))
            ch.box((x0, grip_y - 0.03, bar_z - 0.03), (x1, head_y - 0.06, bar_z + 0.03), "trim")
    # mudguards
    ch.box((-tw / 2 - 0.02, yf - rf, rf + 0.03 if kind != "trail" else rf + 0.22),
           (tw / 2 + 0.02, yf + rf * 0.7, rf + 0.08 if kind != "trail" else rf + 0.26), body)
    ch.box((-tw / 2 - 0.02, yb - rb * 0.9, rb + 0.05), (tw / 2 + 0.02, yb + rb * 0.3, rb + 0.10), "trim")
    # the overhangs: the front mudguard's nose and the tail / number plate carry the bike to its stated length
    ch.box((-0.05, yf + rf * 0.5, rf + 0.02), (0.05, hl, rf + 0.06), body if kind != "trail" else "trim")
    ch.box((-0.08, -hl, rb + 0.10), (0.08, yb - rb * 0.8, rb + 0.30), "trim")
    # lamps: two halves, so the measured RIGHT-hand lamp centre sits just right of the centreline
    lamp_y = head_y + 0.10 if low else head_y + 0.14
    lamp_z = bar_z - (0.10 if low else 0.22)
    tail_z = seat - 0.06
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 0.005, sx * 0.07))
        ch.box((x0, lamp_y, lamp_z - 0.05), (x1, lamp_y + 0.02, lamp_z + 0.05), "front.lamp.light")
        ty = -hl + 0.06 if not low else yb - 0.12          # the tail lamp's face, inside the stated length
        ch.box((x0, ty - 0.02, tail_z - 0.03), (x1, ty, tail_z + 0.03), "back.lamp.light")
    # the front cowl: a scooter's / cub's leg shield, a sport bike's full fairing, the police half cowl, a trail's plate
    fa = P("fairing")
    if low:
        fa.box((-hw + 0.04, head_y - 0.12, 0.22), (hw - 0.04, head_y - 0.02, bar_z - 0.12), body)
    elif kind == "sport":
        fa.box((-hw + 0.02, head_y - 0.05, 0.25), (hw - 0.02, hl - 0.04, bar_z + 0.08), body)
    elif kind == "police":
        fa.box((-0.30, head_y - 0.02, lamp_z - 0.20), (0.30, head_y + 0.20, bar_z + 0.05), body)
        for sx in (-1, 1):                     # the crash bars, the widest thing on it
            x0, x1 = sorted((sx * (hw - 0.02), sx * (hw - 0.07)))
            ch.box((x0, s_front + 0.10, 0.30), (x1, s_front + 0.18, 0.55), "chrome")
    else:
        fa.box((-0.14, head_y + 0.08, lamp_z - 0.12), (0.14, head_y + 0.12, lamp_z + 0.12), body)
    if c.get("screen"):
        top = H if kind == "police" else H - 0.04
        P("windscreen").box((-0.20, head_y + 0.02, bar_z + 0.05), (0.20, head_y + 0.06, top), "glass")
    if c.get("basket"):
        ch.box((-0.17, yf - 0.10, bar_z - 0.30), (0.17, yf + 0.18, bar_z - 0.08), "trim")
    if c.get("box"):
        bh = {"scooter": 0.30, "cub": 0.30, "police": 0.36}[kind]
        bw = {"scooter": 0.38, "cub": 0.44, "police": 0.42}[kind]
        b0 = -hl + 0.04
        P("top_box").box((-bw / 2, b0, seat - 0.02), (bw / 2, b0 + 0.40, seat - 0.02 + bh), c["box_mat"])
    if c.get("bar"):                           # the 白バイ's red lamps on their posts behind the pillion seat
        for sx in (-1, 1):
            ch.box((sx * 0.22 - 0.02, s_rear - 0.10, seat), (sx * 0.22 + 0.02, s_rear - 0.06, H - 0.12), "frame")
            ch.box((sx * 0.22 - 0.05, s_rear - 0.12, H - 0.14), (sx * 0.22 + 0.05, s_rear - 0.04, H - 0.02), c["bar"])
    # the mirrors on stalks at the bar ends
    for name, sx in (("mirror_l", -1), ("mirror_r", 1)):
        m = P(name)
        x = sx * (min(bar_half, hw - 0.06) - 0.02)
        m.box((x - 0.015, head_y - 0.03, bar_z), (x + 0.015, head_y, bar_z + 0.18), "frame")
        m.box((x - 0.06, head_y - 0.04, bar_z + 0.16), (x + 0.06, head_y, bar_z + 0.24), "chrome")
    # wheels
    P("wheel_f").cylinder(0.0, yf, rf, rf, tw, "tyre")
    P("wheel_b").cylinder(0.0, yb, rb, rb, tw, "tyre")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    coll = bpy.context.scene.collection
    for p in parts.values():
        p.emit(coll)
    pillion_y = s_rear + 0.12
    for n, (x, y, z) in (("seat_front_l", (0.0, hip_y, seat)),
                         ("seat_rear_l", (0.0, pillion_y - 0.05, seat + (0.10 if kind == "sport" else 0.0)))):
        e = bpy.data.objects.new(n, None)
        e.location = (x, y, z)
        e.empty_display_size = 0.2
        coll.objects.link(e)
    grip_x = bar_half - GRIP_IN
    for n, sx in (("grip_l", -1), ("grip_r", 1)):
        e = bpy.data.objects.new(n, None)
        e.location = (sx * grip_x, grip_y, bar_z)
        e.empty_display_type = 'SPHERE'
        e.empty_display_size = 0.03
        coll.objects.link(e)
    bpy.context.scene["placeholder_car"] = "generated by blender/tools/make_placeholder_bikes.py; replace the parts, " \
                                           "keep their names and the seat_* / grip_* Empties"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DIR, vid + ".blend"))
    print("[make_placeholder_bikes] %s: %s, %d parts" % (vid, kind, len(parts)))


def main():
    ids = [a for a in argv if not a.startswith("--")] or list(BIKES)
    for vid in ids:
        path = os.path.join(DIR, vid + ".blend")
        if not FORCE and not cars.generated(path):
            print("[make_placeholder_bikes] %s: KEPT, %s was not written by this script (--force overwrites)" % (vid, path))
            continue
        build(vid, BIKES[vid])


main()
