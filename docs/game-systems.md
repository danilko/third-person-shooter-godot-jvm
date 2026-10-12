# game-systems

Moved out of `CLAUDE.md` verbatim on 2026-10-09 (PLAN.md 0.5 / F12). Sections:

- Performance Foundation (Part D)
- AI (7-state singleton FSM)
- Event System (EventBus AutoLoad)
- MovementController flags (Player vs AICharacter)
- Audio: every sound is a file (2026-09-29)
- The player profile, the economy and save v2 (2026-10-10, under Performance Foundation)
- Owned cars and the safe-house garage (2026-10-10, after it)
- Authoring foundations: GameplayEvents, DataTable, MarkerRegistry, WorldLedger (PLAN.md 2.0, 2026-10-10, after it)
- The campaign graph, its lint, and the career override stack (PLAN.md 2.1 step 1, 2026-10-10, after it)
- The Activity runtime: typed Java missions, the konbini job as the reference, replay, game-over rules (PLAN.md 2.1, 2026-10-10, after it)

---

## Performance Foundation (Part D)

Drop-in accelerators that change nothing visually. Each degrades gracefully if its AutoLoad is
absent (test scenes), so they are safe to rely on but never required for correctness.

### Spatial partitioning — SpatialEntityGrid (`com.openworld.world`, AutoLoad, D1)

Uniform XZ spatial hash (`cellSize` exported, 50 m). `Character` and `Vehicle` (both in the
"characters" group) `register()` in `_ready()`, re-bucket via a throttled `updateSpatialCell()`
(0.25 s) called at the **top of `_physicsProcess`, before the non-authority early return** — so
puppet bodies (e.g. remote players on the host) keep their cell current too — and `unregister()`
in `_exitTree()`. `AICharacter.discoverTarget()` calls `queryRadius(pos, detectionRange)` instead of
`getNodesInGroup("characters")`, falling back to the group scan when `SpatialEntityGrid.get()` is
null. Reached via a JVM-static `get()`; all maps + the static are cleared in `_exitTree()`
(leak discipline).

### AI level-of-detail — AILodLevel (`com.openworld.ai`, D2)

`AICharacter` carries an `AILodLevel { ACTIVE, PASSIVE, FROZEN }` set every 2 s from
`nearestPlayerDist()` (which now iterates `PlayerRegistry`, not the group): `< 80 m ACTIVE`,
`80–200 m PASSIVE`, `> 200 m FROZEN`.
- **FROZEN** — `AICharacter._physicsProcess` returns before `super` (whole FSM + animation tick
  skipped). MovementController, a separate node, still decelerates the body to rest.
- **PASSIVE** — `AIController.gatherInput` returns a hold-heading command (no NavAgent / FSM /
  aim), and `AnimationController._physicsProcess` skips **all AnimationTree writes** when
  `getLodLevel() != ACTIVE` — those JVM-bridge calls are the dominant per-AI cost, so this is the
  real mid-range win.
- Returning to ACTIVE from any non-ACTIVE tier clears stale nav/search state.
`isLodFrozen()` is kept as a back-compat shorthand for `lodLevel == FROZEN`.

### Faction relationships — FactionManager / FactionTable (`com.openworld.character`, D3)

`Faction.areHostile()` is a **thin delegate** to the `FactionManager` AutoLoad (registered via
`Faction.setRegistry`), so **all call-sites stay unchanged** and there is no duplicated rule.
`FactionManager.areHostile()` is the single owner of the logic: NEUTRAL is never hostile → an
explicit `FactionTable` entry wins (`HOSTILE/DESPISE` → hostile) → otherwise the inherent default
(same faction allied, different factions hostile). The table (`DefaultFactions.tres`, a flat
`Dictionary<String,String>` keyed `"a>b"`) only needs **overrides** of that default — it ships just
the editable `player↔enemy = HOSTILE` rows. `setRelationship(a,b,rel)` flips a relationship at
runtime (mission betrayals; required before Part F). With no registry loaded (engine-free tests)
`Faction.areHostile()` returns false.

#### Multi-faction & runtime changes (high-level — details will firm up with Part F mission state)

Factions are arbitrary strings on `CharacterInfo.faction`, resolved fresh every target scan, so any
number of parties works with **no code change** — author a `FactionTable` (`.tres`) with only the
pairs that *differ* from the default (different faction ⇒ hostile, same ⇒ allied, `"neutral"` ⇒
never fights). Two runtime levers, both **host-authoritative and replicated** over the world-event
seam (`WORLD_EVENT_FACTION_*`):
- `FactionManager.setRelationship(a, b, rel)` — flip a whole party relationship (the betrayal beat).
- `Character.setFaction(s)` — swap one character's allegiance (e.g. a cornered NPC turning hostile).

Use these setters, **not** a raw `characterInfo.faction = …` write, so the change syncs to clients
(and rides the late-join baseline). **Lifetime:** the live table is a `duplicate()` of the shipped
`.tres`, and `FactionManager` is an AutoLoad, so a flip persists across scenes/missions until
`FactionManager.reset()` restores defaults (already called on full restart in
`GameManager.restartLevel`; call it at mission end for per-mission scope — auto-scoping belongs with
Part F). Behaviours that *react* to factions (a bystander fleeing when a fight erupts, corner
detection that triggers a swap) are AI-perception features not built yet — they'll land with Part E2
`StimulusManager` / the AI FSM.

#### Presets, wildcard rows and the mission layer (F2, 2026-09-17)

- **The rule has one engine-free owner: `character.FactionRules`** (`FactionRulesTest`, 7 cases).
  `FactionManager.areHostile` and `FactionTable.relationship` both call it. The order is: `neutral`
  is never hostile, then an exact pair (either direction), then a **wildcard row**, then the default.
- **Wildcard row.** `"civilian>*"` (or `"*>civilian"`) means "toward every OTHER faction". It is how
  a preset says "civilians are neutral to everyone" without listing each faction and going stale when
  one is added. It never applies to a faction and itself. If both sides carry wildcards that disagree,
  the LESS hostile one wins, so a civilian stays out of a hostile-to-all faction's fight.
  `FactionTable.row` checks `containsKey` before `get`, because godot-jvm's `Dictionary.get` on a
  missing key is not guaranteed to return null.
- **Presets** in `character/`, beside `DefaultFactions.tres`:
  - `OpenWorldFactions.tres`: player, police, gang_a, gang_b, civilian. Civilians are neutral to all,
    police are neutral to the player and hostile to both gangs.
  - `GangA_vs_Police.tres`: gang_a DESPISES police, the player sides with police, gang_b sits it out
    (`gang_b>*` NEUTRAL).
  - `Faction` gained `POLICE`/`GANG_A`/`GANG_B`/`CIVILIAN` constants and nameplate colours.
- **Three layers, one live table.** The live table is a `duplicate(true)` of the highest layer
  present: mission (`applyMissionTable`), then region (`applyTable`, from `RegionConfig`), then
  `DefaultFactions.tres`. A region change while a mission runs is remembered but does not replace the
  mission's table.
  - Rebuilding the table discards runtime flips. That is the per-mission scope the flips want.
  - `reset()` clears both layers.
- **Missions.** `MissionInfo.factionTable` (`@Export`, nullable) is applied by
  `MissionManager.startMission` BEFORE the ELIMINATE_ALL count and removed on complete and on fail.
  - Clients get it as a resource path in `WORLD_EVENT_MISSION_STARTED`'s second argument
    (`GameManager.applyMissionStarted`). A table built in code or embedded as a sub-resource has no
    loadable path and is not mirrored. That loses nothing today: hostility is only decided on the host.
  - Worked example: `game/mission/GangA_vs_Police_Mission.tres`.
  - `MissionManager.startMissionFromPath` / `completeMissionNow` and `FactionManager.activeLayerNow` /
    `hostileNow` are registered for probes. So is `AICharacter.targetIdNow`.
- **Gate `tools/godot/probe_faction_presets.gd`** (21/21, stable over 3 runs). It uses real AI that
  stand still and think, plus a Player.
  - Control, shipped defaults: the policeman targets the nearest body, the civilian.
  - `OpenWorldFactions` as the region layer: police target a gang, and nobody targets or is targeted
    by the civilian.
  - The mission layer: police and gang_a target each other, gang_b and the civilian are left out, and
    a region change does not replace the layer.
  - Armed with ASR1s through real pickups, police and gang_a damage each other and nobody else.
  - Completing the mission restores the defaults.
  - Probe trap: with `MovementController` off, a target 90° to the side stays past the aim reach and
    W21's fire gate holds every shot. The policeman targeted gang_a for 20 s with a full magazine.

---

#### The CAMPAIGN layer (PLAN.md 0.35 / CR3, 2026-10-09)

Runtime flips are per-layer by design (a rebuild discards them; `FactionFlips` re-applies the wanted / gang ones every
0.5 s), which made a STORY change ("the police now hate gang_a") vanish at the next region boundary or mission.
`FactionManager.setCampaignRelationship(a, b, rel)` (`flipCampaignNow` for probes / console) writes a fourth layer that
every rebuild lays over the region / default table; an active mission table still wins and the campaign rows land
again when it ends. Only `reset()` (new game / full restart) clears it; the save carries it as `campaign_factions`
(restored after the reset a load does). Replicated through the SAME faction world event with a third argument
`"campaign"` (no new event number), and sent flagged in the late-join baseline so a client keeps it across its own
region rebuilds. Gate `tools/godot/probe_campaign_factions.gd` 12/12 (`--control` makes the flip a runtime one, fails 4).
Player <-> gang_a / gang_b now ship NEUTRAL in `DefaultFactions.tres` (see "Gang hangouts").

### The story layer — MissionDirector (`com.openworld.game.mission`, AutoLoad, F1, 2026-09-17)

The one owner of story logic, beside `MissionManager`, which keeps objective TRACKING. The split is
the whole design: **"may this mission run" is campaign state; "is it won yet" is not.** Four jobs.

- **NamedCharacterRegistry** — `characterId → live AICharacter`. **Registration has ONE owner,
  `AICharacter._ready()`**, gated on `@Export storyCharacter`; `ZoneManager.spawnNamed` sets that flag
  before `addChild` so a streamed `NamedCharacterConfig` and a hand-placed story AI take the identical
  path. **The flag exists because the ID cannot answer the question** — an ambient AI's id is a random
  UUID and a named one's is authored, and those are the same type of string. A second body claiming a
  live id is refused and reported (which boss you commanded must not depend on streaming order); one
  replacing a FREED node is the ordinary zone reload. `_exitTree` drops the entry, so the map is
  authoritative about "is the boss loaded right now" with no tree scan.
