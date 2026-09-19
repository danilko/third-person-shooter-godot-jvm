// Binbun3D "Godot Water" (CC0), PBR lighting with caustics.
#define USE_CAUSTICS 1
#define USE_REFRACTION 1
#define USE_DISPLACEMENT 1
#define USE_STYLIZED_LIGHTING 0
#define USE_UNSHADED 0
// Set to 1 if using gl_compatibility renderer
#define GL_COMPATIBILITY 0

shader_type spatial;
#include "water_common.gdshaderinc"
