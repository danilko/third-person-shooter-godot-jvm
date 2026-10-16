# assets/audio — every sound the game plays, and what is still missing

**Rule: no sound is generated in code.** A sound is a file in this folder. Code that wants a non-weapon
sound names it in `com.openworld.audio.Sound` and plays it through `com.openworld.audio.Sounds`, which
loads `<name>.ogg` (else `<name>.wav`). A missing file is silence, and the game prints
`[Sounds] missing audio: ...` once. Weapon fire/reload sounds are the exception: each weapon scene names
its own files (`fire_audio`, `reload_audio`).

Licence: only CC0 / MIT / public-domain audio, credited in `CREDITS.md` (same rule as art and map data).
Format: `.ogg` for anything longer than ~1 s or looping, `.wav` for short one-shots. Mono for 3D sounds.

## Shipped

| file | used by | source / licence |
|---|---|---|
| `weapons/<ID>_fire.wav` | PIS1, PIS2, DUP1, REV1, SMG1, ASR1, ASR2, SHG1, SNR1 | Still North Media, *The Free Firearm Sound Effects Library*, **Prepared** edition (NEAR take of a real gun per weapon), CC0 |
| `weapons/<ID>_reload.wav` | the same nine | the same library, **Raw** edition: mag out / in, slide, bolt, pump, cylinder takes, laid out over each weapon's reload time, CC0 |
| `weapons/<ID>_swing.wav` | MEW1, MEW2, BAT1, Fist (`fire_audio`, played on every swing) | Still North Media, *Medieval Weapons Sound Effects Library* (Weapon Textures), CC0 |
| `hit_marker.wav` | `Sound.HIT_MARKER` (HitMarker) | Kenney *Interface Sounds* `tick_002`, CC0 |
| `Rifle_*.wav`, `Pistol_*.wav` | **unused since 2026-10-08** (every weapon has its own sounds now) | Johnny Rouddro, Godot TPS (Asset Library #716), MIT |

**Weapon sounds are BUILT, not hand-edited**: `python3 tools/audio/build_weapon_sfx.py` cuts them from the source
libraries and normalises them; its `RECIPES` table says which real gun and which takes each weapon uses (e.g. ASR1 =
AK-47, SNR1 = Mosin-Nagant, SHG1 = Benelli Nova, REV1 = S&W 642 pitched down 12 %). To change a sound, change the
recipe and rebuild, then `godot --headless --path . --import`. Gate: `tools/godot/probe_weapon_audio.gd`.

**One loudness scale** (max momentary loudness, BS.1770, peaks limited at -1 dBFS): gunshots -13 LUFS (the old
`Rifle_fire.wav` level) with a per-weapon offset (pistols -2, heavy guns +1..+2), reloads -24, swings -20. The old
reloads were -33 / -37, almost inaudible under a shot. A new sound joins at its category's level.

**Source libraries** (CC0, downloaded once, outside the repo, each with `LICENSE.txt` + a per-file `SOUNDS.csv`
listing source URL, authors and possible uses): `/data/danilko/game_assets/audio/`
`still_north_firearms_cc0` (Prepared 56 + Raw 724 takes, 22 guns), `still_north_medieval_cc0` (44 swing/draw/bow
textures + 48 weapon-on-weapon impacts), `kenney_cc0` (all 10 Kenney audio packs). Candidates for what is still
missing: `SHORTLIST.md`.

## Wired in code (`SoundTest` checks this table lists every `Sound`)

A `Sound` with N takes is `<file>_1` .. `<file>_N` (one picked per play). Everything except `hit_marker` and
`siren` (`python3 tools/audio/build_siren.py`) and `engine/*` (`python3 tools/audio/build_engine.py`; `--check` compares it with `EngineAudio.BAND_HZ`) is BUILT by `python3 tools/audio/build_sfx.py` (its `SPECS` table: source takes, layers, loudness), then
`godot --headless --path . --import`. **None of it was auditioned by ear** (2026-10-08): the picks are by name and
waveform; listen in game and change the row. Gate: `tools/godot/probe_sfx.gd`.

| file | `Sound` | what plays it | source (all CC0) |
|---|---|---|---|
| `hit_marker` | `HIT_MARKER` | the local player's hit confirmed (HitMarker), 2D, short tick | shipped |
| `siren` | `SIREN` | an emergency vehicle on a call (Vehicle.refreshEmergency), 3D, LOOPING (the loop is in the WAV's `smpl` chunk). the AMBULANCE's two-tone ピーポー (AMB1), and the fallback for the other two (user 2026-10-12: one siren first, then split after hearing it) | Freesound thabigm 758375 (CC0; HQ preview, 2 cycles looped by `tools/audio/build_siren.py`) |
| `siren_police` | `SIREN_POLICE` | a police vehicle on a call (POC1, MPC1, ARV1), 3D, LOOPING: one slow wail, 5.6 s, 570 -> 1 270 -> 670 Hz. NOT a Japanese patrol car (none CC0 on Freesound): a New York one | Freesound MultiMax2121 156869 (CC0; HQ preview, `tools/audio/build_siren.py`) |
| `siren_fire` | `SIREN_FIRE` | a fire engine / ladder truck on a call (FIE1, LAT1), 3D, LOOPING: one faster, higher wail, 4.9 s, 750 -> 1 630 -> 720 Hz. NOT a Japanese fire engine (no bell): a Toronto one | Freesound TRP 717906 (CC0; HQ preview, same script) |
| `engine/start` | `ENGINE_START` | a player getting into a standing car (carrier.vehicle.EngineAudio), 3D, one shot: the starter and the catch | Freesound vacuumfan7072 322552 (CC0; HQ preview, cut by `tools/audio/build_engine.py`) |
| `engine/idle` | `ENGINE_IDLE` | a running car standing or pulling away, 3D, LOOPING (`smpl` chunk). Engine sounds play only for running cars within 45 m of the camera, at most 6 at once | same take, its idle |
| `engine/low` | `ENGINE_LOW` | the engine at ~2 850 rpm (firing 95 Hz), LOOPING, pitched 0.65-1.6 by engine speed and cross-faded with its neighbours | Freesound dezoris 183654 (CC0; HQ preview): one dyno pull, re-timed to a steady pitch by `tools/audio/build_engine.py` |
| `engine/mid` | `ENGINE_MID` | ~4 500 rpm (150 Hz), as above | same pull |
| `engine/high` | `ENGINE_HIGH` | ~6 600 rpm (220 Hz), as above | same pull |
| `vehicle/horn` | `CAR_HORN` | the horn held (H / D-pad down in a car; carrier.vehicle.CarSounds), 3D, LOOPING (`smpl`): 0.145 s of a 407 Hz beep, stopped on release. Replicated (snapshot flag bit 7); heard within 120 m | Freesound misperpodcast 733553, a 2008 Fiat Panda (CC0; HQ preview, cut by `tools/audio/build_vehicle_sfx.py`) |
| `vehicle/skid` | `CAR_SKID` | tyres squealing while they slide (sideways, a locked brake, the handbrake at speed), 3D, LOOPING (`smpl`), level and pitch by how hard; within 60 m, at most 4 cars | Freesound audible-edge 71737, a Chrysler LHS (CC0; HQ preview, same script) |
| `sfx/car_crash_light` | `CAR_CRASH_LIGHT` | a car's scored crash of 2.5-8 m/s (VehicleDamageModel), louder with the speed; within 80 m | Kenney `impactMetal_medium` + `impactPlate_medium` layered |
| `sfx/car_crash_heavy` | `CAR_CRASH_HEAVY` | a crash of 8 m/s and more | Kenney `impactMetal_heavy` + `impactPlate_heavy` + Sci-fi `explosionCrunch`, layered, pitched 0.9 |
| `sfx/impact_flesh` | `IMPACT_FLESH` | a bullet into a body (ImpactManager, by SurfaceType) | Kenney `impactPunch_medium` |
| `sfx/impact_metal` | `IMPACT_METAL` | a bullet into metal (vehicles, machinery) | Kenney `impactMetal_light` |
| `sfx/impact_stone` | `IMPACT_STONE` | a bullet into stone / concrete / anything untagged | Kenney `impactPlate_light` |
| `sfx/impact_wood` | `IMPACT_WOOD` | a bullet into wood | Kenney `impactWood_light` |
| `sfx/impact_glass` | `IMPACT_GLASS` | a bullet into glass that does not break | Kenney `impactGlass_light` |
| `sfx/splash` | `SPLASH` | a body dropping into water faster than 2 m/s (Character.setInWater, world.Splash), 3D | Freesound Nox_Sound 585744 (CC0; HQ preview, 3 jumps sliced) |
| `sfx/splash_small` | `SPLASH_SMALL` | a bullet or a grenade into water, a gentle entry, a wading step (world.Splash) | Freesound Robo9418 841834 (CC0; HQ preview) |
| `sfx/swim_stroke` | `SWIM_STROKE` | a swimmer's stroke every 1.6 m (CharacterAudio) | Freesound craigsmith 438845 (CC0; HQ preview, 4 strokes sliced) |
| `sfx/melee_hit_flesh` | `MELEE_HIT_FLESH` | a melee blow landing on a body (MeleeItem) | Kenney `impactPunch_heavy` |
| `sfx/melee_hit_hard` | `MELEE_HIT_HARD` | a melee blow on a car, a wall, anything not a body | Still North Medieval Weapon Impacts |
| `sfx/explosion` | `EXPLOSION` | every explosion (ExplosionManager.playBlast), every peer | Kenney Sci-fi `explosionCrunch` + `lowFrequency_explosion` layered |
| `sfx/door_open` | `DOOR_OPEN` | a hinged door starting to open (world.Door) | Kenney RPG Audio `doorOpen` |
| `sfx/door_close` | `DOOR_CLOSE` | a hinged door shutting | Kenney RPG Audio `doorClose` |
| `sfx/door_slide` | `DOOR_SLIDE` | an automatic sliding door or a ticket-gate flap, both ways, at the hinged door's level (user, 2026-10-08) | Kenney Sci-fi `doorOpen`, pitched down |
| `sfx/dry_fire` | `DRY_FIRE` | fire pressed on an empty gun with no reserve (WeaponController) | Still North Raw: Walther PPQ, Tikka, Ruger 10/22 dry fire |
| `sfx/weapon_draw` | `WEAPON_DRAW` | a firearm raised at the end of a switch | Still North Raw: Tikka, Arisaka, PPSh safety off |
| `ui/click` | `UI_CLICK` | a menu row, a wheel card, a pause button; also a store menu, the map, the weapon wheel and the pause menu opening / closing (their own open/close sounds were removed, user 2026-10-08) | Kenney UI Audio `click` |
| `ui/back` | `UI_BACK` | the map waypoint cleared | Kenney Interface Sounds `back_001` |
| `ui/confirm` | `UI_CONFIRM` | a store row taken | Kenney Interface Sounds `confirmation_001` |
| `ui/error` | `UI_ERROR` | (not played yet: a refused purchase) | Kenney Interface Sounds `error_001` |
| `ui/waypoint` | `UI_WAYPOINT` | a map waypoint set | Kenney Interface Sounds `select_001` |
| `ui/mission_start` | `MISSION_START` | a mission started (HUDManager, every peer) | Kenney Music Jingles `jingles_STEEL00` |
| `ui/mission_complete` | `MISSION_COMPLETE` | a mission completed | Kenney Music Jingles `jingles_STEEL07` |
| `ui/mission_fail` | `MISSION_FAIL` | a mission failed | Kenney Music Jingles `jingles_STEEL09` |

## Not wired, no file (each needs a `Sound` entry, a call site, and a file)

Weapons
- ATL1 launcher: fire, reload; rocket flight loop (Kenney Sci-fi `thrusterFire`)
- Throwables (FRG1, PIB1, FLA1, SMO1, REC1): throw, bounce, pin; flashbang ringing, smoke hiss, remote-charge
  stick and detonator click (the blast itself is `EXPLOSION`)
- Holster, scope in/out, pickup, SNR1 bolt cycle after a shot, a melee draw (Still North medieval dagger / katana
  draw + sheath are ready)
- Ricochet, whiz-by
- Glass shatter (car crash, shop / train window): the layered Kenney placeholder was REMOVED (user, 2026-10-08: awkward); a real CC0 shatter is on SHORTLIST

Vehicles
- Engine loops PER CLASS (kei, truck, motorcycle, boat, plane): today every wheeled vehicle has the one car engine (`engine/*`); gear change, turbo, exhaust pops
- Scrape along a wall, tyre burst; a crash a REMOTE peer simulates is silent here (crash sounds play where the car is simulated)
- Door open / close, boost (NOS), gear change
- Wreck burning loop and vehicle explosion; street pole / bollard knocked down

Characters
- Jump, fall damage. FOOTSTEPS and the LANDING thud were built and REMOVED (user, 2026-10-08: rarely heard, two engine calls per body per tick)
- Pain, death (keep generic, no voice lines)

World
- Lift doors + arrival chime
- 踏切 (level crossing) bell, pedestrian signal chime
- Ambient loops: city traffic, harbour/sea, wind, rain; night insects
- Trains: pass-by, brakes, doors, platform announcement chime

UI
- Pickup notice, a refused purchase (`UI_ERROR` exists, not played), the radio chatter line
