"""Build the character toon look as a Blender node group, from the one owner of its numbers (PLAN.md 6.10).

    blender -b <file.blend> --python blender/tools/build_toon_nodegroup.py -- [--save]
    blender -b --python blender/tools/build_toon_nodegroup.py -- --library   # writes assets/vfx/toon/toon_nodes.blend

assets/vfx/toon/toon_params.json -> node group `OW_Toon` (rebuilt in place, idempotent). Its Godot twin is
assets/vfx/toon/toon_character.gdshader, whose uniform defaults tools/build_toon.py generates from the same
file; tools/check_toon_parity.sh renders one lit sphere in both and compares them.

For an artist's PREVIEW in EEVEE (Shader to RGB is EEVEE-only): inputs `Base Color`, `Sun Strength` (the
scene's sun, W/m^2), outputs `Shader` (an Emission: the band colour, already lit) and `Color`. It
reproduces the Godot light() for ONE sun: Blender's diffuse radiance for a white Lambert surface is
S * N.L / pi, so Shader to RGB * pi / S recovers N.L (times the sun's shadow) exactly. The specular band is
Godot-only (0.12 strength); lamps and headlights are the game's.
"""
import json
import math
import os
import sys

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARAMS = os.path.join(ROOT, "assets", "vfx", "toon", "toon_params.json")
LIBRARY = os.path.join(ROOT, "assets", "vfx", "toon", "toon_nodes.blend")
NAME = "OW_Toon"


def build(p):
    g = bpy.data.node_groups.get(NAME) or bpy.data.node_groups.new(NAME, "ShaderNodeTree")
    g.nodes.clear()
    g.interface.clear()
    g.interface.new_socket("Base Color", in_out="INPUT", socket_type="NodeSocketColor").default_value = (1, 1, 1, 1)
    s_in = g.interface.new_socket("Sun Strength", in_out="INPUT", socket_type="NodeSocketFloat")
    s_in.default_value = 3.0
    g.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    g.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    N, L = g.nodes, g.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    gi.location, go.location = (-1200, 0), (900, 0)

    def math_node(op, a=None, b=None, loc=(0, 0)):
        m = N.new("ShaderNodeMath")
        m.operation = op
        m.location = loc
        if a is not None and not hasattr(a, "is_linked"):
            m.inputs[0].default_value = a
        if b is not None and not hasattr(b, "is_linked"):
            m.inputs[1].default_value = b
        return m

    # N.L (with the sun's shadow): white Lambert -> Shader to RGB -> luminance * pi / S
    diff = N.new("ShaderNodeBsdfDiffuse"); diff.location = (-1000, 200)
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = N.new("ShaderNodeShaderToRGB"); s2r.location = (-800, 200)
    bw = N.new("ShaderNodeRGBToBW"); bw.location = (-620, 200)
    pi_over_s = math_node("DIVIDE", math.pi, None, (-620, 40))
    ndl = math_node("MULTIPLY", loc=(-440, 160))
    L.new(diff.outputs[0], s2r.inputs[0]); L.new(s2r.outputs["Color"], bw.inputs[0])
    L.new(gi.outputs["Sun Strength"], pi_over_s.inputs[1])
    L.new(bw.outputs[0], ndl.inputs[0]); L.new(pi_over_s.outputs[0], ndl.inputs[1])

    # the band: smoothstep(threshold - softness, threshold + softness, N.L)
    lit = N.new("ShaderNodeMapRange"); lit.location = (-260, 160)
    lit.interpolation_type = "SMOOTHSTEP"
    lit.inputs["From Min"].default_value = p["shade_threshold"] - p["shade_softness"]
    lit.inputs["From Max"].default_value = p["shade_threshold"] + p["shade_softness"]
    L.new(ndl.outputs[0], lit.inputs["Value"])

    # shade colour = base * shade_tint; the band mixes shade -> base
    tint = N.new("ShaderNodeMix"); tint.data_type = "RGBA"; tint.blend_type = "MULTIPLY"
    tint.location = (-260, -80); tint.inputs["Factor"].default_value = 1.0
    t = p["shade_tint"]
    tint.inputs[7].default_value = (t[0], t[1], t[2], 1.0)          # B (colour)
    L.new(gi.outputs["Base Color"], tint.inputs[6])                  # A (colour)
    band = N.new("ShaderNodeMix"); band.data_type = "RGBA"; band.location = (0, 0)
    L.new(lit.outputs[0], band.inputs["Factor"])
    L.new(tint.outputs[2], band.inputs[6]); L.new(gi.outputs["Base Color"], band.inputs[7])

    # rim: 1 - N.V past (1 - rim_width), on the lit side only, added as base * rim * strength
    geo = N.new("ShaderNodeNewGeometry"); geo.location = (-800, -300)
    dot = N.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"; dot.location = (-620, -300)
    L.new(geo.outputs["Normal"], dot.inputs[0]); L.new(geo.outputs["Incoming"], dot.inputs[1])
    facing = math_node("SUBTRACT", 1.0, None, (-440, -300))
    L.new(dot.outputs["Value"], facing.inputs[1])
    rim = N.new("ShaderNodeMapRange"); rim.location = (-260, -300); rim.interpolation_type = "SMOOTHSTEP"
    rim.inputs["From Min"].default_value = 1.0 - p["rim_width"] - p["rim_softness"]
    rim.inputs["From Max"].default_value = 1.0 - p["rim_width"] + p["rim_softness"]
    L.new(facing.outputs[0], rim.inputs["Value"])
    rim_amt = math_node("MULTIPLY", None, p["rim_strength"], (-80, -300))
    L.new(rim.outputs[0], rim_amt.inputs[0])
    rim_lit = math_node("MULTIPLY", loc=(80, -300))
    L.new(rim_amt.outputs[0], rim_lit.inputs[0]); L.new(lit.outputs[0], rim_lit.inputs[1])
    add = N.new("ShaderNodeMix"); add.data_type = "RGBA"; add.blend_type = "ADD"; add.location = (280, 0)
    L.new(rim_lit.outputs[0], add.inputs["Factor"])
    L.new(band.outputs[2], add.inputs[6]); L.new(gi.outputs["Base Color"], add.inputs[7])

    emit = N.new("ShaderNodeEmission"); emit.location = (520, 80)
    L.new(add.outputs[2], emit.inputs["Color"])
    L.new(emit.outputs[0], go.inputs["Shader"]); L.new(add.outputs[2], go.inputs["Color"])
    g["toon_params"] = json.dumps(p, sort_keys=True)                  # what it was built from
    g.use_fake_user = True
    return g


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = json.load(open(PARAMS))
    if "--library" in argv:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build(p)
        bpy.ops.wm.save_as_mainfile(filepath=LIBRARY)
        print("[toon-nodes] wrote", os.path.relpath(LIBRARY, ROOT))
        return
    build(p)
    print("[toon-nodes] built %s in %s" % (NAME, bpy.data.filepath or "(unsaved)"))
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()


if __name__ == "__main__":
    main()
