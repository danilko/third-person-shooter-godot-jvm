# input

The gamepad and the input map (PLAN.md 1.1 / F1, started 2026-10-09). Sections:

- The pad layout is one table
- Which device the human is on
- On foot: analog walk, a look RATE, the turn boost
- Aim assist (pad only)
- In a vehicle: the triggers are the pedals
- Menus and pause
- Prompts show the pad's glyph
- The interact key uses ONE thing (AR4, input half)
- What is not done yet

---

## The pad layout is one table

`tools/input/joypad_bindings.py` owns every joypad event in `project.godot` (`--check` exits 1 when the file differs).
It strips the `[input]` section's joypad events and writes them back from its `PAD` table; keyboard events are never
touched, except on the actions the tool creates (`KEYS`). Edit the table and re-run it; never add a pad event in the
editor's Input Map (the next run would delete it).

Steam Deck / Xbox positions, GTA V / PUBG console practice:

| on foot | | in a car | |
|---|---|---|---|
| left stick | move (part way = walk) | left stick | steer |
| right stick | look | right stick | look while aiming (RB) |
| LT / RT | aim / fire | LT / RT | reverse (brakes first) / throttle, analog |
| A | jump | A | handbrake (+ drift) |
| B | crouch | B | -- (crouch = descend in a helicopter) |
| X | reload | X | reload / flip upright |
| Y | enter a vehicle | Y | exit |
| LB | weapon wheel (pick with either stick) | RB | fire a passenger weapon (aims too) |
| RB | scope zoom cycle; detonate | L3 | NOS (sprint) |
| L3 | stealth walk; hold breath | R3 | rear view |
| R3 | shoulder swap | | |
| D-pad | up map, down crawl, left holster, right interact | | |
| View | first / third person | Start | pause |

Not on the pad on purpose: `weapon_slot_0..6` (the wheel), `drop` (rare; the D-pad is full), `brake` (LT reverses,
which brakes first), `scope_zoom_in/out` (RB cycles). `flashlight` (PLAN.md 3.2, keyboard T) has NO pad button yet: the
D-pad and the face buttons are full, so its default is the user's to pick; the controller page's "Flashlight" row
binds one meanwhile (a pad row with no default reads as unbound). T, not CS 1.6's F: F is `use_carrier` here;
`probe_rebind.gd` moved its "free key" from T to Y.

**One input, two contexts, two actions.** RT is fire on foot and the throttle in a car. That is done with two actions
(`fire`, `throttle`) each read only by its own context (PlayerController's on-foot / vehicle halves) -- never one
action read in both. New actions for it: `throttle` / `reverse` (W / S + the triggers), `vehicle_fire` (left mouse +
RB), `pause` (Esc + Start), `look_left/right/up/down` (right stick only).

**Deadzones.** Godot rescales an action's strength from its deadzone to 1. Stick actions get 0.2 (a half-pushed stick
reads ~0.4); `throttle` / `reverse` 0.1; `fire` / `aim` 0.25 (a quarter pull). The default 0.5 made a half trigger read
as NOTHING (measured: 0 m/s at half throttle).

**Godot 4.7's built-in `ui_accept` / `ui_cancel` carry no pad event** (`ui_up..ui_right` do carry the D-pad and the
left stick). The table overrides both with A / B and restates their keyboard defaults (by keycode, as Godot has them);
without it no menu could be driven from a pad at all.

## Which device the human is on

