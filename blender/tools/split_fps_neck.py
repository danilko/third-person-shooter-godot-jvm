"""Split the collar out of the body mesh so first person can hide it (W36).

    blender -b assets/characters/godot_chan/merged_animation.blend --python-exit-code 1 \\
        --python blender/tools/split_fps_neck.py -- [--save]

In first person the camera sits inside the head, and `MeshConfig.headMeshPaths` hides the head, hair,
eyes and headphones -- but the COLLAR is part of `armor`, the whole-body mesh, and read as a dark
wedge at the bottom of the view in every frame (worst mid weapon-switch, with no weapon in view to
distract from it). Faces whose vertices are mostly driven by `neck_01` / `head` move to their own
mesh, `armor_neck` -- same material, same armature, same weights -- which the visuals scene lists
among the head meshes. Idempotent: a file that already has `armor_neck` is left alone.
"""
import bpy
import bmesh
import sys

NECK = {"neck_01", "head"}
SRC, DST = "armor", "armor_neck"


def main():
    save = "--save" in sys.argv
    if DST in bpy.data.objects:
        print(f"[split_fps_neck] {DST} already exists")
        return
    o = bpy.data.objects[SRC]
    names = {g.index: g.name for g in o.vertex_groups}
    neck_v = set()
    for v in o.data.vertices:
        if v.groups:
            g = max(v.groups, key=lambda x: x.weight)
            if names.get(g.group) in NECK:
                neck_v.add(v.index)
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(o.data)
    for f in bm.faces:
        n = sum(1 for v in f.verts if v.index in neck_v)
        f.select = n * 2 > len(f.verts)
    picked = sum(1 for f in bm.faces if f.select)
    bmesh.update_edit_mesh(o.data)
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    new = [ob for ob in bpy.context.selected_objects if ob != o][0]
    new.name = DST
    new.data.name = DST
    print(f"[split_fps_neck] moved {picked} faces ({len(new.data.vertices)} verts) from {SRC} to {DST}")
    if save:
        bpy.ops.wm.save_mainfile()


main()
