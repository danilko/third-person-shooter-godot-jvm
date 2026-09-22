"""Blender half of the toon parity gate (PLAN.md 6.10). Headless EEVEE, no display needed.

    blender -b --factory-startup --python blender/tools/toon_parity_blender.py -- [--shot=<png>] [--control]

The same stand as tools/godot/probe_toon_parity.gd: an orthographic camera down -Y (Blender's forward),
a unit sphere wearing the `OW_Toon` node group (built fresh from toon_params.json), ONE sun at
SUN_AZIMUTH_DEG in the view plane, a black world. Rendered to linear EXR, and read the same way: along
the midline each pixel's normal is known, so the lit->shade edge IS an N.L. Prints TERMINATOR_NDL,
EDGE_WIDTH_NDL and LEVELS in the Godot probe's format. `--control` uses a plain Diffuse BSDF.
"""
import math
import os
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_toon_nodegroup as T  # noqa: E402

SUN_AZIMUTH_DEG = 50.0
SUN_STRENGTH = 3.0
W, H = 640, 480
ORTHO = 2.2


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    control = "--control" in argv
    shot = next((a[7:] for a in argv if a.startswith("--shot=")), "")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("black")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    sc.world = world

    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.0)
    sphere = bpy.context.object
    bpy.ops.object.shade_smooth()
    mat = bpy.data.materials.new("toon_probe")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if control:
        d = nt.nodes.new("ShaderNodeBsdfDiffuse")
        nt.links.new(d.outputs[0], out.inputs["Surface"])
    else:
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = T.build(__import__("json").load(open(T.PARAMS)))
        grp.inputs["Sun Strength"].default_value = SUN_STRENGTH
        grp.inputs["Base Color"].default_value = (1, 1, 1, 1)
        # measure the band alone, as the Godot probe does
        for n in grp.node_tree.nodes:
            if n.type == "MATH" and n.operation == "MULTIPLY" and abs(n.inputs[1].default_value - T.json.load(open(T.PARAMS))["rim_strength"]) < 1e-9:
                n.inputs[1].default_value = 0.0
        nt.links.new(grp.outputs["Shader"], out.inputs["Surface"])
    sphere.data.materials.append(mat)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ORTHO * W / H         # Blender's ortho scale spans the WIDTH
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (0, -5, 0)
    cam.rotation_euler = (math.pi / 2, 0, 0)     # looks down +Y at the sphere; +X is screen right
    sc.camera = cam

    az = math.radians(SUN_AZIMUTH_DEG)
    to_light = (math.sin(az), -math.cos(az), 0.0)   # toward the camera side, tilted to +X
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = SUN_STRENGTH
    sun_data.angle = 0.0
    sun_data.use_shadow = False
    sun = bpy.data.objects.new("sun", sun_data)
    sc.collection.objects.link(sun)
    # a sun shines down its own -Z: aim -Z along -to_light
    import mathutils
    sun.rotation_euler = mathutils.Vector(to_light).to_track_quat("Z", "Y").to_euler()

    exr = os.path.join(tempfile.gettempdir(), "toon_parity_%d.exr" % os.getpid())
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.filepath = exr
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(exr)
    px = img.pixels[:]
    os.remove(exr)
    if shot:
        sc.render.image_settings.file_format = "PNG"
        img.save_render(shot)

    def lum(x, y):                                # EXR rows run bottom-up
        i = ((H - 1 - y) * W + x) * 4
        return 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]

    y = H // 2
    row = [lum(x, y) for x in range(W)]
    ppu = H / ORTHO
    cx = W * 0.5

    def at(u):
        return row[max(0, min(W - 1, int(cx + u * ppu)))]

    lit_level, shade_level = at(math.sin(az)), at(-0.85)
    x0 = int(cx + math.sin(az) * ppu)
    # normal at screen u on the midline, in the frame where the camera looks down +Y: (u, -sqrt(1-u^2), 0)
    tl = to_light

    def ndl_at(level):
        for x in range(x0, 0, -1):
            u = (x + 0.5 - cx) / ppu
            if abs(u) >= 1.0:
                return float("nan")
            if row[x] < level:
                n = (u, -math.sqrt(1 - u * u), 0.0)
                return n[0] * tl[0] + n[1] * tl[1] + n[2] * tl[2]
        return float("nan")

    mid = ndl_at((lit_level + shade_level) * 0.5)
    hi = ndl_at(shade_level + 0.75 * (lit_level - shade_level))
    lo = ndl_at(shade_level + 0.25 * (lit_level - shade_level))
    print("LEVELS lit %.3f shade %.3f (shade/lit %.3f)" % (lit_level, shade_level, shade_level / max(lit_level, 1e-6)))
    print("EDGE_WIDTH_NDL %.4f" % (hi - lo))
    print("TERMINATOR_NDL %.4f" % mid)


main()
