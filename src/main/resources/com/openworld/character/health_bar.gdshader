shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled;

// Fill ratio 0..1; left edge is always anchored.
uniform float progress : hint_range(0.0, 1.0) = 1.0;
uniform vec4  bg_color : source_color = vec4(0.12, 0.12, 0.12, 0.82);
uniform vec4  fg_color : source_color = vec4(0.18, 0.82, 0.18, 1.0);

void vertex() {
    // Manual billboard: keep the object's world position and scale but replace
    // its rotation with the camera's orientation so the quad always faces the lens.
    //
    // Scale is extracted from the model matrix (length of each basis vector).
    vec3 scale = vec3(
        length(MODEL_MATRIX[0].xyz),
        length(MODEL_MATRIX[1].xyz),
        length(MODEL_MATRIX[2].xyz)
    );

    // Rebuild MODELVIEW_MATRIX:
    //   Columns 0-2: camera right/up/back axes (from INV_VIEW_MATRIX) scaled by the
    //                object's own scale — gives correct size while facing the camera.
    //   Column 3:    MODEL_MATRIX[3] is the WORLD-SPACE position.
    //                The outer VIEW_MATRIX multiplication transforms it to view space
    //                exactly once.  (Putting a pre-transformed view-space position here
    //                would apply VIEW_MATRIX twice and place the quad at the wrong depth.)
    MODELVIEW_MATRIX = VIEW_MATRIX * mat4(
        vec4(INV_VIEW_MATRIX[0].xyz * scale.x, 0.0),
        vec4(INV_VIEW_MATRIX[1].xyz * scale.y, 0.0),
        vec4(INV_VIEW_MATRIX[2].xyz * scale.z, 0.0),
        MODEL_MATRIX[3]
    );
}

void fragment() {
    // UV.x runs 0 (left edge) → 1 (right edge) across the quad.
    // Pixels left of `progress` show the foreground colour — left-anchored fill.
    vec4 c = UV.x <= progress ? fg_color : bg_color;
    ALBEDO = c.rgb;
    ALPHA  = c.a;
}
