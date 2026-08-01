"""Headless generator: a scratch prototype .blend exercising RKA_OT_build_intersection (the
curb-corner + lane-turn-centerline builder -- road_blender_godot.md Kit geometry v2 item 4).
Builds one 4-way cross and one 3-way T side by side so the shapes can be opened, inspected, and
manually extended (more lanes, other presets/radii via the operator's F9 redo panel, or by
running "Build Intersection" again from the Road Kit panel) in a normal Blender session.

Run: blender --background --python tools/build_intersection_prototype.py

Writes kit/intersection_prototype.blend. Does NOT touch kit/lane_kit.blend -- a wholly separate
file. Imports the addon directly by path, no dependency on it being symlink-installed into
Blender's user addons directory.
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.realpath(__file__))
BLENDER_SRC = os.path.dirname(HERE)                              # blender
REPO_ROOT = os.path.dirname(BLENDER_SRC)                          # repo root
WORLD_SOURCE = os.path.join(REPO_ROOT, "assets", "world_source")  # data root
ADDONS_DIR = os.path.join(BLENDER_SRC, "addons")

bpy.ops.wm.read_factory_settings(use_empty=True)

if ADDONS_DIR not in sys.path:
    sys.path.insert(0, ADDONS_DIR)
import road_kit_authoring  # noqa: E402
road_kit_authoring.register()

KIT_DIR = os.path.join(WORLD_SOURCE, "kit")
DISTRICTS_DIR = os.path.join(
    REPO_ROOT, "src", "main", "resources", "com", "openworld", "world", "districts")
DEMO_GLTF = os.path.join(DISTRICTS_DIR, "District_intersectiondemo.glb")

bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
bpy.ops.rka.build_intersection(
    preset='4WAY', kerb_radius=9.0, lane_width=5.0, lanes=1,
    export_path=os.path.join(KIT_DIR, "intersection_prototype.4way.lanekit.json"),
    gltf_export_path=DEMO_GLTF)

bpy.context.scene.cursor.location = (80.0, 0.0, 0.0)
bpy.ops.rka.build_intersection(
    preset='3WAY_T', side_angle=90.0, kerb_radius=9.0, lane_width=5.0, lanes=1,
    export_path=os.path.join(KIT_DIR, "intersection_prototype.3way_t.lanekit.json"))

bpy.context.scene.cursor.location = (0.0, -80.0, 0.0)
bpy.ops.rka.build_intersection(
    preset='3WAY_Y', side_angle=120.0, kerb_radius=9.0, lane_width=5.0, lanes=1,
    export_path=os.path.join(KIT_DIR, "intersection_prototype.3way_y.lanekit.json"))

bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)

out_path = os.path.join(KIT_DIR, "intersection_prototype.blend")
bpy.ops.wm.save_as_mainfile(filepath=out_path)

for prefix in ("Intersection_4WAY", "Intersection_3WAY_T", "Intersection_3WAY_Y"):
    n = sum(len(c.objects) for c in bpy.data.collections if c.name.startswith(prefix))
    print("%s: %d object(s)" % (prefix, n))
print("Wrote %s" % out_path)
for name in ("intersection_prototype.4way.lanekit.json",
             "intersection_prototype.3way_t.lanekit.json",
             "intersection_prototype.3way_y.lanekit.json"):
    print("Wrote %s" % os.path.join(KIT_DIR, name))
print("Wrote %s" % DEMO_GLTF)
