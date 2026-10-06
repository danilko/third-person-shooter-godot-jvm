// L4D-style target outline (user, 2026-10-06): an inverted hull drawn as a GeometryInstance3D material_overlay,
// so it works on any skinned mesh with no per-mesh setup. Front faces are culled and the hull pushed out along the
// normal, so only a rim shows round the body (depth-tested: a hull drawn through walls would fill the whole body).
shader_type spatial;
render_mode unshaded, cull_front, blend_mix, shadows_disabled;

uniform vec4 outline_color : source_color = vec4(0.35, 1.0, 0.45, 0.85);
uniform float width = 0.025;

void vertex() {
	VERTEX += NORMAL * width;
}

void fragment() {
	ALBEDO = outline_color.rgb;
	ALPHA = outline_color.a;
}
