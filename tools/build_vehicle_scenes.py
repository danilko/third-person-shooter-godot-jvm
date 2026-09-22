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
    "PIT1": {"name": "PIT-1", "mass": 1900, "rest": 0.45, "spring": 16000, "damping": 6500, "over": 0.25,
             "max_speed": 40.0, "accel": 13000.0, "crash_hp": 5.0, "health": 650, "paint": "car",
             # Vehicle.tscn has four seats and an inherited scene cannot delete one: a single-cab pickup's other two
             # ride in the BED (GTA's answer), sitting on its floor - measured flat at 0.855 m, 0.9-2.1 m aft.
             "extra_seats": [[-0.45, 0.855, 1.5], [0.45, 0.855, 1.5]]},
    "POC1": {"name": "POC-1", "mass": 1700, "rest": 0.38, "spring": 16000, "damping": 6000, "over": 0.2,
             "max_speed": 50.0, "accel": 12000.0, "crash_hp": 5.0, "health": 600, "paint": ""},
}
WHEELS = {"RR": "wheel_rb", "RL": "wheel_lb", "FR": "wheel_rf", "FL": "wheel_lf"}
SEAT_ORDER = ["seat_front_l", "seat_front_r", "seat_rear_l", "seat_rear_r"]   # Seat0 = the driver, left


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
    radius = d["wheels"]["wheel_lf"]["radius"]
    spring_eq = t["rest"] - t["mass"] * G / (4.0 * t["spring"])
    if spring_eq <= 0.02:
        raise SystemExit(f"{vid}: the spring bottoms out at rest (equilibrium {spring_eq:.3f} m): stiffen it")
    seats = [d["seats"][n] for n in SEAT_ORDER if n in d["seats"]] + t.get("extra_seats", [])
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
"""
    hull = ", ".join(f"{f(x)}, {f(y + MODEL_Y)}, {f(z)}" for x, y, z in d["hull"])
    nodes = [f"""[gd_scene format=3]

[ext_resource type="PackedScene" uid="uid://c7aoav51c2882" path="res://src/main/resources/com/openworld/vehicle/Vehicle.tscn" id="1_base"]
[ext_resource type="PackedScene" path="res://assets/vehicles/{vid}.glb" id="2_model"]
[ext_resource type="Script" path="res://src/main/java/com/openworld/carrier/vehicle/VehicleDamageModel.java" id="3_dm"]
[ext_resource type="Resource" path="res://src/main/resources/com/openworld/vehicle/{vid}Config.tres" id="4_cfg"]

[sub_resource type="ConvexPolygonShape3D" id="ConvexPolygonShape3D_hull"]
points = PackedVector3Array({hull})

; GENERATED by tools/build_vehicle_scenes.py from assets/vehicles/{vid}.vehicle.json - do not hand-edit.
[node name="{vid}" instance=ExtResource("1_base")]
mass = {f(t["mass"])}
vehicle_config = ExtResource("4_cfg")

[node name="Health" parent="."]
max_health = {f(t["health"])}

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
        cx, cy, cz = d["wheels"][mesh]["centre"]
        nodes.append(f'[node name="{k}" parent="Wheels"]\ntransform = {xform(cx, cy + MODEL_Y + spring_eq, cz)}\n'
                     f'model_mesh = "{mesh}"\n')
    nodes += [
        '[node name="CollisionShape3D" parent="."]\nshape = SubResource("ConvexPolygonShape3D_hull")\n',
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
