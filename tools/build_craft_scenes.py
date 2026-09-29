#!/usr/bin/env python3
"""Writes the placeholder AIRCRAFT and BOATS' Godot scenes (user, 2026-09-28) from their model facts.

    python3 tools/build_craft_scenes.py [ID ...]      (default: every row of TUNING)
    python3 tools/build_craft_scenes.py --check       (exit 1 if a scene is stale)

For each craft it reads `assets/vehicles/<ID>.craft.json` (seats and the cockpit eye, written by
blender/tools/make_placeholder_craft.py) and writes src/main/resources/com/openworld/vehicle/<ID>.tscn: an INHERITED
scene of the flyable `Airplane.tscn` or the drivable `Boat.tscn` whose prototype box is hidden under the model, its
collision box, entrance, seats and cockpit camera fitted, and its VehicleConfig scaled to its size:

  * an aircraft's lift balances its weight at its take-off speed (Airplane.java: lift = liftCoefficient * v^2, capped
    at 1.3 x weight), its thrust gives it ~12-15 m/s^2, and its pitch / roll torques follow its box's inertia;
  * a boat floats with its four buoyancy corners (Boat.java) ~0.4 m deep (4 x buoyancyStrength x depth = weight), and
    its thrust and rudder follow its mass.
The numbers are PLACEHOLDER tuning, stated per row; nothing in a scene is hand-placed.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "src", "main", "resources", "com", "openworld", "vehicle")
G = 9.8

TUNING = {
    # base, mass (kg), health, collision box (x, y, z) m, entrance box, config fields, camera spring length (m)
    "FIJ1": dict(base="Airplane", name="FIJ-1 fighter", mass=12000.0, health=900.0, box=(1.6, 1.8, 15.0),
                 entrance=(7.0, 4.0, 17.0), spring=24.0,
                 cfg=dict(max_speed=140.0, acceleration=170000.0, lift_coefficient=42.0, pitch_torque=700000.0,
                          roll_torque=130000.0, upright_torque=360000.0, airborne_angular_damp=1.2,
                          grounded_angular_damp=1.5)),
    "LIP1": dict(base="Airplane", name="LIP-1 light plane", mass=1100.0, health=300.0, box=(1.1, 1.2, 7.2),
                 entrance=(5.0, 3.0, 8.0), spring=13.0,
                 cfg=dict(max_speed=60.0, acceleration=16000.0, lift_coefficient=10.0, pitch_torque=12000.0,
                          roll_torque=7000.0, upright_torque=4000.0, airborne_angular_damp=1.2,
                          grounded_angular_damp=1.5)),
    "WOB1": dict(base="Boat", name="WOB-1 work boat", mass=9000.0, health=1200.0, box=(4.2, 1.5, 12.0),
                 entrance=(7.0, 4.0, 14.0), spring=16.0,
                 cfg=dict(max_speed=10.0, acceleration=60000.0, hull_half_width=2.0, hull_half_length=5.8,
                          buoyancy_strength=55000.0, buoyancy_damping=14000.0, water_drag=1.0,
                          rudder_torque=180000.0, upright_torque=60000.0, downforce_coefficient=0.0,
                          grounded_angular_damp=2.5)),
    "FIB1": dict(base="Boat", name="FIB-1 fishing boat", mass=5000.0, health=700.0, box=(2.9, 1.2, 10.4),
                 entrance=(5.5, 3.5, 12.0), spring=14.0,
                 cfg=dict(max_speed=14.0, acceleration=45000.0, hull_half_width=1.4, hull_half_length=5.0,
                          buoyancy_strength=32000.0, buoyancy_damping=8000.0, water_drag=1.0,
                          rudder_torque=90000.0, upright_torque=30000.0, downforce_coefficient=0.0,
                          grounded_angular_damp=2.5)),
}
HIDE = {"Airplane": ["BodyMesh/Fuselage", "BodyMesh/Wing", "BodyMesh/Tail"], "Boat": ["BodyMesh/Hull"]}
SEATS = {"Airplane": 2, "Boat": 4}


def f(v):
    return "%.4f" % v


def build(cid):
    t = TUNING[cid]
    facts = json.load(open(os.path.join(ROOT, "assets", "vehicles", cid + ".craft.json")))
    base = t["base"]
    seats = facts["seats"]
    if len(seats) < SEATS[base]:
        raise SystemExit("%s: %d seats; %s.tscn has %d and an inherited scene cannot remove one" % (
            cid, len(seats), base, SEATS[base]))
    L = ["[gd_scene format=3]", "",
         '[ext_resource type="PackedScene" path="res://src/main/resources/com/openworld/vehicle/%s.tscn" id="1_base"]' % base,
         '[ext_resource type="PackedScene" path="res://assets/vehicles/%s.glb" id="2_model"]' % cid,
         '[ext_resource type="Script" path="res://src/main/java/com/openworld/carrier/vehicle/VehicleConfig.java" id="3_cfg"]',
         '[ext_resource type="Script" path="res://src/main/java/com/openworld/character/CharacterInfo.java" id="4_ci"]',
         '[ext_resource type="PackedScene" path="res://src/main/resources/com/openworld/vehicle/VehicleWreck.tscn" id="5_wreck"]',
         '[ext_resource type="PackedScene" path="res://assets/vfx/explosion/effects/burst/vfx_burst_explosion_01.tscn" id="6_fx"]',
         "", '[sub_resource type="Resource" id="Resource_ci"]', 'script = ExtResource("4_ci")',
         'display_name = "%s"' % t["name"], "", '[sub_resource type="Resource" id="Resource_cfg"]',
         'script = ExtResource("3_cfg")']
    for k, v in t["cfg"].items():
        L.append("%s = %s" % (k, f(v)))
    L += ['wreck_scene = ExtResource("5_wreck")', 'explosion_vfx = ExtResource("6_fx")', "",
          '[sub_resource type="BoxShape3D" id="BoxShape3D_body"]', "size = Vector3(%s, %s, %s)" % tuple(map(f, t["box"])),
          "", '[sub_resource type="BoxShape3D" id="BoxShape3D_entrance"]',
          "size = Vector3(%s, %s, %s)" % tuple(map(f, t["entrance"])), "",
          "; GENERATED by tools/build_craft_scenes.py from assets/vehicles/%s.craft.json - do not hand-edit." % cid,
          '[node name="%s" instance=ExtResource("1_base")]' % cid, "mass = %s" % f(t["mass"]),
          'character_info = SubResource("Resource_ci")', 'vehicle_config = SubResource("Resource_cfg")', "",
          '[node name="Health" parent="."]', "max_health = %s" % f(t["health"]), ""]
    for path in HIDE[base]:
        parent, name = path.rsplit("/", 1)
        L += ['[node name="%s" parent="%s"]' % (name, parent), "visible = false", ""]
    L += ['[node name="Model" parent="." instance=ExtResource("2_model")]', ""]
    for i in range(SEATS[base]):
        x, y, z = seats[i]
        L += ['[node name="Seat%d" parent="Seats"]' % i,
              "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %s, %s, %s)" % (f(x), f(y), f(z)), ""]
    L += ['[node name="CollisionShape3D" parent="."]', 'shape = SubResource("BoxShape3D_body")', "",
          '[node name="EntranceShape" parent="EntranceArea"]', 'shape = SubResource("BoxShape3D_entrance")', ""]
    ex, ey, ez = facts["eye"]
    L += ['[node name="FPSCameraMount" parent="."]',
          "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %s, %s, %s)" % (f(ex), f(ey), f(ez)), "",
          '[node name="SpringArm" parent="CameraController/Yaw/Pitch/Pivot"]', "spring_length = %s" % f(t["spring"]), ""]
    return "\n".join(L)


def main():
    args = sys.argv[1:]
    check = "--check" in args
    stale = []
    for cid in [a for a in args if not a.startswith("--")] or list(TUNING):
        text = build(cid)
        path = os.path.join(RES, cid + ".tscn")
        old = open(path).read() if os.path.exists(path) else None
        if old != text:
            stale.append(os.path.relpath(path, ROOT))
            if not check:
                open(path, "w").write(text)
    if check and stale:
        print("stale (run tools/build_craft_scenes.py):", *stale, sep="\n  ")
        sys.exit(1)
    print(("up to date" if check else "wrote") + ": " + (", ".join(stale) if stale else "nothing changed"))


if __name__ == "__main__":
    main()
