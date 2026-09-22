// Character toon shader, CUTOUT surfaces (hair cards, lashes): double-sided and alpha-tested.
shader_type spatial;
render_mode cull_disabled;

#include "res://assets/vfx/toon/toon_common.gdshaderinc"

uniform float alpha_scissor : hint_range(0.0, 1.0) = 0.5;

void vertex() {
	face_normal_view = toon_face_view(VIEW_MATRIX);
}

void fragment() {
	vec4 c = texture(albedo_texture, UV) * albedo_color;
	ALBEDO = c.rgb;
	ALPHA = c.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	toon_light(NORMAL, LIGHT, VIEW, LIGHT_COLOR, ATTENUATION, LIGHT_IS_DIRECTIONAL, ALBEDO, DIFFUSE_LIGHT, SPECULAR_LIGHT);
}
