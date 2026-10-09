package com.openworld.game;

import com.openworld.ai.AIBehaviorConfig;
import com.openworld.character.AICharacter;
import com.openworld.character.Player;
import com.openworld.util.CollisionLayers;
import com.openworld.world.Places;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.FileAccess;
import godot.api.Node;
import godot.api.PhysicsRayQueryParameters3D;
import godot.core.Dictionary;
import godot.core.Vector3;
import godot.global.GD;
import com.openworld.util.MiniJson;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Gang members standing at their gang's places (PLAN.md THE ORDER 0.1 / H1, user 2026-10-09: "hard to see one in the
 * crowd to trigger the attack"). Before this nothing put an ambient gang member in the world, so gang standing could
 * only rise at a gray-area counter or in a mission -- the gang half of the escalation was unreachable in play.
 *
 * <p>GTA's hangout: a handful of members loiter in front of each place the places record marks with a {@code gang}
 * (GangOffice, the port compound, the mansion, the gang's pachinko and club ...), in the gang's own uniform
 * ({@code gangs.json} bodies + {@code character/outfits.json}), so they READ against the crowd. Player and gangs are
 * NEUTRAL by default ({@code DefaultFactions.tres}): the first hit on a member is {@code hit_member} heat, which is
 * one star, which is {@code attack_at} -- the whole gang turns hostile through {@link GangSystem}'s flips, and the
 * dispatch hunts from {@code chase_at}. Nothing new decides hostility here.
 *
 * <p>Spawned on proximity like a shop clerk (a member is a full ~125-node body): within {@code near} of a player,
 * returned past {@code far} of every player. A hangout whose members all went down stays empty until every player has
 * left past {@code far} (then it may fill again). Authority only; bodies reach peers through announceSpawn /
 * announceDespawn. Data: {@code gangs.json} {@code hangout}. {@link #enabled} off is the control.
 */
@Script(className = "GangHangouts")
public class GangHangouts extends Node {

    private static GangHangouts instance;

    public static GangHangouts get() { return instance != null && GD.isInstanceValid(instance) ? instance : null; }

    @Visible public boolean enabled = true;
    public boolean getEnabled() { return enabled; }
    public void setEnabled(boolean v) { enabled = v; }

    private int count = 4;
    private double near = 70.0, far = 110.0, ringMin = 3.0, ringMax = 8.0, patrolRadius = 6.0;
    private final List<String> weapons = new ArrayList<>(List.of("PIS1"));

    private static final class Hangout {
        final Places.Place place;
        final List<AICharacter> members = new ArrayList<>();
        boolean spent;
        Hangout(Places.Place p) { place = p; }
    }

    private final List<Hangout> hangouts = new ArrayList<>();
    private String loadedFor;
    private double scanIn;
    private int spawned;
    private final Map<String, Integer> byGang = new HashMap<>();

    @Register
    @Override
    public void _ready() {
        instance = this;
        if (!FileAccess.fileExists(GangSystem.TABLE)) return;
        Object doc = MiniJson.parse(FileAccess.getFileAsString(GangSystem.TABLE));
        if (!(doc instanceof Map<?, ?> m) || !(m.get("hangout") instanceof Map<?, ?> h)) return;
        count = (int) num(h.get("count"), count);
        near = num(h.get("near"), near);
        far = num(h.get("far"), far);
        if (h.get("ring") instanceof List<?> ring && ring.size() == 2) {
            ringMin = num(ring.get(0), ringMin);
            ringMax = num(ring.get(1), ringMax);
        }
        patrolRadius = num(h.get("patrol_radius"), patrolRadius);
        if (h.get("weapons") instanceof List<?> w && !w.isEmpty()) {
            weapons.clear();
            for (Object o : w) weapons.add(String.valueOf(o));
        }
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
        hangouts.clear();
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                || !net.isNetworked() || net.isServer();
    }

    /** The places record is per scene: rebuild the hangout list when the scene changes. */
    private void refreshPlaces() {
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        String key = scene != null ? scene.getSceneFilePath() + "#" + scene.getInstanceId() : null;
        if (key == null || key.equals(loadedFor)) return;
        loadedFor = key;
        hangouts.clear();
        for (Places.Place p : Places.all())
            if (p.gang() != null && !p.gang().isEmpty() && p.go() != null) hangouts.add(new Hangout(p));
    }

    @Register
    @Override
    public void _process(double delta) {
        scanIn -= delta;
        if (scanIn > 0) return;
        scanIn = 0.5;
        if (!enabled || !authority()) return;
        refreshPlaces();
        List<Player> players = PlayerRegistry.getPlayers();
        if (players.isEmpty()) return;
        for (Hangout h : hangouts) {
            h.members.removeIf(m -> !GD.isInstanceValid(m));
            double d = Double.MAX_VALUE;
            for (Player p : players) if (GD.isInstanceValid(p)) d = Math.min(d, flat(p.getGlobalPosition(), h.place.go()));
            boolean anyAlive = false;
            for (AICharacter m : h.members) if (!m.isDead()) { anyAlive = true; break; }
            if (d > far) {
                // everyone has left: the living go back where they came from, and the hangout may fill again
                for (AICharacter m : h.members) if (!m.isDead()) release(m);
                h.members.removeIf(m -> !m.isDead());
                h.spent = false;
            } else if (d < near && h.members.isEmpty() && !h.spent) {
                fill(h);
            } else if (!h.members.isEmpty() && !anyAlive) {
                h.spent = true;
            }
        }
    }

    private void fill(Hangout h) {
        EnforcementDispatch ed = EnforcementDispatch.get();
        if (ed == null) return;
        Vector3 go = h.place.go();
        Vector3 out = go.minus(h.place.at());
        out.setY(0);
        out = out.length() < 1e-3 ? new Vector3(0, 0, 1) : out.normalized();
        Vector3 side = new Vector3(-out.getZ(), 0, out.getX());
        String gang = h.place.gang();
        // a stable spread per place, so a hangout looks the same each time it fills
        java.util.Random r = new java.util.Random(h.place.name().hashCode() * 31L + (long) (go.getX() * 7 + go.getZ()));
        for (int i = 0; i < count; i++) {
            Vector3 at = null;
            for (int k = 0; k < 8 && at == null; k++) {
                double o = ringMin + r.nextDouble() * (ringMax - ringMin);
                double s = (r.nextDouble() * 2 - 1) * ringMax;
                at = ground(go.plus(out.times(o)).plus(side.times(s)), go.getY());
            }
            if (at == null) continue;
            AICharacter ai = ed.spawnHangoutBody(gang, at, weapons.get(i % weapons.size()));
            if (ai == null) continue;
            AIBehaviorConfig cfg = new AIBehaviorConfig();
            cfg.patrolRadius = (float) patrolRadius;
            ai.behaviorConfig = cfg;
            h.members.add(ai);
            spawned++;
            byGang.merge(gang, 1, Integer::sum);
        }
    }

    private void release(AICharacter m) {
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net
                && m.getCharacterInfo() != null) net.announceDespawn(m.getCharacterInfo().characterId);
        m.queueFree();
    }

    /** Walkable ground near {@code p}, within a storey of the door's height; null if none. */
    private Vector3 ground(Vector3 p, double doorY) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return null;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        var q = PhysicsRayQueryParameters3D.create(new Vector3(p.getX(), doorY + 3.0, p.getZ()),
                new Vector3(p.getX(), doorY - 3.0, p.getZ()), CollisionLayers.WORLD,
                new godot.core.VariantArray<>(godot.core.RID.class));
        Dictionary<Object, Object> hit = sp.intersectRay(q);
        if (hit == null || hit.isEmpty() || !(hit.get("position") instanceof Vector3 g)) return null;
        if (hit.get("normal") instanceof Vector3 n && n.getY() < 0.8) return null;
        return Math.abs(g.getY() - doorY) < 1.2 ? g : null;
    }

    private static double num(Object o, double def) { return o instanceof Number n ? n.doubleValue() : def; }

    private static double flat(Vector3 a, Vector3 b) {
        double dx = a.getX() - b.getX(), dz = a.getZ() - b.getZ();
        return Math.sqrt(dx * dx + dz * dz);
    }

    // ── probe surface ──
    /** "hangouts,live members,spawned total" */
    @Register public String hangoutsNow() {
        int live = 0;
        for (Hangout h : hangouts) for (AICharacter m : h.members) if (GD.isInstanceValid(m) && !m.isDead()) live++;
        return hangouts.size() + "," + live + "," + spawned;
    }

    /** Live members at the hangout nearest {@code at} (within 60 m). */
    @Register public godot.core.VariantArray<Node> membersNear(Vector3 at) {
        godot.core.VariantArray<Node> out = new godot.core.VariantArray<>(Node.class);
        for (Hangout h : hangouts) {
            if (flat(h.place.go(), at) > 60) continue;
            for (AICharacter m : h.members) if (GD.isInstanceValid(m) && !m.isDead()) out.append(m);
        }
        return out;
    }
}
