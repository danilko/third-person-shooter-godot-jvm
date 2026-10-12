# CC0 sound shortlist (research, 2026-10-08) — nothing here is downloaded yet

Candidates for the missing sounds in `README.md`. Every Freesound row was checked on its OWN sound page
("Creative Commons 0"); Kenney packs ship a CC0 `License.txt` (verified by unzipping); OpenGameArt rows were
checked on the asset page. Re-check the licence on download and record URL + author + licence in `CREDITS.md`.

**Rejected sources** (not CC0, or no redistribution): Sonniss GDC bundles, Pixabay, Mixkit, Zapsplat, BBC
Sound Effects. Also rejected: OGA "Footsteps on different surfaces" (CC-BY), OGA "Gunshots" by kurt (uploader
doubts the licence), craigsmith "SSE Vintage Guns" (digitised Hollywood FX), florianreichelt explosions
(provenance), any recorded 発車メロディ (composed music, copyright).

Workflow notes: many picks are long takes to SLICE; engines are one loop per class pitched at runtime (no CC0
matched idle/low/mid/high RPM set exists — `AudioStreamSynchronized` can crossfade if we cut our own from the
contact-mic recording below). Gunshots are layered offline: body + mechanical + tail.

## Key packs (one download covers many rows)

| pack | licence | covers |
|---|---|---|
| Still North **Free Firearm Sound Library** — https://opengameart.org/content/the-free-firearm-sound-library (194 MB .7z) | CC0, "may be used without royalty or credit" | real pistols, revolvers, carbines, auto rifles, pump shotguns, bolt actions; close / 10 yd / 20 yd / rear mics (body + tail from one shot); suppressed; handling foley. Model list unpublished — inspect the archive. **First choice for every gunshot.** |
| Still North **Medieval weapon textures** — https://opengameart.org/content/medieval-sound-effects-weapon-textures | CC0 | axe, dagger, katana swings; dagger draw/sheath (MEW1, MEW2) |
| Kenney **Impact Sounds** — https://kenney.nl/assets/impact-sounds | CC0 | `footstep_concrete/grass/wood/snow/carpet` ×5, `impactPunch_*`, `impactMetal_*`, `impactWood_*`, `impactPlate_*`, `impactSoft_*` (landing, body thud), `impactGlass_*` (clinks, NOT a shatter) |
| Kenney **RPG Audio** — https://kenney.nl/assets/rpg-audio | CC0 | `footstep` ×10, `doorOpen/Close`, `creak`, `drawKnife`, `knifeSlice`, `chop`, `metalClick`, `metalLatch`, `cloth*` |
| Kenney **Sci-fi Sounds** — https://kenney.nl/assets/sci-fi-sounds | CC0 | `explosionCrunch` ×5 + `lowFrequency_explosion` ×2 (layer as explosion / crash crunch), `thrusterFire` ×5 (rocket flight / burning wreck loop), `engineCircular` ×5 (13 Hz pulse loop: maybe a placeholder idle — listen first). Lasers etc. off-tone. |
| Kenney **Interface Sounds** / **UI Audio** — https://kenney.nl/assets/interface-sounds , https://kenney.nl/assets/ui-audio | CC0 | `tick_001/002` (hit marker), `click`, `back`, `confirmation`, `select`, `open/close`, `maximize`, `drop`, `pluck`, `error` |
| Kenney **Music Jingles** — https://kenney.nl/assets/music-jingles | CC0 | 85 short stingers (SAX / STEEL sets for mission complete / fail) |

## Weapons