- **`commandCharacter(id, ScriptCommand)`.** `ScriptCommand` is a `Resource` whose every field is a
  command with an explicit **do-nothing sentinel** (`targetState = ""`, `move = false`,
  `invincible = KEEP`), never a mirror of the AI's state — so a partly-filled order cannot quietly
  reset the rest of the body. `move` is a separate flag from `moveTo` because **(0,0,0) is a legal
  destination** (it is the spec's own verify case), so "is the vector set" is not derivable.
  `assignSquad` is code-set rather than exported: a `.tres` cannot hold a node.
- **`triggerBeat(beatId)`** — runs the Java handler registered under that id (beats are methods, not a
  scripting language) and emits `EventBus.missionBeatTriggered` either way, so a beat with no logic yet
  is still an event dialogue/HUD can hang off. `ZoneTrigger` (F3) is the caller that is still missing.
- **The mission-output graph.** A completion folds `(missionId, outcomeVariant)` into an accumulated
  set and re-evaluates an append-only unlock table. **Idempotent on variant** (a replay adds no branch,
  so the tree is bounded by `missions × variants`, not by replay count), **sticky** (a branch once open
  never closes), and unique items granted exactly once via `grantUniqueOnce`'s membership check.
  **Ordinary rewards have no code here on purpose** — there is nothing to gate, and a field nothing
  reads is wrong the day something reads it. It listens to **`EventBus.missionCompleted`**, which fires
  on *every* peer (a client gets it mirrored by `GameManager.applyMissionCompleted`), so every peer's
  graph advances with no new message — and the idempotency is what makes that safe.

**Commands are host-side, and that needs no gate:** only the host runs an `AIController`; a client's
copy of the same body is a puppet, so `commandCharacter` returns false there and the motion it causes
on the host replicates the ordinary way. A beat script may therefore run on both peers without knowing
which it is.

**`ScriptedMoveState` — an order is not a mood.** Nothing in the world cancels it: not sight of an
enemy, not being shot, not gunfire. The autonomous states are the opposite by design, and mixing the
two gives a cutscene walk a passing civilian can derail. The director cancels it (`releaseCharacter`,
or the next command). **A NavAgent off the navmesh does not go silent — it lies:** with no navigation
map under the body it reports `isNavigationFinished() == false` forever and hands back the body's own
position, one tick stale, so the steering vector points exactly BACKWARD along its own travel and
feeds itself — measured on the bare probe stand, the AI ran from 20 m off the origin to **110 m in
30 s**. The agent is believed only while its next point is a real step ahead (`NAV_MIN_STEP` 0.5 m);
otherwise the destination answers. Arrival is likewise asked of the DESTINATION, never of
`isNavigationFinished()` alone — an arrival that is a lie fires the next beat in the wrong place.

**Invulnerability is one flag in one place**, `Health.invulnerable`, checked at the top of
`applyDamage` — the single site every source funnels through (bullet, blast, fall, a relayed client
request), so it can never mean "immune to some damage". `@Visible`, not `@Export`: live mission state,
not something a scene authors. Not replicated — the host is the only peer that applies damage.
`releaseCharacter` clears it with the order, so a beat cannot leave someone immortal.

**A mission vehicle is not ambient traffic** (the `TERRAIN3D_TRANSITION.md` note, now enforced).
`registerMissionEntity(key, node, failOnLoss)` is the declaration; `ZoneManager` asks
`isMissionProtected` in ONE place — before the reclaim, not inside each of the seven reclaim reasons —
and `freeTrafficCar` leaves a protected car and its driver exactly as they are, dropping only the
pairing. From there the MISSION owns them: registering an entity is taking responsibility for it.
Losing one registered `failOnLoss` calls **`MissionManager.failMission`** — the mission system's rule,
never the streamer's. Loss is detected as a FREED node rather than a `Health.died` connection, because
a wreck replaced by a wreck scene emits nothing a mission could hear.

**The debug console** (`debug.DebugConsole`, **backtick** via `DebugHarness`) is F1's stated
prerequisite: iterating a beat in one session instead of one restart per edit. Built in code like
`PerfDebugOverlay`, so no scene wiring; opening it sets `inputBlocked` on every registered local player
and frees the mouse (otherwise typing "state" walks the player and shoots). Its command table is
hand-written, not reflective — a typo in a reflective console is a silent no-op — and everything it
drives is already a `@Register`ed method, the same surface a probe uses, so it can never reach further
into the game than the gates can. `named / move / state / invincible / release / beat / mission
start|complete|fail / unlock / close`, and the weapon commands (the CS `give` / Unreal `summon` idiom, host or
single player only): `weapons`, `give <id>` (straight into the inventory through `requestEquip`), `drop <id>|all`
(a row of pickups 3 m ahead) and `ammo`. They read `weapon.WeaponCatalog`, the one runtime reader of
`weapon_catalog.json` (the aim bench uses it too), so a new catalog weapon is spawnable with no other edit; the
built-in fist is excluded. Gate `tools/godot/probe_debug_weapons.gd` 6/6. The debug HUD (`PerfDebugOverlay`, **Shift+F3** cycles, console
`hud 0-3`) is levelled like CS's `net_graph`: 1 a corner FPS counter, 2 the engine monitors + JVM heap + streaming
+ a `FrameTimeGraph` (240 frames, 60/30 fps lines, avg / 1%-low / max), 3 adds the local player's live state
(position, speed, stance, view, health, vehicle, weapon + ammo + `WeaponState` + spread, what the aim ray is on)
and `NetworkManager.debugNetLine` (rtt, loss, kbit/s from ENet's own statistics). Gate
`tools/godot/probe_debug_hud.gd` 10/10 (`-- --shot=<png>` with a display).

**Gate `tools/godot/probe_mission_director.gd`** (34/34; `-- --control` turns the boss's
`story_character` flag off and fails 11). Real AI bodies on a bare stand, with a **Player in the scene
because an AICharacter with no player within 80 m is LOD-FROZEN and never thinks** — it is also the
hostile the scripted walk must ignore. Cases: the registry (an ambient AI is not in it; a duplicate id
refused; a freed body leaves it), the spec's own verify (`command_move_to` origin → SCRIPTED_MOVE,
20.44 m → **1.20 m in 6.8 s**), the order held for the whole walk past a hostile, an invincible boss
taking **0 hits from a 1e6-damage kill** and dying the moment it is released, beats, the graph (locked
→ wrong variant does not open it → the declared one does → replay adds no branch → sticky), the
director refusing to start a locked mission and starting it once unlocked, a mission entity freed
failing the ACTIVE mission by name, and the console reaching the director. **Not covered, on purpose:**
`ZoneManager`'s half of the vehicle rule needs a streamed zone with live traffic
(`probe_traffic_spawn.gd`'s stand), so what this asserts is the ANSWER the streamer reads.

### The caller the story layer was missing — `world.ZoneTrigger` (F3, 2026-09-17)

F1 built `triggerBeat` and nothing in the world called it. `ZoneTrigger` is an `Area3D` an artist
drops in a scene: the right body enters, it fires one beat, and **that is the whole of it** — mission
start zones, objective markers, ambush triggers and cutscene entries are all the same volume with a
different beat id. What the beat DOES stays a Java handler registered by id on the director, so a
trigger can never become a second place story logic lives; a beat with no handler still emits
`EventBus.missionBeatTriggered`, so an authored volume is useful to dialogue and HUD before any Java
exists for it.

- **"Has this already fired" is the DIRECTOR's answer, not a flag on the node.** `oneShot` asks
  `MissionDirector.beatFireCount(beatId)`, and that is load-bearing rather than tidy: a trigger
  authored inside a streamed zone's geometry is **freed and re-instanced every time the player walks
  away and back**, so a local flag re-arms the ambush on every pass with nothing to see. The
  director's fired-beat log is campaign state and outlives the node — and `resetCampaign()` re-arms
  every trigger with it, which is the same answer for the same reason. `campaignOneShot` is the
  control knob (`@Visible`, always on) that puts the local flag back, and the gate measures it.
- **The mask is not authored.** `_ready` states `CHARACTER | VEHICLE` itself. A seated occupant is on
  collision layer **0** (`CharacterDriveState.enter`), so without the VEHICLE half a player who
  DRIVES to the mission marker trips nothing — and an area whose mask silently excludes the thing it
  watches for looks exactly like a trigger that was never wired. A carrier hands the trigger whichever
  seated occupant qualifies. `carrierAware` is that half's control knob.
- **Every peer fires its own.** The volume is symmetric — a client's copy fires as the client's copy
  of the body arrives — which is the director's own rule that a beat script runs on both peers without
  knowing which it is. A beat whose EFFECT is host-authoritative is gated inside its handler, exactly
  as `commandCharacter` already is. A `hostOnly` flag on the volume would move that decision into the
  scene, away from the only thing that knows the answer.
- **Gates that need no code**, each one export and each one a real authoring case:
  `requiredMissionId` (an ambush does not fire before its mission), `requiresBeat` (objective markers
  in sequence — otherwise marker 2 fires as you walk past it on the way to marker 1), and
  `requiredCharacterId` (the escortee's drop-off, not the player's). `showDebugVolume` draws the box
  or sphere (armed yellow, spent green), off by default — unlike a zone marker there are many.
- **The escort order the verify needed did not exist.** `commandCharacter` could enter `ESCORT` but
  not say WHOM to escort, so `ScriptCommand.escortTarget` (a live node, therefore code-set like
  `assignSquad`) and `MissionDirector.commandEscortPlayer(id)` are new. The target is resolved through
  `PlayerRegistry` rather than passed in, because a beat fires from a volume that knows nothing about
  which player tripped it and in co-op "the player" is whichever one is there.

**Gate `tools/godot/probe_zone_trigger.gd`** (16/16; `-- --control` turns both knobs off and fails
exactly 2). The spec's own verify is case 1 and is a REAL walk — the player's own `PlayerController`
reading the `forward` action — into the volume, which fires the beat, whose listener orders the boss
to escort; the rest teleport, which crosses the boundary the same way. Also: an ambient AI does not
trip a player trigger, a re-streamed trigger node stays silent for a spent beat, the three gates each
refuse and then admit, a player who DRIVES in trips it (mask 18), and a trigger with no beat id is
inert. **What is NOT asserted, on purpose: metres walked while escorting.** The escort MOTION is
`EscortState`'s and is nav-driven, and this bare stand has no `NavigationRegion3D`, where a NavAgent
reports "not finished" forever and hands back the body's own position — so the gate asserts the ORDER
the trigger delivered (the state, and who is being escorted).

**Probe trap, and it is the shared-sub-resource rule from the other side:** a `.tscn`-embedded
`CharacterInfo` is SHARED by every instantiation, and `Character._ready` only privatizes one whose id
is still **empty** — so a probe that stamps the scene's own resource *renames every AI it spawned
before*. Spawning `ambient_01` silently renamed the boss, and the case keyed on `requiredCharacterId`
failed with "not boss_01" while the registry (keyed by the string handed in at registration) still
said the boss was loaded. Both this probe and `probe_mission_director.gd` now build a fresh
`CharacterInfo` per body, which is the codebase's own "own identity in code, not the scene" rule.

### The campaign save — `game.SaveSystem` (I7, AutoLoad, 2026-09-17)

One JSON document per slot under `user://saves/`, written and read with Godot's own `FileAccess`.
It carries the campaign graph, the faction flips, which mission was running, and each player's
position / facing / health / slot manifest. **Which pieces are in it is the whole design**, and four
rules decide it:

- **Progress is saved; AUTHORING is not.** `MissionDirector.declareUnlock` rows say which variants
  open which mission — that is content, re-declared by the same Java every launch. A saved copy would
  be a second owner that goes stale the day the campaign is edited, with the stale copy winning. What
  is saved is only what the player's play produced: the achieved `(missionId, variant)` set, the
  completed missions, the sticky `unlocked` set, the granted unique items.
- **The fired-beat log is campaign state, not a debug counter.** F3's `ZoneTrigger` decides "has this
  already fired" by asking `MissionDirector.beatFireCount`, precisely so a trigger inside a streamed
  zone cannot re-arm when the zone reloads. A save that left the log out would re-arm **every
  one-shot trigger in the world** on load — the ambush you already sprang, waiting for you again —
  with nothing on screen to say why. `SaveSystem.saveFiredBeats` (`@Visible`, always on) is the
  control knob the gate measures that with, and it is 3 of the probe's checks.
- **An interrupted mission RESTARTS; it does not resume mid-flight.** AI bodies are not saved (a
  streamed world respawns its crowds), so a restored "3 of 7 left" counter would be counted against a
  fresh crowd of 7 — a number that is simply untrue. The slot records the mission's id and its `.tres`
  path and `loadSlot` starts it again **through the director**, so the unlock predicate still decides
  whether it may run and a save cannot smuggle a locked mission back in. That is also what GTA does
  with a save taken during a mission. A mission built in code or embedded as a sub-resource has no
  loadable path (the limit `MissionManager` already documents for its client mirror), so it is
  recorded by id and reported as unresumable rather than half-restored.
- **Only what RUNTIME changed is saved of the factions.** `getActiveRelationships()` — the late-join
  net baseline — returns the whole live table, which is a copy of the shipped/authored `.tres` with
  the flips written into it, so saving that would freeze the shipped defaults into the slot and let an
  old save silently win over an edited preset. `FactionManager.runtimeFlips` records exactly the
  `setRelationship` calls that are still live (cleared by `rebuildLiveTable`, which IS the documented
  "a layer change discards runtime flips" rule) and `getRuntimeOverrides()` is what the slot carries.
  The region and mission LAYERS are not saved either: each is re-applied when its region streams in or
  its mission restarts.
- **The host's save is canonical and needs NO new message.** `saveSlot` refuses on a client
  (`save_refused_client`). A load on the host reaches every client through seams that already exist:
  the faction flips ride `FactionManager.setRelationship`'s world event, the mission restart rides
  `WORLD_EVENT_MISSION_STARTED`, and inventory converges through the periodic `MSG_INVENTORY`
  manifest. An RPC here would be a second way to say what the wire already says.

**The player key is the id that is stable ACROSS LAUNCHES, and that is not the same field in both
cases.** A remote player's `characterId` IS their `PersistentPlayerId` (`GameManager.onPeerIdentified`
makes it so on first join), while a locally-owned body carries a per-launch UUID — so the local body
is keyed by `PersistentPlayerId.getOrCreate()`, the id this install would identify as if it were the
client. One rule, both cases, and the key survives a host/client role swap. A record whose body is not
live yet is **held** (`pendingPlayerCount()`) and applied as that body appears, so loading before or
during a scene coming up works, and a client that joins after the load still gets its own record.

**Nothing new was written to read or apply state.** Inventory is `WeaponController.buildInventoryEntries`
/ `applyReplicatedInventory(entries, addOnly=false)` — the N2 manifest path, with `addOnly` false
because the owned-body guard exists to stop a *lag-stale* manifest fighting live input, and a document
read off disk has nothing to race. Health is `Health.applyReplicatedHealth`, which is already the "set
the number, fire no damage event" path; a save taken while dead is not resurrected into a corpse (a
non-positive value is left alone). `MissionDirector.restoreCampaign` is a REPLACE, then
`reevaluateUnlocks()`, so a requirement declared by this launch's code that the restored achievements
already satisfy opens with everything else.

