package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.DirectionalLight3D;
import godot.api.Environment;
import godot.api.Node;
import godot.api.PackedScene;
import godot.api.WorldEnvironment;
import godot.core.Color;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import com.openworld.ai.vehicle.VehicleAIController;
import com.openworld.carrier.vehicle.Vehicle;
import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.FactionManager;
import com.openworld.character.Player;
import com.openworld.game.GameManager;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Streams open-world zones in and out around players (PLAN.md Part E / E1) — registered as the
 * AutoLoad singleton "WorldZoneManager".
 *
 * <p>{@link WorldZoneMarker}s register here; each tick the manager loads a zone when a player comes
 * within its {@code loadRadius} and unloads it when all players are beyond {@code unloadRadius}
 * (hysteresis prevents boundary flicker). Loading streams in the zone's {@link SpawnConfig} groups
 * (recycled through a {@link SpawnPool}) and {@link NamedCharacterConfig} story AI; unloading
 * returns pooled bodies to the pool and frees named ones.
 *
 * <p><b>Authority:</b> spawning/despawning AI is host-only ({@code NetworkManager.isServer()}) —
 * clients receive the bodies through the existing {@code announceSpawn → MSG_SPAWN} replication
 * path, and late-joiners via {@code sendBaselineSpawns}. Optional zone <i>geometry</i> is purely
 * cosmetic and is instanced locally on every peer.
 *
 * <p>Mirrors {@link SpatialEntityGrid}'s AutoLoad shape: JVM-static {@link #get()} set in
 * {@code _ready()} and cleared in {@code _exitTree()}, where pooled bodies + loaded geometry are
 * also freed (leak discipline — see CLAUDE.md "Known Quirks").
 */
@RegisterClass(className = "WorldZoneManager")
public class WorldZoneManager extends Node {

    private static WorldZoneManager instance;

    /** The live manager, or null if the AutoLoad isn't present (test scenes). */
    public static WorldZoneManager get() { return instance; }

    /** Seconds between load/unload evaluations. */
    @Export @RegisterProperty public float evalInterval = 0.5f;

    /** Max recycled AI bodies the pool retains. */
    @Export @RegisterProperty public int poolCapacity = 64;

    /** Print per-zone load/unload decisions + pool stats to the Output log (E1 walk-test aid). */
    @Export @RegisterProperty public boolean debugLog = true;

    /**
     * Recycle AI bodies through the {@link SpawnPool} across load/unload. <b>Default off / EXPERIMENTAL:</b>
     * reusing a full character body subtree (detach via {@code removeChild}, re-attach via {@code addChild})
     * is unsafe in godot-kotlin-jvm — the body carries a {@code top_level} camera, a muzzle-flash
     * {@code GPUParticles3D}, and a nameplate {@code SubViewport}, and re-attaching that subtree
     * dereferences transforms/particles in a half-initialised state ({@code get_global_transform "not
     * inside tree"} / {@code particles is null}) → native use-after-free crash. With it off, unload frees
     * and load instantiates fresh — correct and stutter-tolerable; spreading spawns across frames is the
     * proper perf answer (TODO) rather than body reuse. Leave off unless you are actively hardening reuse.
     */
    @Export @RegisterProperty public boolean recycleBodies = false;

    private static final String AI_SCENE_PATH =
            "res://src/main/resources/com/openworld/character/AICharacter.tscn";

    private final List<WorldZoneMarker> markers = new ArrayList<>();
    private final Map<WorldZoneMarker, LoadedZone> loaded = new HashMap<>();
    private SpawnPool pool;
    private double evalTimer = 0.0;
    /** Instance id of the scene root last seen, to detect a scene reload/restart (this AutoLoad survives it). */
    private long lastSceneInstanceId = 0;
    /** The loaded zone whose RegionConfig is currently applied globally (I4) — null = baseline / no region. */
    private WorldZoneMarker activeRegionMarker = null;
    // The scene environment as authored, captured the first time a region overrides it, so leaving every
    // region restores the original look instead of leaving the last region's lighting/fog stuck.
    private boolean envBaselineCaptured = false;
    private Color   baselineLightColor;
    private boolean baselineFogEnabled;
    private float   baselineFogDensity;

    /** Per-loaded-zone bookkeeping so unload returns exactly what load created. */
    private static final class LoadedZone {
        final List<AICharacter> pooled = new ArrayList<>();   // SpawnConfig AI → returned to pool
        final List<Character>   named  = new ArrayList<>();   // NamedCharacterConfig AI → freed
        final List<AISquad>     squads = new ArrayList<>();   // one per SpawnConfig group (E3) → freed
        final List<Vehicle>     vehicles = new ArrayList<>(); // VehicleSpawnConfig traffic (I3) → freed
        final Map<Vehicle, AICharacter> driverOf = new HashMap<>(); // traffic car → its AI driver (I3c)
        Node geometryInstance;                                // cosmetic, freed on unload
    }

