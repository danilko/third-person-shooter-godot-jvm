// Speed-feel overlay: radial ZOOM BLUR + "anime speed line" streaks — the two
// screen-space cues racing games use to sell speed (alongside the camera FOV kick).
// The blur is anchored at the screen centre: crisp where you're steering, smeared
// along the radial direction toward the edges, exactly the NFS/Forza look.
// Full-screen ColorRect shader; VehicleCameraController drives `intensity` (0..1)
// from vehicle speed and hides the layer when the vehicle camera is not current,
// so this costs nothing on foot. Not GDScript — shaders are engine assets, game
// logic stays in Java.
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;

uniform float intensity : hint_range(0.0, 1.0) = 0.0;

// ── Radial zoom blur ────────────────────────────────────────────────────────
// Radius (0 = centre, ~1 = edge midpoint) that stays completely sharp.
uniform float blur_clear_radius = 0.35;
// Max UV smear length at the screen edge at full intensity.
uniform float blur_strength : hint_range(0.0, 0.2) = 0.06;

// ── Speed-line streaks ──────────────────────────────────────────────────────
uniform vec4  line_color : source_color = vec4(1.0, 1.0, 1.0, 0.30);
uniform float line_count   = 120.0;
// Streaks stay out of this central radius — road/crosshair remain readable.
uniform float inner_radius = 0.45;
uniform float flicker_speed = 9.0;

float hash(float n) { return fract(sin(n * 127.1) * 43758.5453123); }

void fragment() {
    vec2 p = UV - vec2(0.5);
    // Aspect-correct so the effect radiates in true circles, not ellipses.
    p.x *= SCREEN_PIXEL_SIZE.y / SCREEN_PIXEL_SIZE.x;
    float r = length(p) * 2.0;

    // ── Zoom blur: average samples stepping toward the centre; the step length
    // grows with distance from centre, so the middle stays sharp and the
    // periphery streams past ("clear to more blur as far away from centre").
    float blur_mask = smoothstep(blur_clear_radius, 1.0, r) * intensity;
    float smear = blur_strength * blur_mask;
    vec2 toCenter = vec2(0.5) - SCREEN_UV;
    vec3 acc = vec3(0.0);
    const int TAPS = 8;
    for (int i = 0; i < TAPS; i++) {
        float t = (float(i) / float(TAPS - 1)) * smear;
        acc += texture(screen_tex, SCREEN_UV + toCenter * t).rgb;
    }
    acc /= float(TAPS);

    // ── Speed lines on top of the blurred periphery.
    float ang = atan(p.y, p.x) / TAU + 0.5;   // 0..1 around the circle
    float seg = floor(ang * line_count);
    float f   = fract(ang * line_count);
    float rnd = hash(seg);
    float start  = mix(inner_radius, 0.95, hash(seg + 31.7));
    float flick  = step(0.4, fract(rnd + TIME * flicker_speed * (0.3 + rnd)));
    float line   = smoothstep(0.0, 0.35, f) * smoothstep(1.0, 0.65, f);
    float radial = smoothstep(start, start + 0.3, r);
    float line_a = line * radial * flick * intensity * line_color.a;

    // Composite: blurred screen weighted by the blur mask, streaks over it.
    vec3 rgb = mix(acc, line_color.rgb, line_a);
    COLOR = vec4(rgb, max(blur_mask, line_a));
}
