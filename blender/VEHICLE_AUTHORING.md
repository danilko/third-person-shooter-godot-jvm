# Vehicle authoring — the component car

A car that comes apart in pieces, GTA III / San Andreas style: named PARTS that dent, hang loose and fall off,
driven at runtime by `VehicleDamageModel` (CLAUDE.md, "Vehicles — the component car"). This file is what a model has to be for that to work.

## The pipeline

```
assets/vehicles/<ID>.blend  --blender/tools/build_vehicle.py-->  <ID>.glb + <ID>.vehicle.json
                            --tools/build_vehicle_scenes.py-->   src/main/resources/com/openworld/vehicle/<ID>.tscn
                                                                  + <ID>Config.tres
gate: tools/godot/probe_component_car.gd -- --car=<ID>
```

```bash
blender -b --python blender/tools/build_vehicle.py -- SPC1 PIT1 POC1
python3 tools/build_vehicle_scenes.py            # --check fails on a stale scene
godot --headless --path . --import               # after any .glb change
godot --headless --path . --script tools/godot/probe_component_car.gd -- --car=SPC1 [--control]
```

Nothing in the scene is hand-placed: wheel mounts, the hull, the seats and the camera mounts are computed from
the MEASURED `<ID>.vehicle.json`. Hand tuning (mass, springs, power, health, paint, extra seats) is the `TUNING` table
in `tools/build_vehicle_scenes.py`.

## The standard

* **1 unit = 1 metre, real size.** SPC1 4.49 m, PIT1 5.36 m, POC1 5.41 m (a Crown Victoria is 5.38).
* **Faces +Y** in Blender (Godot −Z), **origin on the ground** at the middle of the wheelbase, centred on the axles.
* **Parts by name** — the runtime finds them by name, like GTA's dff frames, so a renamed part stops breaking with no
  error anywhere:

  | name | kind | what it does |
  |---|---|---|
  | `chassis` | required | never changes state; its `dam` key follows the car's health (the roof caves in) |
  | `wheel_lf` `wheel_rf` `wheel_lb` `wheel_rb` | required | moved under the VehicleWheel at runtime: spin, steer, suspension, flat |
  | `door_lf` `door_rf` (`door_lr` `door_rr`) | optional | dent, swing loose, fall off; open and shut on enter/exit |
  | `bonnet`, `boot` | optional | dent, lift loose (air lifts a loose bonnet at speed), fall off |
  | `bump_front`, `bump_rear` | optional | dent, hang from one end, fall off |
  | `wing_lf` `wing_rf` | optional | dent only |
  | `windscreen` | optional | cracks (dent), then shatters |

* **Each part's origin is its HINGE** — a door on its front edge, the bonnet on its rear edge, the boot on its front
  edge, a bumper on one end. A loose part swings about its origin, so a wrong origin is a door rotating in mid-air.
  `build_vehicle.py` places them; move the origin in the .blend to change one.
* **A `dam` shape key** on every damageable part, value 0: the crumpled version. The runtime blends it in as the part
  takes damage (SA swapped an `_ok` mesh for a `_dam` one; a key is the same art with the in-between for free).
  `build_vehicle.py` GENERATES it (a push-in on the part's exposed side plus a noise field shared across parts, so
  touching panels agree); an artist can replace it with a sculpted key of the same name.
* **Seats**: `seat_front_l/r` (`seat_rear_l/r`) Empties on the TOP of each seat cushion — where a seated body's hips
  go. The scene hangs the seat marker from it (the DriveCarrier pose puts the pelvis 0.452 m above the marker).
  `Vehicle.tscn` always has four seats; a two-seat car's other two need `extra_seats` in TUNING (the pickup's ride in
  the bed).
* **Materials**: any Principled BSDF (flat colours are fine). glTF cannot carry a Translucent/Diffuse/Glass BSDF
  (it exports with no colour and renders opaque WHITE) — the build replaces a Translucent one and refuses the rest.
  A material named `car` is the BODY COLOUR: the game repaints it per car from its id (GTA's carcols idea; every
  peer picks the same). A car that must keep its colours (the police car) has `paint: ""` in TUNING.

* **The collision hull is derived, and it is a GAME body**: the convex hull of the body (no wheels, no windscreen)
  with its floor raised to 0.32 m and nothing wider than the body (mirrors pulled in). Kerbs are the wheels'
  business; a hull down at the real sill height climbs them at speed.

## The two source layouts

