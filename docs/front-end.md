# front-end

The title screen, the settings and what they may touch (PLAN.md 1.3: F2 + H3, started 2026-10-09). Sections:

- The title screen is the main scene
- One owner of the settings: QualitySettings
- What a setting may touch (H3) and the fairness floors
- The settings page
- Key rebinding, FOV, window (2026-10-10)
- The full-screen menu (GameMenu) and controller rebinding
- The minimal HUD (F13)
- Debug keys are DebugWorld's only
- World density: the host's simulation load (2026-10-10)
- The loading screen and its warm-up tour (2026-10-10)
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

## The full-screen menu -- `ui.GameMenu` (user, 2026-10-10; REPLACES "The settings page" above and "The page" below)

The pause menu, the settings page and the key-bindings sub-page were three small centred `PanelContainer`s, each
translucent, opened over one another: hard to read and their transparencies stacked. They are ONE full-screen menu now,
built in code: one backdrop (`Backdrop`, alpha 0.96 in game, opaque on the title -- nothing translucent is ever put on
it, and there is no `PanelContainer` in it), tabs along the top, each tab a whole-screen page of two columns at font 22
(headings 28, rows 42 px).

| tab | what |
|---|---|
| STATUS (in game only) | PLAYER: name, faction, health, money (red in debt), loans, police / gang stars. WEAPONS: every slot with magazine / reserve, the held one marked. CARS OWNED: model, condition, in garage / out. Rebuilt each time the tab is shown. |
| CONTROLS | KEYBOARD & MOUSE (sensitivity, the 22 `BindingTable.ROWS`) beside CONTROLLER (look speed, invert Y, aim assist, the 15 `BindingTable.PAD_ROWS`), and one "Reset keyboard and controller to defaults". |
| DISPLAY | GRAPHICS (preset, render scale, shadow / view distance, FOV) beside WINDOW (mode, resolution, vsync). |
| GAME | OPTIONS (master volume, minimal HUD) beside SESSION (Resume / Restart / Quit to title / Quit game; on the title only Back). |

`PauseMenu` (`inGame`, the scene is its root node only) and `SettingsMenu` (the title's: CONTROLS / DISPLAY / GAME,
`SettingsMenu.open`) are thin subclasses. Tabs: click, LB / RB, PageUp / PageDown. Sliders show their value, switches
spell On / Off. MenuManager still owns pause / resume; Esc / pad B backs out. settings.cfg is written when the menu is
hidden or closed, and ONLY if something changed (a menu merely opened and closed writes nothing -- probes toggle pause).
Pictures: `tools/godot/shot_menu.gd` (xvfb). Probe readouts: `tabs_now`, `tab_now`, `select_tab_now`,
`status_text_now`, `capturing_now`.

**The controller is rebindable** (same request: "no game pad setting"). `BindingTable.PAD_ROWS` is the pad's OWN row
table, because a pad groups actions differently from the keyboard (RT = `fire` + `throttle`, LT = `aim` + `reverse`,
RB = `scope_zoom` + `detonate` + `vehicle_fire`, LS = `walk` + `hold_breath` + `sprint`); an action is in exactly one
pad row (unit-tested). A row's input is a button (`pad:<JoyButton>`) or a trigger (`trig:<4|5>`, captured past half
pull); a taken input is swapped, as on the keyboard. Fixed: the sticks (move, look), Start (reserved: pause), and the
menus' own A / B (`ui_accept` / `ui_cancel` are separate actions, so rebinding crouch off B does not break menus).
`KeyBindings.rebindPad` rebuilds only an action's pad button / trigger events -- its stick and keyboard events are kept
-- and `[pad_bindings] <row> = pad:<n> | trig:<axis>` stores rows that differ from project.godot (still written by
`joypad_bindings.py`, which stays the DEFAULT layout). HUD prompts on a pad now show the input bound NOW
(`KeyBindings.padSpecForPrompt` -> `BindingTable.padGlyph`), as a glyph when one ships (only l1 / r1 / x / y / dpad
left / right / up do), else spelled ("[ LT ]").

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
Gate `tools/godot/probe_minimal_hud.gd` 11/11 (control: FULL keeps all four up).

**The money row -- `ui.CashReadout` (user, 2026-10-10).** The balance had no display outside the shop menu, and the
hospital / arrest card carried the bill as a third line that pushed the English up into the kanji. Now: the respawn
card is the two words only (`入院 HOSPITALIZED`, `逮捕 ARRESTED`, `拉致 ABDUCTED` -- never money;
`probe_wanted_respawn` asserts the exact text), and the money is its own right-aligned row under the clock and the two
star rows (`HUDManager.cashTop()`; the feed starts under it). It reads `Profiles.local().balance`. On a change the
amount moved is drawn left of the balance for 4 s (`-¥15,000  ¥5,000`, red out / green in; two changes inside the 4 s
are summed), so that is where a bill is told. A negative balance (a debt, CR4) is red. Full HUD: always up; minimal:
fade id `cash`, back on a change, held while in debt. The pause menu shows the balance under its title at all times.
The captive's ransom prompt keeps its amounts (it is a decision, not a card).

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

## World density: the host's simulation load (user, 2026-10-10)

