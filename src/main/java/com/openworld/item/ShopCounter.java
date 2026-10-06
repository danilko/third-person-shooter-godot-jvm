package com.openworld.item;

import com.openworld.character.Player;
import com.openworld.ui.ShopMenu;
import com.openworld.util.CollisionLayers;
import com.openworld.weapon.WeaponCatalog;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Area3D;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.Input;
import godot.api.Node;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * A shop's weapon counter (PLAN.md W3, user 2026-10-03; GTA SA's Ammu-Nation): stand at the register and press
 * {@code interact} to open {@link ShopMenu}, a list of what this shop sells. It replaces the floor pads, which stood
 * in the aisles where pedestrians and AI walk: a counter is a sensor volume in front of the register, no collider,
 * nothing on a walkway.
 *
 * <p>A pick is granted through {@link WeaponGrant} on the authoritative peer; a client sends
 * {@code MSG_SHOP_REQUEST} and the host checks the buyer is the character's owner and stands at a counter that sells
 * it. FREE until money exists. Group {@code shop_counter} is how the host finds counters.
 */
@Script(className = "ShopCounter")
public class ShopCounter extends Area3D {

    public static final String GROUP = "shop_counter";

    /** Comma-separated catalog weapon ids and/or supply ids ({@code item/supplies.json}). */
    @Export public String stock = "";
    /** The sensor box in front of the register (local X across the counter, Z toward the customer). */
    @Export public Vector3 size = new Vector3(3.0, 2.0, 1.6);
    @Export public String title = "WEAPONS";

    private final List<String> items = new ArrayList<>();
    private Player inside;

    @Register
    @Override
    public void _ready() {
        for (String s : stock.split(",")) {
            String id = WeaponCatalog.find(s.trim());
            if (id == null && SupplyCatalog.find(s.trim()) != null) id = s.trim();
            if (id != null) items.add(id);
            else if (!s.isBlank()) GD.INSTANCE.printErr("ShopCounter: no weapon or supply '" + s.trim() + "'");
        }
        addToGroup(new StringName(GROUP), true);
        setCollisionLayer(0);
        setCollisionMask(CollisionLayers.CHARACTER);
        setMonitoring(true);
        setMonitorable(false);
        BoxShape3D box = new BoxShape3D();
        box.setSize(size);
        CollisionShape3D cs = new CollisionShape3D();
        cs.setShape(box);
        cs.setPosition(new Vector3(0, size.getY() * 0.5, 0));
        addChild(cs);
        connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
        connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_body_exited"));
        setProcess(false);
    }

    @Register
    public void onBodyEntered(Node body) {
        if (body instanceof Player p && p.isLocallyOwnedPlayer()) {
            inside = p;
            showPrompt(true);
            setProcess(true);
        }
    }

    @Register
    public void onBodyExited(Node body) {
        if (body == inside) {
            inside = null;
            showPrompt(false);
            setProcess(false);
            ShopMenu.closeFor(this);
        }
    }

    @Register
    @Override
    public void _process(double delta) {
        if (inside == null || !GD.isInstanceValid(inside) || !inside.isAlive()) {
            inside = null;
            showPrompt(false);
            ShopMenu.closeFor(this);
            setProcess(false);
            return;
        }
        if (!ShopMenu.isOpen() && !ShopMenu.closedThisFrame() && Input.INSTANCE.isActionJustPressed("interact", false))
            ShopMenu.open(this, inside);
    }

    private void showPrompt(boolean on) {
        if (getNodeOrNull("/root/EventBus") instanceof com.openworld.game.EventBus bus)
            bus.pickupInteractChanged.emit(on, on ? title + " (E)" : "");
    }

    public List<String> items() { return items; }

    /** The menu row that empties the till (only offered while {@link #clerk} is robbable). */
    public static final String TILL = "till";

    /** A gray-area counter's row: pay the gang's "donation" (clears that gang's heat, game.GangSystem). */
    public static final String DONATION = "donation";

    /** Does this counter sell {@code id}? (the till only once its clerk has given up or is down; the donation only at
     *  a gray-area counter) */
    public boolean sells(String id) {
        if (TILL.equals(id)) { var c = clerk(); return c != null && c.robbable(); }
        if (DONATION.equals(id)) { var c = clerk(); return c != null && c.grayArea() && com.openworld.game.GangSystem.get() != null; }
        return items.contains(id);
    }

    /** The clerk serving this counter: the nearest clerk spot within 10 m (the same building). */
    public com.openworld.world.ShopClerkSpot clerk() {
        if (getTree() == null) return null;
        com.openworld.world.ShopClerkSpot best = null;
        double d0 = 10.0;
        for (Node n : getTree().getNodesInGroup(new StringName(com.openworld.world.ShopClerkSpot.GROUP))) {
            if (n instanceof com.openworld.world.ShopClerkSpot c && GD.isInstanceValid(c)) {
                double d = c.getGlobalPosition().distanceTo(getGlobalPosition());
                if (d < d0) { d0 = d; best = c; }
            }
        }
        return best;
    }

    /** The menu's rows: the till first while it can be robbed, then the stock. */
    public List<String> rows() {
        List<String> out = new ArrayList<>();
        if (sells(TILL)) out.add(TILL);
        if (sells(DONATION)) out.add(DONATION);
        out.addAll(items);
        return out;
    }

    /** Is a world point inside this counter's sensor box (plus {@code slack} m)? */
    public boolean holds(Vector3 world, double slack) {
        Vector3 l = getGlobalTransform().affineInverse().times(world);
        return Math.abs(l.getX()) <= size.getX() * 0.5 + slack && Math.abs(l.getZ()) <= size.getZ() * 0.5 + slack
                && l.getY() > -1.0 && l.getY() < size.getY() + 1.0;
    }

    /** Buy {@code id} for {@code who}: grant on the authority, else ask the host. */
    public void buy(Player who, String id) {
        if (!sells(id) || who == null) return;
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net
                && net.isNetworked() && !net.isServer()) {
            net.sendShopRequest(who.getCharacterInfo().characterId, id);
            return;
        }
        grantTo(who, id);
    }

    /** The authority's grant: a supply is carried, a weapon goes through {@link WeaponGrant}. */
    @Register
    public void grantToNow(Node who, String id) {
        if (who instanceof com.openworld.character.Character c) grantTo(c, id);
    }

    public void grantTo(com.openworld.character.Character who, String id) {
        if (!sells(id)) return;
        if (TILL.equals(id)) { clerk().robTill(who); return; }
        if (DONATION.equals(id)) { com.openworld.game.GangSystem.get().donate(who, clerk().gang()); return; }
        if (isSupply(id)) Supplies.give(who, id);
        else WeaponGrant.grant(who, id, this);
    }

    public static boolean isSupply(String id) { return SupplyCatalog.find(id) != null; }

    // ── probe surface ──
    @Register public boolean playerAtCounterNow() { return inside != null; }
    @Register public String stockNow() { return String.join(",", items); }
}