| need | pick | URL | notes |
|---|---|---|---|
| pistol body | 9mm pistol shot — michorvath | https://freesound.org/people/michorvath/sounds/427592/ | backup to Still North |
| shotgun body + tail + pump | Mossberg 500A 1 shot / and echo / and pump — AnthonyChan0 | https://freesound.org/people/AnthonyChan0/sounds/159706/ | real 12 ga outdoors |
| suppressed | SIG P226 suppressed — areniporgen | https://freesound.org/people/areniporgen/sounds/828790/ | phone mic, layer only |
| revolver / SMG / rifle / sniper | — | — | no clean CC0 on Freesound: Still North only |
| pump rack | Remington 870 racking — TotallyPhilip | https://freesound.org/people/TotallyPhilip/sounds/755495/ | slice |
| bolt cycle (SNR1) | Mosin Nagant bolt cycle — Zott820 | https://freesound.org/people/Zott820/sounds/370345/ | |
| slide / mag / holster | Springfield 1911 handling — AnthonyChan0 | https://freesound.org/people/AnthonyChan0/sounds/487500/ | 7.5 min take, slice |
| revolver cylinder (REV1) | Remington 1875 cylinder turn — Guy_Personface | https://freesound.org/people/Guy_Personface/sounds/795318/ | |
| dry fire | Dry_Fire.wav — TampaJoey | https://freesound.org/people/TampaJoey/sounds/588733/ | real S&W 9mm |
| distant gunfire | Distant Gunfire — iainmccurdy | https://freesound.org/people/iainmccurdy/sounds/842326/ | |
| grenade explosion | Explosion, Medium Blast — Kinoton | https://freesound.org/people/Kinoton/sounds/516914/ | + Kenney crunch/sub layers |
| grenade explosion 2 | Grenade Explosion (meaty) — unfa | https://freesound.org/people/unfa/sounds/609587/ | |
| flashbang (FLA1) | CTS 7290 — areniporgen | https://freesound.org/people/areniporgen/sounds/693421/ | real flashbang |
| rocket launch (ATL1) | M142 HIMARS launch 8 — qubodup | https://freesound.org/people/qubodup/sounds/854476/ | from DVIDS (US gov, PD) |
| rocket flight loop | Rocket Launch Boost and Burning (A) — TheLittleCrow | https://freesound.org/people/TheLittleCrow/sounds/774245/ | or Kenney `thrusterFire` |
| smoke hiss (SMO1) | Spray_Can_Hiss_2 — michael_grinnell | https://freesound.org/people/michael_grinnell/sounds/464428/ | loop it |
| pin pull / grenade bounce | — | — | cut from Still North handling foley / Kenney metal |
| punch | Punch 2 Heavy — steveuk87 | https://freesound.org/people/steveuk87/sounds/490769/ | or Kenney `impactPunch_*` |

## Impacts, glass, feedback

| need | pick | URL | notes |
|---|---|---|---|
| car window (`glass_shatter`) | BROKEN CAR WINDOW — thecommondanger | https://freesound.org/people/thecommondanger/sounds/587928/ | pitch-shift for variants |
| shop window | BROKEN PLATE GLASS WINDOW — thecommondanger | https://freesound.org/people/thecommondanger/sounds/587927/ | |
| shop window 2 | Glass panel shattering — LukaCafuka | https://freesound.org/people/LukaCafuka/sounds/758207/ | |
| glass variants | Glass Shatter 1–7 — Greg_Surr (pack) | https://freesound.org/people/Greg_Surr/packs/31121/ | #1, #5 checked CC0; check the rest |
| bullet → flesh | Bullet Flesh pack — JustInvoke | https://freesound.org/people/JustInvoke/packs/8637/ (e.g. /sounds/138481/) | 4 short game-ready variants |
| bullet → ground/concrete | Bullet impact ground — modusmogulus | https://freesound.org/people/modusmogulus/sounds/789388/ | layer with Kenney plate/concrete; no clean CC0 concrete hit found |
| bullet → metal | Kenney `impactMetal_*` (or martian 182263, slice) | https://freesound.org/people/martian/sounds/182263/ | |
| bullet → wood | Single rock hitting wood — worthahep88 | https://freesound.org/people/worthahep88/sounds/319226/ | 4 variants |
| bullet → water | Small Puddle Splash — Robo9418 | https://freesound.org/people/Robo9418/sounds/841834/ |IN (HQ preview, 2026-10-08; swap for the original download) |
| ricochet | Ricochet 4 — saturdaysoundguy | https://freesound.org/people/saturdaysoundguy/sounds/394187/ | |
| whiz-by | Fly-by whiz — modusmogulus | https://freesound.org/people/modusmogulus/sounds/789222/ | whip, no real-bullet CC0 found |
| hit marker (`hit_marker`) | Hit.wav — Abacagi | https://freesound.org/people/Abacagi/sounds/478057/ | or Kenney `tick_001` |
| body fall | BODY FALL V HVY DIRT — leonelmail | https://freesound.org/people/leonelmail/sounds/504626/ | |