* **An artist's authoring layout** (SPC1): the file is the artist's, with their own object names
  (`door.front`, `front.side`, `side.mirror`, …; renamed 2026-09-28 to say what each is). `build_vehicle.py` NEVER writes it: it splits the car in memory by the table
  `SOURCE_GROUPS` / `SPLIT_BY_SIDE` and exports. A new object in the file fails the build until it is added to the
  table. The honeycomb grilles ship as a placeholder plane each (`PLACEHOLDER_PLANES`) — a baked alpha-cut
  honeycomb texture is the planned replacement.
* **Component form** (PIT1, POC1): the .blend already holds the named parts and seat Empties;
  `build_vehicle.py` only places hinges and adds `dam` keys.

## Lamps and glass are MATERIAL NAMES (2026-09-28)

A lamp is any faces wearing one of these materials, on any part (a lamp on a bumper falls off with it):

| material | lit when | glows |
|---|---|---|
| `front.lamp.light` | dark (DayNight) | warm white |
| `back.lamp.light` | dark (dim), braking day and night (bright); also reversing if the car has no reversing face | red |
| `back.lamp.reverse` (optional) | rolling backward, day and night | white |

The game finds these faces by name (`Vehicle.findLampSurfaces`) and lights THEM: off, the face wears its own
material unchanged (an authored Emission lamp is shown with its glow switched off); lit, a glowing copy of that same
material, made once per material and state and shared by every car of the model. The glow is the material's own
colour when it is coloured, else the lamp's usual colour above. `build_vehicle.py` measures the right-hand lamp's
centre into `<ID>.vehicle.json` `lamps`, and the beams and tail lights stand there. Covers
(`front.lamp.cover`, `back.lamp.cover`) and holders are ordinary materials; a Transparent BSDF cover becomes clear
glass (alpha 0.2) at export, a Translucent window alpha 0.4 glass (the placeholders' `glass` is the same).
If a lamp face's part comes off, that lamp's beam goes out. Gate `tools/godot/probe_vehicle_lights.gd -- --car=<ID>`.

## Windows break, and a broken one is shot through (2026-09-28)

A window is the faces wearing the glass material (`window` or `glass`, `VehicleDamageModel.glassMaterials`) in
one of these parts, and each is one breakable pane with its own slot on the wire:

| glass in part | pane |
|---|---|
| `door_lf` / `door_rf` / `door_lr` / `door_rr` | that door's window (`win_lf` ...) |
| `chassis` | the body's glass: rear window and quarter lights (`win_body`) |
| `windscreen` | the windscreen (its part's own slot) |

So keep each door's window in the DOOR part and the rest of the side and rear glass in the chassis. The pane is found
on the mesh's own triangles, so it needs no collider and no Empty.

Every car's glass gives one hit of protection: a pistol or SMG round, a melee blow, a crash or a nearby blast
breaks it and stops there, and a rifle-class round or heavier breaks it and goes straight through. A door wrenched
loose loses its window. `glass_armor` in `tools/build_vehicle_scenes.py`'s TUNING (-> `VehicleConfig.glassArmor`) is
only for a special armoured vehicle: the weapon damage each window soaks before it breaks. Gate
`tools/godot/probe_vehicle_glass.gd -- --car=<ID> [--front]`.

## The Japanese traffic set is placeholders (2026-09-28)

KET1 kei truck, MPC1 mini patrol car, POC1 patrol car, CLC1 classic coupe (AE86 size), KEC1 kei car, TAX1 taxi and
CRT1 crate truck are BLOCK MODELS generated from real dimensions by `blender/tools/make_placeholder_cars.py` (the
table of sizes is at its top), already in component form. The earlier PIT1 pickup and POC1 patrol car were cut from
elbolilloduro's "Vegetation" pack; the owner removed them (provenance not confirmable, `assets/LICENCE_AUDIT.md`).
To model a real car: replace each named part in `<ID>.blend` keeping the names and the `seat_*` Empties (the script
never overwrites a .blend it did not write), then `build_vehicle.py -- <ID>`, `tools/build_vehicle_scenes.py <ID>`,
and `tools/godot/probe_component_car.gd -- --car=<ID>`.

## The wheel sensor

`VehicleConfig.wheelSensor`: 0 = rays (`suspension_samples` fore/aft, shipped), 1 = a swept sphere, 2 = a swept
tyre cylinder. Measured by `tools/godot/bench_wheel_sensor.gd` / `.sh` (CLAUDE.md, "Vehicles — the component car", the review).
