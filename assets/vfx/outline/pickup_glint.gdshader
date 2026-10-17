// A dropped weapon's GLINT (user, 2026-10-16; GTA IV / V's shimmer on a gun on the ground): every `period` seconds a
// bright band sweeps once across the item and the whole item brightens a little, so the eye catches it at 20-30 m
// without the world lighting up. Drawn as the item's material_overlay (ui.PickupHighlight sets it only within
// `far_end` of the camera); additive, so between sweeps it adds nothing. The phase comes from the item's resting
// position, so items lying side by side flash at different times; the WHOLE-item flash grows with distance because the
// band alone is under a pixel wide there.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_back, shadows_disabled, fog_disabled;

uniform vec4 glint_color : source_color = vec4(1.0, 0.94, 0.78, 1.0);
uniform float period = 1.9;          // s between sweeps
uniform float sweep = 0.32;          // fraction of the period one sweep takes
uniform float band_width = 0.06;     // m
uniform float span = 0.6;            // m either side of the item's origin the band travels
uniform float far_start = 18.0;      // m: full strength to here
uniform float far_end = 26.0;        // m: gone here

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 origin = NODE_POSITION_WORLD;
	float d = distance(origin, CAMERA_POSITION_WORLD);
	float fade = 1.0 - smoothstep(far_start, far_end, d);
	float phase = fract(dot(floor(origin * 4.0), vec3(0.1373, 0.2719, 0.4191)));
	float t = fract(TIME / period + phase);
	float s = clamp(t / sweep, 0.0, 1.0);
	float on = step(t, sweep);
	float u = dot(world_pos - origin, normalize(vec3(0.7, 1.0, 0.3)));
	float band = exp(-pow((u - mix(-span, span, s)) / band_width, 2.0));
	float whole = sin(PI * s) * mix(0.25, 0.75, smoothstep(4.0, 16.0, d));
	ALBEDO = glint_color.rgb * (band * 1.3 + whole) * fade * on;
	ALPHA = 1.0;
}
