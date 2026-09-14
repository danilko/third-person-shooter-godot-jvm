@tool
extends RefCounted
## The ONE conversion between the road kit's frame (Z-up, the `.roads.json` record) and Godot's (Y-up).
## Mirrors `point_export.godot` / `point_export.blender`: kit (x, y, z) -> Godot (x, z, -y).
## A second conversion site is how a world ends up mirrored in a way nobody can find.

static func to_godot(k: Vector3) -> Vector3:
	return Vector3(k.x, k.z, -k.y)

static func to_kit(g: Vector3) -> Vector3:
	return Vector3(g.x, -g.z, g.y)

static func from_array(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]) if a.size() > 2 else 0.0)

## Rounded like `PointData.to_dict` (6 decimals), so a diff of the record reads the same either way.
static func to_array(v: Vector3) -> Array:
	return [snappedf(v.x, 0.000001), snappedf(v.y, 0.000001), snappedf(v.z, 0.000001)]
