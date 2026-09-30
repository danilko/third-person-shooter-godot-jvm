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
| `Rifle_fire.wav`, `Rifle_reload.wav` | ASR1, ASR2, SHG1, SMG1, SNR1 | Johnny Rouddro, Godot TPS (Asset Library #716), MIT |
| `Pistol_fire.wav`, `Pistol_reload.wav` | PIS1, PIS2, DUP1, REV1 | same |

## Wired in code, file missing (drop the file in and it plays; `SoundTest` checks this table)

| file | `Sound` | what plays it |
|---|---|---|
| `glass_shatter` | `GLASS_SHATTER` | a car window breaking (crash, bullet, blast, melee), 3D at the pane |
| `hit_marker` | `HIT_MARKER` | the local player's hit confirmed (HitMarker), 2D, short tick |

## Weapons sharing a sound that is not theirs (a per-weapon file replaces the shared one in its scene)

| weapon | now uses | wants |
|---|---|---|
| SHG1 shotgun | Rifle_fire / Rifle_reload | a shotgun blast, a pump rack, shell insertion |
| SNR1 sniper | Rifle_fire / Rifle_reload | a heavy rifle shot, the bolt (`bolt_work` clip), magazine |
| SMG1 | Rifle_fire / Rifle_reload | a light fast SMG shot |
| REV1 revolver | Pistol_fire / Pistol_reload | a heavy revolver shot, cylinder reload |
| PIS2 large pistol | Pistol_fire | a heavier pistol shot |

## Not wired, no file (each needs a `Sound` entry, a call site, and a file)

Weapons
- ATL1 launcher: fire, reload; rocket flight loop
- Throwables (FRG1, PIB1, FLA1, SMO1, REC1): throw, bounce, pin; frag / pipe-bomb explosion, flashbang
  bang + ringing, smoke hiss, remote-charge stick and detonator click
- Melee (MEW1 knife, MEW2 axe, fist): swing, hit flesh, hit hard surface
- Dry fire (empty click), weapon switch / draw, holster, scope in/out, pickup, weapon pad grant
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