"A setting for more crowd vehicles / peds / AI attackers, in case every player's system is high end." It is NOT a
graphics setting and not per machine: `game.WorldDensity` is ONE value per session, the HOST's
(`QualitySettings.worldDensity`, `settings.cfg [world] density`, the GAME tab's "World density"), applied on the
authority only (`applyDensity`: a client's own value changes nothing until it hosts). The bodies it adds are
replicated, collidable and shootable, so every peer plays the same street and the same fight -- H3's rule
("host-decided, never scaled by a peer's hardware") extended, by the user's decision, to how many units may attack
at once.

| level | simulated cars | promoted peds / fighters | attack tokens |
|---|---|---|---|
| NORMAL (the baseline) | 12 | 8 / 6 | as crimes.json / gangs.json |
| HIGH | 16 | 12 / 8 | +1 at every star level that has a limit |
| ULTRA | 22 | 16 / 10 | +2 |

Measured on the development PC (`probe_walk_perf --deck --traffic-budget=N`, vsync on, 2026-10-10): walk_downtown
physics ms p50 6.2 / 9.3 / 13.9 and frame p95 18.1 / 18.1 / 19.6 at 10 / 16 / 22 cars; drive_downtown physics p50
13.7 / 15.0 / 21.9. HIGH is free on a desktop, ULTRA starts to show; with the Deck's CPU factor (x2.2, uncalibrated)
only NORMAL is safe there. Only the CAR column was measured; the ped and token columns are my picks in proportion
(unreviewed). Graphics (render scale, shadows, view distance) stay per machine and never change what is simulated.
Not applied under a probe (`--script`): probes set their own budgets; `set_world_density_now` is their door.

**Later the same day the levels became 20 / 26 / 32 cars** (user: "stable around 12 cars most of the time, even if it
means fewer peds"), paid for by near-only drivers, not by pedestrians: docs/open-world-simulation.md "The cars
stand was an instrument error ...". The paragraph below is the morning's.

**User decisions, 2026-10-10 (same day):** NORMAL is 12 cars, not 10 ("at least 12 -- maybe 8 cars for racing, and
a few crowd cars appearing on the road like an arcade racing game"); the HIGH / ULTRA numbers are accepted. The
levels are DATA: `game/density.json` (`Tables.DENSITY`, one row per level: traffic / walkers / fighters /
attack_tokens; the enum's built-in row only stands in for a missing file), so a level is tuned in one place.
`OW_WORLD_DENSITY=HIGH` runs any session -- the game, a debug run, a probe -- at a level without touching
settings.cfg; `probe_walk_perf -- --density=HIGH` does the same for a perf run. 12 cars on the Deck is NOT measured
(10 was the last value judged against the Deck proxy); census at 12: 6.3-10.6 simulated cars within 200 m at the
five sites run. The race rule the user described -- 8 racers AND a few ambient cars on the course -- belongs to the
racing AI (PLAN 3.4 / 2c.4): racers must not be starved by, or starve, the ambient budget.

## The loading screen and its warm-up tour (user, 2026-10-10)

`game.WorldWarmup`, built in code by `FrontEnd` when the island scene comes up (once per world load). A black cover
("LOADING n / N") stays up while it (1) waits for this machine's player, (2) visits up to 8 region centres of the
places record at least 450 m apart: it sets `ZoneManager.setStreamFocus` there -- the streamer loads those zones
exactly as for a player standing there -- and turns a camera of its own through a circle so every material in view is
compiled and uploaded; a site is left when `streamingPendingNow() == 0` (>= 1.5 s) or after 10 s, the whole tour
after 60 s; (3) clears the focus, hands the view back and waits for the streamer to go quiet round the player.

- **The player is never moved.** Only the focus and a camera travel: a carried body would be clamped by the host
  as a speed hack in co-op, would fall, and would drag traffic and the crowd with it. The focus feeds ONLY the load /
  unload decision (`streamDistXZ`); traffic, the crowd, AI and reclaim keep measuring to real players. The body is
  held (`InputContext.HELD`) and invulnerable behind the cover. Local per peer.
- **What it buys, and what it does not:** shader / pipeline compilation and the first disk read happen behind the
  cover instead of as the hitch on the first visit. The toured zones are UNLOADED again, so their meshes and textures
  are read back (from the OS file cache) when the player really goes there -- it does not hold VRAM. The hitch
  reduction itself is NOT measured yet (it needs a windowed A/B of probe_walk_perf's worst frames with and without).
- Cancel / B / Esc skips the tour. Off under a probe (`--script`), on the headless display, in DebugWorld (it only
  starts for World.tscn), with `OW_NO_WARMUP=1`, and with the user argument `-- --no-warmup` (a debug session that
  wants the island at once); `OW_WARMUP=1` forces it. The user accepted a 15-60 s tour behind the cover (2026-10-10).

Gate: `probe_world_warmup.gd` 11/11 (cover up from the first frame to the end; the player moved 0.00 m; loaded zones
110 -> peak 169 during the tour; held + invulnerable meanwhile; focus, hold and invulnerability gone at the end; the
streamer quiet again) and `-- --control` (no sites: nothing beyond the player's own zones loads, 110 -> 110).

**Skipping the tour (user, 2026-10-10: "so I do not wait for the tour every time when testing").** GAME tab,
"Loading tour" (`QualitySettings.loadingTour`, `settings.cfg` `[world] loading_tour`, default on, client-local): off
= `FrontEnd.startWarmup` adds no `WorldWarmup` and the world is playable at once (the streaming and shader
compilation the tour hides then happen in the first minutes of play). The other ways stay: `-- --no-warmup` on the
command line, `OW_NO_WARMUP=1`, and it never runs headless or under `--script`.
