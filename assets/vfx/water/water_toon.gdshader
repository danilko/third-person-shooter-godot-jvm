// Binbun3D "Godot Water" (CC0), stylized stepped lighting, no caustics — the variant the world's sea uses.
#define USE_CAUSTICS 0
#define USE_REFRACTION 1
#define USE_DISPLACEMENT 1
#define USE_STYLIZED_LIGHTING 1
#define USE_UNSHADED 0
// Set to 1 if using gl_compatibility renderer
#define GL_COMPATIBILITY 0

shader_type spatial;
#include "water_common.gdshaderinc"
