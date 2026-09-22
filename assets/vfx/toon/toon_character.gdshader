// Character toon shader, OPAQUE surfaces (skin, clothes). See toon_common.gdshaderinc.
shader_type spatial;
render_mode cull_back;

#include "res://assets/vfx/toon/toon_common.gdshaderinc"

void vertex() {
	face_normal_view = toon_face_view(VIEW_MATRIX);
}

void fragment() {
	vec4 c = texture(albedo_texture, UV) * albedo_color;
	ALBEDO = c.rgb;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	toon_light(NORMAL, LIGHT, VIEW, LIGHT_COLOR, ATTENUATION, LIGHT_IS_DIRECTIONAL, ALBEDO, DIFFUSE_LIGHT, SPECULAR_LIGHT);
}