**Autosave** (`autosaveEnabled`, slot 0) fires on `EventBus.missionBeatTriggered` and
`missionCompleted` — the F3 hook I7 asked for, now that a beat has a caller. The debug console gained
`save [slot]` / `load [slot]`.

**Registration shapes that had to be worked around**, all the same quirk: godot-jvm merges a JavaBean
accessor with its field into one property, so a registered `setX` with no getter does not compile and
a registered `getX` with no setter registers READ_ONLY. The probe needed four things GDScript could
not reach, and each is a question-named reader or a differently-named action beside the original:
`FactionManager.flipRelationship` (beside `setRelationship`), `Health.healthNow` (beside
`getCurrentHealth`), `WeaponController.activeSlotNow` (beside `getReplicatedActiveSlot`) and
`MissionManager.missionActiveNow` / `activeMissionIdNow` (beside `isActive`). `FactionManager.reset`
and `Health.applyReplicatedHealth` are not accessor-shaped and were annotated in place.

**Gate `tools/godot/probe_save_system.gd`** (36/36; `-- --control` turns `saveFiredBeats` off and
fails exactly 3). Its method is the spec's own verify, and the middle step is the part that matters:
reach a state, save, **LOSE that state in the same session** (the stand-in for quitting), load, and
find it back — a probe that only saves and loads cannot tell a working restore from a state that never
went away. Cases: the graph (a declared unlock, an achieved variant, a granted unique item), a faction
flip, a real ASR1 taken through the ordinary pickup path with a hand-set magazine, position and
health; the file itself (schema, the four blocks, one player); everything wiped; everything restored,
onto the SAME weapon node rather than a duplicate; a real one-shot `ZoneTrigger` dropped on the player
after the load staying silent; the running mission recorded with a loadable path and restarted; and a
missing slot refused rather than half-applied. **The faction flip has to DIFFER from the shipped
default or it is unobservable** — two different factions are hostile by the inherent rule, so a flip
to HOSTILE proves nothing and the case uses FRIENDLY (it cost one false pass first).

