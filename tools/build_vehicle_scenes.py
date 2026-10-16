#!/usr/bin/env python3
"""Writes each component car's Godot scene from its MEASURED model facts.

    python3 tools/build_vehicle_scenes.py [ID ...]        (default: every row of TUNING)
    python3 tools/build_vehicle_scenes.py --check          (exit 1 if a scene is stale)

For each vehicle it reads `assets/vehicles/<ID>.vehicle.json` (written by blender/tools/build_vehicle.py) and writes
  src/main/resources/com/openworld/vehicle/<ID>.tscn        an INHERITED scene of Vehicle.tscn: the model, the
                                                              DamageModel, wheel mounts, hull, seats, mounts;
  src/main/resources/com/openworld/vehicle/<ID>Config.tres  its VehicleConfig: the prototype's handling with the
                                                              suspension fitted to the measured wheels.
Nothing in them is hand-placed, so a model edit is: build_vehicle.py, then this. Hand tuning goes in TUNING.

THE NUMBERS AND WHERE THEY COME FROM
  * the model hangs MODEL_Y under the body origin, so the body's centre of mass (Vehicle pins it 0.3 m under the
    origin) sits ~0.5 m off the ground, where a car's is;
  * a wheel's mount is its modelled centre plus the spring's EQUILIBRIUM length, rest - m g / (4 k): then the
    settled car puts every tyre on the ground inside its own arch (probe_component_car.gd measures it, 3 mm);
  * a seat marker is where a seated character's ORIGIN goes. In the DriveCarrier pose the hips sit HIP_ABOVE
    above it and HIP_BEHIND behind it (measured), so the marker hangs from the modelled cushion top so the hips
    land on the cushion, toward its back;
  * the hull is the model's measured convex hull.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "src", "main", "resources", "com", "openworld", "vehicle")
MODEL_Y = -0.8
LAMP_OUT = 0.62              # a lamp sits this fraction of the way from the centreline out to the flank
LAMP_UP = 0.42               # ... and this fraction of the body's height above the ground
HIP_ABOVE, HIP_BEHIND = 0.452, 0.259       # a seated character's pelvis relative to its origin (seat marker)
HIP_ON_CUSHION = 0.08                      # the pelvis sits this far above the cushion surface
HIP_BACK_OF_CENTRE = 0.15                  # …and this far behind the cushion's centre, toward the backrest
G = 9.8

# Per-vehicle tuning: mass (kg), suspension, power. The rest of the handling is the prototype's (Vehicle.tscn).
TUNING = {
    "SPC1": {"name": "SPC-1", "mass": 1300, "rest": 0.35, "spring": 14000, "damping": 5000, "over": 0.2,
             "max_speed": 55.0, "accel": 10000.0, "crash_hp": 6.0, "health": 500, "paint": "car",
             # a low coupe: a deep bucket seat so the tallest body's head clears the roof (measured by
             # probe_component_car: Fumiriya's crown 0.006 m through the roof on the plain seat)
             "seat_drop": 0.07},
    # The Japanese traffic set (2026-09-28), all PLACEHOLDER block models from blender/tools/make_placeholder_cars.py.
    # Kei class tops out near 140 km/h; the truck is governed. A two-seat cab's other two seats ride on the load
    # (Vehicle.tscn has four and an inherited scene cannot delete one), in Godot model space.
    "KET1": {"name": "KET-1", "mass": 750, "rest": 0.30, "spring": 9000, "damping": 3200, "over": 0.2,
             "max_speed": 33.0, "accel": 6000.0, "crash_hp": 6.0, "health": 380, "paint": "car",
             "extra_seats": [[-0.40, 0.65, 0.90], [0.40, 0.65, 0.90]]},
    "MPC1": {"name": "MPC-1", "mass": 820, "rest": 0.30, "spring": 9500, "damping": 3400, "over": 0.2,
             "max_speed": 38.0, "accel": 6500.0, "crash_hp": 6.0, "health": 420, "paint": ""},
    "POC1": {"name": "POC-1", "mass": 1700, "rest": 0.38, "spring": 16000, "damping": 6000, "over": 0.2,
             "max_speed": 50.0, "accel": 12000.0, "crash_hp": 5.0, "health": 600, "paint": ""},
    "CLC1": {"name": "CLC-1", "mass": 950, "rest": 0.32, "spring": 11000, "damping": 4000, "over": 0.2,
             "max_speed": 50.0, "accel": 9500.0, "crash_hp": 6.0, "health": 450, "paint": "car"},
    "KEC1": {"name": "KEC-1", "mass": 950, "rest": 0.30, "spring": 10000, "damping": 3600, "over": 0.2,
             "max_speed": 38.0, "accel": 7000.0, "crash_hp": 6.0, "health": 420, "paint": "car"},
    "TAX1": {"name": "TAX-1", "mass": 1450, "rest": 0.36, "spring": 14000, "damping": 5200, "over": 0.2,
             "max_speed": 45.0, "accel": 10500.0, "crash_hp": 5.0, "health": 550, "paint": ""},
    "CRT1": {"name": "CRT-1", "mass": 7500, "rest": 0.45, "spring": 60000, "damping": 22000, "over": 0.25,
             "max_speed": 25.0, "accel": 45000.0, "crash_hp": 3.0, "health": 1500, "paint": "",
             "extra_seats": [[-0.50, 3.10, 1.50], [0.50, 3.10, 1.50]]},
    # the emergency vehicles of the mission buildings (user, 2026-09-28): placeholder blocks, real sizes and weights
    "AMB1": {"name": "AMB-1", "mass": 3200, "rest": 0.40, "spring": 28000, "damping": 10000, "over": 0.2,
             "max_speed": 38.0, "accel": 20000.0, "crash_hp": 4.0, "health": 900, "paint": ""},
    "FIE1": {"name": "FIE-1", "mass": 7000, "rest": 0.45, "spring": 56000, "damping": 20000, "over": 0.25,
             "max_speed": 30.0, "accel": 42000.0, "crash_hp": 3.0, "health": 1400, "paint": "",
             "extra_seats": [[-0.45, 1.55, 1.30], [0.45, 1.55, 1.30]]},
    # the post offices' vans (user, 2026-10-03): a kei van and a 2 t box truck, Japan Post red
    "POV1": {"name": "POV-1", "mass": 1000, "rest": 0.30, "spring": 10500, "damping": 3800, "over": 0.2,
             "max_speed": 36.0, "accel": 7200.0, "crash_hp": 6.0, "health": 450, "paint": "",
             "extra_seats": [[-0.34, -0.55, 0.72], [0.34, -0.55, 0.72]]},
    "POT1": {"name": "POT-1", "mass": 3500, "rest": 0.40, "spring": 30000, "damping": 11000, "over": 0.22,
             "max_speed": 32.0, "accel": 22000.0, "crash_hp": 4.0, "health": 950, "paint": "",
             "extra_seats": [[-0.42, 1.10, 1.05], [0.42, 1.10, 1.05]]},
    # a container truck: tractor + 20 ft chassis made rigid, loaded (user, 2026-09-29); governed like the crate truck
    "COT1": {"name": "COT-1", "mass": 16000, "rest": 0.50, "spring": 120000, "damping": 44000, "over": 0.25,
             "max_speed": 24.0, "accel": 85000.0, "crash_hp": 2.5, "health": 2200, "paint": "car",
             "extra_seats": [[-0.50, 3.85, 1.00], [0.50, 3.85, 1.00]]},
    # the logistics hub's box truck (user, 2026-10-05): a 4 t cab-over, governed like the crate truck
    "BOT1": {"name": "BOT-1", "mass": 8000, "rest": 0.45, "spring": 62000, "damping": 23000, "over": 0.25,
             "max_speed": 27.0, "accel": 46000.0, "crash_hp": 3.0, "health": 1500, "paint": "",
             "extra_seats": [[-0.50, 3.15, 1.50], [0.50, 3.15, 1.50]]},
    # the enforcement escalation's armour (user, 2026-10-06, PLAN.md W6): heavy, slow, very tough; a car hit by one
    # loses. Masses are the real vehicles' (riot vehicle ~12 t, Type 16 ~26 t, Type 10 ~44 t) and the springs scale
    "ARV1": {"name": "ARV-1", "mass": 12000, "rest": 0.50, "spring": 95000, "damping": 34000, "over": 0.25,
             "max_speed": 28.0, "accel": 80000.0, "crash_hp": 1.5, "health": 1600, "paint": "",
             "hit_mult": 0.4, "blast_mult": 2.5},
    "LTK1": {"name": "LTK-1", "mass": 26000, "rest": 0.55, "spring": 210000, "damping": 72000, "over": 0.25,
             "max_speed": 27.0, "accel": 170000.0, "crash_hp": 0.6, "health": 2400, "paint": "",
             "hit_mult": 0.3, "blast_mult": 2.5,
             "extra_seats": [[-0.60, 0.60, 1.20], [0.60, 0.60, 1.20]]},
    "TNK1": {"name": "TNK-1", "mass": 44000, "rest": 0.45, "spring": 360000, "damping": 125000, "over": 0.25,
             "max_speed": 19.0, "accel": 260000.0, "crash_hp": 0.3, "health": 3200, "paint": "",
             "hit_mult": 0.25, "blast_mult": 2.5,
             "extra_seats": [[-0.60, 0.70, 0.95], [0.60, 0.70, 0.95]]},
    "LAT1": {"name": "LAT-1", "mass": 13000, "rest": 0.48, "spring": 100000, "damping": 36000, "over": 0.25,
             "max_speed": 24.0, "accel": 70000.0, "crash_hp": 2.5, "health": 2000, "paint": "",
             "extra_seats": [[-0.50, 3.10, 1.55], [0.50, 3.10, 1.55]]},
    # MOTORCYCLES (PLAN.md 3.1b / 2c.7, the bike set of 2026-10-15): placeholder blocks from
    # blender/tools/make_placeholder_bikes.py, real masses. `bike` = the Motorcycle script, four rays BIKE_TRACK either
    # side of the two wheels (the model keeps its own wheels: Motorcycle.java), `lean` its most lean (deg), `aero` its
    # drag (a bike's frontal area is about half a car's), `rider` the rider's pose bent from the car's seated clip
# (character.RiderPoseModifier: lean forward, thighs up / feet back, extra knee bend, deg -- 0s = the scooter's
# feet-forward floorboard). MY PICKS, unreviewed: every speed, force, lean and pose below.
    "SCT1": {"name": "SCT-1", "mass": 90, "rest": 0.16, "spring": 4200, "damping": 700, "over": 0.12,
             "max_speed": 17.0, "accel": 420.0, "crash_hp": 8.0, "health": 160, "paint": "car",
             "bike": True, "lean": 35.0, "aero": 0.25, "steer": 30.0, "rider": [0.0, 0.0, 0.0]},
    "POB1": {"name": "POB-1", "mass": 100, "rest": 0.16, "spring": 4600, "damping": 760, "over": 0.12,
             "max_speed": 24.0, "accel": 520.0, "crash_hp": 8.0, "health": 180, "paint": "",
             "bike": True, "lean": 35.0, "aero": 0.25, "steer": 30.0, "rider": [6.0, 22.0, 25.0]},
    "TRB1": {"name": "TRB-1", "mass": 135, "rest": 0.22, "spring": 5200, "damping": 900, "over": 0.15,
             "max_speed": 36.0, "accel": 980.0, "crash_hp": 7.0, "health": 200, "paint": "car",
             "bike": True, "lean": 42.0, "aero": 0.22, "steer": 28.0, "rider": [10.0, 25.0, 30.0]},
    "SSB1": {"name": "SSB-1", "mass": 200, "rest": 0.18, "spring": 7600, "damping": 1250, "over": 0.12,
             "max_speed": 72.0, "accel": 2300.0, "crash_hp": 7.0, "health": 220, "paint": "car",
             "bike": True, "lean": 50.0, "aero": 0.20, "steer": 24.0, "rider": [45.0, 35.0, 45.0]},
    "PMB1": {"name": "PMB-1", "mass": 280, "rest": 0.18, "spring": 10000, "damping": 1700, "over": 0.12,
             "max_speed": 55.0, "accel": 2400.0, "crash_hp": 6.0, "health": 300, "paint": "",
             "bike": True, "lean": 42.0, "aero": 0.26, "steer": 26.0, "rider": [6.0, 22.0, 25.0]},
}
WHEELS = {"RR": "wheel_rb", "RL": "wheel_lb", "FR": "wheel_rf", "FL": "wheel_lf"}
# a motorcycle's four rays: each axle's pair stands BIKE_TRACK either side of its one wheel, inside the tyre's
# footprint plus a hand's width -- wide enough to stand, narrow enough that a kerb meets both rays of an axle together
BIKE_TRACK = 0.16
BIKE_WHEELS = {"RR": ("wheel_b", 1), "RL": ("wheel_b", -1), "FR": ("wheel_f", 1), "FL": ("wheel_f", -1)}
BIKE_SEATS = ["seat_front_l", "seat_rear_l"]
MOTORCYCLE = "res://src/main/java/com/openworld/carrier/motorcycle/Motorcycle.java"
SEAT_ORDER = ["seat_front_l", "seat_front_r", "seat_rear_l", "seat_rear_r"]   # Seat0 = the driver, left


# ARMOUR (user 2026-10-07: "these vehicles cannot be shot down"): a row may set the damage kinds on its Health --
# `hit_mult` (bullets, pellets, melee) and `blast_mult` (explosions); unset keeps Vehicle.tscn's 0.4 / 2.5. GTA's
# early-GTA shape (user 2026-10-07): ONE damage rule, so a rifle hurts a tank too, it just takes many rounds
# (ARV-1 2 rockets / 200 ASR1 rounds, LTK-1 3 / 400, TNK-1 4 / 640, at ATL1's 320 and ASR1's 20).
def health_mults(t):
    out = ""
    if "hit_mult" in t:
        out += "\nhit_damage_multiplier = %s" % f(t["hit_mult"])
    if "blast_mult" in t:
        out += "\nexplosion_damage_multiplier = %s" % f(t["blast_mult"])
    return out


def f(x):
    """A float literal that stays a FLOAT: godot-jvm refuses an int literal (`14000`) for a float property ("JVM
    expected a DOUBLE but received a LONG") and silently keeps the default, so the decimal point is always kept."""
    s = f"{float(x):.4f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def xform(x, y, z):
    return f"Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {f(x)}, {f(y)}, {f(z)})"


def build(vid):
    t = TUNING[vid]
    d = json.load(open(os.path.join(ROOT, "assets", "vehicles", vid + ".vehicle.json")))
    lo, hi = d["bounds"]["min"], d["bounds"]["max"]
    bike = t.get("bike", False)
    radius = d["wheels"]["wheel_b" if bike else "wheel_lf"]["radius"]
    spring_eq = t["rest"] - t["mass"] * G / (4.0 * t["spring"])
    if spring_eq <= 0.02:
        raise SystemExit(f"{vid}: the spring bottoms out at rest (equilibrium {spring_eq:.3f} m): stiffen it")
    seats = [d["seats"][n] for n in SEAT_ORDER if n in d["seats"]] + t.get("extra_seats", [])
    seat_limit = 0
    if bike:
        # the real seats (the rider, a pillion if the model has one); the rest of Vehicle.tscn's four sit on the
        # rider's and are cut by VehicleConfig.seatLimit
        seats = [d["seats"][n] for n in BIKE_SEATS if n in d["seats"]]
        seat_limit = len(seats)
        seats += [seats[0]] * (4 - len(seats))
    if len(seats) != 4:
        raise SystemExit(f"{vid}: {len(seats)} seats; Vehicle.tscn has 4 and an inherited scene cannot remove one - "
                         f"add extra_seats to its TUNING row")
    front_z, top_y = lo[2], hi[1] + MODEL_Y
    # LAMPS, derived (never hand-placed): the front/rear face of the measured bounds, LAMP_OUT of the way out
    # to the flank, at LAMP_UP of the body's height. Body space, so MODEL_Y applies; the left lamp is the
    # mirror of the right, which is why only one is written.
    lamp_x = LAMP_OUT * max(-lo[0], hi[0])
    lamp_y = LAMP_UP * hi[1] + MODEL_Y
    head = (lamp_x, lamp_y, lo[2])
    tail = (lamp_x, lamp_y + 0.05, hi[2])
    # a model that AUTHORS its lamps (faces wearing front.lamp.light / back.lamp.light, measured by build_vehicle.py)
    # puts the lights where those lamps are instead
    lamps = d.get("lamps", {})
    if "head" in lamps:
        head = (lamps["head"][0], lamps["head"][1] + MODEL_Y, lamps["head"][2])
    if "tail" in lamps:
        tail = (lamps["tail"][0], lamps["tail"][1] + MODEL_Y, lamps["tail"][2])

    cfg = f"""[gd_resource type="Resource" script_class="VehicleConfig" format=3]

[ext_resource type="Script" path="res://src/main/java/com/openworld/carrier/vehicle/VehicleConfig.java" id="1_cfg"]
[ext_resource type="Curve" uid="uid://cvaccel240crv" path="res://src/main/resources/com/openworld/vehicle/VehicleAccelCurve.tres" id="2_accel"]
[ext_resource type="PackedScene" uid="uid://cvhwreck1a1b" path="res://src/main/resources/com/openworld/vehicle/VehicleWreck.tscn" id="3_wreck"]
[ext_resource type="PackedScene" path="res://assets/vfx/explosion/effects/burst/vfx_burst_explosion_01.tscn" id="4_blast"]

; GENERATED by tools/build_vehicle_scenes.py from assets/vehicles/{vid}.vehicle.json - edit TUNING there, not this.
[resource]
script = ExtResource("1_cfg")
wheel_radius = {f(radius)}
rest_distance = {f(t["rest"])}
over_extend = {f(t["over"])}
spring_strength = {f(t["spring"])}
spring_damping = {f(t["damping"])}
suspension_samples = 3
max_speed = {f(t["max_speed"])}
acceleration = {f(t["accel"])}
z_traction = 0.02
acceleration_curve = ExtResource("2_accel")
hull_half_width = {f(max(-lo[0], hi[0]))}
hull_half_length = {f(max(-lo[2], hi[2]))}
crash_health_per_dv = {f(t["crash_hp"])}
wreck_scene = ExtResource("3_wreck")
explosion_vfx = ExtResource("4_blast")
headlight_offset = Vector3({f(head[0])}, {f(head[1])}, {f(head[2])})
taillight_offset = Vector3({f(tail[0])}, {f(tail[1])}, {f(tail[2])})
seat_drop = {f(t.get("seat_drop", 0.0))}
glass_armor = {f(t.get("glass_armor", 0.0))}
"""
    if bike:
        cfg += f"""seat_limit = {seat_limit}
motorcycle_lean_degrees = {f(t["lean"])}
aero_drag_coefficient = {f(t["aero"])}
tire_max_turn_degrees = {f(t["steer"])}
rider_lean_forward = {f(t.get("rider", [0, 0, 0])[0])}
rider_thigh_raise = {f(t.get("rider", [0, 0, 0])[1])}
rider_knee_bend = {f(t.get("rider", [0, 0, 0])[2])}
"""
    bike_script = '\nscript = ExtResource("5_moto")' if bike else ""
    # a bike's get-on box hugs the bike: Vehicle.tscn's 4 x 7 m one would catch the next bike along a parked row
    entrance_res = (f'\n[sub_resource type="BoxShape3D" id="BoxShape3D_bike_entrance"]\n'
                    f'size = Vector3(2.4, 2.5, {f(hi[2] - lo[2] + 1.4)})\n') if bike else ""
    hull = ", ".join(f"{f(x)}, {f(y + MODEL_Y)}, {f(z)}" for x, y, z in d["hull"])
    nodes = [f"""[gd_scene format=3]

[ext_resource type="PackedScene" uid="uid://c7aoav51c2882" path="res://src/main/resources/com/openworld/vehicle/Vehicle.tscn" id="1_base"]
[ext_resource type="PackedScene" path="res://assets/vehicles/{vid}.glb" id="2_model"]
[ext_resource type="Script" path="res://src/main/java/com/openworld/carrier/vehicle/VehicleDamageModel.java" id="3_dm"]
[ext_resource type="Resource" path="res://src/main/resources/com/openworld/vehicle/{vid}Config.tres" id="4_cfg"]
{'[ext_resource type="Script" path="' + MOTORCYCLE + '" id="5_moto"]' + chr(10) if bike else ""}
[sub_resource type="ConvexPolygonShape3D" id="ConvexPolygonShape3D_hull"]
points = PackedVector3Array({hull})
{entrance_res}
; GENERATED by tools/build_vehicle_scenes.py from assets/vehicles/{vid}.vehicle.json - do not hand-edit.
[node name="{vid}" instance=ExtResource("1_base")]{bike_script}
mass = {f(t["mass"])}
vehicle_config = ExtResource("4_cfg")

[node name="Health" parent="."]
max_health = {f(t["health"])}{health_mults(t)}

[node name="Model" parent="." instance=ExtResource("2_model")]
transform = {xform(0, MODEL_Y, 0)}

[node name="DamageModel" type="Node" parent="."]
script = ExtResource("3_dm")
paint_material = "{t["paint"]}"
"""]
    for i, (x, y, z) in enumerate(seats):
        mx, my, mz = x, y + MODEL_Y + HIP_ON_CUSHION - HIP_ABOVE, z + HIP_BACK_OF_CENTRE - HIP_BEHIND
        if i == 0:
            nodes.append(f'[node name="DriverSeat" parent="."]\ntransform = {xform(mx, my, mz)}\n')
        nodes.append(f'[node name="Seat{i}" parent="Seats"]\ntransform = {xform(mx, my, mz)}\n')
    for k, mesh in WHEELS.items():
        if bike:
            src, side = BIKE_WHEELS[k]
            cx, cy, cz = d["wheels"][src]["centre"]
            nodes.append(f'[node name="{k}" parent="Wheels"]\n'
                         f'transform = {xform(cx + side * BIKE_TRACK, cy + MODEL_Y + spring_eq, cz)}\n')
            continue
        cx, cy, cz = d["wheels"][mesh]["centre"]
        nodes.append(f'[node name="{k}" parent="Wheels"]\ntransform = {xform(cx, cy + MODEL_Y + spring_eq, cz)}\n'
                     f'model_mesh = "{mesh}"\n')
    nodes += [
        '[node name="CollisionShape3D" parent="."]\nshape = SubResource("ConvexPolygonShape3D_hull")\n',
        *(['[node name="EntranceShape" parent="EntranceArea"]\nshape = SubResource("BoxShape3D_bike_entrance")\n']
          if bike else []),
        f'[node name="FPSCameraMount" parent="."]\ntransform = {xform(0, top_y - 0.35, front_z * 0.4)}\n',
        f'[node name="VehicleWeaponMount" parent="."]\ntransform = {xform(0, -0.2, front_z + 0.2)}\n',
        f'[node name="ObstacleRay" parent="."]\ntransform = {xform(0, -0.45, front_z - 0.1)}\n',
        f'[node name="Nameplate" parent="."]\ntransform = {xform(0, top_y + 0.4, 0)}\n',
        f'[node name="DamageVfx" parent="."]\ntransform = {xform(0, top_y - 0.6, front_z * 0.7)}\n',
    ]
    return cfg, "\n".join(nodes)


def main():
    args = sys.argv[1:]
    check = "--check" in args
    ids = [a for a in args if not a.startswith("--")] or list(TUNING)
    stale = []
    for vid in ids:
        cfg, scene = build(vid)
        for path, text in ((os.path.join(RES, vid + "Config.tres"), cfg), (os.path.join(RES, vid + ".tscn"), scene)):
            old = open(path).read() if os.path.exists(path) else None
            if old != text:
                stale.append(os.path.relpath(path, ROOT))
                if not check:
                    open(path, "w").write(text)
    if check and stale:
        print("stale (run tools/build_vehicle_scenes.py):", *stale, sep="\n  ")
        sys.exit(1)
    print(("up to date" if check else "wrote") + ": " + (", ".join(stale) if stale else "nothing changed"))


if __name__ == "__main__":
    main()
