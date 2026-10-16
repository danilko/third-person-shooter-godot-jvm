package com.openworld.game.encounter;

import com.openworld.character.AICharacter;
import com.openworld.character.Player;
import com.openworld.game.EnforcementDispatch;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.data.Tables;
import com.openworld.world.MarkerRegistry;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.Node;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * PEOPLE ON SITE AT GUARDED BUILDINGS (PLAN.md 1j / 2.2, user 2026-10-08: "police / bank / hospital / gang places have
 * people on site"). WHO STANDS WHERE IS AUTHORED: every building's {@code MARK_spawn} Empties are baked into its scene
 * as {@code mission_marker} nodes with a {@code team} prop (police, guard, soldier, gang, staff, civilian ...);
 * {@code character/loadouts.json}'s {@code teams} says which teams are guards and what each carries. Nothing new is
 * baked: this reads the markers the buildings already carry (MarkerRegistry), so a level designer adds a guard by adding
 * a marker to the building's .blend (or a Marker3D in group {@code mission_marker} with {@code kind=spawn},
 * {@code team=...} to any scene).
 *
 * <p>Spawned like a shop clerk (a guard is a full ~125-node body): within {@code near} of a player, taken away past
 * {@code far} of every player while calm. A BUILDING whose guards fought or went down stays empty until every player
 * has left past {@code far}. Only in a variant someone can walk into ({@code _Shop} / {@code _Open} scenes) -- a shut
 * building's staff are inside where nobody can reach -- or at a post under open sky (a shut base's gate guard). Capped per building and island-wide. Each guard stands at its
 * marker looking out of its -Z (a {@code post=patrol} marker walks a few metres round it), holds the post with a
 * short leash when it fights, and is of its loadout's side (police, the military as police, a gang) -- so it joins in
 * through the ordinary faction and wanted rules (P1e's per-target hostility). Guards are the building's own staff:
 * they are NOT drawn from the forces' station pools. Authority only. {@link #enabled} off is the control.
 */
@Script(className = "SiteGuards")
public class SiteGuards extends Node {

    private static SiteGuards instance;

    public static SiteGuards get() { return instance != null && GD.isInstanceValid(instance) ? instance : null; }

    @Visible public boolean enabled = true;
    public boolean getEnabled() { return enabled; }
    public void setEnabled(boolean v) { enabled = v; }

    /** One building's guards, keyed by its scene root. */
    private static final class Site {
        final Node root;
        final List<MarkerRegistry.Marker> posts = new ArrayList<>();
        final List<AICharacter> guards = new ArrayList<>();
        boolean spent;
        Site(Node root) { this.root = root; }
        Vector3 centre() {
            Vector3 c = new Vector3(0, 0, 0);
            for (MarkerRegistry.Marker m : posts) c = c.plus(m.position());
            return posts.isEmpty() ? c : c.div((double) posts.size());
        }
    }

    private final Map<Long, Site> sites = new LinkedHashMap<>();
    private double scanIn;
    private int spawned;
    private final Map<String, Integer> byTeam = new HashMap<>();

    @Register
    @Override
    public void _ready() { instance = this; }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        sites.clear();
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                || !net.isNetworked() || net.isServer();
    }

    private static Loadouts table() {
        Loadouts lo = Tables.LOADOUTS.get();
        return lo != null ? lo : new Loadouts();
    }

    /** A building variant someone can walk into: its scene is a {@code _Shop} / {@code _Open} one. A marker in a scene
     *  that is not a building (a designer's Marker3D in a level) counts as open. */
    static boolean openVariant(String sceneFile) {
        if (sceneFile == null || sceneFile.isEmpty() || !sceneFile.contains("/world/buildings/")) return true;
        String f = sceneFile.substring(sceneFile.lastIndexOf('/') + 1);
        return f.endsWith("_Shop.tscn") || f.endsWith("_Open.tscn");
    }

    /** Marker instance id -> nothing solid over it (a post in the open: a gate, a yard). Asked once per marker. */
    private final Map<Long, Boolean> skyCache = new HashMap<>();
    private final Map<Long, Double> firstSeen = new HashMap<>();
    private double clock;

    /** A post under open sky is reachable whatever the variant: the island places the military base SHUT (its
     *  interiors are not walkable), but its gate guard stands outside. */
    private boolean underSky(MarkerRegistry.Marker m) {
        Boolean known = skyCache.get(m.node.getInstanceId());
        if (known != null) return known;
        // a building that has just streamed in may not have its colliders in the physics space yet (nothing over
        // the post would read as open sky): asked only once the marker has been seen for a second
        double seen = firstSeen.computeIfAbsent(m.node.getInstanceId(), k -> clock);
        if (clock - seen < 1.0) return false;
        return skyCache.computeIfAbsent(m.node.getInstanceId(), k -> {
            if (getViewport() == null || getViewport().getWorld3d() == null) return false;
            Vector3 p = m.position().plus(new Vector3(0, 1.0, 0));
            var q = godot.api.PhysicsRayQueryParameters3D.create(p, p.plus(new Vector3(0, 40, 0)),
                    com.openworld.util.CollisionLayers.WORLD, new godot.core.VariantArray<>(godot.core.RID.class));
            var hit = getViewport().getWorld3d().getDirectSpaceState().intersectRay(q);
            return hit == null || hit.isEmpty();
        });
    }

    /** The building a marker belongs to: the nearest ancestor that is a scene's root (owner of the Markers node). */
    private static Node buildingOf(Node marker) {
        Node o = marker.getOwner();
        return o != null ? o : marker.getParent();
    }

    /** Re-read the guard posts from the live markers (buildings stream in and out). */
    private void refreshSites(Loadouts lo) {
        Map<Long, Site> seen = new LinkedHashMap<>();
        for (MarkerRegistry.Marker m : MarkerRegistry.ofKind(this, "spawn")) {
            if (lo.forTeam(m.team()) == null && lo.get(m.prop("loadout", "")) == null) continue;
            Node b = buildingOf(m.node);
            if (b == null || (!openVariant(b.getSceneFilePath()) && !underSky(m))) continue;
            long id = b.getInstanceId();
            Site s = seen.get(id);
            if (s == null) {
                Site old = sites.get(id);
                s = old != null ? old : new Site(b);
                s.posts.clear();
                seen.put(id, s);
            }
            s.posts.add(m);
        }
        // a building that streamed out takes its guards with it (they are freed with nothing: release the living)
        for (Map.Entry<Long, Site> e : sites.entrySet())
            if (!seen.containsKey(e.getKey())) for (AICharacter g : e.getValue().guards) if (GD.isInstanceValid(g) && !g.isDead()) release(g);
        sites.clear();
        sites.putAll(seen);
        if (skyCache.size() > 4096) skyCache.clear();
        if (firstSeen.size() > 4096) firstSeen.clear();
    }

    @Register
    @Override
    public void _process(double delta) {
        clock += delta;
        scanIn -= delta;
        if (scanIn > 0) return;
        scanIn = 0.5;
        if (!enabled || !authority()) return;
        Loadouts lo = table();
        refreshSites(lo);
        List<Player> players = PlayerRegistry.getPlayers();
        if (players.isEmpty()) return;
        int live = liveAll();
        for (Site s : sites.values()) {
            s.guards.removeIf(g -> !GD.isInstanceValid(g));
            Vector3 c = s.centre();
            double d = Double.MAX_VALUE;
            for (Player p : players) if (GD.isInstanceValid(p)) d = Math.min(d, p.getGlobalPosition().distanceTo(c));
            boolean anyAlive = false, anyFighting = false;
            for (AICharacter g : s.guards) {
                if (g.isDead()) continue;
                anyAlive = true;
                if (g.getTarget() != null) anyFighting = true;
            }
            if (d > lo.site.far()) {
                for (AICharacter g : s.guards) if (!g.isDead()) release(g);
                s.guards.clear();
                s.spent = false;
            } else if (d < lo.site.near() && s.guards.isEmpty() && !s.spent) {
                live += fill(s, lo, Math.max(0, lo.site.cap() - live));
            } else if (!s.guards.isEmpty() && (!anyAlive || anyFighting)) {
                // engaged or down: not filled again until everyone has left (a fight is not reset by walking off 70 m)
                s.spent = true;
                for (AICharacter g : s.guards) if (!g.isDead()) g.lodPinnedActive = true;
            }
        }
    }

    private int fill(Site s, Loadouts lo, int room) {
        EnforcementDispatch ed = EnforcementDispatch.get();
        if (ed == null || room <= 0) return 0;
        int n = 0;
        for (MarkerRegistry.Marker m : s.posts) {
            if (n >= Math.min(room, lo.site.perBuilding()) || !m.valid()) break;
            Loadouts.Loadout l = lo.get(m.prop("loadout", ""));
            if (l == null) l = lo.forTeam(m.team());
            if (l == null) continue;
            // a gang guard belongs to the gang the marker (or its place) names; police / soldiers to their side
            String side = l.sideOr(m.prop("gang", com.openworld.character.Faction.GANG_A));
            Vector3 at = m.position();
            AICharacter g = ed.spawnPlaced(side, side, l, at, Loadouts.roll(m.node.getPath().getPath()));
            if (g == null) continue;
            Vector3 f = m.facing();
            g.postFacePoint = at.plus(new Vector3(f.getX() * 5, 1.4, f.getZ() * 5));
            g.holdPoint = new Vector3(at);
            boolean patrols = "patrol".equals(m.prop("post", "stand"));
            g.standsAtPost = !patrols;
            g.holdLeash = patrols ? 10.0 : 6.0;
            if (patrols) {
                g.patrolRoute = List.of(at.plus(new Vector3(f.getZ() * 4, 0, -f.getX() * 4)),
                        at.plus(new Vector3(-f.getZ() * 4, 0, f.getX() * 4)));
            }
            g.holdCrouch = false;
            s.guards.add(g);
            spawned++;
            byTeam.merge(m.team(), 1, Integer::sum);
            n++;
        }
        return n;
    }

    private void release(AICharacter g) {
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net && g.getCharacterInfo() != null)
            net.announceDespawn(g.getCharacterInfo().characterId);
        g.queueFree();
    }

    private int liveAll() {
        int n = 0;
        for (Site s : sites.values()) for (AICharacter g : s.guards) if (GD.isInstanceValid(g) && !g.isDead()) n++;
        return n;
    }

    // ── probe / console surface ──

    /** "sites,live guards,spawned total" */
    @Register
    public String guardsNow() { return sites.size() + "," + liveAll() + "," + spawned; }

    /** Spawned per team so far: "police=3,soldier=4". */
    @Register
    public String byTeamNow() {
        StringBuilder b = new StringBuilder();
        for (Map.Entry<String, Integer> e : byTeam.entrySet()) {
            if (b.length() > 0) b.append(',');
            b.append(e.getKey()).append('=').append(e.getValue());
        }
        return b.toString();
    }

    /** One live guard for a probe: "faction;weapons;target;distToPost;state;lod;postAbove" (target "player" / "other" / ""). */
    @Register
    public String guardReadoutNow(int i) {
        int k = 0;
        for (Site s : sites.values()) for (AICharacter g : s.guards) {
            if (!GD.isInstanceValid(g) || g.isDead()) continue;
            if (k++ != i) continue;
            StringBuilder w = new StringBuilder();
            if (g.weaponController != null) for (int j = 0; j < g.weaponController.slotCount(); j++) {
                var it = g.weaponController.getWeaponItem(j);
                if (it == null || it.weaponId.isEmpty() || "fist".equalsIgnoreCase(it.weaponId)) continue;
                if (w.length() > 0) w.append('+');
                w.append(it.weaponId);
            }
            String t = g.getTarget() instanceof Player ? "player" : g.getTarget() != null ? "other" : "";
            double d = g.holdPoint == null ? -1 : Math.hypot(g.getGlobalPosition().getX() - g.holdPoint.getX(),
                    g.getGlobalPosition().getZ() - g.holdPoint.getZ());
            String st = g.getController() instanceof com.openworld.ai.AIController c && c.getCurrentState() != null
                    ? c.getCurrentState().getClass().getSimpleName() : "-";
            return (g.characterInfo != null ? g.characterInfo.faction : "") + ";" + w + ";" + t + ";" + d + ";" + st
                    + ";" + g.getLodLevel() + ";" + (g.holdPoint != null ? g.holdPoint.getY() - g.getGlobalPosition().getY() : 0);
        }
        return "gone";
    }

    /** The live guards (a probe drives / checks them). */
    @Register
    public godot.core.VariantArray<AICharacter> guardBodiesNow() {
        godot.core.VariantArray<AICharacter> out = new godot.core.VariantArray<>(AICharacter.class);
        for (Site s : sites.values()) for (AICharacter g : s.guards) if (GD.isInstanceValid(g) && !g.isDead()) out.append(g);
        return out;
    }
}