**Not covered, on purpose:** the client refusal and the co-op mirror need two processes
(`tools/net/run_net_*.sh`'s shape), so what this asserts is the ANSWER each seam reads. World entity
state — which AI are dead, which pickups are gone, where the traffic is — is **not** saved at all, and
that is the boundary the mission-restart rule above is drawn around.

### The player profile, the economy and save v2 (PLAN.md 1.4: AR2 + CR4 + CR5, 2026-10-10)

**Money was a field on the BODY** (`Character.cash`), mutated in four systems (the robbed till, gang fees, the
ransom, respawn bills), hand-copied across a respawn, never saved, never replicated -- and on a co-op client the shop
showed the client's own body's 0. Now (`game.profile`, all engine-free and unit-tested except `Profiles`):

- **`PlayerProfile`** -- what a PLAYER owns: a SIGNED `balance`, `debts` (lender, principal, due), CR2's `CareerState`
  data (base, records per career, the override journal), CR1's `CampaignState` data (flags, achieved, chapter / phase,
  endings seen, checkpoint, content version), owned cars (`VehicleInstanceData`: model, paint, upgrades, condition,
  garage -- never written into the shared `VehicleConfig`), unlocks. `toMap` / `fromMap` is its ONE shape, on disk AND
  on the wire; unknown keys are kept. Career / campaign are carried and saved, but NOTHING writes them yet: their
  engines (the override stack, the campaign graph, MissionDirector's sets moving in) come with AR1 in 2.1.
- **`Economy.transfer(from, to, amount, reason)`** -- the one door; either side may be the world (null). Only a
  reason that `allowsDebt` (hospital / bail bills, fines, loans) may take a balance below zero (CR4): a bill the
  player cannot cover leaves the balance negative, which is the debt, paid back by the next income. A purchase, fee or
  ransom is refused when short. Listeners hear every applied transfer (the save's dirty flag today; AR3 later).
  `RecoveryRules.charge` ("never more than there is") is gone with the field.
- **`Profiles`** -- a body asks for its player's profile: the body this machine plays -> `local()` (this install's,
  `user://profile.json`), another player's body on the HOST -> the session copy keyed by their PersistentPlayerId, an
  AI -> null. `Character.cashNow` / `giveCashNow` read / write through it.
- **The handshake (MSG_PROFILE = 35, reliable ch 0, the profile's JSON, <= 3800 bytes)**: a client sends its profile
  right after the identify reply; the host keeps it as the session copy (keyed by the id the peer IDENTIFIED as, never
  what the payload claims), changes it (money moves on the host), and sends it back to the owner at most twice a
  second when its revision changed; the owner replaces its local copy and saves it. A client writes its OWN profile;
  only the world save is host-only.
- **Save v2** (`SafeSave`, `SaveMigrations`): both files are written `.tmp` -> read back and checked -> the old file
  to `.bak1` (and that to `.bak2`) -> moved into place, with a `#sha256:` first line; a torn or edited file falls back
  to the newest good backup. The world slot is schema 2; an older slot is MIGRATED through an ordered step list (v1
  ->v2 only stamps the version: the world keys did not change), a newer one refused. Autosave is coalesced
  (`autosaveMinSeconds` 30): a beat writes if the last write is older than that, else the window's end writes it; a
  mission end always writes (world + profile); quit and Quit to title flush both.
- **Probes never touch the player's saves**: a run under `--script` uses `user://test/profile.json` (deleted at the
  start of each run, so one probe's money never leaks into the next probe's exact checks) and `user://test/saves`.

**F3, prices on (same day).** `game/economy.json` is THE table (`EconomyTable`, parse unit-tested, and the test fails
if a catalog weapon or a supply has no price): guns at CS 1.6's own prices, in dollars (PIS2 400 ... ASR1 2 500, SNR1
4 750; ten times that, as yen, until 2026-10-12 -- a v1 profile's balance and debts are divided by ten on load,
`SaveMigrations.PROFILE`), a REFILL of one already carried at `refill_fraction` 0.2, supplies per unit (a purchase tops the stack up),
`starting_cash` 2 000 for a profile created from nothing (a probe's is 0: it sets its own), rewards
`mission_default` 1 000 / per mission (m01_konbini 1 500) / `race_by_place` [800, 400, 200]. Bills stay where
they were authored (crimes.json / gangs.json, RecoveryRules). `ShopCounter.grantTo` charges FIRST (refused when short
-> no MSG_SHOP_GRANT to a client; refunded if the grant fails) and returns whether it sold; the menu tags rows
"$25,000" / "REFILL $5,000" / "SHORT $..." / "FULL". `Payouts`: a mission the players win (`winningFaction ==
"player"`, not a race) pays every player in the session once per profile, before the completion autosave; a race pays
each human finisher by place. The co-op gate's DebugHarness funds both profiles before its purchases.

Gates: `probe_profile.gd` 19/19 (the test file; grant / refused purchase / bill into debt through a body; checksum,
.bak1 rotation, a TORN file falls back to .bak1 and the torn value never loads; a v1 slot migrates and loads, a newer
one is refused; two beats in the window write once, the window writes the second, a mission end writes at once;
a players' win pays 1 000, a police win nothing -- 21/21 with F3); `probe_weapon_counter` (no money: refused; the
price taken; the refill price); `probe_race` (first place +800, once);
`tools/net/run_title_coop.sh` now also runs the handshake (the joiner's 4321 dollars held by the host, the host pays the
joiner's body 1000, the joiner gets 5321 back and saves it). Unit: `PlayerProfileTest`, `EconomyTest`, `SafeSaveTest`,
`SaveMigrationsTest`. Both processes of the co-op test share `user://test/` (one machine); harmless today.

### Owned cars and the safe-house garage -- `world.Garage` (PLAN.md 1.4 / F4, 2026-10-10)

GTA San Andreas' rule: **drive a car into the bay, get out, and it is yours.** `Garage` records it in the driver's
`PlayerProfile.vehicles` (`VehicleInstanceData`: its id, its scene, `condition` = hull health 0..1, `garage = "home"`),
adds it to the group `owned_vehicle`, and puts it back in the bay the next time a world loads.

- **Where the bay is: derived, not authored.** World.tscn is generated (`island_buildings.patch_start` owns the start),
  so `Garage.ensureHome(scene)` -- called by `SaveSystem._process` once per scene -- takes the starting car
  (`VehicleRoot`, parked nose-in) and tries the bay 2.5 m to its side, then the other side, then two over, taking the
  first whose box holds no WORLD / VEHICLE collider. No `VehicleRoot`: no garage. The same rule gives DebugWorld one.
- **The player learns it from the world**, not the HUD: a yellow painted outline on the ground (four unshaded strips
  built in `_ready`, no collision). There is no prompt and no message.
- **Kept only when DRIVEN in.** A car is stored when a `Player` was seen driving it inside the bay and it is now empty
  and slower than 0.6 m/s. A car that merely ends up in the bay (pushed, spawned) is not taken -- the probe's control.
- **One car per bay**: a second car stored there drops the older row. **Driven (or pushed) out**, the row stays but
  `garage` becomes `""`: it is the player's while it exists, and it is NOT restored after a reload. Brought back, it
  is stored again in the same row.
- **Reclaim**: `Garage.owned(node)` is checked by `ZoneManager.missionProtected` (all three reclaim paths) and by
  `ParkedVehicle.untouched`, so streaming never takes an owned car.
- **Identity**: the restored car gets a fresh `CharacterInfo` in code carrying the stored id (the shared sub-resource
  rule); the paint is derived from that id, so the same id is the same colour. `VehicleInstanceData.paint` and
  `.upgrades` are carried and saved but nothing writes them yet (respray / NOS come with 3.3).
- **Authority**: the host stores and restores. A co-op guest's car goes into the host's session copy of the guest's
  profile and reaches the guest's file through the profile deltas; RESTORING is for this machine's own profile only,
  so a guest's garage car comes back when they host. A restored car is announced like any spawned vehicle.
- **Not done**: a damaged car is restored damaged (no free repair); a car wrecked while its row still says `home` is
  rebuilt at no less than 5 % health; only one garage (`home`) exists; the two-peer store path has no gate of its own.

Gate: `tools/godot/probe_garage.gd` (in `nightly_gates.sh`), 15/15 on the real World.tscn -- the bay exists, is marked
and one bay from the start car; a dropped car is not kept (control); driven in at 60 % health it is kept with that
condition; driven out the row loses its garage, back in it is one row again; written to the profile FILE, read back,
and a second world load puts the same id in the bay at 60 %.

### Authoring foundations (PLAN.md 2.0: AR3 + DataTable + MarkerRegistry + CR3, 2026-10-10)

Four pieces every later system (activities 2.1, encounters 2.2, careers 3.3, surprise events 4.3b) stands on. All but
`MarkerRegistry` are engine-free and unit-tested.

**`game.event.GameplayEvents` -- the one typed action -> consequence stream (AR3).** `Health.applyDamage` used to call
`WantedSystem.reportHit` and `GangSystem.reportHit` itself, `FirearmItem` called `report("gunfire")`, `ShopClerkSpot`
called both systems twice: every new consequence meant another hook inside the seam. Now a seam PUBLISHES what
happened and knows nothing of who cares:

| event (`GameplayEvent`, a sealed interface of records) | published by |
|---|---|
| `Damaged` / `Killed` (actor, target, at, headshot, weapon) | `Health.applyDamage` |
| `WeaponFired` (every shot, any character) | `FirearmItem.postGunshotStimulus` |
| `Threatened` (actor, clerk, the protecting gang or "") | `ShopClerkSpot.react` |
| `Theft` ("till", amount, the gang whose place it was or "") | `ShopClerkSpot.robTill` |
| `ZoneEntered` (the trigger's beat id) | `ZoneTrigger.fire` |
| `BalanceChanged` (from / to PLAYER ids, amount, reason) | `Economy.transfer`, bridged in `GameManager` |
| `FlagChanged` (a world flag) | `WorldLedger.setFlag` / `clearFlag` |

- **Authority only.** `publish` on a co-op client DROPS the event (a client's own shot runs the fire path too);
  `GameManager` installs "single player or the host". `EventBus` is unchanged: untyped Godot signals for the UI.
- **Order is by `Phase`, not by who subscribed first:** ACTIVITY -> CAREER -> ECONOMY -> WANTED -> GANG -> LEDGER ->
  DIRECTOR -> OBSERVER. Each subscriber gets the event and its `Ruling`. An ACTIVITY-phase subscriber may
  `sanction(by)` (the act is lawful in its context -- an officer shooting during an arrest: WANTED and GANG skip it),
  `veto(by)` (no later phase hears it) or `sandbox(by)` (it happened inside a mission REPLAY, CR7: the ledger does
  not record it; heat is ordinary and stays). An event published from inside a subscriber is queued and delivered
  after the current one. A subscriber that throws is logged and does not silence the rest.
- **`CrimeMap` says which crime an event is** (pure, `CrimeMapTest`; a test asserts every id it can return is a row
  of crimes.json / gangs.json). `WantedSystem` (phase WANTED) and `GangSystem` (phase GANG) subscribe; nothing calls
  into them to report a crime any more (`report` / `reportNow` remain as their own API and the probes' surface).
  A new consequence is a subscriber; a new crime is a table row + one line in `CrimeMap`; a new kind of act is a new
  record in `GameplayEvent`'s `permits` list + its publisher.
- `Actor` (id, faction, PLAYER / AI / NONE, name, storyId) and `Spot` (x, y, z, placeId) are plain data;
  `game.event.Actors` is the engine side (a body -> an Actor, an attacker known only by id -> a live player's body or
  an AI of unknown faction). A STORY character's `storyId` is its characterId (`AICharacter.storyCharacter`), ""
  for everyone else.
- Not published yet (no consumer until 2.1 / 3.0 / 3.3): VehicleTaken, ItemDelivered, Interacted, ActivityOutcome,
  CareerPushed / Popped, DebtOverdue. `car_theft`, `train_attack`, `bank_attack`, `attack_vip` are rows of
  crimes.json that nothing reports yet (as before).

**`util.DataTable<T>` + `util.DataReader` -- one loader, validated (the review's "typed records + one loader").**
Eight tables were each walked by hand with casts and `getOrDefault`: a misspelt key silently kept the default.
`DataReader` is a JSON object that remembers what was read from it -- `str / num / lng / integer / bool / strings /
nums / ints / stringLists / child / rows / items`, `reqNum / reqStr` for a value that must be there -- and `finish()`
names every key nobody asked for and every value of the wrong type with its path (`crimes.gunfire.min_star: unknown
key`). A key named `note`, ending `_note` or starting `_` is a comment. Several parsers may read one file (crimes.json
feeds the wanted rules, the dispatch and the recovery fees): a child object has ONE reader however many ask.
`game.data.Tables` is THE list: `CRIMES` (wanted, dispatch, fees), `GANGS` (rules, hunters, bodies per gang, hangout,
abduction), `ECONOMY`, `SUPPLIES`, `AMMO_SUPPLY`, `OUTFITS`, and `Tables.recovery()` (the two-file `RecoveryRules`).
A table with problems still LOADS (defaults fill the gaps -- a typo must not stop the game on a player's machine) and
logs each problem; the GATE refuses it: `DataTablesTest` loads every table from the source tree and fails on any
problem (its control parses a table with a typo and gets exactly the three problems). `reload()` re-reads a file and
tells its listeners -- `WantedSystem` / `GangSystem` re-derive their rules and keep the players' heat -- which is the
debug hot reload (console: `tables reload`; `tables` lists them). Each parser keeps its `parse(String)` (the unit
tests use it) beside `read(DataReader)`. Not in the list: the generated `weapon/weapon_catalog.json` and the baked
world records (places, street names, sidewalks) -- build outputs, not tuning.

**`world.MarkerRegistry` -- the one reader of level-design markers.** A building's `MARK_<kind>_<n>` Empties are
baked into its scene as nodes in the group `mission_marker` with their props as metadata (`kind`, `team`, `weapon`,
...; -Z is the way one faces). `ofKind(ctx, kind)`, `near(ctx, kind, at, radius)` (nearest first), `nearest(...)`,
`under(buildingRoot, kind)` (one building's own, no tree-wide index) return typed `Marker`s (`position()`,
`facing()`, `prop(key, def)`, `num`, `team()`). Buildings stream, so the index is rebuilt from the group when the
tree's node count changed or after 1 s, and a freed marker is never returned. Queries are for events (a mission
starting, a wave spawning), not every frame. `ShopClerkSpot.callResponders` (the gang's spawn points) is its first
user; F6's encounters and cover points (2.2) are the next. Console: `markers`.

**`game.WorldLedger` -- what the story changed in the WORLD for good (CR3).** The island is generated and streamed:
nothing in a scene can remember that a boss is dead. The ledger does, keyed by ids that survive streaming and
rebuilds: WORLD FLAGS (`setFlag / clearFlag / flag / isSet` -- a fact about the place, never a player's choice),
DEAD STORY CHARACTERS (`markDead / isDead`) and PLACE OVERRIDES (`setPlace(placeId, owner, state)`, `ownerOf(placeId,
generated)`). It is the HOST's (the co-op model: the world is the host's, the story is each player's), saved in the
world slot as `ledger` (`toMap` / `fromMap`, an old slot reads as empty), and a change marks the world dirty for the
coalesced autosave. CR3's fourth part, faction-baseline overrides, is `FactionManager`'s campaign layer (0.35): it
already has its owner, its save key and its replication, so it is not duplicated.
- A story character is DEAD once the ledger's subscriber (phase LEDGER) hears `Killed` with a `storyId` -- not inside
  a sandbox. `ZoneManager.spawnNamed` does not build one that is dead; a HAND-PLACED one (`storyCharacter` ticked in
  a scene) frees itself in `AICharacter._ready`; a load replaces the ledger FIRST and sweeps the live story
  characters it says are dead (`MissionDirector.removeDeadStoryCharacters`).
- A world STARTS with an empty ledger: `FrontEnd.start` resets it (Continue's load then replaces it), and for New
  game / Host also calls `MissionDirector.resetCampaign()` -- the director is an AutoLoad and used to carry the
  previous session's completed / unlocked sets into a new game started from the title in the same process.
  `GameManager.restartLevel` resets it with the factions.
- NOT yet: replication to clients (AR5's join baseline, 2.4 -- a client's ledger is empty, which is harmless today
  because only the host spawns AI and evaluates requirements); a consumer of place overrides (the first mission that
  changes a shop's owner reads `ownerOf`); typed `Flag<T>` keys with a declared scope (CR1, 2.1 -- they wrap this).
  Console: `ledger`, `ledger flag <id> [value]`, `ledger dead <storyId>`.

Gates: unit `DataReaderTest`, `DataTablesTest`, `GameplayEventsTest`, `CrimeMapTest`, `WorldLedgerTest`;
`probe_gameplay_events.gd` 21/21 (the tables load clean in the engine; a player's hit on a civilian is a star and on
a gang member a gang star with only the event between them -- controls: the same hit SANCTIONED gives none, an AI's
hit gives the player none; a transfer is an event; a killed story character is in the ledger and removed when
spawned again, an ambient one is not recorded, with the ledger reset the same boss lives; save -> reset -> load
brings the death, a flag and a place override back and sweeps the live boss); `probe_markers.gd` 15/15 (two Koban,
expected counts read from the scene file's TEXT; by kind, near, under, the facing of a turned building; one freed ->
its markers are gone). Both are in `tools/nightly_gates.sh`.

### The campaign graph, its lint, and the career override stack (PLAN.md 2.1 step 1: CR1 + CR2 + CR6, 2026-10-10)

ENGINE-FREE, and NOTHING RUNS ON IT YET: `MissionDirector` still owns the unlock sets the game plays by. This is the
declared campaign the Activity runtime (2.1, next) will read; it is here so the shape is fixed and proven first.

- **`game.campaign.FlagKey`** -- a flag is DECLARED: id, scope (WORLD = the host's ledger, PERSONAL = the player's
  profile; never both -- the co-op model's rule 2) and a finite set of values (a BOOL, or a CHOICE among names). The
  finite domain is what lets the lint walk every state.
- **`Requirement`** -- a typed predicate algebra, DATA not lambdas: `flag(key[, value])`, `achieved(activity[,
  variant])`, `career`, `cashAtLeast`, `storyAlive(storyId)` (a WORLD requirement: "the boss is alive in the world this
  would run in"), `beforeEnding / afterEnding`, `endingSeen`, `all / any / not`. It is asked against a
  `CampaignView`: ONE player's story + the world they are in.
- **`Effect`** -- what a variant changes: `set / clear(flag)`, `storyDead`, `place(id, owner, state)`,
  `ending(id)`, `chapter`. `world()` says which change the host's world (a guest's need the host's consent; a replay
  applies none).
- **`ActivityDef` / `CampaignBuilder` / `CampaignModule` / `content.CampaignModules`** -- a content pack is a class
  that declares flags, activities (`requires`, `variant(name, effects...)`, `sticky()`, `repeatable()`, `kind(JOB /
  RACE)`, `planned()` = named but not authored) and endings; the index lists the packs. `content.Act1` is what exists:
  `m01_konbini` (BOSS_KILLED -> the boss is dead in the world, BOSS_SPARED -> the personal flag) and the planned
  `m02_informant` (needs the spare AND the boss alive in that world). `openEnded()` until an ending is authored.
- **`CampaignGraph`** -- `isAvailable / available / whyNot / complete(activity, variant, write, world)`. Unlocks are
  DERIVED at every evaluation (a choice can CLOSE a branch); only `sticky()` is remembered
  (`CampaignState.sticky`). An activity NOBODY declared is not available -- MissionDirector's "no declared row =
  unlocked" let an unstreamed node open a gated mission. An ending is a state transition (phase `POST_ENDING`).
  Completions are remembered as `"activity#variant"`, MissionDirector's key shape.
- **`LiveCampaign(profile, ledger)`** is the real state (personal -> `PlayerProfile.campaign`, world ->
  `WorldLedger`); **`SimCampaign`** an in-memory one (the lint, tests, CR6's fake host), optimistic about career and
  money unless pinned.
- **`CampaignLint.check(graph)`** -- (1) everything NAMED is DECLARED (a requirement's flag / value / activity /
  variant / ending, an effect's flag / value / ending; every activity has a variant or is planned), (2) everything
  declared is REACHABLE, (3) **NO DEAD END**: a brute-force walk over every available activity x variant from the
  empty state; every reachable state must have reached an ending or still be able to. Capped (200 000 states; a
  truncated walk is a problem, not a pass). Notes say what was NOT proven: an open-ended campaign skips (3); the walk
  is one world with its one player -- the guest-in-another-world cross product (rule 3) is not checked yet.
- **`profile.CareerState` override stack (CR2)** -- `push(instanceId, career, real)` / `pop(instanceId)` (wherever
  it is in the stack) / `effective()` / `count(counter, n)` (onto a SCRATCH record under a TEMP override, discarded
  on pop; onto the real record under REAL) / `reconcile(running)` after a load (the journal is saved, the activity is
  not). Only the Activity framework will push and pop.

Gates (unit): `CampaignGraphTest` (derived unlocks, a branch that closes, sticky, repeatable, the live split of story
and world, a guest without consent, a world requirement), `CampaignLintTest` (the SHIPPED modules lint clean; a
branching sample with two endings is proven; the control -- a variant that clears the choice every later node needs
-- is found as `DEAD END`; undeclared names; an unstartable activity; a truncated walk), `CareerStateTest`.

### The Activity runtime -- typed Java missions (PLAN.md 2.1: AR1 = F5, CR4, CR5's checkpoint, CR6, CR7; 2026-10-10)

A mission, a job or a race is an **Activity**: a Java class a designer writes from typed parts, run by a framework
that owns everything a mission node used to hand-roll. No JSON mission graph, no beat scripting language (user,
2026-10-09: "mission design in Java, with strong types"). `game.activity`, all of it engine-free except
`ActivityRuntime`.

```java
public final class KonbiniActivity extends Activity {              // game.campaign.content
    @Override protected void define(Plan p) {
        p.startsOnZone("m01_start").cast(boss, crew...).relation("player", "gang_a", "HOSTILE")
         .replayWorld(Requirement.storyAlive(boss));
        p.rules().failWhenAllDown("every player is down").failWhen("left the area", a -> !a.host().present(boss));
        p.stage("FIGHT").checkpoint().marker(boss)
            .enter(a -> { for (String id : everyone) a.setFaction(id, "gang_a"); a.unlockDoors(25); })
            .on(GameplayEvent.Killed.class, e -> boss.equals(e.target().id()), (a, e) -> a.complete("BOSS_KILLED"))
            .when("the boss gives up", a -> crewUp(a) == 0 && a.host().healthFraction(boss) < 0.5, a -> a.go("SURRENDER"));
        p.stage("SURRENDER").enter(...).after(15, spared).when("he got away", ..., spared);
    }
}
// and in the content pack:   b.activity("m01_konbini").runs(KonbiniActivity::new).variant("BOSS_KILLED", ...)
```

| part | what it is |
|---|---|
| `Activity` | the class a designer extends; `define(Plan)` is called once per run. Tuning = its public fields. NO engine types. |
| `Plan` | stages (the first declared is the start), `rules()`, `startsOnZone`, `cast`, `relation` (faction overlay rows), `temporaryCareer(career, real, roles)`, `maxParticipants`, `closed()`, `replayPay(share)`, `replayWorld(needs)` |
| `Stage` | `enter` / `exit`, and TRIGGERS live while it is current: `on(EventType, match, react)` (a `GameplayEvent`), `after(seconds, react)` (once per entry), `when(name, holds, react)` (asked every step, level-triggered), `tick`; `checkpoint()`, `objective(speaker, line)`, `marker(what)` |
| `RuleSet` | live in every stage: `failWhenAllDown`, `failWhen`, `failOn(event)` (whoever did it: an outsider robbing the shop a participant clerks), `sanction` / `veto` (through the event's `Ruling`, phase ACTIVITY), `penalty(counter, n, event)` (a participant's career strike) |
| `ActivityInstance` | one RUN, handed to every reaction: `go(stage)` / `complete(variant)` / `fail(why)` (the first request in a step wins), `host()`, `board()`, `setFaction`, `unlockDoors`, `say`, `mark`, `nearestParticipantDistance` |
| `Blackboard` | the run's own state, typed by `Key<T>` constants (`count`, `number`, `flag`, `text`); goes into the checkpoint |
| `ActivityHost` | EVERYTHING an activity asks of the world: players, story characters, the placement, doors, the overlay, speaker lines, money. Two implementations: `ActivityRuntime` (engine) and `FakeActivityHost` (a table in memory + a clock) |
| `ActivityDirector` | runs N instances; see below |
| `ActivityResult` | what ONE participant got: outcome, variant, `storyCredit`, `worldApplied`, `pay` |

**What the director owns** (so no mission class does):
- **Who may start.** The OWNER's own story against this world: `CampaignGraph.isAvailable(id, LiveCampaign(their
  profile, the host's ledger))`. A guest needs the host's consent for an activity with a WORLD effect in any variant
  (`ActivityRuntime.grantWorldConsent`; the prompt UI is not built). `whyNot(id, player, mode)` says why.
- **Who takes part.** One OWNER; anyone walking into the start zone of a running, open activity JOINS as ASSIST. A
  player is in at most one run; an activity id runs once at a time (its story characters are one set in the world).
  Different activities run concurrently. A helper's `eligible` flag = could they have started it themselves.
- **The end.** `COMPLETED`: each ELIGIBLE participant gets the variant in THEIR story (`CampaignGraph.complete`); the
  variant's WORLD effects are applied once, through the owner; everyone is paid `economy.json`'s reward (an
  ineligible helper is paid and nothing else -- no spoiler-locking of their branch). `FAILED` / `ABORTED`: nothing
  credited; characters whose faction the run changed get the old one back (a completed run keeps them: the outcome is
  the world's new state). Always: `host.release(run)` re-locks its doors and drops its overlay, marker and staging,
  and the temporary career pops. Then `GameplayEvent.ActivityOutcome` is published.
- **The temporary career** (CR2): pushed at start / join for the listed roles, popped at any end; in a REPLAY it is
  always TEMP. `ActivityRuntime` reconciles journals once a second on the authority (an override whose run is gone).
- **Checkpoint + RETRY** (CR5). Entering a `checkpoint()` stage records `ActivityCheckpoint(activity, stage, mode,
  blackboard)` in the OWNER's profile (`activity_checkpoint`). A failed or aborted run keeps it; `retry(owner)`
  starts again AT that stage with that blackboard. A checkpoint restarts a STAGE: its `enter` must set up what it
  needs (earlier stages' did not run). Completing, or starting anything fresh, forgets it. A save load aborts every
  run (`SaveSystem.loadSlot`), so the checkpoint in the profile is what a retry after Continue starts from.
- **REPLAY** (CR7): the same class in a sandbox. Needs it completed, and each `replayWorld` need to hold (or
  `host.canStage` it). No story credit, no world effect, pay = reward x `replayPay` (default 0), penalties only onto
  the temporary career's scratch record; every event by a participant or about the `cast` is `ruling.sandbox`ed, so
  the ledger does not record a boss killed in a replay. Heat earned is ordinary and stays.
- **A broken activity fails by name** instead of hanging: an undeclared variant, an unknown stage, stages that loop
  without waiting (16 hops).

**`ActivityRuntime`** (AutoLoad, after RaceDirector) is the engine side: it owns the director, steps it in
`_physicsProcess`, subscribes it in `Phase.ACTIVITY`, and is the `ActivityHost` -- players are `PlayerRegistry` bodies
(the id is the body's characterId) with `Profiles.of(body)`; story characters are `MissionDirector`'s named registry;
the place is the `ActivityPlacement` node registered for the id; the overlay is `FactionManager.setActivityOverlay`
(a per-run layer over everything, kept apart from runtime flips; N at once, where `applyMissionTable` swapped one table
for the island); a speaker's line is `EventBus.radioChatter`. AUTHORITY ONLY (single player or the host).
- What the rest of the game hears: `EventBus.missionStarted / missionCompleted / missionFailed` exactly as for a legacy
  mission (HUD banner, autosave), and the three existing mission world events mirror a start / end to clients (their
  objective-type argument is `"ACTIVITY"`; no new event ints -- AR5 replaces this). A client's own result arrives in
  its profile.
- `MissionDirector.hasAchieved / hasCompleted / isMissionUnlocked` answer from THIS machine's profile for an id the
  campaign graph declares, and `onMissionCompleted` no longer records such an id: the one global copy every peer
  advanced from the host's signal is only the legacy `MissionInfo` missions' now.
- `RespawnSystem` tells it a player was hospitalised / arrested / abducted: the run they OWN fails (user, 2026-10-03).
  `ZoneTrigger.requiredMissionId` also accepts a running activity.
- **A placement node** (`game.mission.KonbiniMission`, `M01_Konbini.tscn`) implements `ActivityPlacement`: its
  position is the anchor, `configure(Activity)` sets the run's fields from its exports, and it mirrors the stage into
  its `phase` / `outcome` readouts. It declares nothing and decides nothing. The scene's `ZoneTrigger` is no longer
  one-shot: walking in again after a failure starts the job again.
- **New game is a new story** (`FrontEnd`): the profile's `CampaignState` is reset (money, cars, career records
  stay). Hosting does not reset it.

**Changed the same day on the user's play notes** ("hard to see the mission objective", "I accidentally enter the
mission"):
- **A mission is never started by walking in.** `ZoneEntered` on an activity's start zone makes the director call
  `host.offer(activity, player)`; `ActivityRuntime` shows it as an interact prompt, `Start: <title> (E)` (the runtime
  is the `control.Interactable` behind it), and the interact key calls `director.accept`. The offer is withdrawn 18 m
  from the placement, when it starts, or when it stops being startable. Walking into the zone of a job that is already
  RUNNING still joins it. A co-op guest's prompt and interact key are not on the wire (MSG_INTERACT, 3.0), so a guest
  who may start one still starts it by walking in.
- **The objective line.** `Stage.objective(speaker, line)` -> `host.say` -> a yellow line at the top centre of a
  participant's screen (30 px, outlined): bright for 8 s after it changes, then dimmed to 60 % and THERE for as long as
  the run is; gone with the run. A line somebody speaks is also radio chatter in the status feed; one with no speaker
  ("") is only the objective. This overrides the minimal-HUD "a subtitle, then gone" for objectives: it failed the play
  test. Local to the machine the activity runs on -- a co-op guest sees none yet (AR5).
- **The marker.** `Stage.marker(storyId)` puts a yellow arrow over that story character's head, drawn through walls,
  for a participant on this machine; cleared with the stage / the run.
- `KonbiniActivity` now has objectives ("Take down Kaneda's crew", "Kaneda gives up -- finish him, or let him run").

**Game-over rules** (CR4): `GameOverRule` (`id`, `breached(profile, story)`, `graceSeconds`, `warning`;
`GameOverRule.debtOver(...)`), declared with `CampaignBuilder.gameOverRule`, judged by `GameOverWatch` once a second on
the authority for every player: a breach is WARNED once, CLEARED if it stops, and past its grace it is THAT player's
game over -- `PlayerProfile.rollbackToCheckpoint()` (balance, debts, career, story, cars; the world is untouched, the
session goes on). `PlayerProfile.takeCheckpoint()` is called when a STORY completion is credited and the first time the
watch sees a clean profile, and NEVER in a breached state, so a game over cannot land in another. No module declares
a rule yet (the thresholds are a design decision), so nothing fires in play; the card and the safe-house respawn come
with the first rule.

**The konbini job, redesigned (user, 2026-10-11: "the current setup does not make sense: the player cannot enter the
store, the AI crew can shoot out ... the player should be able to trigger the mission while inside, or at least force
entry").** What was wrong was one fact: `island_buildings` puts the mission node on its building's footprint CENTRE,
and the scene had been authored as if that were the shop's door -- so the crew (offsets of a few metres round the
node) stood INSIDE a mission building whose doors were locked until the job started, and the start zone (22 x 16 m
about the node) reached the pavement by about a metre. Now:
* the shop is an ordinary OPEN konbini (`PUBLIC_BUILDINGS` -> its `_Shop` scene: clerk, counter, weapons), before,
  during and after the job; `OPEN_BUILDINGS` (locked until a mission) is empty;
* the mission node is turned to its building's yaw (`anchored_missions` carries it, `patch_missions` writes the
  basis) and the scene is authored in the BUILDING's frame, +Z = the shop front; a named character's `offset` is
  applied in its zone marker's frame (`ZoneManager`: it was a world offset);
* the crew stands on the pavement in front (local z 11-12; the facade is at 9.1), and the start zone is the whole
  shop plus that pavement (22 x 30 m), so the job is offered inside the store too: walk in, buy a gun, start it
  from behind the shelves. The fight is on the street, where the crew can path; the glass rule is the same for
  both sides (a round under 30 damage breaks a pane and stops, a heavier one carries on -- docs/combat.md).
`probe_konbini_mission` asserts it: the shop's doors unlocked before the job, 3 of 3 crew under open sky, the offer
taken with a roof over the player, the shop still open afterwards (kill / spare PASS, the control fails 2).
NOT done: a version with the crew INSIDE (needs AI on the interior navmesh, which only the enforcement dispatch
uses today); the clerk does not react to the fight.

**"Is it over?" and three shop defects found playing it (user, 2026-10-11).**
* **A result banner and a mission log.** A finished run was a sound and nothing else. `ActivityRuntime.announceResult`
  shows "MISSION COMPLETE -- <title>   +$<pay>" (green) or "MISSION FAILED -- <title> (<why>)" (red) for 7 s where
  the objective was, to this machine's player when they took part, and puts the same line in the status feed. The
  pause menu has a **MISSIONS** tab (`GameMenu.missionsPage`, from `ActivityRuntime.missionLog()`): every mission
  of the campaign graph as IN PROGRESS (its objective) / COMPLETED (how it ended) / AVAILABLE (marked M on the map)
  / LOCKED (why). This is the "mission list" of 2.1's leftovers in its read-only form: no start / replay / retry
  buttons yet.
* **E never opened a store again after it was closed with E** ("after the first purchase E cannot open again").
  `ShopMenu.closedThisFrame` refused a reopen "until E is released", and looked for the release only inside that
  method -- which runs only while E is DOWN. It is a span of 6 physics steps now. `probe_weapon_counter` closed with
  E only as its last step, and its next "open for the Esc test" was never checked: three checks added.
* **A clerk could not be held up without a gun** ("the robbery does not happen with normal melee"). A threat was a
  drawn non-fist weapon aimed, or the clerk being hurt -- and a punch does not reach over a counter. Fists (empty or
  holstered hands) and melee weapons now threaten in the combat stance from `MELEE_THREAT_RANGE` 4 m
  (`ShopClerkSpot.threatReach`); a gun still from 25 m. Only the reach is probed (`threat_reach_now`), not a played
  hold-up with raised fists.

**The mission test kit** (CR6). TIER 1, JUnit, engine-free: `KonbiniActivityTest` (15: every path of the shipped
mission against `FakeActivityHost` with scripted events and a clock -- start, surrender only when both conditions
hold, both spares, both kills, a death with no event, fail + restore, retry, a helper joining and being credited, a
helper who already did it, the guest's consent, a replay changing nothing), `ActivityDirectorTest` (11: the framework --
careers TEMP / REAL, sanction / veto / failOn an outsider, blackboard + checkpoint through a save file, timers,
concurrency, the owner leaving, replay pay, broken activities, the lint), `GameOverWatchTest` (5). `ActivityLint`
checks the CLASSES (a stage with nothing in it, two activities on one start zone, a `replayWorld` naming personal
state). TIER 2, headless in World.tscn: `probe_konbini_mission.gd --case=kill|spare [--control]` (36 checks: the offer and its
prompt, the objective line and the marker, the real
bodies, doors, overlay, profile, ledger, reward) and the generic `probe_activity.gd --activity=m01_konbini
--script=fail_retry|replay [--control]`; each control fails on exactly its asserted line.

**Found on the way:** `ZoneManager` created a `SidewalkWalkerController` for every promoted ped and never attached
it for a FIGHTER -- a parentless Node per promoted fighter, the "Leaked instance: Node" + "1 resources still in use
(SidewalkWalkerController.java)" at exit that had been seen once and not traced. It is freed now.

**Not built (PLAN.md 2.1 LEFT):** the race port (races are still `MissionManager` + `RaceDirector`); staging a replay's
world (a dead story character standing again -- needs the streamer to respawn a named character, so today a replay is
offered only where its world holds); the consent prompt, the retry prompt and the mission list (phone / map) -- the
APIs are `grantWorldConsent`, `retryNow`, `whyNotNow`; a guest's `carryHome` effects; world markers drawn for
`Stage.marker` (stored, `markedNow`); the faction overlay is island-wide, not participant-scoped (hostility is by
faction string); the game-over card.

### Street races — `game.mission.RaceDirector` + `world.RaceCheckpoint` (R2, AutoLoad, 2026-09-17)

GTA SA/VC-style checkpoint races over the existing road network, and the **first objective type
beyond ELIMINATE_ALL with real logic**. `MissionObjectiveType.RACE` had been schema only since C1.

**Where it sits is the F1 split, applied again.** "May this mission run" is `MissionDirector`'s;
"is it won yet" is `MissionManager`'s — and a race is the second kind, so `MissionManager.startMission`
hands a `RACE` mission to `RaceDirector` and the director hands the answer back through
`completeMission` / `failMission`, exactly as the ELIMINATE_ALL counter does. It is a separate class
rather than another branch in `MissionManager` because a race carries live per-racer state (progress,
laps, placings, a clock) and a per-frame tick that no counter-shaped objective has.

- **The route is checkpoints in index order, and they register themselves.** `RaceCheckpoint` calls
  `registerCheckpoint` in `_ready` and `unregisterCheckpoint` in `_exitTree` — the
  `Character`↔`SpatialEntityGrid` idiom — keyed by `raceId`, so a circuit authored inside a streamed
  zone assembles and disassembles itself with no tree scan, and a world holds as many circuits as it
  has names. Two gates claiming one index is refused and reported (`MissionDirector`'s duplicate-id
  rule, same reason: which gate is #2 must not depend on streaming order).
- **A checkpoint reports; it does not adjudicate.** It tells the director "this body touched index N"
  and nothing else. **Only the racer's OWN next index counts** — so driving back through a gate you
  already took is not progress and cutting the course cannot skip one — and that rule lives in one
  place because it is the same rule for every gate in the world. `orderedCheckpoints` is the control
  knob (`@Visible`, always on) that puts the naive "any untaken gate counts" implementation back, and
  the gate measures the difference rather than asserting it in prose.
- **The racer is the CHARACTER, never the vehicle**, keyed by `characterId` — the id the whole net
  layer already uses. A racer who wrecks their car, steals another and drives on is the same racer;
  one who bails out and runs the last 50 m finishes on foot, which is what GTA does and what falls
  out of keying on the driver. A carrier hands the gate **every** seated occupant, because who is
  enrolled is the director's answer and a passenger who is a racer has as much claim to the gate they
  were carried through as the driver.
- **The mask is not authored**: `CHARACTER | VEHICLE`, stated by the node, for `ZoneTrigger`'s reason
  — a seated occupant is on collision layer **0** (`CharacterDriveState.enter`), so a gate watching
  only CHARACTER is invisible to every car in the race, which looks exactly like a gate that was never
  wired. Likewise a gate with no authored `CollisionShape3D` states a default cylinder: an `Area3D`
  with no shape detects nothing and says nothing about it.
- **Enrolment needs no authoring.** Every live `Player` races (in co-op that is the whole session,
  the only default a mission cannot get wrong); AI racers and anyone else come from `addRacer`, which
  works mid-race so a late joiner is not a special case.
- **The MISSION ends when every HUMAN has finished**, not when the first one does — a co-op partner
  two corners behind would otherwise be cut off mid-race. The variant is `WON` if any human took place
  1, else `FINISHED`. AI racers keep their places and can end nothing: the mission is the players'.
  `MissionInfo.timeLimit` — declared since C1 and never implemented — is the time trial's clock here,
  and running it out calls `failMission`. Only the host may fail on the clock: two peers failing one
  mission is two events for one fact.
- **`endRace` FREEZES rather than wipes.** The placings, the clock and the roster stay readable until
  the next `startRace`, because the moment a race ends is exactly when the results are wanted — by the
  finish panel, by a beat that reads who won, and by a probe. Only `raceActiveNow()` changes.
- **Standings** are checkpoints cleared, then distance to the next gate, recomputed at 4 Hz. Cheap and
  exact enough for a HUD list; the only authoritative place is a FINISHED one, fixed when it is set.
- **A race that cannot be finished is refused, loudly.** Fewer than two gates under that `raceId` and
  `startRace` says so and does not start: a race silently running with no route is a mission the
  player can never complete, and the cause (a mis-typed name, or a zone that has not streamed) is
  invisible from the HUD.

**Authoring costs one field and one marker prefix.** `MissionInfo.raceId` (empty = the circuit named
after the mission — the case that needs no second name) and `raceLaps`; `WorldBaker` bakes
`race_<raceId>_<idx>` empties into gates, the same `<name>_<n>` convention `lane_`/`spawn_` already
use, with `radius`/`height` metas. **Shift+F4** on `DebugHarness` drops a four-gate circuit around the
nearest player and starts a one-lap RACE mission over it — through `MissionManager.startMission`, so
it exercises the shipped path rather than a shortcut.

**AI racers are the shipped traffic brain plus ONE behavioural exception.**
`VehicleAIController.racing` makes `shouldYield()` false: a race runs on a closed course, and
first-come-first-served right of way at every junction is exactly what makes an AI racer finish last.
Everything else a racer wants — a higher `cruiseThrottle`/`cruiseSpeed`, a bolder `cornerLateralAccel`
(3.2d's corner-speed governor) — is already an exported number, so a racer is TUNING plus that one
flag rather than a second controller.

**The HUD polls, and a race is not a SITUATION.** `ui.RaceHUD` (countdown, clock, position, lap and
checkpoint count, and the boost meter `Vehicle.getBoostFraction()` has exposed since the vehicle
overhaul with no gauge) is self-gated like `WeaponProgress`/`ScopeOverlay` and deliberately **not** in
`HUDManager`'s `BASE_LAYOUT`: a race is orthogonal to ON_FOOT/VEHICLE — you can finish one on foot —
so the table could only hold a stale answer. **A race therefore needs no `EventBus` signal of its
own**: the HUD polls, and the one event anything else cares about is the mission completing, which
already exists. `ui.GpsArrow` points at the racer's next checkpoint while a race runs and at the
player's own waypoint otherwise — DERIVED, never latched, because a race that WROTE the waypoint would
clobber the destination the player set before it and not give it back (W29's rule for the view
preference, applied to the waypoint).

**Replication is three constants and no new message.** `WORLD_EVENT_RACE_START` (key = raceId,
value = the countdown still to run, args = missionId, laps, then a `characterId` + `"0"/"1"` human
flag per racer — the ROSTER rides in the event because a client cannot re-derive which AI the host
enrolled), `_CHECKPOINT` (the RESULT — nextIndex and lap — not a delta, so a dropped grant is healed
by the next one) and `_FINISH`. **The race ENDING needs no event of its own**: it is the mission
completing or failing, which already replicates, and `RaceDirector` listens to those two signals on
every peer. Only the host grants a checkpoint (`onCheckpointTouched` returns immediately off the host)
and only the host decides a finish. Late join replays the start plus each racer's progress as *the
same events* a live race sends (`NetworkManager.sendBaselineRace` → `sendWorldEventTo`, new, and now
the shape every baseline can use), so a joiner runs the path a live event already exercises.
**The payload's shape has one owner**: `RaceDirector.startArgs` builds it and
`RaceDirector.applyRemoteStart` parses it, next to each other on purpose — an off-by-one between a
builder here and a parser in `GameManager` shows up as "the client thinks the AI is a human and waits
for it to finish", with nothing on either peer to say so. `GameManager`'s three `applyRace*` are pure
routing.

**Gate `tools/godot/probe_race.gd`** (42/42; `-- --control` turns `orderedCheckpoints` off and fails
exactly 4, with no cascade — each later case restarts the race, and the knob's only effect is whether
an out-of-order touch counts). Real Player, Vehicle and AICharacter bodies against the real AutoLoads,
started the shipped way (a `MissionInfo` written as a `.tres` and handed to
`MissionManager.startMissionFromPath`), never by calling `startRace`. Cases: a mission naming a
circuit that is not there does not start a race; the countdown holds the clock AND refuses a gate
cleared during it; the ordering rule (out of order, in order, and back through the one just taken);
the GPS target and the self-gated HUD; the lap closing into a finish and the mission completing as
`WON`, with the results still readable afterwards; two laps of the same four gates; the time trial
failing the mission; a **car** carrying the racer clearing a gate (mask 18); an AI racer enrolled
mid-race and scored by the same rules; standings; the `racing` exception measured on two real cars in
a real `IntersectionZone` (ambient yields, the SAME brain with the flag on does not); the co-op mirror
(the host's own wire payload fed back through `applyRemoteEventCsv` rebuilds its roster, and a
mirrored checkpoint/finish lands); and a duplicate index refused / a freed gate leaving the route.

**Not covered, on purpose:** the AI racer's LANE-FOLLOWING — a bare stand has no road network, and
driving a lane is `probe_road_traffic`'s and `probe_traffic_spawn`'s gate, not this one's; and the
two-process co-op run (`tools/net/run_net_*.sh`'s shape), for which what is asserted is the ANSWER each
seam reads. Race state is also **not saved** (I7's boundary): an interrupted race restarts with its
mission, which is the rule a fresh crowd already forced on every other objective.

**Probe traps.** The junction arbiter registers a car on `body_entered` and skips one with no
`VehicleAIController`, so a brain attached AFTER the car is already inside the volume is never
registered and reads as "not yielding" for the wrong reason; and re-attaching a brain to flip `racing`
loses that membership the same way (`VehicleProbeHelper.setRacing` flips the flag on the brain already
in the junction). Two helpers were added there rather than registering `attachController`/`shouldYield`
on the gameplay classes: a probe-support node exists precisely so a test does not add engine-visible
surface to `Vehicle` and `VehicleAIController`.

---

---

## AI (7-state singleton FSM)

The AI body is `AICharacter`; its brain is `AIController` (`com.openworld.ai`), which runs the
FSM in `gatherInput`. States are **stateless** singleton objects under `com.openworld.ai.character`.
All mutable data lives on `AICharacter`. `AIState.update()` returns the next state; a different
reference triggers a transition.

| State | Key behaviour |
|:------|:--------------|
| `PatrolState` | NavAgent random walk within `patrolRadius` of spawn. → Chase/Attack on sight. → Search on hit. |
| `ChaseState` | Sprint to target (or last known pos). → Attack when in range + LoS. → Patrol after `LOST_PLAYER_TIMEOUT` (3 s). |
| `AttackState` | Strafe laterally. Reaction delay before first shot. Per-shot `hitChance` roll. Suppression fire for `suppressionDuration` after losing LoS. → Search when suppression expires. → RefillAmmo when dry. |
| `SearchState` | Sprint to last known position, strafe to peek. Re-engage on sight. → Patrol after 5 s. |
| `RefillAmmoState` | Sprint to `ammoRefill` Area3D. Fill all weapons on arrival. → Patrol. |
| `EscortState` | Follow + defend a designated `Character`. → Attack if the escort target is attacked. |
| `FleeState` | Sprint away from an attacker for a set distance. → Patrol on arrival. |

Targeting is faction-aware (`AICharacter.discoverTarget()`): same-faction AI ignore each other
and neutral factions are never targeted (friendly escorts / non-hostile NPCs).

### Key AICharacter fields (timers all on AICharacter, not states)

```java
double attackTimer         // counts down per-shot cooldown
double lostPlayerTimer     // time since last LoS in Attack/Chase
double reactionTimer       // counts up from AttackState.enter; fires when >= reactionTime
double underAttackTimer    // set to UNDER_ATTACK_DURATION (2.5 s) on damage
double strafeTimer         // counts down; refresh strafe direction on <= 0
double searchTimer         // counts up in SearchState
Vector3 lastKnownPlayerPosition
Vector3 currentAimTarget   // where AimRay is tracking this frame
```

### SightRay vs AimRay separation

- **SightRay**: pure LoS check — `hasLineOfSight()`. Never moves the camera.
- **AimRay**: fire direction — `AICharacter.snapAimRay(target)` forces it to point at the
  computed aim target just before `command.fire = true`.
- These are independent so accurate LoS never implies accurate aim.

---

## Event System (EventBus AutoLoad)

`EventBus` is a global `Node` registered as AutoLoad. Any node reaches it via
`getNodeOrNull("/root/EventBus")`.

Key signals (not exhaustive — see `EventBus.java` for the full set, which also includes
`all_players_died`, `player_spawned`, `pickup_interact_changed`, `player_ammo_changed`,
`weapon_picked_up`, and the multi-character spawn/health/ammo signals used by `HUDManager`):

| Signal | Emitter | Payload |
|:-------|:--------|:--------|
| `player_died` | `Player.onDied()` | — |
| `enemy_killed` | (future use) | score: `int` |
| `player_health_changed` | (future use) | currentHealth: `float` |
| `ammo_picked_up` | (future use) | weapon index: `int` |
| `character_eliminated` | `Health.takeDamage()` | `Signal7`: attackerName, attackerFaction, victimName, victimFaction, weaponName, weaponIcon, headshot |

`GameManager` connects `playerDied → onPlayerDied()` in `_ready()`.
The HUD (`HUDManager`/`CharacterHUD`) connects `characterEliminated` for the kill feed.

---

## MovementController flags (Player vs AICharacter)

| Export flag | Player | AICharacter |
|:------------|:------:|:-----------:|
| `worldSpaceMovement` | `false` | `true` |

Player input is camera-relative (rotated by `camRotation` at the source, in `PlayerController`).
AI input is world-space (set directly by the AI FSM).

**Combat facing is the AIM yaw, not the camera yaw.** `MovementController.aimYaw()` yaws `meshRoot`
toward `Character.getAimTargetPosition()` — the same world point the spine IK (`SpineAimModifier`,
a `LookAtModifier3D` tracking the `AimTarget` marker) and the bullet converge on. The TPS camera
sits off the shoulder, so its yaw and the body→aim-point yaw differ by several degrees at close
range: keying the body off the camera left the visible body/gun square to a wall while the shot
went past it. It falls back to the raw `camRotation` for a non-`Character` body or an aim point
within 0.5 m horizontally (directly overhead/underfoot). Together with the muzzle leg of the
two-stage trace this makes the three agree — body, bone-driven gun, and bullet.

---

## Audio: every sound is a file (2026-09-29)

No sound is synthesised in code (`SoundTest` refuses `new AudioStreamWAV(` / `AudioStreamGenerator` under
`src/main/java`). A non-weapon sound is a `com.openworld.audio.Sound` entry naming `assets/audio/<file>.ogg|.wav`,
played through `audio.Sounds` (`stream` / `play3D`); a missing file is silence plus one `[Sounds] missing audio`
line. Weapons keep `fire_audio` / `reload_audio` in their scenes. `assets/audio/README.md` is the list of what
ships, what is wired but missing a file (`glass_shatter`, `hit_marker`) and what is not wired yet; `SoundTest`
checks its "Wired in code" table against the enum. Licence rule as for art: CC0 / MIT / public domain, credited.

### Two-lane ramps, the Suburb crossroads, and the lane-split pair kept level (2026-10-04, user-asked)

- **Every expressway ramp's BODY is two lanes** (`island_expressway.widen_ramps`, user: a one-lane ramp was a race
  bottleneck; user's choice "narrow to 1 at the gore"). Each EXPRESSWAY end (a gore = AUX link, or a joint = a lane split
  or JCT carriageway) keeps the one lane its mainline slot hands over until the ramp has parted from every road it meets
  there, then opens or closes over `WIDEN_TAPER` (13 m: the rule wants 11.6 m at 40 km/h x 0.25, and
  `island_grades.ramp_curves` never subdivides a taper span). The ground end runs both lanes into the intersection. The
  mainline aux slots are unchanged. Rules each a measured defect first:
  * **The hold is side-aware**: a one-way road lays its lanes to the LEFT of its stations, so the added lane reaches only
    toward a partner on the left (port exit 140 -> 109 m single, Y4 94 -> 59).
  * **The road's BASE stays one lane** (stations carry the two): `island_dike` sizes a crossing's floor from the base,
    and at two the Suburb exit stayed up over the crest 30 m longer and came down at 8.4 %.
  * **A station reused for a taper end must lie OUTSIDE the taper** and lane counts are assigned by those stations, or
    a 13 m taper became 10 m. `island_grades.level_gores` never inserts its parting station into a taper span, nor within
    `GORE_MIN_SPAN` of the station BEFORE it (two coincident stations were a zero span the profile solve divided by).
  * Single stretches left: where a ramp still runs beside its mainline (a gore) or its lane-split sibling (T1+T3 and
    T2+T4 run 6 m apart: a split hands each ramp one lane of a 2-lane carriageway).
- **The Suburb junctions** (probe_road_clear: connectors through two overlapping pads). `kogai_michi` met `wangan_dori` at
  34 deg (mouths ~200 m apart), the dike side road ran 20-40 m from `wangan_dori` and crossed it 45 m on, and the exit
  landed on THAT junction. Now (`tools/island_suburb_kogai.py`, one-shot on the arterials input): `wangan_dori`'s
  junction at record x 775 is a crossroads of `eki_ginza_suburb` (north) and the **Suburb exit** (south,
  `island_plan.SB_JUNCTION` / `SB_JUNCTION_ROADS`); `kogai_michi` leaves `wangan_dori` at the Suburb station's own T
  (x 929, opposite `ekimae_suburb`), and the side road's piece there is not built (`island_dike.SIDE_DROP`; a dropped
  piece keeps its number, and a frozen record naming `teibo_sokudo_<n>` matches the family, `island_core_streets._family`).
  Moving the side road away instead (`SIDE_EXTRA` 60 -> 25) cost the exit 60 m of run: 12 %.
- **No street crosses a ramp mid-air** (`island_streets._raised_ramp`): a line crossing an expressway road between
  `RAMP_AT_GRADE` 0.6 m and `RAMP_UNDER` 5.5 m (too high to meet, too low to pass under) is refused, so it is nudged
  or dropped. `cho_sw_345` had cut the connector's SB exit 3 m up in its descent; that junction's pad sloped 20 % and
  the two-lane deck overhung its own connectors (probe_road_clear).
- **The port's EB entrance with two lanes**: its second lane (on its left) lay over the dike road's footway, so the dike
  road moved a further 5 m north (`tools/island_dike_port_gap_2lane.py`, one-shot); its T arm leans 30 deg east toward
  the merge (`_t_arm(skew=, lean=)`, `PORT_ON_SKEW`: square, the gap left ~10 m to turn 90 deg, an R 9 corner whose
  setback slid all three mouths onto one point); it levels over a 30 m landing into the T (`PORT_ON_LANDING`: on the
  turn the inner lane's path is shorter, so a grade there read K 4.4), and it merges 20 m further east
  (`PORT_ON_X` -250) for the length. `ramp_curves` also subdivides a ramp's last span into a GROUND junction's mouth
  (`rg._tapers` counted any non-SEGMENT end as a taper) and faces that mouth level.
- **T1 + T3 are ONE profile** (`island_grades.PAIR_RAMPS`): each ramp is solved alone, and the two halves of the EB
  lane split, 6 m apart, came out 0.5-0.8 m apart -- a step probe_road_clear reads as a wall. The later one takes the
  earlier one's SOLVED height on every sample of a run >= 60 m beside it. Limited to that pair on purpose: pinning a JCT
  split's halves (Y1/Y2, which part vertically) put Y2 at 7 %, and pinning T4 to T2 met T4's held gore at another slope.

### Every crossing is a junction; two lanes at every gore (2026-10-04 evening, user-asked)

- **A new layout gate: `island_layout.ungapped_crossings`** (asserted; also in `--check`). Two at-grade road
  centrelines crossing with no junction (expressway and rail skipped, |dz| < 4 m), and a road passing THROUGH a pad it
  is not an arm of (within 0.85 of the nearest mouth's distance from the centre, or through the mouths' convex hull).
  The committed layout had 6; validate and flow read every one clean, because a crossing is two consistent roads.
- **Three causes, each fixed at its source:**
  * `island_core_streets.CUT_CROSSINGS` is on: an authored street crossing a road between its ends makes a crossroads
    there. `kojo_minami` is removed (the dike's side road fronts that block), and the Industry station's access
    (`island_rail_layout.HUB_ACCESS`, at (103, -664)) joins the side road x kojo_waku crossroads: a 5-arm pad.
  * `island_streets._line_ok` / `_line_split`: a crossing that crowds a junction is dropped as a node, and now it is
    also a WALL the line may not pass. The line keeps the run of its nodes with the most junctions, and its limit
    stops a new-line crossing from extending it past the wall.
  * `plan_region`: a crossing of two NEW lines given up (e.g. for MIN_SPAN) is no longer still crossed. At settle,
    one of the two lines is trimmed short of it: the line whose shorter side holds fewer junctions loses that side.
- **Every expressway ramp is two lanes at its gore** (`ENTRY_LANES` / `EXIT_GROUND_LANES` 2, and the three ground
  ramps that defaulted to 1). The four T ramps stay one lane at BOTH ends: at J0 the 2+2 Wangan splits lane by lane,
  and their spur gores would need a 108 m taper span where the bridge-approach stations are 71-76 m apart (the slot
  ran to the road's end; `T_GORE_LANES`, `widen_ramps` already skips the hold at a two-lane gore). Five rules came
  with it:
  * `point_validate.check_tapers` exempts an ENTRANCE's gore station: the acceleration lane begins at the nose at
    full width. It mirrors the exit exemption that was already there.
  * `island_grades.level_gores` is side-aware. A one-way ramp lays its lanes LEFT of its driving direction, so with
    the mainline on its right the bands have parted at `half(main) + edge + the mainline's AUX width there + 1 m`.
    The old full-width rule held a two-lane exit ~30 m too long. The aux term is load-bearing: at a gore the ramp's
    lanes lie on the mainline's aux pavement.
  * `island_grades.ramp_curves` and `island_dike.crossing_needs`: a ramp's own GROUND junction (its arms, `TEE_SKIP`
    40 m) is not a road it flies over. The wider band read port_off as crossing the port loop's dike ramp, and it
    was lifted 17 m.
  * `island_expressway.station_by_x` faces an inserted station on its alignment's design tangent. Chord-faced where
    the Wangan bends, port_off's mouth read 5.7 deg off and the gate said `ramp_wrong_side`.
  * `_carry` rounds its end to the NEARER station and never onto the road's end. Y3's carry rounded up onto the
    connector joint, which left an `open_end`.
- Re-placed for room: `Y3_ON_Y` -700 -> -650 (Y3 descends in one straight grade after its last crossing,
  `Y3_GORE_HOLD`), `PORT_OFF_X` -200 -> -170, `PORT_ON_X` -250 -> -230; Y2 flies on a 4.5 % cone.

