"""Placeholder cars, generated from real Japanese dimensions, in the component form the damage model needs.

    blender -b --factory-startup --python-exit-code 1 --python blender/tools/make_placeholder_cars.py -- [ID ...] [--force]

Owner decision (2026-09-28): the elbolilloduro pack cars (PIT1 pickup, POC1 patrol car) leave the project, and the
traffic gets Japanese types instead. Each car here is a BLOCK MODEL of the right size -- a lower body, a cabin, doors,
bonnet/boot, bumpers, a windscreen and four cylinders -- written to `assets/vehicles/<ID>.blend` in COMPONENT FORM
(named parts + `seat_*` Empties, +Y forward, origin on the ground at mid-wheelbase; see blender/VEHICLE_AUTHORING.md),
so `build_vehicle.py` places hinges and `dam` keys, `tools/build_vehicle_scenes.py` builds the scene, and the damage
model, seats and wheels work. An artist replaces the parts IN the .blend, keeping the names and the seat Empties.

A .blend this script did not write (no `placeholder_car` scene property) is never overwritten; `--force` overwrites a
generated one after it has been edited.

Dimensions are the real vehicle's, rounded (length x width x height, wheelbase, tyre radius):
  KET1  kei truck (軽トラ, Suzuki Carry / Honda Acty class)       3.395 x 1.475 x 1.765  wb 1.905  cab-over
  MPC1  mini patrol car (ミニパト, kei hatch, black-and-white)      3.395 x 1.475 x 1.52   wb 2.46
  POC1  patrol car (パトカー, Crown patrol class, black-and-white) 4.91  x 1.80  x 1.53   wb 2.92
  CLC1  classic coupe (AE86 Trueno size, 2+2 hatchback)           4.205 x 1.625 x 1.335  wb 2.40
  KEC1  kei car (軽自動車, tall wagon, N-BOX class)                3.395 x 1.475 x 1.79   wb 2.52
  TAX1  taxi (JPN Taxi class, indigo, roof lamp)                  4.40  x 1.695 x 1.75   wb 2.75
  CRT1  crate truck (4-ton military / container flatbed, olive)   8.40  x 2.49  x 3.10   wb 4.60  cab-over
  AMB1  ambulance (高規格救急車, Himedic class, white, red bar)       5.65  x 1.89  x 2.49   wb 3.11
  FIE1  fire engine (消防ポンプ車 CD-I, red, cab-over)                6.40  x 2.20  x 2.90   wb 3.40  cab-over
  LAT1  ladder truck (はしご車 30 m class, red, cab-over, ladder)     10.0  x 2.49  x 3.50   wb 5.00  cab-over
  COT1  container truck (海上コンテナ車: a cab-over tractor + a 20 ft skeletal chassis, ONE rigid body)
                                                                   10.40 x 2.49 x 3.79   wb 7.80  tractor
        carrying the container terminal's own 20 ft box, ISO 668: 6.058 x 2.438 x 2.591 (build_zombie_yard.ISO_20),
        its top at 3.79 m (Japan's 3.8 m road height). A tractor and trailer are two bodies joined at the fifth wheel;
        the vehicle runtime has one rigid body with four wheels, so this is the pair made rigid -- the front axle
        under the tractor, the rear under the chassis's bogie. A rigid 40 ft rig (16.5 m, a 13 m wheelbase) could
        not turn at a junction, which is why the box is the 20 ft one (user, 2026-09-29).
(AMB1 / FIE1 / LAT1: user, 2026-09-28 -- the hospital's and the fire stations' vehicles, placed by the mission
buildings' MARK_vehicle markers.)
"""
import math
import os
import sys

import bmesh
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "assets", "vehicles")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORCE = "--force" in argv

