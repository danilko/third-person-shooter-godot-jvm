extends SceneTree
## Solve the character's holster sockets from a body-frame design, and print them as .tscn transforms.
##
##   godot --headless --fixed-fps 60 --path . --script tools/godot/solve_holster_sockets.gd
##
## PLAN.md A4. A holster socket is a Marker3D under a BoneAttachment3D (BackHolster on spine_03,
## HipWeaponHolster on spine_01), so its authored transform is in a BONE's frame and says nothing
## legible about where the weapon ends up. The design is in the BODY's frame -- "a sling running
## down-left across the back, 20 cm behind the spine, tilted 22 degrees from vertical" -- and this
## script is the one place that conversion happens, so a socket is never nudged by eye.
##
## `WeaponController.reparentWeapon` puts the weapon's HOLSTER point (or its grip -- W20) on the
## socket, so the socket carries the SLING: where the strap sits on the back and which way it runs.
## Per-weapon differences (a launcher whose grip is 0.40 m from the tube's rear) belong in that
## weapon's own `holsterPoint`, never here -- one shared fact, one owner.
##
## Frames: body x = right, y = up, z = BACKWARD (the mesh is -Z forward). A socket's basis is built
## so that
##   local -Z  -> the sling direction (down, tilted `tilt_deg` toward the given side)
##   local  X  -> body +z, i.e. straight out of the back: the weapon lies FLAT against it, which is
##               how a slung long gun sits (its side against the back, sights facing along the body).
## The hip sockets keep their authored bases; only the back pair is solved here.

const PLAYER := "res://src/main/resources/com/openworld/character/Player.tscn"

## The back sling, per socket. `pos` is body-frame (right, up, back); `tilt_deg` is from vertical,
## positive = the muzzle swings toward the body's LEFT and the butt rides up to the RIGHT.
##
## Numbers, measured on GodotChan (1.49 m to the crown; shoulders 1.20, hips 0.77, head_2 1.357,
## back surface 0.13 behind the mesh origin):
##   - tilt 22 deg: enough that an 0.88 m rifle's butt clears the skull laterally (0.13 -> 0.23 m)
##     and an 0.98 m shotgun's muzzle stays above the knee, without the lateral span a sling angle
##     of 40 deg costs (L*sin: 0.33 m at 22 deg, 0.57 m at 40 deg, on a 0.30 m shoulder width).
##   - the pair is separated in DEPTH, not laterally: a slung gun's tall axis lies across the back
##     (0.18-0.29 m of it), so two guns 0.16 m apart laterally overlap, while 0.12 m of depth
##     clears the thickest pair (0.12 + 0.08 boxes).
## The hip pair. The LEFT hip (`ShortWeaponHolsterMaker1`) measures clean as authored -- a pistol
## hangs down it 12 deg off vertical, 1.4 cm of contact with the arm -- so it is the reference, and
## the RIGHT hip is defined as its MIRROR. It was authored pointing nearly FORWARD (75 deg from
## vertical), which drove a holstered knife into the hip: 17.3% of its volume inside the spine and
## thigh bones. Mirroring is a conjugation (body-frame reflection on both sides), so the sling and
## the weapon's own up mirror while its thickness axis is negated -- which keeps the frame
## right-handed and only decides which face of the weapon looks outward.
const HIP_MIRROR := {"ShortWeaponHolsterMaker2": "ShortWeaponHolsterMaker1"}

const BACK_SOCKETS := {
	"LongWeaponHolsterMaker1": {"pos": Vector3(0.120, 1.090, 0.200), "tilt_deg": 22.0},
	"LongWeaponHolsterMaker2": {"pos": Vector3(0.020, 1.055, 0.320), "tilt_deg": 22.0},
}

func _find(n: Node, nm: String) -> Node:
	if n.name == nm:
		return n
	for c in n.get_children():
		var r: Node = _find(c, nm)
		if r != null:
			return r
	return null

