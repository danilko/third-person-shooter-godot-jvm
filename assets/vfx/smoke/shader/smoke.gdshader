// Binbun3D "Godot 4.x Smoke VFX Effects" (https://binbun3d.itch.io/smoke-vfx), CC0 1.0 — see assets/vfx/LICENSE.txt.
shader_type spatial;
render_mode blend_mix, specular_disabled, diffuse_toon;

#include "util/blend.gdshaderinc"
#include "util/alpha.gdshaderinc"

group_uniforms Masks;
uniform sampler2D mask1_texture;
uniform vec2 mask1_scroll = vec2(0.0);
uniform vec2 mask1_scale = vec2(1.0);
uniform bool use_mask2 = false;
uniform sampler2D mask2_texture;
uniform vec2 mask2_scroll = vec2(0.0);
uniform vec2 mask2_scale = vec2(1.0);
uniform float mask2_strength : hint_range(0.0, 1.0, 0.01);
uniform int mask2_blend_mode : hint_range(0, 11, 1) = 0;
uniform bool use_mask3 = false;
uniform sampler2D mask3_texture;
uniform vec2 mask3_scroll = vec2(0.0);
uniform vec2 mask3_scale = vec2(1.0);
uniform float mask3_strength : hint_range(0.0, 1.0, 0.01);
uniform int mask3_blend_mode : hint_range(0, 11, 1) = 0;

group_uniforms Color;
uniform vec4 primary_color : source_color;
uniform vec4 secondary_color : source_color;
uniform vec4 tertiary_color : source_color;
uniform float color_smoothness : hint_range(0.0, 1.0, 0.1) = 0.5;

group_uniforms Geometry;
uniform bool billboard = false;
uniform float displacement_scale : hint_range(0.0, 1.0, 0.05) = 0.0;
uniform float displacement_offset : hint_range(0.0, 1.0, 0.05) = 0.5;

group_uniforms UV;
uniform float time_scale = 1.0;

group_uniforms Emission;
uniform float emission_strength = 2.0;

group_uniforms ProximityFade;
uniform bool proximity_fade = false;
uniform float proximity_fade_distance : hint_range(0.0, 4096.0, 0.01) = 1.0;

group_uniforms Transparency;
uniform vec4 edge_cutoff = vec4(0.0);
uniform float alpha_smoothness : hint_range(0.0, 1.0, 0.05) = 0.954;
uniform float alpha_multiplier : hint_range(0.0, 1.0, 0.05) = 0.954;
uniform int alpha_mode : hint_range(0, 3, 1) = 0;
uniform float alpha_cutoff : hint_range(0.0, 1.0, 0.01) = 0.05;
uniform float dither_cutoff : hint_range(0.0, 1.0, 0.01) = 0.8;
uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;

group_uniforms Shading;
uniform sampler2D normal_texture;
uniform float normal_strength : hint_range(0.0, 1.0, 0.01) = 0.97;
uniform float roughness : hint_range(0.0, 1.0, 0.01) = 0.8;

float mask(vec2 uv, float offset){
	float scaled_time = TIME * time_scale;
	vec2 m1_uv = uv * mask1_scale + vec2(offset) + (vec2(TIME) * mask1_scroll);
	float m1 = texture(mask1_texture, m1_uv).r;
	float m = m1;
	if(use_mask2){
		vec2 m2_uv = uv * mask2_scale + vec2(offset) + (vec2(TIME) * mask2_scroll);
		float m2 = texture(mask2_texture, m2_uv).r;
		m = mix(m, blendf(m, m2, mask2_blend_mode), mask2_strength);
	}
	if(use_mask3){
		vec2 m3_uv = uv * mask3_scale  + (vec2(TIME) * mask3_scroll);
		float m3 = texture(mask3_texture, m3_uv).r;
		m = mix(m, blendf(m, m3, mask3_blend_mode), mask3_strength);
	}
	return m;
}

void vertex(){
	if(billboard){
		// Billboard Mode: Enabled
		MODELVIEW_MATRIX = VIEW_MATRIX * mat4(
				MAIN_CAM_INV_VIEW_MATRIX[0],
				MAIN_CAM_INV_VIEW_MATRIX[1],
				MAIN_CAM_INV_VIEW_MATRIX[2],
				MODEL_MATRIX[3]);
		MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
	}
}

void fragment() {
	float mask_value = mask(UV, COLOR.r);

	float color_mask = smoothstep(0.5 - (color_smoothness * .5), 0.5 + (color_smoothness * .5), mask_value);
	
	ALBEDO = mix(mix(secondary_color, primary_color, pow(color_mask, 2.0)).rgb, tertiary_color.rgb, COLOR.b);

	EMISSION = ALBEDO * emission_strength;
	
	
	if(normal_strength != 0.0){
		vec2 centered = UV * 2.0 - 1.0;
		float dist = length(centered);
		vec3 normal;
		normal.xy = vec2(centered.x, -centered.y*0.1)  * 1.5 * normal_strength;
		normal.z = sqrt(1.0 - clamp(dot(normal.xy, normal.xy), 0.0, 1.0));
		NORMAL = normalize(normal);
		
		vec2 normal_uv = UV * mask2_scale + vec2(COLOR.r) + (vec2(TIME) * mask2_scroll);
		vec3 normal_map = textureLod(normal_texture, normal_uv, 4.0).rgb;
		NORMAL_MAP = mix(vec3(0.5), normal_map, normal_strength);
	}
	
	ROUGHNESS = roughness;

	float alpha_mask = clamp(0.5 - (alpha_smoothness * .5), 0.5 + (alpha_smoothness * .5), mask_value);
	float alpha = clamp((pow(alpha_mask, 3.0) * alpha_multiplier) * (COLOR.a), 0.0, 1.0);
	if(edge_cutoff != vec4(0.0)){
		if(UV.x < edge_cutoff.x){ discard; }
		if(UV.y < edge_cutoff.y){ discard; }
		if(UV.x > 1.0-edge_cutoff.z){ discard; }
		if(UV.y > 1.0-edge_cutoff.w){ discard; }
	}
	
	// Proximity Fade: Enabled
	if(proximity_fade){
		float proximity_depth_tex = textureLod(depth_texture, SCREEN_UV, 0.0).r;
		vec4 proximity_view_pos = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, proximity_depth_tex, 1.0);
		proximity_view_pos.xyz /= proximity_view_pos.w;
		alpha *= clamp(1.0 - smoothstep(proximity_view_pos.z + proximity_fade_distance, proximity_view_pos.z, VERTEX.z), 0.0, 1.0);
	}

	if(alpha_mode == 0){
		ALPHA = alpha;
	} else {
		if(alpha_discard(alpha, FRAGCOORD, alpha_mode, dither_cutoff, alpha_cutoff)){
			discard;
		}
	}
	
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
