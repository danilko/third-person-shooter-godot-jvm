# front-end

The title screen, the settings and what they may touch (PLAN.md 1.3: F2 + H3, started 2026-10-09). Sections:

- The title screen is the main scene
- One owner of the settings: QualitySettings
- What a setting may touch (H3) and the fairness floors
- The settings page
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

## What is not done yet

- Host / Join / Continue run through FrontEnd but have no probe of their own yet (Host = the F6 path, Join = F7).
- Key / pad REBINDING, resolution / window mode, FOV, subtitles, head-bob (F2's list); a Deck preset driven by
  `perf_budget.json` (needs the F10 Deck run); LAN discovery for Join.
- F13: the HUD's show-on-change policy and the minimal / full toggle reading `[hud] mode`.
