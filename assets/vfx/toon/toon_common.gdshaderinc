// The character toon look (PLAN.md 6.10). Our own code, written for this project (see README.md).
//
// A RAMP OVER THE ENGINE'S LIGHTS, not a self-lit (MToon-style) look: every light that reaches the surface
// -- the sun and moon (world.DayNight), the street-lamp pool (world.StreetLights), headlights -- lights it
// through light(), and ATTENUATION carries the shadow maps, so a character receives shadows and (as any
// opaque mesh) casts them. Three things a PBR Lambert does not:
//   * the diffuse falls off in a BAND at shade_threshold instead of a gradient, and the shade side keeps
//     shade_tint of the light instead of going black (the anime "shadow colour");
//   * a highlight BAND where N.H passes specular_threshold;
//   * a RIM of light on silhouettes that face the light.
// The numbers are generated from toon_params.json into toon_params.gdshaderinc: edit the JSON.

#include "res://assets/vfx/toon/toon_params.gdshaderinc"

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap, repeat_enable;
uniform vec4 albedo_color : source_color = vec4(1.0);
// Face control: the face's normal is pulled toward face_forward (a WORLD direction, written each frame by
// character.ToonLook from the head bone) by face_flatten. PER INSTANCE, so every character shares one
// material per source material and still has its own face direction; face_weight is 1 on the face mesh
// and 0 everywhere else.
instance uniform vec3 face_forward = vec3(0.0);
instance uniform float face_weight : hint_range(0.0, 1.0) = 0.0;

varying vec3 face_normal_view;

// the face direction in VIEW space; vertex() assigns it (Godot allows a varying to be written only there)
vec3 toon_face_view(mat4 view_matrix) {
	return (view_matrix * vec4(face_forward, 0.0)).xyz;
}

vec3 toon_normal(vec3 n) {
	float w = face_weight * face_flatten;
	if (w <= 0.0 || dot(face_normal_view, face_normal_view) < 1e-6) {
		return n;
	}
	return normalize(mix(n, normalize(face_normal_view), w));
}

void toon_light(vec3 normal, vec3 light, vec3 view, vec3 light_color, float attenuation, bool directional,
		vec3 albedo, inout vec3 diffuse_light, inout vec3 specular_light) {
	vec3 n = toon_normal(normal);
	float ndl = dot(n, light);
	float lit = smoothstep(shade_threshold - shade_softness, shade_threshold + shade_softness, ndl);
	vec3 band;
	if (directional) {
		// the sun: ATTENUATION is the shadow alone, so a cast shadow lands in the shade band, not in black
		band = mix(shade_tint, vec3(1.0), lit * attenuation);
	} else {
		// a lamp: ATTENUATION is distance AND shadow together, so the whole band fades with range
		band = mix(shade_tint, vec3(1.0), lit) * attenuation;
	}
	diffuse_light += light_color * band / PI;

	float ndh = dot(n, normalize(light + view));
	float spec = smoothstep(specular_threshold - specular_softness, specular_threshold + specular_softness, ndh);
	// a lighter tone OF THE SURFACE, not white: LIGHT_COLOR carries a factor of pi (hence the / PI on the
	// diffuse too), and a white band at that scale drew bright streaks across dark cloth (measured by eye on
	// shot_toon_character.gd, gone with the band off)
	specular_light += light_color * albedo * spec * specular_strength * lit * attenuation / PI;

	float facing = 1.0 - clamp(dot(n, view), 0.0, 1.0);
	float rim = smoothstep(1.0 - rim_width - rim_softness, 1.0 - rim_width + rim_softness, facing);
	diffuse_light += light_color * rim * rim_strength * lit * attenuation / PI;
}
