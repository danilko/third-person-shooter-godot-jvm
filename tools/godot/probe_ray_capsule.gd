extends SceneTree
## Does a ray aimed at the CENTRE of a small capsule always hit it? (PLAN.md P0 0.4, 2026-09-17)
##   stdbuf -oL $G --headless --path . --script tools/godot/probe_ray_capsule.gd
## Rays from distance D, from origins jittered by up to 1 m, aimed exactly at the capsule's centre;
## counts rays that report NOTHING. Cases: a plain capsule, the same capsule on a scaled shape node
## (the hitbox layout: CollisionShape3D scaled 1.6), and each at several distances.

func _case(label: String, radius: float, height: float, shape_scale: float, body_basis: Basis, d: float, n: int, past := 2.0, seg := 0.0) -> int:
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = radius
	cap.height = height
	cs.shape = cap
	cs.transform = Transform3D(Basis(Vector3.RIGHT, PI / 2).scaled(Vector3.ONE * shape_scale), Vector3.ZERO)
	body.add_child(cs)
	root.add_child(body)
	body.global_transform = Transform3D(body_basis, Vector3(0, 1, 0))
	await physics_frame
	await physics_frame
	var space := body.get_world_3d().direct_space_state
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var centre := body.global_position
	var misses := 0
	for i in range(n):
		var dir := Vector3(rng.randf_range(-1, 1), rng.randf_range(-0.05, 0.05), rng.randf_range(-1, 1)).normalized()
		var o := centre - dir * d + Vector3(rng.randf_range(-1, 1), rng.randf_range(-1, 1), rng.randf_range(-1, 1)) * 0.0
		var to := centre + (centre - o).normalized() * past
		var hit := {}
		if seg <= 0.0:
			hit = space.intersect_ray(PhysicsRayQueryParameters3D.create(o, to))
		else:
			var a := o
			var total := o.distance_to(to)
			var u := (to - o) / total
			var done := 0.0
			while done < total and hit.is_empty():
				var step := minf(seg, total - done)
				hit = space.intersect_ray(PhysicsRayQueryParameters3D.create(a, a + u * step))
				a += u * step
				done += step
		if hit.is_empty():
			misses += 1
	print("%-28s past %4.0f seg %3.0f d %6.0f m: %4d / %d rays at the centre report nothing" % [label, past, seg, d, misses, n])
	body.free()
	return misses

func _initialize() -> void:
	var tilted := Basis(Vector3(0.3, 1, 0.2).normalized(), 0.9)
	for d in [5.0, 250.0]:
		await _case("thigh r0.0348 x1.6", 0.0348, 0.348, 1.6, tilted, d, 400)
	await _case("thigh, long past", 0.0348, 0.348, 1.6, tilted, 5.0, 400, 500.0)
	await _case("thigh, 32 m segments", 0.0348, 0.348, 1.6, tilted, 250.0, 400, 2.0, 32.0)
	await _case("thigh, 64 m segments", 0.0348, 0.348, 1.6, tilted, 250.0, 400, 2.0, 64.0)
	await _case("thigh, 64 m seg, 1000 m", 0.0348, 0.348, 1.6, tilted, 1000.0, 400, 2.0, 64.0)
	await _case("finger r0.009 x1.6 seg 64", 0.009, 0.05, 1.6, tilted, 1000.0, 400, 2.0, 64.0)
	quit(0)