# Flat colours; "car" is repainted per car at runtime (TUNING paint = "car"), every other name keeps its colour.
COLOURS = {
    "car": (0.75, 0.75, 0.76), "glass": (0.08, 0.10, 0.13), "interior": (0.12, 0.12, 0.13), "tyre": (0.04, 0.04, 0.04),
    "trim": (0.10, 0.10, 0.10), "police_black": (0.02, 0.02, 0.025), "police_white": (0.92, 0.92, 0.92),
    "lamp_red": (0.85, 0.04, 0.04), "taxi_body": (0.05, 0.07, 0.22), "taxi_lamp": (0.95, 0.80, 0.25),
    "olive": (0.22, 0.26, 0.15), "crate": (0.35, 0.30, 0.20),
    "container": (0.55, 0.12, 0.08), "frame": (0.08, 0.08, 0.09),
    "amb_white": (0.93, 0.93, 0.92), "fire_red": (0.72, 0.05, 0.04), "steel": (0.62, 0.63, 0.65),
    # lamps: the runtime finds these faces BY MATERIAL NAME and lights them (Vehicle.LAMP_SURFACE_*)
    "front.lamp.light": (0.85, 0.85, 0.82), "back.lamp.light": (0.45, 0.03, 0.03), "back.lamp.reverse": (0.75, 0.75, 0.75),
}
# see-through glass, the same as SPC1's (build_vehicle.py turns its Translucent window into this)
GLASS_ALPHA = 0.4

# shape: "sedan" (bonnet, cabin, boot), "hatch" (short bonnet, cabin to the tail), "wagon" (tall box, stub bonnet),
#        "cabover" (cab at the front, a bed behind; `bed` = load bed, `crate` = a crate on it)
CARS = {
    "KET1": dict(L=3.395, W=1.475, H=1.765, wb=1.905, r=0.28, tw=0.16, shape="cabover", cab=1.30, doors=2,
                 body="car", upper="car", seats=[(-0.33, 0.95, 0.72), (0.33, 0.95, 0.72)]),
    "MPC1": dict(L=3.395, W=1.475, H=1.52, wb=2.46, r=0.29, tw=0.16, shape="hatch", doors=4,
                 body="police_black", upper="police_white", bar="lamp_red",
                 seats=[(-0.34, 0.25, 0.52), (0.34, 0.25, 0.52), (-0.34, -0.55, 0.55), (0.34, -0.55, 0.55)]),
    "POC1": dict(L=4.91, W=1.80, H=1.53, wb=2.92, r=0.34, tw=0.22, shape="sedan", doors=4,
                 body="police_black", upper="police_white", bar="lamp_red",
                 seats=[(-0.40, 0.30, 0.52), (0.40, 0.30, 0.52), (-0.40, -0.60, 0.55), (0.40, -0.60, 0.55)]),
    "CLC1": dict(L=4.205, W=1.625, H=1.335, wb=2.40, r=0.29, tw=0.19, shape="hatch", doors=2,
                 body="car", upper="car",
                 seats=[(-0.37, 0.10, 0.36), (0.37, 0.10, 0.36), (-0.33, -0.75, 0.40), (0.33, -0.75, 0.40)]),
    "KEC1": dict(L=3.395, W=1.475, H=1.79, wb=2.52, r=0.28, tw=0.16, shape="wagon", doors=4,
                 body="car", upper="car",
                 seats=[(-0.34, 0.25, 0.66), (0.34, 0.25, 0.66), (-0.34, -0.60, 0.68), (0.34, -0.60, 0.68)]),
    "TAX1": dict(L=4.40, W=1.695, H=1.75, wb=2.75, r=0.31, tw=0.19, shape="wagon", doors=4,
                 body="taxi_body", upper="taxi_body", roof_lamp="taxi_lamp",
                 seats=[(-0.38, 0.35, 0.62), (0.38, 0.35, 0.62), (-0.38, -0.55, 0.64), (0.38, -0.55, 0.64)]),
    "CRT1": dict(L=8.40, W=2.49, H=3.10, wb=4.60, r=0.52, tw=0.30, shape="cabover", cab=1.85, doors=2, crate=True,
                 body="olive", upper="olive", seats=[(-0.55, 2.90, 1.45), (0.55, 2.90, 1.45)]),
    "AMB1": dict(L=5.65, W=1.89, H=2.49, wb=3.11, r=0.33, tw=0.21, shape="wagon", doors=4,
                 body="amb_white", upper="amb_white", bar="lamp_red",
                 seats=[(-0.42, 1.35, 0.78), (0.42, 1.35, 0.78), (-0.45, -0.40, 0.80), (0.45, -0.40, 0.80)]),
    "FIE1": dict(L=6.40, W=2.20, H=2.90, wb=3.40, r=0.40, tw=0.26, shape="cabover", cab=1.70, doors=2, crate=True,
                 crate_mat="fire_red", body="fire_red", upper="fire_red", bar="lamp_red",
                 seats=[(-0.48, 2.25, 1.25), (0.48, 2.25, 1.25)]),
    "LAT1": dict(L=10.0, W=2.49, H=3.50, wb=5.00, r=0.50, tw=0.30, shape="cabover", cab=2.00, doors=2, crate=True,
                 crate_mat="fire_red", ladder=True, body="fire_red", upper="fire_red", bar="lamp_red",
                 seats=[(-0.55, 3.85, 1.50), (0.55, 3.85, 1.50)]),
    "COT1": dict(L=10.40, W=2.49, H=3.79, wb=7.80, r=0.53, tw=0.46, shape="tractor", cab=2.10, cab_h=3.05, doors=2,
                 body="car", upper="car", seats=[(-0.55, 4.05, 1.55), (0.55, 4.05, 1.55)]),
}
ISO_20 = (6.058, 2.438, 2.591)       # the container terminal's 20 ft box (blender/tools/build_zombie_yard.py ISO_20)
CLEAR = 0.20                   # ground to the underside of the body


def mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    c = COLOURS[name]
    bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
    bsdf.inputs["Roughness"].default_value = 0.05 if name in ("glass",) else 0.6
    if name == "glass":
        bsdf.inputs["Alpha"].default_value = GLASS_ALPHA
        m.surface_render_method = 'BLENDED'
    m.diffuse_color = (c[0], c[1], c[2], GLASS_ALPHA if name == "glass" else 1.0)
    return m


class Part:
    def __init__(self, name):
        self.name, self.bm, self.mats = name, bmesh.new(), []

    def slot(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def box(self, lo, hi, m):
        i = self.slot(m)
        v = [self.bm.verts.new((hi[0] if k & 1 else lo[0], hi[1] if k & 2 else lo[1], hi[2] if k & 4 else lo[2]))
             for k in range(8)]
        for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            self.bm.faces.new([v[j] for j in f]).material_index = i

    def wedge(self, x0, x1, y_lo, y_hi, z_lo, z_hi, slope_front, m):
        """A box whose top edge at the FRONT (or rear) is pulled in by slope_front: a windscreen / a rear hatch."""
        i = self.slot(m)
        pts = [(x0, y_lo, z_lo), (x1, y_lo, z_lo), (x0, y_hi, z_lo), (x1, y_hi, z_lo)]
        yf = y_hi - slope_front if slope_front > 0 else y_hi
        yb = y_lo - slope_front if slope_front < 0 else y_lo
        pts += [(x0, yb, z_hi), (x1, yb, z_hi), (x0, yf, z_hi), (x1, yf, z_hi)]
        v = [self.bm.verts.new(p) for p in pts]
        for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            self.bm.faces.new([v[j] for j in f]).material_index = i

    def cylinder(self, cx, cy, cz, r, w, m, n=16):
        i = self.slot(m)
        rings = [[self.bm.verts.new((cx + s * w / 2, cy + r * math.cos(2 * math.pi * k / n),
                                     cz + r * math.sin(2 * math.pi * k / n))) for k in range(n)] for s in (-1, 1)]
        for k in range(n):
            self.bm.faces.new((rings[0][k], rings[0][(k + 1) % n], rings[1][(k + 1) % n], rings[1][k])).material_index = i
        self.bm.faces.new(rings[0]).material_index = i
        self.bm.faces.new(list(reversed(rings[1]))).material_index = i

    def emit(self, coll):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(mat(m))
        o = bpy.data.objects.new(self.name, me)
        coll.objects.link(o)
        return o


def build(vid, c):
    L, W, H, wb, r, tw = c["L"], c["W"], c["H"], c["wb"], c["r"], c["tw"]
    hl, hw = L / 2, W / 2
    body, upper = c["body"], c["upper"]
    belt = min(H * 0.55, CLEAR + 0.65 if c["shape"] != "cabover" else H * 0.5)   # top of the lower body
    parts = {}
    P = lambda n: parts.setdefault(n, Part(n))
    # The body runs to within PROUD of the ends and the bumpers overlap it: the lamp offsets are derived from the
    # car's BOUNDS (tools/build_vehicle_scenes.py), so a bumper sticking out 18 cm left every lamp floating in the air.
    bump = 0.03
    side = 0.05                                          # door panel thickness; the body is inset by it where doors are
    ch = P("chassis")
    front, rear = hl - bump, -hl + bump

    if c["shape"] == "tractor":
        # the tractor: a cab-over cab, its frame and the fifth wheel; the skeletal chassis: two long rails, cross
        # members, the landing legs, the rear bogie's mudguards; the 20 ft ISO box locked on top at its twist locks
        cab_h = c["cab_h"]
        cab_rear = front - c["cab"]
        cbelt = cab_h * 0.5
        ch.box((-hw + side, cab_rear, CLEAR + 0.35), (hw - side, front, cbelt), body)
        ch.box((-hw + 0.04, cab_rear, cbelt), (hw - 0.04, front - 0.02, cab_h - 0.08), "glass")
        ch.box((-hw + 0.02, cab_rear, cab_h - 0.08), (hw - 0.02, front - 0.01, cab_h), upper)
        ch.box((-hw + 0.3, cab_rear - 0.25, cab_h - 0.6), (hw - 0.3, cab_rear, cab_h + 0.25), upper)   # the wind deflector
        deck = 1.20                                          # the chassis's top: the container's floor
        for sx in (-1, 1):                                    # the rails, the tractor's frame under them
            ch.box((sx * 0.55 - 0.12, rear, deck - 0.30), (sx * 0.55 + 0.12, cab_rear, deck), "frame")
            ch.box((sx * 0.45 - 0.10, cab_rear - 3.0, 0.75), (sx * 0.45 + 0.10, front - 0.4, 1.00), "frame")
        for k in range(8):
            y = rear + 0.3 + k * (cab_rear - 0.8 - rear) / 7
            ch.box((-hw + 0.05, y - 0.08, deck - 0.22), (hw - 0.05, y + 0.08, deck - 0.02), "frame")
        ch.box((-0.6, cab_rear - 1.6, 1.00), (0.6, cab_rear - 0.4, 1.12), "steel")          # the fifth wheel
        for sx in (-1, 1):
            ch.box((sx * 0.9 - 0.06, -0.2, 0.25), (sx * 0.9 + 0.06, -0.08, deck - 0.3), "steel")  # landing legs
            ch.box((sx * (hw - 0.02) - 0.02, -wb / 2 - r - 0.3, r + 0.1), (sx * (hw - 0.02) + 0.02,
                   -wb / 2 + r + 0.3, r + 0.25), "trim")                                            # mudguards
        cl, cw, chh = ISO_20
        cf = cab_rear - 0.45                                  # the container's front face
        ch.box((-cw / 2, cf - cl, deck), (cw / 2, cf, deck + chh), "container")
        for k in range(1, 24):                                # the corrugation, 2 cm proud
            y = cf - k * cl / 24
            for sx in (-1, 1):
                x0, x1 = sorted((sx * cw / 2, sx * (cw / 2 + 0.02)))
                ch.box((x0, y - 0.05, deck + 0.10), (x1, y + 0.05, deck + chh - 0.10), "container")
        for x in (-cw / 2 + 0.3, -0.3, 0.3, cw / 2 - 0.3):     # the doors' locking bars at the rear
            ch.box((x - 0.03, cf - cl - 0.03, deck + 0.1), (x + 0.03, cf - cl, deck + chh - 0.1), "steel")
        if c.get("bar"):
            ch.box((-hw + 0.25, front - 0.60, cab_h), (hw - 0.25, front - 0.30, cab_h + 0.18), c["bar"])
        windscreen = (cab_rear, front)
        door_y = (cab_rear + 0.15, front - 0.25)
        parts_doors = [("door_lf", -1, door_y), ("door_rf", 1, door_y)]
        bonnet = None
        boot = None
        belt = cbelt
        H = cab_h
    elif c["shape"] == "cabover":
        cab_rear = front - c["cab"]
        # the cab: lower box + glass band + roof, full height
        ch.box((-hw + side, cab_rear, CLEAR), (hw - side, front, belt), body)
        ch.box((-hw + 0.04, cab_rear, belt), (hw - 0.04, front - 0.02, H - 0.08), "glass")
        ch.box((-hw + 0.02, cab_rear, H - 0.08), (hw - 0.02, front - 0.01, H), upper)
        # the load bed: a floor and low sides, behind the cab
        floor = CLEAR + (0.45 if not c.get("crate") else 0.75)
        ch.box((-hw, rear, CLEAR), (hw, cab_rear - 0.05, floor), body)
        side_h = 0.35 if not c.get("crate") else 0.45
        for s in (-1, 1):
            x0, x1 = sorted((s * hw, s * (hw - 0.05)))
            ch.box((x0, rear, floor), (x1, cab_rear - 0.05, floor + side_h), body)
        ch.box((-hw, cab_rear - 0.10, floor), (hw, cab_rear - 0.05, H - 0.15), "trim")     # headboard
        if c.get("crate"):
            ch.box((-hw + 0.15, rear + 0.3, floor), (hw - 0.15, cab_rear - 0.35, H), c.get("crate_mat", "crate"))
        if c.get("ladder"):              # the ladder truck's nested ladder, over the body to above the cab
            ch.box((-0.45, rear + 0.4, H), (0.45, front - 0.3, H + 0.30), "steel")
        if c.get("bar"):                 # the emergency light bar on the cab roof
            ch.box((-hw + 0.25, front - 0.60, H), (hw - 0.25, front - 0.30, H + 0.18), c["bar"])
        windscreen = (cab_rear, front)
        door_y = (cab_rear + 0.15, front - 0.25)
        parts_doors = [("door_lf", -1, door_y), ("door_rf", 1, door_y)]
        bonnet = None
        boot = None
    else:
        bonnet_len = {"sedan": 0.30 * L, "hatch": 0.27 * L, "wagon": 0.12 * L}[c["shape"]]
        boot_len = 0.18 * L if c["shape"] == "sedan" else 0.0
        a_pillar = front - bonnet_len                    # where the windscreen meets the bonnet
        c_pillar = rear + boot_len if boot_len else rear + 0.05
        roof_z = H - (0.05 if not c.get("bar") and not c.get("roof_lamp") else 0.13)
        # lower body, full length (inset at the sides where the doors hang)
        ch.box((-hw + side, rear, CLEAR), (hw - side, front, belt), body)
        # the greenhouse: glass band + roof, from the windscreen to the rear
        slope = min(0.55, (roof_z - belt) * 0.9) if c["shape"] != "wagon" else 0.18
        ch.wedge(-hw + 0.08, hw - 0.08, c_pillar, a_pillar, belt, roof_z - 0.06, slope, "glass")
        ch.box((-hw + 0.08, c_pillar + (0.10 if c["shape"] == "sedan" else 0.0), roof_z - 0.06),
               (hw - 0.08, a_pillar - slope, roof_z), upper)
        if c.get("bar"):                                 # the patrol car's light bar
            ch.box((-hw + 0.25, a_pillar - slope - 0.45, roof_z), (hw - 0.25, a_pillar - slope - 0.20, H), c["bar"])
        if c.get("roof_lamp"):                           # the taxi's andon
            ch.box((-0.22, a_pillar - slope - 0.55, roof_z), (0.22, a_pillar - slope - 0.30, H), c["roof_lamp"])
        windscreen = (a_pillar - slope, a_pillar)
        span = a_pillar - c_pillar
        if c["doors"] == 4:
            mid = c_pillar + span * 0.45
            parts_doors = [("door_lf", -1, (mid, a_pillar - 0.05)), ("door_rf", 1, (mid, a_pillar - 0.05)),
                           ("door_lr", -1, (c_pillar + 0.10, mid - 0.02)), ("door_rr", 1, (c_pillar + 0.10, mid - 0.02))]
        else:
            parts_doors = [("door_lf", -1, (c_pillar + span * 0.30, a_pillar - 0.05)),
                           ("door_rf", 1, (c_pillar + span * 0.30, a_pillar - 0.05))]
        bonnet = (a_pillar, front)
        boot = (rear, c_pillar) if boot_len else None

    # bumpers, bonnet, boot, windscreen, doors
    P("bump_front").box((-hw + 0.03, hl - 0.16, CLEAR + 0.02), (hw - 0.03, hl, CLEAR + 0.32), "trim")
    P("bump_rear").box((-hw + 0.03, -hl, CLEAR + 0.02), (hw - 0.03, -hl + 0.16, CLEAR + 0.32), "trim")
    if bonnet:
        P("bonnet").box((-hw + side, bonnet[0], belt), (hw - side, bonnet[1], belt + 0.04), body)
    if boot:
        P("boot").box((-hw + side, boot[0], belt), (hw - side, boot[1], belt + 0.04), body)
    wz0 = belt if c["shape"] != "cabover" else belt
    P("windscreen").box((-hw + 0.12, windscreen[1] - 0.04, wz0 + 0.02),
                        (hw - 0.12, windscreen[1], (H - 0.12) if c["shape"] in ("cabover", "tractor") else wz0 + 0.30),
                        "glass")
    for name, s, (y0, y1) in parts_doors:
        d = P(name)
        x0, x1 = sorted((s * hw, s * (hw - side)))
        top = belt + (0.45 if c["shape"] not in ("cabover", "tractor") else 0.55)
        d.box((x0, y0, CLEAR + 0.10), (x1, y1, belt), body)
        d.box((x0 + (0.005 if s < 0 else 0), y0 + 0.04, belt), (x1 - (0.005 if s > 0 else 0), y1 - 0.04, min(top, H - 0.12)),
              "glass")
    # lamps, on the body's front and rear faces (proud by 2 cm), in the chassis
    lamp_z = min(max(0.42 * H, CLEAR + 0.20), belt - 0.10)
    if c["shape"] == "tractor":          # the chassis's rear light bar carries the tail lamps
        lamp_z = 0.95
        ch.box((-hw, rear, 0.82), (hw, rear + 0.12, 1.08), "frame")
    lx = 0.62 * hw
    for s in (-1, 1):
        x = s * lx
        ch.box((x - 0.15, front, lamp_z - 0.06), (x + 0.15, front + 0.02, lamp_z + 0.06), "front.lamp.light")
        ch.box((x - 0.12, rear - 0.02, lamp_z - 0.01), (x + 0.12, rear, lamp_z + 0.11), "back.lamp.light")
        rx = s * max(0.15, lx * 0.55)
        ch.box((rx - 0.05, rear - 0.02, lamp_z - 0.01), (rx + 0.05, rear, lamp_z + 0.07), "back.lamp.reverse")
    # seats, so see-through glass does not show an empty box: a cushion and a backrest per seat marker
    for (x, y, z) in c["seats"]:
        ch.box((x - 0.22, y - 0.25, z - 0.25), (x + 0.22, y + 0.25, z), "interior")
        ch.box((x - 0.22, y - 0.33, z), (x + 0.22, y - 0.23, z + 0.55), "interior")
    # wheels
    for name, sx, sy in (("wheel_lf", -1, 1), ("wheel_rf", 1, 1), ("wheel_lb", -1, -1), ("wheel_rb", 1, -1)):
        P(name).cylinder(sx * (hw - tw / 2 - 0.01), sy * wb / 2, r, r, tw, "tyre")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    coll = bpy.context.scene.collection
    for p in parts.values():
        p.emit(coll)
    names = ["seat_front_l", "seat_front_r", "seat_rear_l", "seat_rear_r"]
    for n, (x, y, z) in zip(names, c["seats"]):
        e = bpy.data.objects.new(n, None)
        e.location = (x, y, z)
        e.empty_display_size = 0.2
        coll.objects.link(e)
    bpy.context.scene["placeholder_car"] = "generated by blender/tools/make_placeholder_cars.py; replace the parts, " \
                                           "keep their names and the seat Empties"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DIR, vid + ".blend"))
    print("[make_placeholder_cars] %s: %s, %d parts, %d seats" % (vid, c["shape"], len(parts), len(c["seats"])))


def generated(path):
    if not os.path.exists(path):
        return True
    bpy.ops.wm.open_mainfile(filepath=path)
    return "placeholder_car" in bpy.context.scene


def main():
    ids = [a for a in argv if not a.startswith("--")] or list(CARS)
    for vid in ids:
        path = os.path.join(DIR, vid + ".blend")
        if not FORCE and not generated(path):
            print("[make_placeholder_cars] %s: KEPT, %s was not written by this script (--force overwrites)" % (vid, path))
            continue
        build(vid, CARS[vid])


main()
