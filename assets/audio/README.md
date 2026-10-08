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

| file | `Sound` | what plays it | status |
|---|---|---|---|
| `glass_shatter` | `GLASS_SHATTER` | a car window breaking (crash, bullet, blast, melee), 3D at the pane | missing |
| `hit_marker` | `HIT_MARKER` | the local player's hit confirmed (HitMarker), 2D, short tick | shipped |
| `siren` | `SIREN` | an emergency vehicle on a call (Vehicle.refreshEmergency), 3D, LOOPING (import with loop on) | missing |

## Not wired, no file (each needs a `Sound` entry, a call site, and a file)

Weapons
- ATL1 launcher: fire, reload; rocket flight loop
- Throwables (FRG1, PIB1, FLA1, SMO1, REC1): throw, bounce, pin; frag / pipe-bomb explosion, flashbang
  bang + ringing, smoke hiss, remote-charge stick and detonator click
- Melee hits: flesh, hard surface (swings shipped). Ready in the source libraries: Kenney `impactPunch_*`, Still North
  Weapon Impacts (metal clash, haft on haft)
- Dry fire (empty click), weapon switch / draw, holster, scope in/out, pickup, SNR1 bolt cycle after a shot. Ready
  in Still North Raw: every gun's dry fire, safety, slide/bolt takes; medieval dagger / katana draw + sheath
- Bullet impacts per `SurfaceType` (flesh, concrete, metal, glass, wood, water), ricochet, whiz-by
- Explosions (the Binbun3D explosion scenes carry an `AudioStreamPlayer3D` with no stream)

Vehicles
- Engine loop (idle/rev, pitched by rpm) per class: car, kei, truck, motorcycle, boat, plane
- Crash impact (thud / crunch, by impact strength), scrape along a wall, tyre skid, tyre burst
- Horn, door open / close, boost (NOS), gear change, siren (POC1, MPC1, AMB1, FIE1, LAT1)
- Wreck burning loop and vehicle explosion; street pole / bollard knocked down

Characters
- Footsteps per surface, jump, land, fall damage, swim strokes, splash
- Pain, death (keep generic, no voice lines)

World
- Doors: hinged open/close, automatic sliding door, ticket gate flaps, lift doors + arrival chime
- 踏切 (level crossing) bell, pedestrian signal chime
- Ambient loops: city traffic, harbour/sea, wind, rain; night insects
- Trains (when the train runtime exists): pass-by, brakes, doors, platform announcement chime

UI
- Menu click / back, map open / waypoint set, mission start / complete / fail, pickup notice