func _tick(n: int) -> void:
	for i in range(n):
		await physics_frame

## `var_to_str` is the ENGINE's own serialization, which is what a .tscn holds. Printing the basis
## component by component is how this went wrong once: a Transform3D literal's 9 basis floats are
## rows (`Basis.rows`), not the three axis vectors, so writing x/y/z in order transposes it -- and a
## transposed sling basis is not obviously wrong, it just lays the rifle across the back HORIZONTALLY
## (measured: 89 deg from vertical instead of 22, with the position still exactly right).
func _fmt(t: Transform3D) -> String:
	return var_to_str(t)

func _initialize() -> void:
	var world := Node3D.new()
	root.add_child(world)
	var floor_body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200, 1, 200)
	cs.shape = box
	floor_body.add_child(cs)
	floor_body.position = Vector3(0, -0.5, 0)
	world.add_child(floor_body)
	var p: Node3D = (load(PLAYER) as PackedScene).instantiate() as Node3D
	world.add_child(p)
	p.position = Vector3(0, 1.2, 0)
	await _tick(60)

	var mesh_root: Node3D = _find(p, "MeshRoot") as Node3D
	var to_body: Transform3D = mesh_root.global_transform.affine_inverse()
	for socket_name in BACK_SOCKETS:
		var socket: Node3D = _find(p, socket_name) as Node3D
		var holder: Node3D = socket.get_parent() as Node3D
		var d: Dictionary = BACK_SOCKETS[socket_name]
		var tilt: float = deg_to_rad(float(d["tilt_deg"]))
		# local -Z -> the sling; local X -> out of the back; local Y = Z x X keeps it right-handed.
		var z_axis := Vector3(sin(tilt), cos(tilt), 0.0)
		var x_axis := Vector3(0.0, 0.0, 1.0)
		var y_axis: Vector3 = z_axis.cross(x_axis)
		var want_body := Transform3D(Basis(x_axis, y_axis, z_axis).orthonormalized(), d["pos"] as Vector3)
		# body -> world -> the holder bone's frame: what goes in the .tscn.
		var local: Transform3D = holder.global_transform.affine_inverse() * mesh_root.global_transform * want_body
		print("APPLY %s %s" % [socket_name, _fmt(local)])
		socket.transform = local
		await _tick(2)
		_report(socket, mesh_root, to_body)

	for socket_name in HIP_MIRROR:
		var socket: Node3D = _find(p, socket_name) as Node3D
		var source: Node3D = _find(p, String(HIP_MIRROR[socket_name])) as Node3D
		var holder: Node3D = socket.get_parent() as Node3D
		var src_body: Transform3D = to_body * source.global_transform
		var m := Basis(Vector3(-1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, 1))
		var want_body := Transform3D(m * src_body.basis * m, m * src_body.origin)
		var local: Transform3D = holder.global_transform.affine_inverse() * mesh_root.global_transform * want_body
		print("APPLY %s %s" % [socket_name, _fmt(local)])
		socket.transform = local
		await _tick(2)
		_report(socket, mesh_root, to_body)
	quit(0)

## Read a socket back the way the probe does, as a check that the conversion is the right way round.
func _report(socket: Node3D, mesh_root: Node3D, to_body: Transform3D) -> void:
	var got: Vector3 = to_body * socket.global_position
	var axis: Vector3 = mesh_root.global_transform.basis.inverse() * (-socket.global_transform.basis.z)
	var up: Vector3 = mesh_root.global_transform.basis.inverse() * socket.global_transform.basis.y
	print("  -> at right %+.3f up %+.3f back %+.3f ; sling right %+.2f up %+.2f back %+.2f (%.0f deg from vertical) ; weapon up right %+.2f up %+.2f back %+.2f"
		% [got.x, got.y, got.z, axis.x, axis.y, axis.z, rad_to_deg(acos(clampf(-axis.y, -1.0, 1.0))),
			up.x, up.y, up.z])
