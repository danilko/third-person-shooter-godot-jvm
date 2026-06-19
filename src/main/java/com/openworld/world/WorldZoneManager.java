package com.openworld.world;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.Node;
import godot.api.PackedScene;
import godot.core.NodePath;
import godot.core.Vector3;
import godot.global.GD;

import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;

import java.util.ArrayList;
import java.util.HashMap;
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

    /** Per-loaded-zone bookkeeping so unload returns exactly what load created. */
    private static final class LoadedZone {
        final List<AICharacter> pooled = new ArrayList<>();   // SpawnConfig AI → returned to pool
        final List<Character>   named  = new ArrayList<>();   // NamedCharacterConfig AI → freed
        final List<AISquad>     squads = new ArrayList<>();   // one per SpawnConfig group (E3) → freed
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

        // AI population is host-authoritative; clients receive it via MSG_SPAWN.
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

        for (SpawnConfig cfg : zone.spawnConfigs) {
            if (cfg == null) continue;
            // One squad per SpawnConfig group so the band shares awareness (PLAN.md E3).
            AISquad squad = new AISquad();
            container.addChild(squad);
            lz.squads.add(squad);
            for (int i = 0; i < cfg.count; i++) {
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

        if (debugLog) {
            GD.print("WorldZoneManager: LOADED zone '" + zone.zoneId + "' — "
                    + lz.pooled.size() + " ambient (" + recycledCount + " recycled, " + freshCount
                    + " fresh), " + lz.named.size() + " named; pool idle now " + sp.idleCount());
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
    private void silenceWeaponAudio(Character ai) {
        Node wcNode = ai.getNodeOrNull(new NodePath("WeaponController"));
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

    private Vector3 randomPointInBox(Vector3 center, Vector3 size) {
        float hx = (float) size.getX() * 0.5f;
        float hz = (float) size.getZ() * 0.5f;
        return new Vector3(
                (float) center.getX() + GD.randfRange(-hx, hx),
                (float) center.getY(),
                (float) center.getZ() + GD.randfRange(-hz, hz));
    }
}
