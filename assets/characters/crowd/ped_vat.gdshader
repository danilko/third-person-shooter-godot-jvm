// A crowd pedestrian played from a VERTEX ANIMATION TEXTURE (tools/godot/bake_ped_vat.gd, world.PedCrowd).
//
// One MultiMesh instance per ped; the whole body type is one draw call. Per instance:
//   INSTANCE_CUSTOM = (first row of the clip, frame count, start time in seconds, frames per second)
//   COLOR           = tint (rgb) and its strength (a; 0 = the body as authored)
// Unshaded like the body it is baked from (the VRoid export is KHR_materials_unlit), alpha-cut hair.
shader_type spatial;
render_mode unshaded, cull_back, depth_draw_opaque;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D vat_pos : filter_nearest, repeat_disable;
uniform float alpha_scissor = 0.5;

varying vec4 tint;

void vertex() {
	float row0 = INSTANCE_CUSTOM.x;
	float frames = max(INSTANCE_CUSTOM.y, 1.0);
	float f = mod(max(TIME - INSTANCE_CUSTOM.z, 0.0) * INSTANCE_CUSTOM.w, frames);
	float f0 = floor(f);
	float f1 = mod(f0 + 1.0, frames);
	vec3 a = texelFetch(vat_pos, ivec2(VERTEX_ID, int(row0 + f0)), 0).xyz;
	vec3 b = texelFetch(vat_pos, ivec2(VERTEX_ID, int(row0 + f1)), 0).xyz;
	VERTEX = mix(a, b, f - f0);
	tint = COLOR;
}

void fragment() {
	vec4 c = texture(albedo_tex, UV);
	// Tint strength in COLOR.a (0 = the body as authored). A clothing-only mask is a follow-up.
	ALBEDO = c.rgb * mix(vec3(1.0), tint.rgb, tint.a);
	ALPHA = c.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
}
