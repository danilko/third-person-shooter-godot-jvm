# front-end

The title screen, the settings and what they may touch (PLAN.md 1.3: F2 + H3, started 2026-10-09). Sections:

- The title screen is the main scene
- One owner of the settings: QualitySettings
- What a setting may touch (H3) and the fairness floors
- The settings page
- Key rebinding, FOV, window (2026-10-10)
- The minimal HUD (F13)
- Debug keys are DebugWorld's only
- Gate
- What is not done yet

---

## The title screen is the main scene

`project.godot run/main_scene` is `ui/TitleScreen.tscn` (it booted straight into `World.tscn`; co-op was the debug keys
F6 / F7, which still work in the world). `ui.TitleScreen` builds itself in code: Continue (enabled only with an
autosave, `SaveSystem.autosaveSlot`), New game, Host co-op, an address + Join co-op, Settings, Quit; the first enabled
button takes focus so a pad works at once (docs/input.md).

A choice that needs the world to be UP first (load the autosave into live bodies, host, join) is carried across the
scene change by the `FrontEnd` AutoLoad: `FrontEnd.start(node, action, address)` changes the scene, and its
`_process` runs the action ONCE, the first frame the world's local player exists (`lastRunNow()` says what ran).
`FrontEnd.toTitle` (the pause menu's new "Quit to title") leaves any session, unpauses and loads the title. Every gate
still names its scene explicitly, so the main-scene change touches none of them.

## One owner of the settings: QualitySettings

`game.QualitySettings` (AutoLoad, after `ViewDistance`) owns `user://settings.cfg` -- `[graphics] preset render_scale
shadow_distance view_distance`, `[controls] look_sensitivity pad_look_scale invert_y aim_assist`, `[audio] master`,
`[hud] mode`. It applies on load, on every change, and again within 1 s of a new scene or a new local player (a world
loads its own sun; a respawn makes a new body):

- render scale -> the root viewport's `scaling_3d_scale` (0.5..1);
- shadow distance -> the scene's `SunLight` `SHADOW_MAX_DISTANCE` (the moon keeps its own 256 m);
- view distance -> `ViewDistance.streetDistance` (unless `OW_VIEW_DISTANCE` is set for a measurement);
- look sensitivity -> `TPSCameraController.yaw/pitchSensitivity` (x 0.07); pad look / invert / aim assist ->
  `PlayerCameraController` (x 220 / 150 deg/s);
- master volume -> the Master bus (the only bus there is; SFX / music buses when the audio has them);
- HUD mode -> stored only, until F13 reads it.

Presets: LOW 0.67 / 150 m / 300 m, MEDIUM 0.85 / 300 / 400, HIGH 1.0 / 600 / 500 (= the shipped look, the default).
A graphics value moved by hand makes the preset CUSTOM unless it lands back on one.

## What a setting may touch (H3) and the fairness floors

Only CLIENT-LOCAL knobs -- what this machine draws and how its human aims. Nothing a co-op peer could fight over is a
setting: enforcement units, AI decisions, damage, the promoted crowd (walkerBudget / promoteDistance) and simulated
traffic stay host-decided (H3's design, PLAN.md). Two floors so a low preset is never an advantage or a blind spot:
the view distance never goes below 250 m (the engagement range) and the sun's shadows never below 80 m (a character's
shadow round a corner must not be a high-settings advantage).

## The settings page

`ui.SettingsMenu.open(parent, returnFocusTo)` -- one row per value (an OptionButton for the preset, HSliders,
CheckButtons), built in code; from the pause menu (a "Settings" button PauseMenu adds above Quit) and from the title.
Back or ui_cancel (Esc / pad B) saves and closes; while it is open MenuManager ignores pause / back. On a pad: D-pad
up / down moves, left / right moves a slider or the preset, A toggles.

## Key rebinding, FOV, window (PLAN.md 1.3 rest, 2026-10-10)

**Rebinding is per CONTROL ROW, not per action.** project.godot gives several actions one key on purpose -- W is
`forward` AND `throttle`, Space is `jump` / `upright` / `handbrake` / `drift`, Shift is `sprint` / `hold_breath` /
`brake`, and the `movement` action carries all six movement keys. `control.BindingTable` (engine-free, `BindingTableTest`)
lists 22 rows, each the actions sharing a key; rebinding a row moves the key on every action in it, so the car and the
body never split. A key another row holds is SWAPPED to that row (never double-bound). Esc is reserved (pause / back);
the slot numbers, the wheel zoom and the pad are not rebindable (the pad's layout is `joypad_bindings.py`'s table and
its prompts read it; on the Deck, Steam Input remaps a pad). `control.KeyBindings` applies it: an affected action's
keyboard/mouse events are REBUILT from every row that holds it (editing events one by one dropped a key from the shared
`movement` action in a swap) and its pad events are kept. Defaults are read off the InputMap once, before any user
binding; `[bindings] <row> = key:<physical> | mouse:<index>` stores only rows that differ.

**Prompts follow the binding.** Prompts are still written with the default letter ("[ F ]  Enter vehicle", none = E);
`KeyGlyph.actionOf` names its action and `KeyBindings.shownKey` returns the key bound now, which the HUD draws (as a glyph
when one ships -- only B / E / F / H do -- else as "[ T ]"). A pad still shows the pad glyph.

**The page**: Settings -> "Key bindings..." (`ui.KeyBindingsMenu`): a row's button, then the new key or mouse button;
Esc cancels a capture; "Reset to defaults"; Back / Esc saves. One `pressed` handler reads WHICH row from the focused
button: a bound Callable (`MethodCallable.bindUnsafe`, either overload) fails inside `connect()` under godot-jvm rc1 with
"Cannot call a method on a previously freed instance".

**FOV**: `[view] fov_offset` (-10..+20 deg) is added to every on-foot FOV (TPS and FPS share `TPSCameraController
.setCameraFov`, the one writer) and to the vehicle camera's base, never to a scope's declared FOV; the scope's
sensitivity ratio uses the offset FOV. **Window**: `[display] window_mode` (WINDOWED / FULLSCREEN borderless /
EXCLUSIVE), `resolution` ("" = leave the size; 1280x720 / 1280x800 (Deck) / 1600x900 / 1920x1080 / 2560x1440, centred),
`vsync`; applied only when changed and never on the headless display server.

**Subtitles are deferred (decision 2026-10-10)**: nothing speaks yet -- the radio chatter is already text -- so a
subtitle switch would toggle nothing. It comes with F5's speakers (objectives told by NPCs), PLAN 2.1.

Gate `tools/godot/probe_rebind.gd` 20/20 (in nightly_gates): the page rebinds Use to T through a real key event (pad
events kept), the Door prompt then names T (control: E before), a swap with Reload, forward -> Up moves throttle and
`movement` too and a swap inside `movement` loses no key, settings.cfg round trip (save, reset, reload), +10 deg FOV
reaches the camera. It backs up and restores the user's settings.cfg.

## The minimal HUD (F13)

`[hud] mode = minimal` (Settings: "Minimal HUD"; default full). `HUDManager.tickMinimal` fades four always-on widgets
and brings each back when its state CHANGES or must be seen, then holds it `HOLD_SECONDS` (4) and fades it in 0.4 s:
health (FootHUD/Health -- a hit; held below 35 %), the weapon panel (switch / shot / reload / holster; held while
aiming), the minimap (held in a vehicle, with a waypoint, or wanted), the game clock (always faded in minimal: the
light tells the time, the map shows it). The rest was already show-on-change or self-gated (stars hidden at zero and
flashing on a change, the slots column on a switch, the feed, hit marker, damage indicator, prompts). A fade is a
MODULATE under the situation table's visibility, so they never fight; `full` = alpha 1, the HUD exactly as before.
Gate `tools/godot/probe_minimal_hud.gd` 6/6 (control: FULL keeps all four up).

## Debug keys are DebugWorld's only (user, 2026-10-09)

"For main world, remove the F1-F12 debug testing, to not let the user accidentally trigger it." `World.tscn` no longer
has the `DebugHarness` node, so the island has none of F1-F12, Shift/Ctrl variants or the debug console; DebugWorld
(and the hosts/ test scenes) keep it. Consequence: the Ctrl+F9 bug-report line exists in DebugWorld only -- in the
main world a position is reported from the map's postal grid.

## Gate

`tools/godot/probe_front_end.gd` 15/15 (in nightly_gates): the title is the main scene and a button has focus;
Continue is enabled exactly with an autosave; New game reaches the world with its player; LOW / HIGH reach the sun,
the render scale and the view distance; the floors hold (control: values asked below them); a hand value makes the
preset Custom; Settings opens from the pause menu and its close writes settings.cfg (read back); Quit to title lands
on the title unpaused. The probe backs up the user's settings.cfg and puts it back.

The title's world actions have their own gates (2026-10-10), pressed as the buttons: `probe_title_actions.gd
--role=continue` 7/7 (New game, walk 6 m, autosave, Quit to title, Continue is enabled, press it: the player is back
0.15 m from the saved spot; the user's autosave is backed up) and `tools/net/run_title_coop.sh` (Host co-op on one
title, Join co-op 127.0.0.1 on another: both see the session, `NetworkManager.session_now`, and both players). Both in
nightly_gates.

## What is not done yet

- Subtitles (with F5's speakers, above), head-bob (there is no head-bob to switch off yet); a Deck preset driven by
  `perf_budget.json` (needs the F10 Deck run); LAN discovery for Join.
- F13: the HUD's show-on-change policy and the minimal / full toggle reading `[hud] mode`.
