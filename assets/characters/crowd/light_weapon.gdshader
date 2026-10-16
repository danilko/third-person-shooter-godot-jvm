// A light combatant's WEAPON (PLAN.md 2.3, ai.light.LightCombatants): one MultiMesh instance per body that carries
// it, riding the body's RIGHT HAND as baked per frame by tools/godot/bake_ped_vat.gd (`hand` per clip frame).
//
// The mesh is the weapon in its own root's frame (the grip; tools/godot/bake_light_weapons.gd, one surface, each part
// its mean colour in the vertex colour, sRGB); `socket` is the body's socket for it in the hand bone's frame
// (SocketRifle / SocketPistol / ... from the bake's `sockets`), and this shader puts the two in the hand's pose for
// the frame the body is showing. Unshaded, like the body. It reads the SAME instance
// custom data as ped_vat.gdshader (first row, frames, start, fps), so the two can never disagree on the frame.
//   hand_tex: RGBAF, 3 texels a row, one row per VAT row: (basis column x, origin.x), (column y, origin.y),
//             (column z, origin.z) of the hand in the ped root's frame.
shader_type spatial;
render_mode unshaded, cull_back, depth_draw_opaque;

uniform sampler2D hand_tex : filter_nearest, repeat_disable;
uniform mat4 socket = mat4(1.0);

varying vec3 tone;

mat4 hand(int row) {
	vec4 a = texelFetch(hand_tex, ivec2(0, row), 0);
	vec4 b = texelFetch(hand_tex, ivec2(1, row), 0);
	vec4 c = texelFetch(hand_tex, ivec2(2, row), 0);
	return mat4(vec4(a.xyz, 0.0), vec4(b.xyz, 0.0), vec4(c.xyz, 0.0), vec4(a.w, b.w, c.w, 1.0));
}

void vertex() {
	float row0 = INSTANCE_CUSTOM.x;
	float frames = max(INSTANCE_CUSTOM.y, 1.0);
	float f = mod(max(TIME - INSTANCE_CUSTOM.z, 0.0) * INSTANCE_CUSTOM.w, frames);
	float f0 = floor(f);
	float f1 = mod(f0 + 1.0, frames);
	float k = f - f0;
	mat4 h0 = hand(int(row0 + f0));
	mat4 h1 = hand(int(row0 + f1));
	vec4 v = socket * vec4(VERTEX, 1.0);
	vec4 p = mix(h0 * v, h1 * v, k);
	VERTEX = p.xyz;
	NORMAL = normalize(mat3(h0) * mat3(socket) * NORMAL);
	tone = pow(COLOR.rgb, vec3(2.2));
}

void fragment() {
	ALBEDO = tone;
}
