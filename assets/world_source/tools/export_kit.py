#!/usr/bin/env python3
"""
export_kit.py — export every kit leaf (visual + its -colonly proxy) to one .glb each.

This is the game's per-asset library: each leaf becomes export/<Name>.glb, with the
`-colonly` box riding along so Godot's importer builds the CollisionShape3D. Every
placement in Godot is then an instance of one of these files (per BLENDER_CONVENTIONS).

RUN per kit:
  blender --background <kit>.blend --python tools/export_kit.py -- <COLL>
"""
import bpy, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "lib"))
import kit_common as kc

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
coll_name = argv[0] if argv else None
EXPORT = os.path.join(ROOT, "export")
os.makedirs(EXPORT, exist_ok=True)

coll = bpy.data.collections.get(coll_name)
n = 0
for o in list(coll.objects):
    if o.name.endswith("-colonly"):
        continue
    proxy = bpy.data.objects.get(o.name + "-colonly")
    objs = [o] + ([proxy] if proxy else [])
    kc.export_gltf(objs, os.path.join(EXPORT, o.name + ".glb"))
    n += 1
print("EXPORTED %d leaves from %s -> export/" % (n, coll_name))