## Vehicles

| need | pick | URL | notes |
|---|---|---|---|
| engine START (chosen 2026-10-12) | toyota camry startup better — vacuumfan7072 | https://freesound.org/people/vacuumfan7072/sounds/322552/ | CC0, phone recording; starter ~9 s, ~4 s of idle after; preview downloaded |
| engine RUNNING (chosen 2026-10-12) | DynoJet Scion FR-S — dezoris | https://freesound.org/people/dezoris/sounds/183654/ | CC0, Tascam + ME-66; one rev idle -> redline (~22 s) and back: cut rpm loops; dyno-room roar; preview downloaded |
| engine idle, fallback | Toyota Matrix exterior chimes, car start, idle ... — MixMessiah | https://freesound.org/people/MixMessiah/sounds/628547/ | CC0; idle steady 47-56 s but ~12 dB over its noise; doors too quiet; cut the chime; preview downloaded |
| car engine "RPM set" | racing car engine loops — domasx2 (OGA) | https://opengameart.org/content/racing-car-engine-sound-loops | one PD sample pitched 6 ways; nearest to a set |
| small car idle + doors | car_idle_ext_loop + pack (one Honda CR-V) — AndrewAlexander | https://freesound.org/people/AndrewAlexander/sounds/369054/ (pack /packs/20743/) | idle, ignition, decel, reverse, doors from one car |
| sports car | Muscle_Idle / Revving — FreeCarSoundsGaming (pack /packs/30160/) | https://freesound.org/people/FreeCarSoundsGaming/sounds/535038/ | looped; also truck idles |
| RPM source to cut loops | Mini Cooper S contact recording — TheLittleCrow | https://freesound.org/people/TheLittleCrow/packs/37350/ | engine-block contact mic, no wind |
| truck / diesel | Truck Engine Idle Loops — qubodup | https://freesound.org/people/qubodup/sounds/187564/ | US gov footage |
| motorcycle | motorcycle_9 — Lauri_Lehtonen | https://freesound.org/people/Lauri_Lehtonen/sounds/714073/ | |
| boat outboard | River boat outboard constant speed — nomadas | https://freesound.org/people/nomadas/sounds/690161/ | steady RPM |
| prop plane | 75 Hz Flying Plane Loop — TheRandomSoundByte2637 | https://freesound.org/people/TheRandomSoundByte2637/sounds/607776/ | synth, clean loop |
| helicopter (HLC1) | UH-60 hover loop 1 — qubodup | https://freesound.org/people/qubodup/sounds/854493/ | seamless, US Army footage |
| heavy crash | Car Crash — squareal | https://freesound.org/people/squareal/sounds/237375/ | |
| crash + glass | Car Crash (with Glass) — magnuswaker | https://freesound.org/people/magnuswaker/sounds/592388/ | trim for lighter hits |
| metal scrape | MetalScrape_6 — deerlord | https://freesound.org/people/deerlord/sounds/534851/ | |
| tyre squeal | Chrysler LHS tire squeal 02 — audible-edge | https://freesound.org/people/audible-edge/sounds/71737/ | |
| tyre burst | Tire Puncture Pop — JohnsonBrandEditing | https://freesound.org/people/JohnsonBrandEditing/sounds/243375/ | designed |
| horn | Car horn inside, Fiat Panda — misperpodcast | https://freesound.org/people/misperpodcast/sounds/733553/ | small-car horn, suits kei |
| siren (`siren`) | Japan Nara Medic Sirene ... Passing By — thabigm | https://freesound.org/people/thabigm/sounds/758375/ |IN (HQ preview, 2026-10-12; a Japanese ambulance ピーポー, used for every emergency vehicle) |
| siren, not used | SS2000_wail_seamless — ThePeasantJoe | https://freesound.org/people/ThePeasantJoe/sounds/800708/ | seamless wail (a US-style wail) |
| gear shift | Lotus Elise shifting — conicity | https://freesound.org/people/conicity/sounds/697837/ | |
| NOS boost | Rocket Boost Engine Loop — qubodup | https://freesound.org/people/qubodup/sounds/146770/ | |

