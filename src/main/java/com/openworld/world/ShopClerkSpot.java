package com.openworld.world;

import com.openworld.ai.AIController;
import com.openworld.ai.ClerkController;
import com.openworld.character.AICharacter;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Faction;
import com.openworld.character.Player;
import com.openworld.control.Controller;
import com.openworld.game.PlayerRegistry;
import com.openworld.item.WeaponGrant;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PackedScene;
import godot.core.Vector3;
import godot.global.GD;

import java.util.UUID;

/**
 * Where a shop's clerk stands (PLAN.md W3; user 2026-10-03). AN ARTIST'S DECISION, carried in the shop's model: a
 * {@code MARK_clerk} Empty behind the register (its -Z is the way the clerk faces), with custom properties
 * {@code surrender} (0..1, the chance the clerk gives up when threatened), {@code weapons} (comma catalog ids the
 * clerk fights back with -- a heavy weapon from under the counter) and {@code faction}. The building builder turns
 * the marker into this node; nothing in the island generation knows about clerks.
 *
 * <p>On the authoritative peer, when the building streams in, a clerk (an ordinary AICharacter) is spawned here with a
 * {@link ClerkController}: still, hands empty, facing the counter. A THREAT -- a player in combat aiming within
 * {@link #AIM_RADIUS} of the clerk from within {@link #THREAT_RANGE}, or the clerk getting hurt -- is rolled ONCE
 * (by the clerk's id, so a peer and a replay agree): SURRENDER (crouches behind the counter and stays) or FIGHT
 * (draws a weapon from {@link #weapons}, turns to {@link #FIGHT_FACTION} so it is hostile to everyone, and gets the
 * ordinary AI brain back). The clerk is freed with the building.
 */
@Script(className = "ShopClerkSpot")
public class ShopClerkSpot extends Node3D {

    static final String AI_SCENE = "res://src/main/resources/com/openworld/character/AICharacter.tscn";
    public static final String FIGHT_FACTION = "vigilante";
    static final double AIM_RADIUS = 1.6, THREAT_RANGE = 25.0;

    @Export public double surrender = 0.6;
    @Export public String weapons = "SHG1,ASR2,SMG1";
    @Export public String faction = Faction.NEUTRAL;
    /**
     * A GRAY-AREA shop (an adult shop): who comes out when the clerk is threatened, "faction:count:weapons" -- e.g.
     * {@code gang_a:3:SMG1,SHG1,ASR2} (user, 2026-10-03: the local gang, directly, on top of the police). They stand
     * up at the building's {@code MARK_spawn team=gang} markers, else round this spot, and threatening or robbing
     * here raises that gang's heat (game.GangSystem). Its counter takes the gang's "donation". Empty for an
     * ordinary shop.
     */
    @Export public String responders = "";
    /** Yen in the till (the robbery's take; a counter beside the clerk hands it over once). */
    @Export public int till = 30000;

    public static final String GROUP = "shop_clerk";
    private boolean tillTaken;

    private AICharacter clerk;
    private AIController brain;
    private ClerkController still;
    /** 0 calm, 1 surrendered, 2 fighting. */
    private int state;
    private double scan;

    /**
     * The clerk is a full AI body, so it exists only while a player is near (2026-10-04: every open shop in range
     * spawning its clerk at load cost frame time downtown, measured with probe_walk_perf.gd): spawned within
     * {@link #SPAWN_NEAR}, returned beyond {@link #DESPAWN_FAR} while still calm. A clerk who surrendered, fought or
     * died is not brought back while this shop stays loaded (`spent`).
     */
    static final double SPAWN_NEAR = 60.0, DESPAWN_FAR = 100.0;
    private boolean spent;
    private double nearScan;
    /** A clerk has stood here (so "no clerk" means it went down, not that it never spawned). */
    private boolean spawnedOnce;
    /** Consecutive scans a player has aimed a drawn weapon at the clerk (a glance is not a threat). */
    private int aimedScans;
    static final int THREAT_SCANS = 3;

    @Register
    @Override
    public void _ready() {
        addToGroup(new godot.core.StringName(GROUP), true);
    }

