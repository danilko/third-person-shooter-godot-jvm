// A crowd pedestrian played from a VERTEX ANIMATION TEXTURE (tools/godot/bake_ped_vat.gd, world.PedCrowd).
//
// One MultiMesh instance per ped; the whole body type is one draw call. Per instance:
//   INSTANCE_CUSTOM = (first row of the clip, frame count, start time in seconds, frames per second)
//   COLOR           = tint strength in a (0 = the body as authored; rgb must stay white: it carries the part)
// The mesh's own vertex COLOR.r is the vertex's cloth PART x 1/8 (bake_ped_vat.gd PARTS: 0 skin/hair, 1 Tops,
// 2 Bottoms, 3 Onepice, 4 Accessory, 5 Shoes, 6 any other cloth); a layer with `dressed` paints each part its
// outfit's flat colour (character/outfits.json, the light combatant tier -- PLAN.md 2.3), as Outfits does to a body.
// Unshaded like the body it is baked from (the VRoid export is KHR_materials_unlit), alpha-cut hair.
shader_type spatial;
render_mode unshaded, cull_back, depth_draw_opaque;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D vat_pos : filter_nearest, repeat_disable;
uniform float alpha_scissor = 0.5;
uniform bool dressed = false;
uniform vec3 outfit[7];   // LINEAR (LightLooks converts the table's sRGB); r < 0 = keep the part

varying vec4 tint;
varying flat int part;

void vertex() {
	float row0 = INSTANCE_CUSTOM.x;
	float frames = max(INSTANCE_CUSTOM.y, 1.0);
	float f = mod(max(TIME - INSTANCE_CUSTOM.z, 0.0) * INSTANCE_CUSTOM.w, frames);
	float f0 = floor(f);
	float f1 = mod(f0 + 1.0, frames);
	vec3 a = texelFetch(vat_pos, ivec2(VERTEX_ID, int(row0 + f0)), 0).xyz;
	vec3 b = texelFetch(vat_pos, ivec2(VERTEX_ID, int(row0 + f1)), 0).xyz;
	VERTEX = mix(a, b, f - f0);
	// the instance colour multiplies the vertex colour: an instance white in rgb leaves the part readable
	part = int(round(COLOR.r * 8.0));
	tint = vec4(1.0, 1.0, 1.0, COLOR.a);
}

void fragment() {
	vec4 c = texture(albedo_tex, UV);
	// Tint strength in COLOR.a (0 = the body as authored). A clothing-only mask is a follow-up.
	ALBEDO = c.rgb * mix(vec3(1.0), tint.rgb, tint.a);
	if (dressed && part > 0 && part < 7 && outfit[part].r >= 0.0) ALBEDO = outfit[part];   // < 0: the part keeps its own
	ALPHA = c.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
}