`control.InputDevice` is the one owner of "is this a pad player?": `game.GameManager._input` feeds it every event; a
pad button press or a stick past 0.35 makes it `PAD`, a key / mouse button or a mouse move past 4 px makes it
`KEYBOARD_MOUSE` (so a resting stick's drift or a nudged mouse does not flip it). Read by the analog car controls, aim
assist, the vehicle camera's aim rule and the prompt glyphs. `GameManager.input_device_now()` / `force_input_device()`
for probes.

## On foot: analog walk, a look RATE, the turn boost

- `PlayerController`: a movement stick pushed less than `ANALOG_WALK_BELOW` (0.65) is a walk (GTA / RDR2). Measured
  7.97 m/s full, 3.00 m/s at 0.45.
- `PlayerCameraController.padLook`: the right stick is a RATE (deg/s at full deflection: `padYawRate` 220, `padPitchRate`
  150), shaped by `padCurve` 2 (fine aim near the centre), x `padAimScale` 0.55 while aiming, x the scope ratio like the
  mouse. Held fully over for `padBoostDelay` 0.25 s the yaw ramps up by `padTurnBoost` 0.7 over `padBoostRamp` 0.35 s
  (a 180 should not take a second). `padInvertY`. Measured: 51 deg in 0.25 s full, 7 deg at half (the curve), 304 deg
  in 1 s held (205 without the boost).

## Aim assist (pad only)

`camera.AimAssist.pick(self, camera, cone, range)`: the living `Character` nearest the crosshair within a cone, not the
shooter and not another `Player` (no help onto a co-op friend), within `assistRange` 70 m, with a clear world line from
the camera to its chest (1.25 m, lower for the active crouch / crawl capsule). Two effects, both only while
`InputDevice.pad()` and `aimAssist`:

- **the ADS snap** (CoD): pressing aim pulls the view onto the nearest body within `assistSnapCone` 7 deg over
  `assistSnapTime` 0.14 s. Measured 3.47 -> 0.37 deg; with assist off 3.18 -> 3.18; a mouse player 3.18 -> 3.18.
- **friction**: the stick's look rate x `assistSlowdown` 0.45 while the crosshair is within 1.5 body radii of a body.
  Measured 1.24 vs 2.75 deg in 4 frames.

No magnetism while moving (rotational assist) -- add it only if a Deck play test asks; CS has none.

## In a vehicle: the triggers are the pedals

`gatherVehicleInput`: `motor = throttle - reverse` (analog: half RT 10.5 m/s vs full 21.2 after 1.5 s; LT -11.0); a
keyboard player's `forward` / `back` still add in (the same W / S; probes and scripts press those actions), but NOT on a
pad, where the left stick's forward would be a second throttle. `fire` likewise: `vehicle_fire`, plus `fire` only on
keyboard and mouse. `VehicleCameraController.isAimingOrFiring` follows the same rule, or reversing on LT swung the
camera into aim; its right-stick look is `padLookRate` 160 deg/s while aiming.

## Menus and pause

`MenuManager`: `pause` (Esc / Start) opens and closes the pause menu; `ui_cancel` (Esc / B) only BACKS OUT of an open
store or pause menu -- B is crouch in play and must never open a menu. Opening the pause / game-over menu focuses its
first button (`focusFirstButton`), so the D-pad and A work at once.

The weapon wheel (`WeaponRadialMenu.selectFromStick`): whichever stick is pushed further past 0.5 points at the slot,
the pointer's angle rule; releasing LB closes on it.

## Prompts show the pad's glyph

`KeyGlyph.padGlyph(key)` maps a prompt's key letter to its action's pad input from the table (E -> D-pad right, F ->
Y, H -> D-pad left, R -> X, B -> RB, G -> LB, M -> D-pad up) and `texturePath(key, pad)` to Kenney's Steam Deck glyph
(`assets/ui/prompts/steamdeck_*.png`, CC0, Double). `CharacterHUD` re-draws a shown prompt when the device changes.
Unit test `KeyGlyphTest`.

## The interact key uses ONE thing (AR4, input half)

Before: Door, ShopCounter, AmmoSupply and Pickup each polled `Input.isActionJustPressed("interact")` themselves, so one
E beside a door and a pickup did BOTH, and no AI or remote body could use anything through one path. Now:

- `UserCommand.interact` (PlayerController: the interact key's edge, same as `useLadder`); `Character.applyInput` calls
  `control.Interactions.useBest(this)` when it fires (alive, on foot).
- The OFFERS are the prompts: every `EventBus.interactPrompt(source, on, label)` passes through
  `Interactions.prompt`, and a source that implements `control.Interactable` with an E-keyed label (KeyGlyph: no hint
  = E; the car's "[ F ]" prompt is not E) is on offer until it withdraws. The HUD shows the NEWEST prompt, so E uses the
  newest live offer -- what the prompt says is what E does.
- `Door`, `ShopCounter`, `AmmoSupply`, `Pickup` implement `interact(actor)` with exactly what their poll did (the
  counter / supply compare the actor by INSTANCE ID, never by wrapper -- the stale-wrapper quirk).
- `ShopMenu.closedThisFrame` has one frame of slack now: E opens the counter from the PHYSICS step, and a press that
  lands between frames is "just pressed" both in the process step that closed the menu and the next physics step
  (probe_weapon_counter caught the reopen).
- Gate `tools/godot/probe_interact.gd` 6/6: a manual door and a waiting pistol both offer (control: 2 offers); E takes
  the pistol (the newest) and the door does not move; E again opens the door.
- Still polling on purpose: `RespawnSystem`'s "[E] pay" ransom (the player is dead -- no body runs a command) and the
  UI's own keys (ShopMenu, the map). No MSG_INTERACT yet: each interactable keeps its own host path (shop request,
  pickup request, supply use), unchanged.

## Overlays push INPUT CONTEXTS (AR4, input half, 2026-10-10)

Before: five owners wrote ONE `Character.inputBlocked` boolean and set the mouse mode themselves -- the weapon wheel,
the shop, the map, the console and an arrest. With the wheel held over the map, closing the map wrote `false` and
`CAPTURED` under the still-open wheel; and the wheel's release handler ran even when the press had been refused (a
reload), clearing whatever else was open. Now:

- `control.InputContextStack` on every Character (`inputContexts`), engine-free and unit-tested
  (`InputContextStackTest`): each owner pushes under its OWN name (`radial`, `shop`, `map`, `console`, `pause`,
  `arrest`) and pops that name, in any order; a pop of a name that is not there is a no-op. The top decides.
- `control.InputContext`: `MENU` (blocks the controller, shows the pointer) and `HELD` (blocks, pointer stays
  captured: an arrest). Gameplay is the EMPTY stack. On foot vs in a vehicle is deliberately NOT a context: it is
  already derived from the seat (`currentVehicleNode`), and a pushed copy would be a second latch.
- `Character.inputBlocked()` (was the field) reads the stack; the pointer follows the top context, applied by the
  Character only for the body this machine plays (a host arresting a client's body must not free its own mouse).
  `MenuManager`'s pause is a context too, so resuming over an open shop or map keeps their pointer.
- Readouts: `input_blocked_now()`, `input_contexts_now()` ("map:MENU,radial:MENU").
- Gate `tools/godot/probe_input_contexts.gd` 7/7 (in nightly_gates; under xvfb it also checks the pointer): map, wheel
  over it, map shut -> still blocked with the pointer free; wheel released -> free and captured; a stray wheel release
  under the map does not free the body. `--legacy` (the map's close also clears the wheel, what the one flag did)
  fails the case.

**Found with it: E could not close the shop above 60 fps.** `ShopMenu.closedThisFrame` guarded the reopen with one
PROCESS frame of slack, but E opens the counter from the PHYSICS step; with 2+ process frames per physics step (a
144 Hz display, an uncapped headless run) the same held press reopened the store two frames after closing it --
`probe_weapon_counter`'s "interact opens it again and interact closes it" had been failing on HEAD for this reason.
Now an E close refuses a reopen until E is released, at any frame rate; the probe holds its press like a person does.

**MSG_INTERACT is deferred to 3.0 (decision 2026-10-10).** Every interactable today already has a correct path: the
door is cosmetic and local per peer (the no-sync rule), a pickup swap rides MSG_PICKUP_REQUEST and its tested grant
policy, the counter's menu is local UI whose purchase is MSG_SHOP_REQUEST, the ammo supply rides MSG_SHOP_REQUEST,
and AI bodies are the host's, so they call `interact` directly. One generic message would have no consumer until a
client's use must change HOST state with no item transaction behind it -- PuzzleStation, captive actions (cuff /
lead / load), seats in 3.0 -- so it is built with the first of them, not ahead of it.

## Gate

`tools/godot/probe_gamepad.gd` 18/18 (in `tools/nightly_gates.sh`): real joypad events through
`Input.parse_input_event` on a real Player in WorldSystems.tscn -- device switching, the analog walk, the look rate /
curve / boost, the ADS snap with both controls, friction, Start pauses / B never does / B backs out, Y enters a car,
RT throttle (half slower than full), LT reverse, the triggers neither fire nor aim in a car.

## What is not done yet

- AR4's input half, rest: a CLOSE_UP / PUZZLE context when 3.0's CloseUpMode lands (pushed like the others), and
  MSG_INTERACT with its first host-state consumer (3.0, above).
- UI focus in the shop and the map (the pause / game-over menus are done); a settings page for sensitivity, invert,
  aim assist (F2).
- Rebinding (F2), a Deck play test of the rates (F10), rumble.
