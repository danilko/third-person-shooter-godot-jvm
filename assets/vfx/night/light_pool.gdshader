// A FAKE pool of light: a box drawn around a lamp (one MultiMesh instance per lamp) that reads the scene's depth,
// rebuilds the world point behind each pixel and ADDS a soft warm disc onto whatever surface is inside the box --
// road, kerb, a car, a person. No light is evaluated anywhere: it is one additive draw per batch, which is what
// lets every lamp on the island have a pool (world.StreetLights; the real OmniLights are only the nearest few).
// The box mesh is 1 m on a side, centred; the instance's scale is the pool's size (x = z = diameter, y = height).
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, depth_test_disabled, cull_front, shadows_disabled, fog_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
uniform vec3 tint : source_color = vec3(1.0, 0.82, 0.55);
/** Set every frame by StreetLights: strength x DayNight.nightFactor. 0 by day (and the node is hidden then). */
uniform float intensity = 0.0;

varying flat vec3 v_center;
varying flat vec2 v_half;   // x: pool radius, y: half height

void vertex() {
	v_center = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	v_half = vec2(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz)) * 0.5;
}

void fragment() {
	float depth = texture(depth_tex, SCREEN_UV).r;
	vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	view.xyz /= view.w;
	vec3 world = (INV_VIEW_MATRIX * vec4(view.xyz, 1.0)).xyz;
	vec3 d = world - v_center;
	float r = length(d.xz) / max(v_half.x, 0.001);
	if (r >= 1.0 || abs(d.y) >= v_half.y) discard;
	float fall = (1.0 - r);
	fall *= fall;
	float vfade = 1.0 - smoothstep(0.4, 1.0, abs(d.y) / v_half.y);
	ALBEDO = tint * (fall * vfade * intensity);
}
