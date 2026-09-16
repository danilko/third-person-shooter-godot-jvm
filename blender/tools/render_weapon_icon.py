"""Render a weapon icon: white silhouette, side view, muzzle right (PLAN.md 2.7 piece 7).

  blender --background assets/weapons/<ID>.blend --python-exit-code 1 --python blender/tools/render_weapon_icon.py -- <raw.png> <ID>

then fit the raw render into the 411x139 icon frame the other icons use (white, alpha from the render):
  python3 blender/tools/render_weapon_icon.py --fit <raw.png> assets/ui/<ID>.png
"""
import sys

if "--fit" in sys.argv:
    from PIL import Image
    raw, dst = sys.argv[sys.argv.index("--fit") + 1:sys.argv.index("--fit") + 3]
    im = Image.open(raw).convert("RGBA")
    crop = im.crop(im.getbbox())
    s = min(367 / crop.size[0], 127 / crop.size[1])   # AR4.png's silhouette box inside 411x139
    crop = crop.resize((max(1, int(crop.size[0] * s)), max(1, int(crop.size[1] * s))), Image.LANCZOS)
    white = Image.new("RGBA", crop.size, (255, 255, 255, 255))
    white.putalpha(crop.split()[3])
    out = Image.new("RGBA", (411, 139), (0, 0, 0, 0))
    out.paste(white, ((411 - crop.size[0]) // 2, (139 - crop.size[1]) // 2), white)
    out.save(dst)
    print("wrote", dst)
    sys.exit(0)

import bpy, mathutils
out = sys.argv[sys.argv.index("--")+1]
wid = sys.argv[sys.argv.index("--")+2]
scn = bpy.context.scene
col = bpy.data.collections.get(wid)
objs = [o for o in col.all_objects if o.type == 'MESH']
mn = mathutils.Vector((1e9,)*3); mx = mathutils.Vector((-1e9,)*3)
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
for o in bpy.data.objects:
    if o.type in ('MESH','CURVE') and o not in objs: o.hide_render = True
ctr = (mn + mx) / 2
cam_data = bpy.data.cameras.new("icon_cam"); cam_data.type = 'ORTHO'
L = mx.y - mn.y; H = mx.z - mn.z
cam_data.ortho_scale = max(L, H * 411/139) * 1.06
cam = bpy.data.objects.new("icon_cam", cam_data); scn.collection.objects.link(cam)
cam.location = (mx.x + 5, ctr.y, ctr.z)
dirv = mathutils.Vector((-1, 0, 0))
cam.rotation_euler = dirv.to_track_quat('-Z', 'Y').to_euler()
scn.camera = cam
scn.render.engine = 'BLENDER_WORKBENCH'
scn.display.shading.light = 'FLAT'
scn.display.shading.color_type = 'SINGLE'
scn.display.shading.single_color = (1, 1, 1)
scn.display.shading.show_object_outline = False
scn.render.film_transparent = True
scn.render.resolution_x = 1644; scn.render.resolution_y = 556; scn.render.resolution_percentage = 100
scn.render.image_settings.file_format = 'PNG'; scn.render.image_settings.color_mode = 'RGBA'
scn.render.filepath = out
bpy.ops.render.render(write_still=True)
print("rendered", out, "len", L, "height", H)