    private double nearestPlayer() {
        double best = Double.MAX_VALUE;
        Vector3 here = getGlobalPosition();
        for (Player p : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(p)) best = Math.min(best, p.getGlobalPosition().distanceTo(here));
        }
        return best;
    }

    private boolean authority() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                || !net.isNetworked() || net.isServer();
    }

    @Register
    public void spawnClerk() {
        if (clerk != null || !authority() || getTree() == null || getTree().getCurrentScene() == null) return;
        if (!(GD.load(AI_SCENE) instanceof PackedScene ps) || !(ps.instantiate() instanceof AICharacter ai)) return;
        CharacterInfo info = new CharacterInfo();
        info.characterId = UUID.randomUUID().toString();
        info.displayName = "Clerk";
        info.faction = faction;
        ai.characterInfo = info;
        Node container = getTree().getCurrentScene().getNodeOrNull("Characters");
        if (container == null) container = getTree().getCurrentScene();
        container.addChild(ai);
        ai.activateForSpawn(getGlobalPosition().plus(new Vector3(0, 0.05, 0)));
        dropBrain();
        Controller c = ai.detachController();
        brain = c instanceof AIController a ? a : null;
        still = new ClerkController();
        still.facePoint = getGlobalPosition().plus(getGlobalBasis().getZ().times(-3.0)).plus(new Vector3(0, 1.4, 0));
        ai.attachController(still);
        clerk = ai;
        spawnedOnce = true;
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net) net.announceSpawn(ai);
    }

    @Register
    @Override
    public void _physicsProcess(double delta) {
        nearScan -= delta;
        if (nearScan <= 0.0 && authority()) {
            nearScan = 0.5;
            double d = nearestPlayer();
            if (clerk == null && !spent && d < SPAWN_NEAR) spawnClerk();
            else if (clerk != null && state == 0 && d > DESPAWN_FAR && GD.isInstanceValid(clerk) && !clerk.isDead()) {
                if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                    net.announceDespawn(clerk.getCharacterInfo().characterId);
                clerk.queueFree();
                clerk = null;
                dropBrain();
            }
        }
        if (clerk == null || state == 2) return;
        if (!GD.isInstanceValid(clerk) || clerk.isDead()) { clerk = null; spent = true; return; }
        scan -= delta;
        if (scan > 0 || state == 1) return;
        scan = 0.2;
        Player who = threatener();
        if (who != null) react(who);
    }

    /** The player threatening the clerk (aiming at it, or having just hurt it), else null. */
    private Player threatener() {
        boolean hurt = clerk.getNodeOrNull("Health") instanceof com.openworld.character.Health h && h.hurtWithin(1.0);
        Vector3 chest = clerk.getGlobalPosition().plus(new Vector3(0, 1.2, 0));
        Player aimer = null;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || !p.isAlive() || !p.isCombat() || p.inputBlocked()) continue;
            if (!drawsWeapon(p)) continue;
            if (p.getGlobalPosition().distanceTo(chest) > THREAT_RANGE) continue;
            Vector3 aim = p.getAimTargetPosition();
            if (aim == null) continue;
            // the aim LINE passing the clerk, not the aim point (it may land on the wall behind)
            Vector3 eye = p.getGlobalPosition().plus(new Vector3(0, 1.5, 0));
            Vector3 d = aim.minus(eye);
            double len = d.length();
            if (len < 0.01) continue;
            Vector3 dir = d.div(len);
            double t = chest.minus(eye).dot(dir);
            if (t < 0) continue;
            if (eye.plus(dir.times(t)).distanceTo(chest) <= AIM_RADIUS) { aimer = p; break; }
        }
        // a threat is HOLDING a weapon on the clerk, not a glance: a player who walks up to the counter faces the
        // clerk, and a purchase that hands over a weapon draws it with the aim line already on the clerk
        aimedScans = aimer != null ? aimedScans + 1 : 0;
        if (aimer != null && aimedScans >= THREAT_SCANS) return aimer;
        if (!hurt) return null;
        Player near = null;
        double best = THREAT_RANGE;
        for (Player p : PlayerRegistry.getPlayers()) {
            if (!GD.isInstanceValid(p) || !p.isAlive()) continue;
            double d = p.getGlobalPosition().distanceTo(chest);
            if (d < best) { best = d; near = p; }
        }
        return near;
    }

    /** A real weapon in the hands: not fists, not a holster, not a healing supply. */
    private static boolean drawsWeapon(Player p) {
        var wc = p.weaponController;
        if (wc == null || wc.isHolstered()) return false;
        var w = wc.getCurrentWeaponItem();
        return w != null && !(w instanceof com.openworld.weapon.FistItem) && !(w instanceof com.openworld.weapon.SupplyItem);
    }

    /** The one roll: by the clerk's id, so it is the same answer every time it is asked. */
    static boolean rollsSurrender(String id, double chance) {
        return Math.floorMod(id.hashCode() * 2654435761L, 1000L) / 1000.0 < chance;
    }

    private void react(Player who) {
        // a threatened clerk is a crime (police respond); a gray-area shop also calls its gang
        com.openworld.game.WantedSystem ws = com.openworld.game.WantedSystem.get();
        String pid = who.getCharacterInfo() != null ? who.getCharacterInfo().characterId : "";
        if (ws != null) ws.report("threaten_clerk", clerk.getGlobalPosition(), pid);
        if (!responders.isBlank()) callResponders(pid);
        if (rollsSurrender(clerk.characterInfo.characterId, surrender)) {
            state = 1;
            spent = true;
            still.surrendered = true;
            GD.print("ShopClerkSpot: the clerk surrenders");
            return;
        }
        state = 2;
        spent = true;
        String[] list = weapons.split(",");
        String w = list[Math.floorMod(clerk.characterInfo.characterId.hashCode(), list.length)].trim();
        if (!w.isEmpty()) WeaponGrant.grant(clerk, w, this);
        clerk.setFaction(FIGHT_FACTION);
        if (brain != null) {
            clerk.attachController(brain);
            brain.start();
        }
        GD.print("ShopClerkSpot: the clerk fights back with " + w);
    }

    /** The gray-area shop's people come out armed with heavy weapons, and their faction now shoots this player while
     *  the player is lethal-wanted (the robbery makes it lethal). */
    private void callResponders(String playerId) {
        String[] parts = responders.split(":");
        if (parts.length < 2) return;
        String gang = parts[0].trim();
        int n = Math.max(0, Integer.parseInt(parts[1].trim()));
        String[] guns = parts.length > 2 ? parts[2].split(",") : new String[] {"SMG1"};
        com.openworld.game.GangSystem gs = com.openworld.game.GangSystem.get();
        if (gs != null) gs.report(gang, "threaten_clerk", playerId);
        java.util.List<Vector3> spots = new java.util.ArrayList<>();
        if (getParent() != null) {
            for (Node m : getParent().getChildren()) {
                if (m instanceof Node3D m3 && "gang".equals(String.valueOf(m3.getMeta(new godot.core.StringName("team"), ""))))
                    spots.add(m3.getGlobalPosition());
            }
        }
        if (!(GD.load(AI_SCENE) instanceof PackedScene ps) || getTree().getCurrentScene() == null) return;
        Node container = getTree().getCurrentScene().getNodeOrNull("Characters");
        if (container == null) container = getTree().getCurrentScene();
        for (int i = 0; i < n; i++) {
            if (!(ps.instantiate() instanceof AICharacter ai)) continue;
            CharacterInfo info = new CharacterInfo();
            info.characterId = UUID.randomUUID().toString();
            info.displayName = "Enforcer";
            info.faction = gang;
            ai.characterInfo = info;
            container.addChild(ai);
            Vector3 at = !spots.isEmpty() ? spots.get(i % spots.size())
                    : getGlobalPosition().plus(getGlobalBasis().getZ().times(2.0 + i)).plus(getGlobalBasis().getX().times(i % 2 == 0 ? 1.5 : -1.5));
            ai.activateForSpawn(at.plus(new Vector3(0, 0.05, 0)));
            WeaponGrant.grant(ai, guns[i % guns.length].trim(), this);
            gangSpawned.add(ai);
            if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net) net.announceSpawn(ai);
        }
        GD.print("ShopClerkSpot: " + n + " " + gang + " come out");
    }

    private final java.util.List<AICharacter> gangSpawned = new java.util.ArrayList<>();

    /** The till can be robbed once the clerk has surrendered or is down. */
    public boolean robbable() {
        if (tillTaken) return false;
        if (!authority()) return clientSeesClerkDown();
        // "no clerk" only counts once one has stood here: before the clerk spawns (or on a peer that never spawns
        // one) the till is not on offer, or an ordinary purchase lands on the robbery row
        return state == 1 || (spawnedOnce && (clerk == null || !GD.isInstanceValid(clerk) || clerk.isDead()));
    }

    /** A client's view: the host's clerk is a replicated puppet; the till is offered once that body is down. The host
     *  re-checks the robbery against its own state. (A surrendered clerk is not visible to a client's menu yet.) */
    private boolean clientSeesClerkDown() {
        if (getTree() == null) return false;
        for (Node n : getTree().getNodesInGroup(new godot.core.StringName("characters"))) {
            if (n instanceof AICharacter a && a.characterInfo != null && "Clerk".equals(a.characterInfo.displayName)
                    && a.getGlobalPosition().distanceTo(getGlobalPosition()) < 4.0) return a.isDead();
        }
        return false;
    }

    /** Take the till (a ShopCounter's robbery row): the cash, and the crime -- lethal, so police come shooting. */
    public int robTill(com.openworld.character.Character who) {
        if (!robbable() || who == null) return 0;
        tillTaken = true;
        who.cash += till;
        com.openworld.game.WantedSystem ws = com.openworld.game.WantedSystem.get();
        // police treat every store the same (user, 2026-10-03); a gray-area shop adds its gang's heat on top
        if (ws != null && who.getCharacterInfo() != null)
            ws.report("rob_store", getGlobalPosition(), who.getCharacterInfo().characterId);
        com.openworld.game.GangSystem gs = com.openworld.game.GangSystem.get();
        if (gs != null && grayArea() && who.getCharacterInfo() != null)
            gs.report(gang(), "rob_gray", who.getCharacterInfo().characterId);
        return till;
    }

    public boolean grayArea() { return !responders.isBlank(); }

    /** The gang behind a gray-area shop ("" for an ordinary shop). */
    public String gang() { return grayArea() ? responders.split(":")[0].trim() : ""; }

    @Register
    @Override
    public void _exitTree() {
        for (AICharacter g : gangSpawned) if (GD.isInstanceValid(g) && !g.isDead()) g.queueFree();
        gangSpawned.clear();
        if (clerk != null && GD.isInstanceValid(clerk)) {
            if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net
                    && clerk.characterInfo != null) net.announceDespawn(clerk.characterInfo.characterId);
            clerk.queueFree();
        }
        dropBrain();
        clerk = null;
    }

    /** Free the clerk's detached AI brain. It is OFF-TREE (detachController), so nothing else ever frees it: a calm
     *  clerk returned past DESPAWN_FAR used to leave it behind on every round trip, and the next spawn overwrote the
     *  reference -- the "Node ... removed with remove_child() but not freed" leak at exit (PLAN.md 0.2). free(), not
     *  queueFree(): an off-tree node is safe to free at once, and at quit a queued deletion may never be flushed. */
    private void dropBrain() {
        if (brain != null && GD.isInstanceValid(brain) && brain.getParent() == null) brain.free();
        brain = null;
    }

    /** True while a detached brain is held (probe readout). */
    @Register public boolean brainHeldNow() { return brain != null && GD.isInstanceValid(brain); }

    // ── probe surface ──
    @Register public Node clerkNow() { return clerk; }
    @Register public int clerkStateNow() { return state; }
    @Register public boolean robbableNow() { return robbable(); }
    @Register public void threatenNow(Node player) { if (clerk != null && player instanceof Player p && state == 0) react(p); }
}
