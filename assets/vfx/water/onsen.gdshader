// The hot-spring variant of Binbun3D "Godot Water" (CC0): the same body (water_common.gdshaderinc), for a small, still
// pool -- no vertex displacement (a tub's quad is not subdivided, and a bath does not swell), caustics and refraction
// kept, so the stone floor shows through. Its look is the material's: assets/vfx/water/material/water_onsen.tres.
#define USE_CAUSTICS 1
#define USE_REFRACTION 1
#define USE_DISPLACEMENT 0
#define USE_STYLIZED_LIGHTING 0
#define USE_UNSHADED 0
#define GL_COMPATIBILITY 0

shader_type spatial;
#include "water_common.gdshaderinc"
