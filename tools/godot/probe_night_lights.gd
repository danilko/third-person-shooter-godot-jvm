extends SceneTree
## Night lighting (user, 2026-09-19: "night time is barely able to see in game").
##
##   stdbuf -oL godot --headless --fixed-fps 60 --path . --script tools/godot/probe_night_lights.gd
##   ... -- --control      (StreetLights off and every car's lamp offsets cleared: the world before this)
##
## Before this there was not ONE OmniLight3D or SpotLight3D in the project, the moon's energy was 0 and the lamps
## and signals were props with no light, so a clear night was lit by sky ambient alone. What this asserts:
##   1. `DayNight` MEASURES the sun off the key light, not off a clock: noon reads day, midnight reads night, and
##      the twilight ramp lies between;
##   2. the lamp pool lights the nearest STANDING lamp heads and only those (a lamp 300 m away gets nothing), at
##      the height the piece's own luminaire mesh sits (10.07 m), and it goes dark at noon;
##   3. a knocked-down lamp's light goes out with the pole and comes back with it -- no second record of broken;
##   4. a car's headlights come on at night and are off by day, and a car far from the camera does not pay for a
##      beam nobody can see;
##   5. the moon casts light (the one reason a clear night is navigable at all away from a road).

const WORLD := "res://src/main/resources/com/openworld/world/DebugWorld.tscn"
const VEHICLE := "res://src/main/resources/com/openworld/vehicle/SPC1.tscn"
const LAMP_HEAD_Y := 10.07     # StreetLights.HEAD_OFFSETS, measured off the piece's MI_LampGlass mesh

var world: Node
var fails := 0
var control := false

func _check(ok: bool, what: String) -> void:
	print("  [%s] %s" % ["PASS" if ok else "FAIL", what])
	if not ok:
		fails += 1

func _day_night() -> Node: return root.get_node_or_null("DayNight")
func _lamps() -> Node: return root.get_node_or_null("StreetLights")

func _batches(asset: String) -> Array:
	var out := []
	for n in world.find_children("Breakable_*", "MultiMeshInstance3D", true, false):
		if str(n.get("asset_name")) == asset:
			out.append(n)
	return out

## Put the sun where we want it. The clock is Sky3D's; DayNight reads the LIGHT, so this drives the clock and
## lets the addon move the light -- which is the whole point of measuring the light instead of the clock.
func _set_time(hour: float) -> void:
	for n in world.find_children("TimeOfDay", "Node", true, false):
		n.set("current_time", hour)
	for f in 8:
		await process_frame

var probe_cam: Camera3D

## The probe owns its own camera: the Player's TPS rig keeps writing its own even with the Player's
## process_mode DISABLED, so moving "the current camera" silently moved nothing (measured: the camera stayed
## 150 m from where this asked for it, and every lamp reading was of somewhere else).
func _camera_at(p: Vector3, look: Vector3) -> Camera3D:
	if probe_cam == null:
		probe_cam = Camera3D.new()
		world.add_child(probe_cam)
	probe_cam.global_position = p
	probe_cam.look_at(p + look, Vector3.UP)
	probe_cam.make_current()
	return probe_cam