    @RegisterFunction
    @Override
    public void _ready() {
        instance = this;
    }

    @RegisterFunction
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        for (LoadedZone lz : loaded.values()) {
            if (lz.geometryInstance != null && GD.isInstanceValid(lz.geometryInstance))
                lz.geometryInstance.queueFree();
        }
        loaded.clear();
        markers.clear();
        if (pool != null) pool.clear();
    }

    // ── Marker registry ───────────────────────────────────────────────────────

    public void registerMarker(WorldZoneMarker marker) {
        if (marker != null && !markers.contains(marker)) {
            markers.add(marker);
            warnIfMisSized(marker);
        }
    }

    /** Read-only view of the registered zone markers (I5 map/minimap region outlines). */
    public List<WorldZoneMarker> getMarkers() { return markers; }

    /**
     * Debug-gated sanity check on a zone's trigger radii. Both {@code loadRadius} and
     * {@code unloadRadius} are measured from the marker (zone <b>center</b>), independent of
     * {@code size}, so for sane streaming they must satisfy
     * {@code unloadRadius > loadRadius > halfExtent} — otherwise the zone unloads while the player is
     * still inside/near the spawn box (flicker, or "everything unloads the moment I step out").
     * Logs once at registration; no behavior change. See CLAUDE.md "Sizing a zone".
     */
    private void warnIfMisSized(WorldZoneMarker marker) {
        if (!debugLog || marker.zone == null) return;
        WorldZone z = marker.zone;
        float halfExtent = (float) Math.max(z.size.getX(), z.size.getZ()) * 0.5f;
        if (z.unloadRadius <= z.loadRadius || z.loadRadius < halfExtent) {
            GD.print("WorldZoneManager: zone '" + z.zoneId + "' has mis-sized radii (load="
                    + z.loadRadius + " unload=" + z.unloadRadius + " halfExtent="
                    + String.format("%.1f", halfExtent) + "m). Expected unloadRadius > loadRadius > "
                    + "halfExtent (radii are center-relative — see CLAUDE.md 'Sizing a zone').");
        }
    }

    public void unregisterMarker(WorldZoneMarker marker) {
        if (marker == null) return;
        if (loaded.containsKey(marker)) unload(marker);
        markers.remove(marker);
    }

    // ── Streaming tick ──────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _physicsProcess(double delta) {
        detectSceneReload();
        cullFinishedVehicles();   // every frame (anti-jam) — a DESPAWN car must not idle at the lane end

        evalTimer -= delta;
        if (evalTimer > 0.0) return;
        evalTimer = evalInterval;

        for (WorldZoneMarker marker : new ArrayList<>(markers)) {
            if (!GD.isInstanceValid(marker) || marker.zone == null) continue;
            float dist = nearestPlayerDistXZ(marker.getGlobalPosition());
            boolean isLoaded = loaded.containsKey(marker);
            if (!isLoaded && dist < marker.zone.loadRadius) {
                load(marker);
            } else if (isLoaded && dist > marker.zone.unloadRadius) {
                unload(marker);
            } else if (debugLog && dist < marker.zone.unloadRadius * 1.2f) {
                // Approach feedback (only for zones the player is near, so far zones stay quiet).
                GD.print("WorldZoneManager: zone '" + marker.zone.zoneId + "' nearestPlayer="
                        + String.format("%.1f", dist) + "m  [load<" + marker.zone.loadRadius
                        + " unload>" + marker.zone.unloadRadius + "]  "
                        + (isLoaded ? "LOADED" : "idle"));
            }
        }

        updateActiveRegion();
        maintainTraffic();
    }

    /**
     * Pick the active region (PLAN.md I4) = the nearest loaded zone that carries a {@link RegionConfig},
     * and apply its <i>global</i> ambience (faction table, AI-LOD bias, lighting/fog, music) only when it
     * changes — so several simultaneously-loaded zones don't thrash the environment, and the player's
     * surroundings track whichever region they're closest to. Leaving every region restores baseline.
     */
    private void updateActiveRegion() {
        WorldZoneMarker nearest = null;
        float best = Float.MAX_VALUE;
        for (Map.Entry<WorldZoneMarker, LoadedZone> e : loaded.entrySet()) {
            WorldZoneMarker m = e.getKey();
            if (!GD.isInstanceValid(m) || m.zone == null || m.zone.regionConfig == null) continue;
            float d = localPlayerDistXZ(m.getGlobalPosition());   // ambience follows THIS peer's player
            if (d < best) { best = d; nearest = m; }
        }
        if (nearest == activeRegionMarker) return;
        activeRegionMarker = nearest;
        applyRegion(nearest != null ? nearest.zone.regionConfig : null);
    }

    /**
     * Push a region's global ambience into the shared systems (PLAN.md I4). A null {@code rc} restores
     * baseline (faction defaults, LOD 1.0, the authored environment) — called when the player leaves the
     * last region. Every step is null/absent-safe so test scenes without a FactionManager or
     * WorldEnvironment simply skip that effect.
     */
    private void applyRegion(RegionConfig rc) {
        // Faction relationships (host + clients resolve locally; betrayal flips still replicate).
        Node fmNode = getNodeOrNull(new NodePath("/root/FactionManager"));
        if (fmNode instanceof FactionManager fm) fm.applyTable(rc != null ? rc.factionTable : null);

        // AI level-of-detail range (process-global).
        AICharacter.setLodDistanceBias(rc != null ? rc.aiLodBias : 1.0f);

        // Scene environment: sun colour temperature + fog. Capture the authored look once so we can revert.
        applyEnvironment(rc);

        if (debugLog) {
            GD.print("WorldZoneManager: active region → "
                    + (rc != null ? "'" + rc.regionName + "' (aiDensity=" + rc.ambientAiDensity
                        + " vehDensity=" + rc.vehicleDensity + " lodBias=" + rc.aiLodBias + ")"
                        : "none (baseline restored)"));
        }
    }

    private void applyEnvironment(RegionConfig rc) {
        DirectionalLight3D light = findInScene(DirectionalLight3D.class);
        WorldEnvironment we = findInScene(WorldEnvironment.class);
        Environment env = (we != null) ? we.getEnvironment() : null;

        if (!envBaselineCaptured && (light != null || env != null)) {
            if (light != null) baselineLightColor = light.getColor();
            if (env != null)  { baselineFogEnabled = env.isFogEnabled(); baselineFogDensity = (float) env.getFogDensity(); }
            envBaselineCaptured = true;
        }
        if (!envBaselineCaptured) return;

        // Each field is FULLY established to this region's look: the region's override if it specifies
        // one (> 0), otherwise the captured baseline. So switching from a foggy region into a non-foggy
        // one (or leaving all regions, rc == null) reverts that field to baseline instead of leaving the
        // previous region's fog/tint stuck — the "fog bleeds into the other region" bug.
        boolean useTemp = rc != null && rc.lightTemperature > 0f;
        if (light != null) {
            if (useTemp) light.setColor(kelvinToColor(rc.lightTemperature));
            else if (baselineLightColor != null) light.setColor(baselineLightColor);
        }
        boolean useFog = rc != null && rc.fogDensity > 0f;
        if (env != null) {
            if (useFog) { env.setFogEnabled(true); env.setFogDensity(rc.fogDensity); }
            else { env.setFogEnabled(baselineFogEnabled); env.setFogDensity(baselineFogDensity); }
        }
    }

    /** Region density multiplier on a base spawn count, clamped to ≥ 0; identity at density 1.0. */
    private static int scaledCount(int base, float density) {
        if (density == 1.0f) return base;
        int n = Math.round(base * density);
        return n < 0 ? 0 : n;
    }

    /** Depth-first search of the current scene for the first node of the given type (null if none). */
    @SuppressWarnings("unchecked")
    private <T extends Node> T findInScene(Class<T> type) {
        if (getTree() == null) return null;
        Node scene = getTree().getCurrentScene();
        return scene != null ? (T) findOfType(scene, type) : null;
    }

    private Node findOfType(Node node, Class<?> type) {
        if (type.isInstance(node)) return node;
        for (Node child : node.getChildren()) {
            Node hit = findOfType(child, type);
            if (hit != null) return hit;
        }
        return null;
    }

    /**
     * Compact colour-temperature → RGB approximation (Tanner Helland), normalized to a Color with white
     * at ~6600 K: warmer (lower K) tints orange, cooler (higher K) tints blue — the city↔mountain shift.
     */
    private static Color kelvinToColor(float kelvin) {
        double t = Math.max(1000f, Math.min(40000f, kelvin)) / 100.0;
        double r, g, b;
        if (t <= 66) {
            r = 255;
            g = 99.4708025861 * Math.log(t) - 161.1195681661;
        } else {
            r = 329.698727446 * Math.pow(t - 60, -0.1332047592);
            g = 288.1221695283 * Math.pow(t - 60, -0.0755148492);
        }
        if (t >= 66)      b = 255;
        else if (t <= 19) b = 0;
        else              b = 138.5177312231 * Math.log(t - 10) - 305.0447927307;
        return new Color((float) clamp01(r / 255.0), (float) clamp01(g / 255.0), (float) clamp01(b / 255.0), 1.0f);
    }

    private static double clamp01(double v) { return v < 0 ? 0 : (v > 1 ? 1 : v); }

    /**
     * Per-frame anti-jam sweep (PLAN.md I3b): free any traffic vehicle that reached a dead-end lane
     * ({@link VehicleAIController#isFinished()}) the moment it finishes, instead of letting it idle at
     * the lane end until the throttled {@link #maintainTraffic} tick (where stacked finished cars would
     * collide into a pile-up). Cheap — an `isFinished` check, no distance maths. Top-up still happens on
     * the throttled tick. Host/SP-only, like the spawn (synced model — clients mirror via despawn).
     */
    private void cullFinishedVehicles() {
        if (loaded.isEmpty()) return;
        NetworkManager net = networkManager();
        if (net != null && net.isNetworked() && !net.isServer()) return;
        for (LoadedZone lz : loaded.values()) {
            if (lz.vehicles.isEmpty()) continue;
            Iterator<Vehicle> it = lz.vehicles.iterator();
            while (it.hasNext()) {
                Vehicle v = it.next();
                boolean dead = !GD.isInstanceValid(v);
                if (dead || (v.getController() instanceof VehicleAIController c && c.isFinished())) {
                    freeTrafficCar(lz, v, net);
                    it.remove();
                }
            }
        }
    }

    /**
     * Ephemeral ambient-traffic upkeep (PLAN.md I3b). Ambient cars are <b>disposable</b>: what is kept
     * constant is the <i>population</i> near the player, not any individual vehicle. Each loaded zone is
     * (1) <b>culled</b> — vehicles that reached a dead-end lane ({@link VehicleAIController#isFinished()},
     * from the lane-graph chaining) or drifted beyond {@code unloadRadius} of every player are freed; and
     * (2) <b>topped up</b> — respawned to the zone's configured count at a route entry. This is the
     * non-circular counterpart to a ring road: a car drives its lane, chains through junctions while
     * lanes connect, and is recycled (despawn + fresh spawn — never teleported, which would pop / break
     * snapshot interpolation) once it runs out of network.
     *
     * <p>Host/SP-only (PLAN.md I3c synced model) — the host owns the traffic population; clients mirror
     * each spawn/despawn over MSG_VEHICLE_SPAWN / MSG_DESPAWN and free ghosts via the client reconcile.
     */
    private void maintainTraffic() {
        if (loaded.isEmpty()) return;
        NetworkManager net = networkManager();
        if (net != null && net.isNetworked() && !net.isServer()) return;
        Node container = charactersContainer();
        if (container == null) return;

        for (Map.Entry<WorldZoneMarker, LoadedZone> e : loaded.entrySet()) {
            WorldZoneMarker marker = e.getKey();
            LoadedZone lz = e.getValue();
            if (!GD.isInstanceValid(marker) || marker.zone == null) continue;
            List<VehicleSpawnConfig> configs = new ArrayList<>();
            for (VehicleSpawnConfig vc : marker.zone.vehicleSpawnConfigs) if (vc != null) configs.add(vc);
            if (configs.isEmpty() && lz.vehicles.isEmpty()) continue;

            // (1) Cull finished / dead / out-of-range cars (driver freed with the car). A car a player
            // carjacked is released, not freed, by freeTrafficCar — so reclaiming it on out-of-range just
            // untracks it and hands it to the player.
            Iterator<Vehicle> it = lz.vehicles.iterator();
            while (it.hasNext()) {
                Vehicle v = it.next();
                boolean dead = !GD.isInstanceValid(v);
                boolean reclaim = dead
                        || (v.getController() instanceof VehicleAIController c && c.isFinished())
                        || nearestPlayerDistXZ(v.getGlobalPosition()) > marker.zone.unloadRadius;
                if (reclaim) {
                    freeTrafficCar(lz, v, net);
                    it.remove();
                }
            }

            // (2) Top each zone back up to its configured vehicle count (region-density scaled to match
            // the load count, PLAN.md I4), cycling configs round-robin.
            float vehDensity = marker.zone.regionConfig != null
                    ? marker.zone.regionConfig.vehicleDensity : 1.0f;
            int target = 0;
            for (VehicleSpawnConfig vc : configs) target += scaledCount(vc.count, vehDensity);
            Vector3 center = marker.getGlobalPosition();
            int spawnIdx = lz.vehicles.size();
            for (int k = lz.vehicles.size(); k < target && !configs.isEmpty(); k++) {
                VehicleSpawnConfig vc = configs.get(k % configs.size());
                Vehicle v = spawnVehicle(vc, center, container, findRoute(vc.routeName), spawnIdx++, lz);
                if (v != null) lz.vehicles.add(v);
            }
        }
    }

    /**
     * This is an AutoLoad, so it survives {@code reloadCurrentScene()}/{@code changeSceneToFile()}
     * (restart, level change). Pooled bodies are parentless — held only by the {@link SpawnPool}
     * deque, NOT in the scene tree — so a scene reload does <b>not</b> free them; re-acquiring one
     * into the new scene resurrects a body that references freed nodes → crash. Detect the scene
     * swap and drop all carried-over state so the new scene starts clean. ({@code loaded} entries key
     * off the old scene's now-freed markers; those bodies were children of the freed scene and are
     * gone with it — only the pool needs explicit freeing.)
     */
    private void detectSceneReload() {
        if (getTree() == null) return;
        Node scene = getTree().getCurrentScene();
        long id = scene != null ? scene.getInstanceId() : 0;
        if (id == lastSceneInstanceId) return;
        lastSceneInstanceId = id;
        loaded.clear();
        if (pool != null) { pool.clear(); pool = null; }
    }

    /** Horizontal (XZ) distance to the nearest live player, or MAX_VALUE if none. */
    private float nearestPlayerDistXZ(Vector3 center) {
        float min = Float.MAX_VALUE;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p)) continue;
            Vector3 pp = p.getGlobalPosition();
            float dx = (float) (pp.getX() - center.getX());
            float dz = (float) (pp.getZ() - center.getZ());
            float d = (float) Math.sqrt(dx * dx + dz * dz);
            if (d < min) min = d;
        }
        return min;
    }

    /**
     * Horizontal distance to <b>this peer's own</b> player only (PLAN.md I4 active region), or MAX_VALUE
     * if none. Streaming load/unload uses {@link #nearestPlayerDistXZ} (any player — every co-op player
     * must get their nearby zones), but region <i>ambience</i> (fog/light/faction/LOD) is local
     * presentation and must follow the LOCAL player: otherwise a remote player walking into a foggy zone
     * would fog every peer (that zone is "nearest to a player") until all players leave it.
     * {@code isLocalOwnedPlayer()} is true for the single-player sole player and, when networked, only the
     * body this peer is authoritative for — so it resolves to one player per peer.
     */
    private float localPlayerDistXZ(Vector3 center) {
        float min = Float.MAX_VALUE;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || !p.isLocalOwnedPlayer()) continue;
            Vector3 pp = p.getGlobalPosition();
            float dx = (float) (pp.getX() - center.getX());
            float dz = (float) (pp.getZ() - center.getZ());
            float d = (float) Math.sqrt(dx * dx + dz * dz);
            if (d < min) min = d;
        }
        return min;
    }

    // ── Load / unload ───────────────────────────────────────────────────────────

    private void load(WorldZoneMarker marker) {
        WorldZone zone = marker.zone;
        LoadedZone lz = new LoadedZone();
        loaded.put(marker, lz);
        marker.setLoadedVisual(true);

        // Cosmetic geometry — instanced locally on every peer.
        if (zone.geometry != null) {
            Node geo = zone.geometry.instantiate();
            if (geo != null) { marker.addChild(geo); lz.geometryInstance = geo; }
        }

        // Everything below is host-authoritative (PLAN.md I3c synced model): clients reconstruct the AI
        // via MSG_SPAWN and the traffic via MSG_VEHICLE_SPAWN, then drive both from snapshots.
        NetworkManager net = networkManager();
        if (net != null && net.isNetworked() && !net.isServer()) return;

        Node container = charactersContainer();
        if (container == null) {
            GD.print("WorldZoneManager: Characters container not found — cannot stream zone '"
                    + zone.zoneId + "'");
            return;
        }
        Vector3 center = marker.getGlobalPosition();
        SpawnPool sp = pool();
        int recycledCount = 0;
        int freshCount = 0;
        // Region density scales this zone's own spawn counts (PLAN.md I4). 1.0 / no region = unchanged.
        float aiDensity  = zone.regionConfig != null ? zone.regionConfig.ambientAiDensity : 1.0f;
        float vehDensity = zone.regionConfig != null ? zone.regionConfig.vehicleDensity  : 1.0f;

        for (SpawnConfig cfg : zone.spawnConfigs) {
            if (cfg == null) continue;
            // One squad per SpawnConfig group so the band shares awareness (PLAN.md E3).
            AISquad squad = new AISquad();
            container.addChild(squad);
            lz.squads.add(squad);
            for (int i = 0; i < scaledCount(cfg.count, aiDensity); i++) {
                AICharacter ai = sp.acquire();
                if (ai == null) continue;
                boolean recycled = sp.wasLastAcquireRecycled();
                if (recycled) recycledCount++; else freshCount++;

                CharacterInfo info = new CharacterInfo();
                info.characterId = UUID.randomUUID().toString();
                info.displayName = cfg.faction + " " + (i + 1);
                info.faction = cfg.faction;
                ai.characterInfo = info;
                if (cfg.behaviorConfig != null) ai.behaviorConfig = cfg.behaviorConfig;

                container.addChild(ai);
                ai.activateForSpawn(randomPointInBox(center, zone.size));
                ai.setSquad(squad);
                // A recycled body keeps its weapon, so skip the equip — unless it somehow came back
                // unarmed (defensive: never leave a streamed AI with only fists).
                if (!recycled || !isArmed(ai)) equipWeapon(ai, cfg.weaponScenePath, container);

                lz.pooled.add(ai);
                if (net != null) net.announceSpawn(ai);
            }
        }

        for (NamedCharacterConfig nc : zone.namedCharacters) {
            if (nc == null) continue;
            AICharacter ai = instantiateNamed(nc);
            if (ai == null) continue;

            CharacterInfo info = new CharacterInfo();
            info.characterId = nc.characterId.isEmpty() ? UUID.randomUUID().toString() : nc.characterId;
            info.displayName = nc.displayName;
            info.faction = nc.faction;
            ai.characterInfo = info;
            if (nc.behaviorConfig != null) ai.behaviorConfig = nc.behaviorConfig;

            container.addChild(ai);
            ai.activateForSpawn(center.plus(nc.offset));
            equipWeapon(ai, nc.weaponScenePath, container);

            lz.named.add(ai);
            if (net != null) net.announceSpawn(ai);
        }

        // Ambient vehicle traffic (PLAN.md I3c) — host-owned + replicated (synced model). spawnVehicle
        // announces each car (MSG_VEHICLE_SPAWN) and its AI driver (MSG_SPAWN + occupancy).
        for (VehicleSpawnConfig vc : zone.vehicleSpawnConfigs) {
            if (vc == null) continue;
            VehicleRoute vroute = findRoute(vc.routeName);
            for (int i = 0; i < scaledCount(vc.count, vehDensity); i++) {
                Vehicle v = spawnVehicle(vc, center, container, vroute, i, lz);
                if (v != null) lz.vehicles.add(v);
            }
        }

        if (debugLog) {
            GD.print("WorldZoneManager: LOADED zone '" + zone.zoneId + "' — "
                    + lz.pooled.size() + " ambient (" + recycledCount + " recycled, " + freshCount
                    + " fresh), " + lz.named.size() + " named, " + lz.vehicles.size()
                    + " vehicles; pool idle now " + sp.idleCount());
        }
    }

    private void unload(WorldZoneMarker marker) {
        LoadedZone lz = loaded.remove(marker);
        if (lz == null) return;
        if (GD.isInstanceValid(marker)) marker.setLoadedVisual(false);

        NetworkManager net = networkManager();
        int recycled = 0;
        int freed = 0;
        for (AICharacter ai : lz.pooled) {
            if (!GD.isInstanceValid(ai)) continue;
            if (net != null && ai.characterInfo != null) net.announceDespawn(ai.characterInfo.characterId);
            silenceWeaponAudio(ai);  // stop in-flight SFX while still in-tree (audio-leak quirk)
            // Only HEALTHY bodies are recycled (and only when recycleBodies is on). A body that died
            // while the zone was loaded is ragdolled (physics off, collision shapes disabled, weapons
            // dropped) — activateForSpawn does not undo that, so resurrecting it crashes. Dead bodies
            // (and everything when recycling is off) follow the normal free flow.
            if (recycleBodies && ai.isAlive() && !ai.isDead()) {
                pool().release(ai);
                recycled++;
            } else {
                ai.queueFree();
                freed++;
            }
        }
        for (Character ai : lz.named) {
            if (!GD.isInstanceValid(ai)) continue;
            if (net != null && ai.characterInfo != null) net.announceDespawn(ai.characterInfo.characterId);
            silenceWeaponAudio(ai);
            ai.queueFree();
        }
        for (AISquad squad : lz.squads) {
            if (GD.isInstanceValid(squad)) squad.queueFree();
        }
        // Ambient vehicles (I3) + their AI drivers (I3c) — freed together, not pooled (full vehicle
        // subtree reuse is unsafe, same reason recycleBodies is off for characters; the body owns a
        // top_level camera + viewport). A player-carjacked car is released, not freed (see freeTrafficCar).
        for (Vehicle v : new ArrayList<>(lz.vehicles)) freeTrafficCar(lz, v, net);
        lz.vehicles.clear();
        lz.driverOf.clear();
        if (lz.geometryInstance != null && GD.isInstanceValid(lz.geometryInstance))
            lz.geometryInstance.queueFree();

        if (debugLog) {
            GD.print("WorldZoneManager: UNLOADED zone '"
                    + (marker.zone != null ? marker.zone.zoneId : "?")
                    + "' — " + recycled + " recycled, " + freed + " dead freed; pool idle now "
                    + (pool != null ? pool.idleCount() : 0));
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private SpawnPool pool() {
        if (pool == null) {
            Object aiScene = GD.load(AI_SCENE_PATH);
            pool = new SpawnPool(aiScene instanceof PackedScene ps ? ps : null, poolCapacity);
        }
        return pool;
    }

    private AICharacter instantiateNamed(NamedCharacterConfig nc) {
        PackedScene scene = nc.scene;
        if (scene == null) {
            Object loadedScene = GD.load(AI_SCENE_PATH);
            if (loadedScene instanceof PackedScene ps) scene = ps;
        }
        if (scene == null) return null;
        Node inst = scene.instantiate();
        if (inst instanceof AICharacter ai) return ai;
        if (inst != null) inst.queueFree();
        return null;
    }

    private Node charactersContainer() {
        if (getTree() == null) return null;
        Node scene = getTree().getCurrentScene();
        return scene != null ? scene.getNodeOrNull("Characters") : null;
    }

    private NetworkManager networkManager() {
        Node n = getNodeOrNull("/root/NetworkManager");
        return n instanceof NetworkManager net ? net : null;
    }

    /**
     * Loads + equips a weapon onto the AI — same deferred path DebugHarness/WeaponPickup use
     * (the WeaponItem must be inside the tree before WeaponController reparents it onto the body).
     */
    private boolean isArmed(AICharacter ai) {
        Node wcNode = ai.getNodeOrNull(new NodePath("WeaponController"));
        return wcNode instanceof WeaponController wc && wc.isArmed();
    }

    /** Stop a body's weapon SFX while it is still in-tree, before freeing it (audio-leak quirk). */
    private void silenceWeaponAudio(Node body) {
        Node wcNode = body.getNodeOrNull(new NodePath("WeaponController"));
        if (wcNode instanceof WeaponController wc) wc.silenceAudio();
    }

    private void equipWeapon(AICharacter ai, String weaponScenePath, Node container) {
        Node wcNode = ai.getNodeOrNull(new NodePath("WeaponController"));
        if (!(wcNode instanceof WeaponController wc)) return;
        Object loaded = GD.load(weaponScenePath);
        if (!(loaded instanceof PackedScene weaponScene)) return;
        Node inst = weaponScene.instantiate();
        if (!(inst instanceof WeaponItem weapon)) { if (inst != null) inst.queueFree(); return; }
        container.addChild(weapon);
        weapon.setGlobalPosition(ai.getGlobalPosition());
        wc.requestEquip(weapon);
    }

    /**
     * Instantiates one ambient vehicle (I3), stamps a host UUID <b>before</b> addChild (required by
     * {@code Vehicle._ready} for replication to resolve — Round 11 N3), places it on the route, and
     * attaches a {@link VehicleAIController} bound to that route. Returns the body, or null on failure.
     */
    private Vehicle spawnVehicle(VehicleSpawnConfig vc, Vector3 center, Node container,
                                 VehicleRoute route, int index, LoadedZone lz) {
        Object loaded = GD.load(vc.vehicleScenePath);
        if (!(loaded instanceof PackedScene scene)) return null;
        Node inst = scene.instantiate();
        if (!(inst instanceof Vehicle v)) { if (inst != null) inst.queueFree(); return null; }

        // ALWAYS a fresh per-instance CharacterInfo — NEVER reuse the one the scene supplied. Vehicle.tscn
        // embeds a single CharacterInfo sub-resource that (unless resource_local_to_scene) is SHARED by
        // every Vehicle.tscn instance; mutating it here rewrote the id + ownerPeerId of every other vehicle
        // (the player's car included), collapsing all vehicles onto one shared id — the cause of the
        // stuck/teleporting traffic, can't-exit, and ownership-migrates-to-all bugs.
        v.characterInfo = new CharacterInfo();
        v.characterInfo.characterId = UUID.randomUUID().toString();
        v.characterInfo.displayName = "Traffic " + (index + 1);
        v.characterInfo.faction = vc.faction;

        container.addChild(v);
        v.setGlobalPosition(vehicleStartPoint(route, center, index));

        VehicleAIController ctrl = new VehicleAIController();
        ctrl.cruiseThrottle = vc.cruiseThrottle;
        v.attachController(ctrl);
        if (route != null) ctrl.setRoute(route);

        // Host-owned synced ambient traffic (PLAN.md I3c): announce the streamed car so clients
        // reconstruct it as a snapshot-driven puppet. The STREAMED_GROUP tag drives both the late-join
        // baseline and the client ghost-reconcile. Host-only inside announceVehicleSpawn; harmless in SP.
        v.addToGroup(new StringName(Vehicle.STREAMED_GROUP));
        NetworkManager net = networkManager();
        if (net != null) net.announceVehicleSpawn(v);

        AICharacter driver = spawnTrafficDriver(vc, v, container);
        if (driver != null) lz.driverOf.put(v, driver);
        return v;
    }

    /**
     * Spawn a visible AI driver and seat it in the traffic car (PLAN.md I3c). The car keeps its own
     * {@link VehicleAIController} (Design B) and the AI rides as a non-driving, drive-state-inert passenger.
     * Host-owned + replicated: the driver body is announced (MSG_SPAWN) and {@code seatTrafficDriver}
     * broadcasts the seat occupancy so clients show the driver. The driver rides unarmed (its default fist
     * suffices for a FIGHT carjack reaction). Returns the driver, or null on failure.
     */
    private AICharacter spawnTrafficDriver(VehicleSpawnConfig vc, Vehicle v, Node container) {
        Object loaded = GD.load(AI_SCENE_PATH);
        if (!(loaded instanceof PackedScene scene)) return null;
        Node inst = scene.instantiate();
        if (!(inst instanceof AICharacter ai)) { if (inst != null) inst.queueFree(); return null; }

        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = "Driver";
        info.faction = vc.faction;
        ai.characterInfo = info;
        if (vc.behaviorConfig != null) ai.behaviorConfig = vc.behaviorConfig;

        container.addChild(ai);
        ai.activateForSpawn(v.getGlobalPosition());
        NetworkManager net = networkManager();
        if (net != null) net.announceSpawn(ai);

        if (getNodeOrNull("/root/GameManager") instanceof GameManager gm) gm.seatTrafficDriver(v, ai);
        else v.tryEnter(ai);   // SP fallback if the GameManager AutoLoad is somehow absent (test scenes)
        return ai;
    }

    /**
     * Free a host-owned traffic car together with its paired AI driver (PLAN.md I3c), announcing each
     * despawn so clients mirror, and dropping the pairing. A car a <b>player</b> has carjacked is never
     * yanked away — it is released to the player (untracked, not freed); its (already-ejected) original
     * driver is still freed. Safe if either node is already invalid.
     */
    private void freeTrafficCar(LoadedZone lz, Vehicle v, NetworkManager net) {
        AICharacter driver = lz.driverOf.remove(v);
        boolean vValid = GD.isInstanceValid(v);
        // Unseat the driver from its car first, so neither node dangles when freed: a seated occupant
        // is dereferenced every frame in Vehicle._physicsProcess, and freeing the car or the driver out
        // of order leaves a use-after-free. Only when the driver is still the occupant — a carjacked car
        // holds a Player and must never be auto-unseated.
        if (vValid && driver != null && v.getOccupant() == driver) v.tryExit();
        if (driver != null && GD.isInstanceValid(driver)) {
            if (net != null && driver.characterInfo != null) net.announceDespawn(driver.characterInfo.characterId);
            silenceWeaponAudio(driver);
            driver.queueFree();
        }
        if (!vValid) return;
        if (v.getOccupant() instanceof Player) return;   // carjacked → released to the player, don't free
        if (net != null && v.getCharacterInfo() != null) net.announceDespawn(v.getCharacterInfo().characterId);
        silenceWeaponAudio(v);
        v.queueFree();
    }

    /** Metres between successive cars queued at a one-way lane's entry (≈ one car length). */
    private static final float VEHICLE_QUEUE_SPACING = 6.0f;

    /**
     * Start position for a streamed vehicle.
     *
     * <p>A <b>loop</b> (ring) lane distributes cars around the ring (so they don't all stack at one
     * point). A one-way {@code DESPAWN} lane instead spawns at the <b>lane entry</b> ({@code waypoints[0]},
     * the zone-side end) — a topped-up car then enters where traffic originates rather than popping in
     * mid-corridor in the player's view (PLAN.md I3b "Respawn polish"). Successive cars are nudged a few
     * metres up the first lane segment so they queue in-lane instead of overlapping. Falls back to the
     * zone center when the route has no markers.
     */
    private Vector3 vehicleStartPoint(VehicleRoute route, Vector3 center, int index) {
        if (route == null) return center;
        List<Vector3> pts = route.waypoints();
        if (pts.isEmpty()) return center;
        if (route.isLoop()) return pts.get(index % pts.size());

        Vector3 entry = pts.get(0);
        if (pts.size() < 2 || index <= 0) return entry;
        Vector3 next = pts.get(1);
        double dx = next.getX() - entry.getX(), dz = next.getZ() - entry.getZ();
        double len = Math.sqrt(dx * dx + dz * dz);
        if (len < 1e-6) return entry;
        // Step forward into the first segment, but never past it (stay within the lane).
        double step = Math.min(index * VEHICLE_QUEUE_SPACING, len * 0.9);
        return new Vector3(entry.getX() + dx / len * step, entry.getY(), entry.getZ() + dz / len * step);
    }

    /** Finds a {@link VehicleRoute} node by name anywhere under the active scene (null if absent). */
    private VehicleRoute findRoute(String routeName) {
        if (routeName == null || routeName.isEmpty() || getTree() == null) return null;
        Node scene = getTree().getCurrentScene();
        return scene != null ? findRouteRecursive(scene, routeName) : null;
    }

    private VehicleRoute findRouteRecursive(Node node, String routeName) {
        if (node instanceof VehicleRoute r && node.getName().toString().equals(routeName)) return r;
        for (Node child : node.getChildren()) {
            VehicleRoute found = findRouteRecursive(child, routeName);
            if (found != null) return found;
        }
        return null;
    }

    private Vector3 randomPointInBox(Vector3 center, Vector3 size) {
        float hx = (float) size.getX() * 0.5f;
        float hz = (float) size.getZ() * 0.5f;
        return new Vector3(
                (float) center.getX() + GD.randfRange(-hx, hx),
                (float) center.getY(),
                (float) center.getZ() + GD.randfRange(-hz, hz));
    }
}