## World, character, UI

| need | pick | URL | notes |
|---|---|---|---|
| footsteps metal | Footsteps On Metal — IENBA | https://freesound.org/people/IENBA/sounds/834029/ | others: Kenney |
| footsteps water | deep water footsteps — bruno.auzet | https://freesound.org/people/bruno.auzet/sounds/553863/ | slice |
| swim stroke | Person Swimming — craigsmith | https://freesound.org/people/craigsmith/sounds/438845/ |IN (HQ preview, 2026-10-08; swap for the original download) |
| splash | Water Jump Mono — Nox_Sound | https://freesound.org/people/Nox_Sound/sounds/585744/ |IN (HQ preview, 2026-10-08; swap for the original download) |
| hinged door | Wooden Door Open and Close — IENBA | https://freesound.org/people/IENBA/sounds/607911/ | or Kenney RPG |
| auto sliding door | Automatic Door — Stroms | https://freesound.org/people/Stroms/sounds/369500/ | |
| lift ding + doors | elevator door and ding — jamie7001 | https://freesound.org/people/jamie7001/sounds/476800/ | US ding |
| 踏切 bell (loop) | Japanese Level Crossing Beeping Loop — JotrainG | https://freesound.org/people/JotrainG/sounds/650317/ | recorded in Japan, seamless |
| 踏切 + train pass-by | Japanese Railroad Crossing — KoimeMatsuchiya | https://freesound.org/people/KoimeMatsuchiya/sounds/872621/ | 50 s |
| ped signal piyo piyo | Traffic light crossing tweet — macdaddyno1 | https://freesound.org/people/macdaddyno1/sounds/349395/ | Tokyo |
| ped signal kakko | CuckooSignal — hrhk | https://freesound.org/people/hrhk/sounds/98154/ | |
| konbini entry chime | 7'11 Sliding Door — plasterbrain | https://freesound.org/people/plasterbrain/sounds/399092/ | generic synth chime |
| train door | train door closing tokyo — cobwebjoe | https://freesound.org/people/cobwebjoe/sounds/136437/ | slice |
| city traffic | busy tokyo street evening rush — markystar | https://freesound.org/people/markystar/sounds/75271/ | crossfade to loop |
| sea | Ocean Ribeira Grande Loop — Nox_Sound | https://freesound.org/people/Nox_Sound/sounds/829629/ | no gulls/boats |
| wind | rushing air, distant traffic — kyles | https://freesound.org/people/kyles/sounds/454072/ | |
| rain | SuburbRain_OutdoorLoop — PhilllChabbb | https://freesound.org/people/PhilllChabbb/sounds/238431/ | |
| cicada | Japanese Cicada — macdaddyno1 | https://freesound.org/people/macdaddyno1/sounds/321591/ | |
| night insects | Japan Kashiwa Insects — RutgerMuller | https://freesound.org/people/RutgerMuller/sounds/365257/ | skip loud bug at ~2/3 |
| UI / stingers | Kenney Interface Sounds, UI Audio, Music Jingles | (see packs) | |

## Gaps (nothing good CC0 found)

Revolver / SMG / rifle / sniper single shots outside the Still North archive; a clean bullet hit on concrete;
a real-bullet whiz-by; grenade pin / bounce; a matched RPM engine set (and anything kei-car specific); a
Japanese patrol siren clean enough to loop; a station departure melody (commission an original); a Japanese
lift voice chime; a harbour mix with gulls and boats; jump grunts.