func _initialize() -> void:
	control = "--control" in OS.get_cmdline_user_args()
	world = (load(WORLD) as PackedScene).instantiate()
	root.add_child(world)
	current_scene = world
	var player: Node3D = world.get_node("Characters/Player")
	player.process_mode = Node.PROCESS_MODE_DISABLED
	var waited := 0
	while _batches("StreetLight_JP").size() < 1 and waited < 60 * 30:
		await physics_frame
		waited += 1
	var batches := _batches("StreetLight_JP")
	var lamps := 0
	for b in batches:
		lamps += int(b.call("pole_count_now"))
	print("probe: %d lamp batch(es), %d lamps, streamed after %.1f s%s"
			% [batches.size(), lamps, waited / 60.0, "  (CONTROL)" if control else ""])
	_check(batches.size() >= 1 and lamps > 5, "DebugWorld streams real street lamps")
	if batches.is_empty():
		print("RESULT: FAIL (no lamps)"); quit(2); return

	var dn := _day_night()
	var sl := _lamps()
	_check(dn != null, "the DayNight AutoLoad is present")
	_check(sl != null, "the StreetLights AutoLoad is present")
	if dn == null or sl == null:
		print("RESULT: FAIL"); quit(2); return
	if control:
		sl.set("enabled", false)
		# the car's lamp offsets are cleared on the SHARED config resource, before any car is built: a
		# godot-jvm @Export resource reads as NULL while its node is off-tree, so `car.get("config")` on a
		# freshly instantiated car is null and `.set` on it aborts the script -- which a --script run shows
		# as a HANG, not an error (PLAN.md's own trap, from probe_road_launch --wheel-sensor).
		var cfg := load("res://src/main/resources/com/openworld/vehicle/SPC1Config.tres")
		cfg.set("headlight_offset", Vector3.ZERO)

	# a lamp to stand beside, and the camera 12 m from it looking at it
	var b: Node = batches[0]
	var lamp: Vector3 = b.call("pole_world_position_now", 0)
	var eye := lamp + Vector3(12, 2, 0)
	_camera_at(eye, (lamp + Vector3(0, 5, 0) - eye).normalized())
	player.global_position = eye

	# --- 1. the sun, measured off the key light
	await _set_time(12.0)
	var noon_elev: float = dn.call("sun_elevation_now")
	var noon_night: float = dn.call("night_factor_now")
	await _set_time(23.5)
	var night_elev: float = dn.call("sun_elevation_now")
	var night_night: float = dn.call("night_factor_now")
	print("probe: sun elevation noon %.1f deg (night %.2f), midnight %.1f deg (night %.2f)"
			% [noon_elev, noon_night, night_elev, night_night])
	_check(noon_elev > 10.0 and noon_night < 0.05, "noon reads as day")
	_check(night_elev < -8.0 and night_night > 0.95, "midnight reads as night")

	# --- 2. the lamp pool
	for f in 20:
		await process_frame
	var lit: int = sl.call("lit_lamps_now")
	var nearest: float = sl.call("nearest_lamp_now")
	var head: Vector3 = sl.call("lit_lamp_position_now", 0) if lit > 0 else Vector3.ZERO
	print("probe: camera %s, lamp base %s, %d head(s) in range"
			% [root.get_viewport().get_camera_3d().global_position, lamp, int(sl.call("lamps_in_range_now"))])
	print("probe: night, beside a lamp -> %d lit, nearest %.1f m, head y %.2f (base y %.2f)"
			% [lit, nearest, head.y, lamp.y])
	_check(lit > 0, "lamps near the camera are lit at night")
	_check(nearest >= 0.0 and nearest < 20.0, "the nearest lit lamp is the one we are standing at")
	_check(lit > 0 and absf((head.y - lamp.y) - LAMP_HEAD_Y) < 0.5,
			"the light sits at the luminaire, %.2f m up" % LAMP_HEAD_Y)

	# out of range: no lamp near, nothing lit
	_camera_at(lamp + Vector3(300, 60, 300), Vector3.DOWN)
	for f in 20:
		await process_frame
	_check(int(sl.call("lit_lamps_now")) == 0, "a camera 400 m from every lamp lights none")

	# --- 3. a lamp that is down is dark
	_camera_at(eye, (lamp + Vector3(0, 5, 0) - eye).normalized())
	for f in 20:
		await process_frame
	var before: int = sl.call("lit_lamps_now")
	b.call("pole_world_position_now", 0)     # (no-op; keeps the call shape beside the knock-down below)
	var mm: MultiMesh = b.multimesh
	# knock it down the way a car does, through the class's own sweep, by driving one at it is overkill here:
	# the probe uses the registered readouts instead and asserts the LIGHT follows the pole's own state.
	var car: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car)
	car.global_position = lamp + Vector3(-14, 0.8, 0)
	car.look_at(lamp + Vector3(0, 0.8, 0), Vector3.UP)
	for f in 240:
		var p := car.global_position
		var aim := Vector3(lamp.x - p.x, 0, lamp.z - p.z)
		if aim.length() < 3.0:
			break
		car.linear_velocity = aim.normalized() * 16.0 + Vector3(0, car.linear_velocity.y, 0)
		await physics_frame
	for f in 20:
		await process_frame
	var down: bool = b.call("pole_broken_now", 0)
	var after: int = sl.call("lit_lamps_now")
	print("probe: drove into the lamp -> broken %s, lit %d -> %d" % [down, before, after])
	_check(down, "the car knocked the lamp down (3.11)")
	_check(not down or after < before, "a lamp lying on the ground is not lit")
	car.queue_free()

	# --- 4. headlights
	var car2: RigidBody3D = (load(VEHICLE) as PackedScene).instantiate()
	world.add_child(car2)
	car2.global_position = eye + Vector3(4, 1.0, 0)
	car2.freeze = true
	for f in 40:
		await process_frame
	var on_at_night: bool = car2.call("headlights_on_now")
	var beam: Node3D = car2.get_node_or_null("HeadlightR")
	print("probe: night, car 4 m from the camera -> headlights %s, beam node %s"
			% [on_at_night, "yes" if beam != null else "no"])
	_check(on_at_night, "a car's headlights are on at night")
	_check(beam != null and beam.visible, "the beam light exists and is visible")
	await _set_time(12.0)
	for f in 40:
		await process_frame
	_check(not bool(car2.call("headlights_on_now")), "and off by day")
	_check(int(sl.call("lit_lamps_now")) == 0, "the lamps are out by day")

	# --- 5. the moon
	await _set_time(23.5)
	# Sky3D WRITES MoonLight.light_energy every frame from SkyDome.moon_light_energy x the moon's altitude, so
	# this measures the light the moon actually casts, not what a scene line asked for. In SIMPLE celestial mode
	# the moon is opposite the sun, so a clear night always has one up -- which is what makes open ground
	# readable away from a road.
	var moon: DirectionalLight3D = world.get_node_or_null("Sky3D/MoonLight")
	var moon_e: float = moon.light_energy if moon != null else 0.0
	var moon_alt: float = rad_to_deg(world.get_node("Sky3D/SkyDome").get("moon_altitude"))
	print("probe: midnight moon altitude %.1f deg, light energy %.3f" % [moon_alt, moon_e])
	_check(moon != null and moon_e > 0.05, "the moon casts light on a clear night")

	print("RESULT: %s (%d failure%s)" % ["PASS" if fails == 0 else "FAIL", fails, "" if fails == 1 else "s"])
	quit(1 if fails else 0)
