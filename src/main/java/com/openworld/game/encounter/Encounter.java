package com.openworld.game.encounter;

import com.openworld.character.AICharacter;
import com.openworld.character.AISquad;
import com.openworld.character.Player;
import com.openworld.game.EnforcementDispatch;
import com.openworld.game.PlayerRegistry;
import com.openworld.game.WorldLedger;
import com.openworld.game.data.Tables;
import com.openworld.util.CollisionLayers;
import com.openworld.world.MarkerRegistry;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PhysicsRayQueryParameters3D;
import godot.core.Dictionary;
import godot.core.Signal0;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * A FIGHT A LEVEL DESIGNER PLACES (PLAN.md 2.2 / F6): "a group of 6 armed gang members that spawns when the player
 * enters this courtyard, attacks in two waves, uses this cover" -- with no code. Drop this node in a scene and give it
 * children:
 * <ul>
 *   <li>{@code MARK_spawn_<n>} (any Node3D / Marker3D): where a member stands up, facing its -Z. A {@code wave} meta
 *       (1, 2, ...) keeps a point for that wave; none = any wave. No spawn points = a ring round the node.</li>
 *   <li>{@code MARK_cover_<n>}: a point a member fights FROM (it goes there, holds it, crouches between shots when
 *       {@link #crouchAtCover}). The buildings' own baked {@code MARK_cover} markers within {@link #coverRadius} count
 *       too.</li>
 *   <li>{@code MARK_patrol_<n>}: a route the first wave walks, in name order, before it is set off.</li>
 * </ul>
 * The rules (when it stands up, turns on the players, sends the next wave, is cleared or resets) are
 * {@link EncounterWaves}'; this node is the engine half. Bodies are the dispatch's placed bodies dressed and armed by
 * {@code character/loadouts.json} ({@link #loadout}). A {@link #manual} encounter is started by an activity
 * ({@code ActivityHost.startEncounter}) or by calling {@code start_now} from a signal (a ZoneTrigger, a door).
 * Authority only; the bodies reach peers through the ordinary spawn messages.
 */
@Script(className = "Encounter")
public class Encounter extends Node3D {

    public static final String GROUP = "encounter";

    /** The name an activity, the console and a ledger flag use for it. */
    @Export public String encounterId = "";
    /** The members' faction (police, gang_a, gang_b, enemy, ...). */
    @Export public String faction = "gang_a";
    /** A row of character/loadouts.json. */
    @Export public String loadout = "gang_member";
    /** Bodies per wave, first wave first: "4,3". */
    @Export public String waves = "4";
    /** A player this close sets it off (0 = only a hurt member, or start_now). */
    @Export public double triggerRadius = 25.0;
    /** Wave 1 stands up when a player is this close; 0 = loadouts.json's encounter.spawn_near. */
    @Export public double spawnNear = 0.0;
    /** Every player past this and the living are taken away (it may happen again); 0 = the table's. */
    @Export public double despawnFar = 0.0;
    /** The next wave comes once this few of the earlier ones are still up ... */
    @Export public int nextWaveAt = 1;
    /** ... and no sooner than this many seconds after the last one. */
    @Export public double waveGap = 4.0;
    /** Never stands up by itself: an activity or a signal starts it. */
    @Export public boolean manual = false;
    /** A cleared encounter stays cleared while the scene stays loaded. */
    @Export public boolean once = true;
    /** The buildings' baked MARK_cover markers within this of the node are cover too (0 = only its own). */
    @Export public double coverRadius = 30.0;
    /** How far from its cover a member will chase (m). */
    @Export public double holdLeash = 8.0;
    @Export public boolean crouchAtCover = true;
    /** A world flag set when it is cleared; a world with the flag set never stands it up again (a saved win). */
    @Export public String ledgerFlag = "";
    @Export public boolean enabled = true;
    /** Members of one wave past this many are LIGHT combatants (PLAN.md 2.3, ai.light.LightCombatants): same orders,
     *  no nodes, promoted to full bodies as players close in or as the budget frees. 0 = every member a full body. */
    @Export public int fullCap = 0;

    public boolean getEnabled() { return enabled; }
    public void setEnabled(boolean v) { enabled = v; }
    public boolean getManual() { return manual; }
    public void setManual(boolean v) { manual = v; }
    public boolean getOnce() { return once; }
    public void setOnce(boolean v) { once = v; }
    public boolean getCrouchAtCover() { return crouchAtCover; }
    public void setCrouchAtCover(boolean v) { crouchAtCover = v; }

    /** It turned on the players. */
    public final Signal0 encounterTriggered = new Signal0(this, new StringName("encounter_triggered"));
    /** Every wave is down. */
    public final Signal0 encounterCleared = new Signal0(this, new StringName("encounter_cleared"));

    private EncounterWaves life;
    private final List<AICharacter> members = new ArrayList<>();
    /** The orders of the members that went to the light tier (PLAN.md 2.3): engage() turns them on the players too. */
    private final List<com.openworld.ai.AIBlackboard> lightMembers = new ArrayList<>();
    private final Set<Node3D> claimedCover = new HashSet<>();
    private AISquad squad;
    private double scanIn;
    private int spawnedTotal, wavesOut;

    @Register
    @Override
    public void _ready() {
        addToGroup(new StringName(GROUP), true);
        Loadouts.EncounterRules d = rules();
        life = new EncounterWaves(new EncounterWaves.Config(EncounterWaves.parseWaves(waves), triggerRadius,
                spawnNear > 0 ? spawnNear : d.spawnNear(), despawnFar > 0 ? despawnFar : d.despawnFar(),
                Math.max(0, nextWaveAt), Math.max(0, waveGap), manual, once));
        if (!ledgerFlag.isEmpty() && WorldLedger.get().isSet(ledgerFlag)) life.markCleared();
        com.openworld.game.event.GameplayEvents.subscribe(com.openworld.game.event.GameplayEvents.Phase.OBSERVER, onEvent);
        squad = new AISquad();
        squad.setName(new StringName("Squad"));
        squad.forgetDuration = 20.0f;
        addChild(squad);
    }

    @Register
    @Override
    public void _exitTree() {
        if (getNodeOrNull("/root/ZoneManager") instanceof com.openworld.world.ZoneManager zm)
            zm.setCombatLoad("encounter:" + getPath().getPath(), 0);
        com.openworld.game.event.GameplayEvents.unsubscribe(onEvent);
        // a streamed-out scene takes its fight with it
        for (AICharacter m : members) if (GD.isInstanceValid(m) && !m.isDead()) despawn(m);
        members.clear();
        com.openworld.ai.light.LightCombatants tier = com.openworld.ai.light.LightCombatants.get();
        if (tier != null && !lightMembers.isEmpty()) tier.releaseOwnedBy(lightOwner());
        lightMembers.clear();
    }

    private static Loadouts.EncounterRules rules() {
        Loadouts lo = Tables.LOADOUTS.get();
        return lo != null ? lo.encounter : Loadouts.EncounterRules.DEFAULT;
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                || !net.isNetworked() || net.isServer();
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        scanIn -= delta;
        if (scanIn > 0 || life == null || !enabled || !authority()) return;
        double dt = 0.25 - scanIn;
        scanIn = 0.25;
        members.removeIf(m -> !GD.isInstanceValid(m));
        int alive = 0;
        // set off by a PLAYER only: a player's hit on a member (the event stream), or a member already on a player
        // (its faction turned on them -- gang heat). Other AI fighting the crew is the world's business: the
        // DebugWorld's zone enemies shooting it must not turn it on the players (probe_encounter)
        boolean provoked = playerHit;
        playerHit = false;
        for (AICharacter m : members) {
            if (m.isDead()) continue;
            alive++;
            if (m.getTarget() instanceof Player) provoked = true;
        }
        // its full members are COMBAT load: the ambient crowd and traffic make room (PLAN.md 2.3 step 8)
        if (getNodeOrNull("/root/ZoneManager") instanceof com.openworld.world.ZoneManager zm)
            zm.setCombatLoad("encounter:" + getPath().getPath(), alive);
        alive += liveLight();
        life.step(dt, nearestPlayer(), alive, provoked, out);
    }

    /** A player hurt or killed a member since the last step. */
    private boolean playerHit;

    private final com.openworld.game.event.GameplayEvents.Subscriber onEvent = (e, ruling) -> {
        com.openworld.game.event.Actor by, to;
        if (e instanceof com.openworld.game.event.GameplayEvent.Damaged d) { by = d.actor(); to = d.target(); }
        else if (e instanceof com.openworld.game.event.GameplayEvent.Killed k) { by = k.actor(); to = k.target(); }
        else return;
        if (by == null || to == null || by.kind() != com.openworld.game.event.Actor.Kind.PLAYER) return;
        for (AICharacter m : members)
            if (GD.isInstanceValid(m) && m.characterInfo != null && to.id().equals(m.characterInfo.characterId)) {
                playerHit = true;
                return;
            }
    };

    private final EncounterWaves.Out out = new EncounterWaves.Out() {
        @Override public int spawnWave(int index, int count) { return spawnWaveNow(index, count); }
        @Override public void engage() { engageNow(); }
        @Override public void releaseAll() { releaseNow(); }
        @Override public void cleared() { clearedNow(); }
    };

    private double nearestPlayer() {
        double best = Double.MAX_VALUE;
        Vector3 here = getGlobalPosition();
        for (Player p : PlayerRegistry.getPlayers())
            if (GD.isInstanceValid(p) && p.isAlive()) best = Math.min(best, p.getGlobalPosition().distanceTo(here));
        return best;
    }

    private Player nearestPlayerBody() {
        Player best = null;
        double bd = Double.MAX_VALUE;
        Vector3 here = getGlobalPosition();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || !p.isAlive()) continue;
            double d = p.getGlobalPosition().distanceTo(here);
            if (d < bd) { bd = d; best = p; }
        }
        return best;
    }

    // ── the children: spawn / cover / patrol points ──

    /** This node's own markers of {@code kind} (any Node3D below it named MARK_<kind>_<n> or with a kind meta), in
     *  name order. */
    private List<Node3D> own(String kind) {
        List<Node3D> out = new ArrayList<>();
        java.util.ArrayDeque<Node> stack = new java.util.ArrayDeque<>(getChildren());
        while (!stack.isEmpty()) {
            Node n = stack.pop();
            stack.addAll(n.getChildren());
            if (n instanceof Node3D n3 && !(n instanceof AICharacter) && kind.equals(MarkerRegistry.kindOf(n3))) out.add(n3);
        }
        out.sort(Comparator.comparing(n -> n.getName().toString()));
        return out;
    }

    private static int waveOf(Node3D n) {
        StringName k = new StringName("wave");
        return n.hasMeta(k) && n.getMeta(k) instanceof Number x ? x.intValue() : 0;
    }

    /** The points wave {@code index} stands up at: those kept for it, else the unkept ones, else all of them. Later
     *  waves come from the point farthest from the players first (out of the fight's middle). */
    private List<Node3D> spawnPoints(int index) {
        List<Node3D> all = own("spawn");
        List<Node3D> kept = new ArrayList<>(), free = new ArrayList<>();
        for (Node3D n : all) {
            int w = waveOf(n);
            if (w == index + 1) kept.add(n);
            else if (w == 0) free.add(n);
        }
        List<Node3D> pts = !kept.isEmpty() ? kept : !free.isEmpty() ? free : all;
        if (index > 0) {
            Player p = nearestPlayerBody();
            if (p != null) {
                Vector3 pp = p.getGlobalPosition();
                pts = new ArrayList<>(pts);
                pts.sort(Comparator.comparingDouble((Node3D n) -> -n.getGlobalPosition().distanceTo(pp)));
            }
        }
        return pts;
    }

    private List<Node3D> coverPoints() {
        List<Node3D> out = own("cover");
        if (coverRadius > 0)
            for (MarkerRegistry.Marker m : MarkerRegistry.near(this, "cover", getGlobalPosition(), coverRadius))
                if (!out.contains(m.node)) out.add(m.node);
        return out;
    }

    // ── what the rules ask ──

    private int liveAll() {
        int n = 0;
        for (Node e : getTree().getNodesInGroup(new StringName(GROUP)))
            if (e instanceof Encounter enc) n += enc.liveNow();
        return n;
    }

    private int spawnWaveNow(int index, int count) {
        EnforcementDispatch ed = EnforcementDispatch.get();
        if (ed == null || getTree() == null) return 0;
        int room = Math.max(0, rules().cap() - liveAll());
        // the full bodies are capped (the island-wide encounter cap); a wave's overflow past fullCap is light
        int full = fullCap > 0 ? Math.min(count, fullCap) : count;
        int nFull = Math.min(full, room);
        int n = nFull + (count - full);
        if (n <= 0) return 0;
        Loadouts lo = Tables.LOADOUTS.get();
        Loadouts.Loadout l = lo != null ? lo.get(loadout) : null;
        String side = l != null ? l.sideOr(faction) : faction;
        List<Node3D> pts = spawnPoints(index);
        List<Node3D> covers = coverPoints();
        List<Node3D> route = index == 0 ? own("patrol") : List.of();
        boolean engaged = life.state() == EncounterWaves.State.ENGAGED;
        int made = 0;
        for (int i = 0; i < n; i++) {
            Vector3 at;
            Vector3 face;
            if (!pts.isEmpty()) {
                Node3D sp = pts.get(i % pts.size());
                // a second body on the same point stands a little beside it
                double side2 = i < pts.size() ? 0 : 1.2 * (i / pts.size());
                at = sp.getGlobalPosition().plus(sp.getGlobalBasis().getX().times(side2));
                Vector3 z = sp.getGlobalBasis().getZ();
                face = at.plus(new Vector3(-z.getX() * 5, 1.4, -z.getZ() * 5));
            } else {
                double a = Math.PI * 2 * i / n + 0.3 * index;
                at = ground(getGlobalPosition().plus(new Vector3(Math.cos(a) * 4.0, 0, Math.sin(a) * 4.0)));
                if (at == null) continue;
                face = at.plus(new Vector3(Math.cos(a) * 5.0, 1.4, Math.sin(a) * 5.0));
            }
            String key = getPath().getPath() + "#" + spawnedTotal;
            if (i >= nFull) {
                if (spawnLight(at, face, covers, route, l, side, key, engaged)) made++;
                spawnedTotal++;
                continue;
            }
            AICharacter ai = ed.spawnPlaced(side, faction, l, at, Loadouts.roll(key));
            spawnedTotal++;
            if (ai == null) continue;
            ai.setSquad(squad);
            ai.blackboard.postFacePoint = face;
            ai.blackboard.holdLeash = holdLeash;
            ai.blackboard.holdCrouch = crouchAtCover;
            Node3D cover = nearestFree(covers, at);
            if (cover != null) {
                claimedCover.add(cover);
                ai.blackboard.holdPoint = cover.getGlobalPosition();
            }
            if (!route.isEmpty() && cover == null) {
                List<Vector3> r = new ArrayList<>();
                for (Node3D p : route) r.add(p.getGlobalPosition());
                ai.blackboard.patrolRoute = r;
            }
            members.add(ai);
            made++;
            if (engaged) arm(ai);
        }
        if (made > 0) wavesOut = index + 1;
        return made;
    }

    /** What its light members are owned as in the tier. */
    private String lightOwner() { return "encounter:" + getPath().getPath(); }

    /** A wave member past {@link #fullCap}: the same orders a full member gets, in the light tier. */
    private boolean spawnLight(Vector3 at, Vector3 face, List<Node3D> covers, List<Node3D> route, Loadouts.Loadout l,
                               String side, String key, boolean engaged) {
        com.openworld.ai.light.LightCombatants tier = com.openworld.ai.light.LightCombatants.ensure(this);
        if (tier == null) return false;
        com.openworld.ai.AIBlackboard bb = new com.openworld.ai.AIBlackboard();
        bb.owner = lightOwner();
        bb.faction = faction;
        bb.side = side;
        bb.loadout = loadout;
        if (l != null) bb.weapon = l.weapon(Loadouts.roll(key));
        bb.postFacePoint = face;
        bb.holdLeash = holdLeash;
        bb.holdCrouch = crouchAtCover;
        Node3D cover = nearestFree(covers, at);
        if (cover != null) {
            claimedCover.add(cover);
            bb.holdPoint = cover.getGlobalPosition();
        }
        if (!route.isEmpty() && cover == null) {
            List<Vector3> r = new ArrayList<>();
            for (Node3D p : route) r.add(p.getGlobalPosition());
            bb.patrolRoute = r;
        }
        bb.huntsPlayers = engaged;
        if (tier.spawn(bb, at, 100.0, com.openworld.ai.light.LightSim.HUMAN) <= 0) return false;
        lightMembers.add(bb);
        return true;
    }

    /** Its light members alive now (light, or promoted to a body that lives). */
    private int liveLight() {
        com.openworld.ai.light.LightCombatants tier = com.openworld.ai.light.LightCombatants.get();
        return tier == null || lightMembers.isEmpty() ? 0 : tier.liveOwnedBy(lightOwner());
    }

    /** The nearest unclaimed cover point within 25 m of {@code at}, else null. */
    private Node3D nearestFree(List<Node3D> covers, Vector3 at) {
        Node3D best = null;
        double bd = 25.0;
        for (Node3D c : covers) {
            if (claimedCover.contains(c) || !GD.isInstanceValid(c)) continue;
            double d = c.getGlobalPosition().distanceTo(at);
            if (d < bd) { bd = d; best = c; }
        }
        return best;
    }

    /** A member turns on the players: hostile to every player, held at full AI detail, the squad told who. */
    private void arm(AICharacter m) {
        m.blackboard.huntsPlayers = true;
        m.lodPinnedActive = true;
        Player p = nearestPlayerBody();
        if (p != null) squad.broadcastSpotted(m, p, p.getGlobalPosition());
    }

    private void engageNow() {
        for (AICharacter m : members) if (GD.isInstanceValid(m) && !m.isDead()) arm(m);
        for (com.openworld.ai.AIBlackboard bb : lightMembers) bb.huntsPlayers = true;
        encounterTriggered.emit();
    }

    private void releaseNow() {
        for (AICharacter m : members) if (GD.isInstanceValid(m) && !m.isDead()) despawn(m);
        members.clear();
        com.openworld.ai.light.LightCombatants tier = com.openworld.ai.light.LightCombatants.get();
        if (tier != null && !lightMembers.isEmpty()) tier.releaseOwnedBy(lightOwner());
        lightMembers.clear();
        claimedCover.clear();
        wavesOut = 0;
    }

    private void clearedNow() {
        claimedCover.clear();
        if (!ledgerFlag.isEmpty()) WorldLedger.get().setFlag(ledgerFlag, true);
        encounterCleared.emit();
    }

    private void despawn(AICharacter m) {
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net && m.getCharacterInfo() != null)
            net.announceDespawn(m.getCharacterInfo().characterId);
        m.queueFree();
    }

    /** Walkable ground under {@code p}, within 3 m of it; null if none. */
    private Vector3 ground(Vector3 p) {
        if (getViewport() == null || getViewport().getWorld3d() == null) return p;
        var sp = getViewport().getWorld3d().getDirectSpaceState();
        var q = PhysicsRayQueryParameters3D.create(p.plus(new Vector3(0, 3, 0)), p.minus(new Vector3(0, 3, 0)),
                CollisionLayers.WORLD, new godot.core.VariantArray<>(godot.core.RID.class));
        Dictionary<Object, Object> hit = sp.intersectRay(q);
        if (hit == null || hit.isEmpty() || !(hit.get("position") instanceof Vector3 g)) return null;
        return g;
    }

    // ── for an activity, a signal, the console and the probes ──

    /** Start it now (a manual encounter, or one an activity sets off): wave 1 at once, engaged. */
    @Register
    public void startNow() { if (life != null) life.start(); }

    /** Take everyone away and go dormant (an activity's end). */
    @Register
    public void stopNow() { if (life != null) life.stop(out); }

    /** Members still up. */
    @Register
    public int liveNow() {
        int n = 0;
        for (AICharacter m : members) if (GD.isInstanceValid(m) && !m.isDead()) n++;
        return n + liveLight();
    }

    /** Waves not out yet (an activity's "is it over" with {@link #liveNow}). */
    @Register
    public int wavesLeftNow() { return life == null ? 0 : life.wavesLeft(); }

    @Register
    public String stateNow() {
        return (life == null ? "NONE" : life.state().name()) + "," + liveNow() + "," + wavesLeftNow() + "," + wavesOut;
    }

    @Register
    public int memberCountNow() { return members.size(); }

    @Register
    public AICharacter memberNow(int i) { return i >= 0 && i < members.size() ? members.get(i) : null; }

    /**
     * One member for a probe: "alive;faction;weapons;hunts;target;hold;distToHold;state" -- target is "player" when it is
     * on a player, "" when on nobody; hold 1/0; distToHold the level distance to its hold point (-1 = none).
     */
    @Register
    public String memberReadoutNow(int i) {
        if (i < 0 || i >= members.size() || !GD.isInstanceValid(members.get(i))) return "gone";
        AICharacter m = members.get(i);
        // every weapon it carries but its fists, by catalog id ("PIS2+BAT1")
        StringBuilder weapon = new StringBuilder();
        if (m.weaponController != null) for (int k = 0; k < m.weaponController.slotCount(); k++) {
            var w = m.weaponController.getWeaponItem(k);
            if (w == null || w.weaponId.isEmpty() || "fist".equalsIgnoreCase(w.weaponId)) continue;
            if (weapon.length() > 0) weapon.append('+');
            weapon.append(w.weaponId);
        }
        String target = m.getTarget() instanceof Player ? "player" : m.getTarget() != null ? "other" : "";
        double dh = -1;
        if (m.blackboard.holdPoint != null) {
            double x = m.getGlobalPosition().getX() - m.blackboard.holdPoint.getX(), z = m.getGlobalPosition().getZ() - m.blackboard.holdPoint.getZ();
            dh = Math.sqrt(x * x + z * z);
        }
        return (m.isDead() ? "dead" : "alive") + ";" + (m.characterInfo != null ? m.characterInfo.faction : "") + ";"
                + weapon + ";" + (m.blackboard.huntsPlayers ? 1 : 0) + ";" + target + ";" + (m.blackboard.holdPoint != null ? 1 : 0) + ";" + dh
                + ";" + (m.getController() instanceof com.openworld.ai.AIController c && c.getCurrentState() != null
                        ? c.getCurrentState().getClass().getSimpleName() : "-")
                + ";" + (m.weaponController != null && m.weaponController.getCurrentWeaponItem() != null
                        ? m.weaponController.getCurrentWeaponItem().weaponId : "")
                + ";" + (m.isMeleeEngagement() ? "melee" : "ranged");
    }

    @Register
    public boolean ledgerFlagSetNow() { return !ledgerFlag.isEmpty() && WorldLedger.get().isSet(ledgerFlag); }

    /** Encounter by id in this tree, else null. */
    public static Encounter find(Node ctx, String id) {
        if (ctx == null || id == null || ctx.getTree() == null) return null;
        for (Node n : ctx.getTree().getNodesInGroup(new StringName(GROUP)))
            if (n instanceof Encounter e && id.equals(e.encounterId)) return e;
        return null;
    }
}
