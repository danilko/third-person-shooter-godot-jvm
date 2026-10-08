package com.openworld.item;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.game.GameManager;
import com.openworld.net.NetworkManager;
import com.openworld.util.CollisionLayers;
import com.openworld.util.MiniJson;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import com.openworld.weapon.WeaponType;
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

import java.util.HashMap;
import java.util.Map;

/**
 * Spare ammunition carried at a vehicle's rear (PLAN.md 1g b3, user 2026-10-07): a police car's trunk, an armoured
 * vehicle's or a tank's stowage. Which vehicles carry it, and how much, is DATA ({@code item/ammo_supply.json}, keyed
 * by the vehicle's catalog id); {@link #attachTo} builds one on a vehicle that is listed, so every such vehicle -- a
 * unit's own car, a parked one, one the player has taken -- behaves the same.
 *
 * <p>ANY character may restock here: a unit out of ammo walks back to the nearest supply
 * ({@code EnforcementDispatch}) and stands at it {@code restock_seconds}; a player presses {@code interact} in the
 * sensor box. A restock fills every weapon the character carries and uses one of the vehicle's {@code stock}. Applied
 * on the authoritative peer and mirrored by {@code WORLD_EVENT_AMMO_REFILL} (AmmoRefill's path); a client asks with
 * {@code MSG_SHOP_REQUEST} item {@link #ITEM}.
 */
@Script(className = "AmmoSupply")
public class AmmoSupply extends Area3D {

    public static final String GROUP = "ammo_supply";
    /** The shop-request item id a client sends to restock at a supply it stands at. */
    public static final String ITEM = "ammo_supply";
    public static final String PATH = "res://src/main/resources/com/openworld/item/ammo_supply.json";

    /** Restocks left. */
    public int stock = 0;
    public int restocks = 0;
    private Player inside;

    // ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────
    private static Map<String, Integer> stockById;
    private static double reach = 2.2, restockSeconds = 2.0;

    @SuppressWarnings("unchecked")
    private static synchronized void load() {
        if (stockById != null) return;
        stockById = new HashMap<>();
        if (!godot.api.FileAccess.fileExists(PATH)) return;
        Map<String, Object> doc = (Map<String, Object>) MiniJson.parse(godot.api.FileAccess.getFileAsString(PATH));
        reach = ((Number) doc.getOrDefault("reach", 2.2)).doubleValue();
        restockSeconds = ((Number) doc.getOrDefault("restock_seconds", 2.0)).doubleValue();
        Map<String, Object> v = (Map<String, Object>) doc.getOrDefault("vehicles", Map.of());
        for (Map.Entry<String, Object> e : v.entrySet())
            stockById.put(e.getKey(), ((Number) ((Map<String, Object>) e.getValue()).getOrDefault("stock", 0)).intValue());
    }

    public static double reach() { load(); return reach; }
    public static double restockSeconds() { load(); return restockSeconds; }

    /** Build a supply on {@code vehicle} if its catalog id is listed: at its rear, {@code halfLength} back from its
     *  centre (body space, -Z forward). Returns the supply or null. */
    public static AmmoSupply attachTo(Node vehicle, String modelId, double halfLength) {
        load();
        Integer s = stockById.get(modelId);
        if (s == null || s <= 0) return null;
        AmmoSupply a = new AmmoSupply();
        a.stock = s;
        a.setName(new StringName("AmmoSupply"));
        a.setPosition(new Vector3(0, 0, halfLength + 0.9));
        vehicle.addChild(a);
        return a;
    }

    @Register
    @Override
    public void _ready() {
        addToGroup(new StringName(GROUP), true);
        setCollisionLayer(0);
        setCollisionMask(CollisionLayers.CHARACTER);
        setMonitoring(true);
        setMonitorable(false);
        BoxShape3D box = new BoxShape3D();
        box.setSize(new Vector3(2.6, 2.2, 2.0));
        CollisionShape3D cs = new CollisionShape3D();
        cs.setShape(box);
        cs.setPosition(new Vector3(0, 1.1, 0));
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
        }
    }

    @Register
    @Override
    public void _process(double delta) {
        if (inside == null || !GD.isInstanceValid(inside) || !inside.isAlive() || inside.currentVehicleNode != null) {
            if (inside != null) showPrompt(false);
            inside = null;
            setProcess(false);
            return;
        }
        if (com.openworld.ui.ShopMenu.isOpen() || !Input.INSTANCE.isActionJustPressed("interact", false)) return;
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && net.isNetworked() && !net.isServer()) {
            if (inside.getCharacterInfo() != null) net.sendShopRequest(inside.getCharacterInfo().characterId, ITEM);
        } else {
            restock(inside);
        }
        showPrompt(true);
    }

    private void showPrompt(boolean on) {
        if (getNodeOrNull("/root/EventBus") instanceof com.openworld.game.EventBus bus)
            bus.pickupInteractChanged.emit(on, on ? (stock > 0 ? "RESTOCK AMMO x" + stock + " (E)" : "AMMO EMPTY") : "");
    }

    /** Does a character standing at {@code world} reach this supply? */
    public boolean reaches(Vector3 world) {
        return getGlobalPosition().distanceTo(world) <= reach() + 0.8;
    }

    /** Does {@code c} carry a firearm that is not full? (nothing to restock otherwise) */
    public static boolean wantsAmmo(Character c) {
        if (!(c.getNodeOrNull("WeaponController") instanceof WeaponController wc)) return false;
        for (int i = 0; i < wc.getSlotCount(); i++) {
            WeaponItem w = wc.getWeaponItem(i);
            if (w != null && !w.isInfiniteAmmo && w.getWeaponType() != WeaponType.MELEE
                    && (w.getMagazine() < w.getMagazineSize() || w.getReserve() < w.getReserveMax())) return true;
        }
        return false;
    }

    /** Authoritative peer: fill {@code c}'s weapons from this supply. False when empty, out of reach or full. */
    public boolean restock(Character c) {
        if (c == null || stock <= 0 || !reaches(c.getGlobalPosition()) || !wantsAmmo(c)) return false;
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && net.isNetworked() && !net.isServer())
            return false;
        if (!(c.getNodeOrNull("WeaponController") instanceof WeaponController wc)) return false;
        wc.fillWeaponAmmo();
        stock--;
        restocks++;
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net && c.getCharacterInfo() != null)
            net.broadcastWorldEvent(GameManager.WORLD_EVENT_AMMO_REFILL, c.getCharacterInfo().characterId, 0f);
        if (getNodeOrNull("/root/EventBus") instanceof com.openworld.game.EventBus bus && c instanceof Player)
            bus.ammoPickedUp.emit(0);
        return true;
    }

    /** The nearest supply with stock within {@code within} m of {@code at}, or null. */
    public static AmmoSupply nearest(Node from, Vector3 at, double within) {
        if (from.getTree() == null) return null;
        AmmoSupply best = null;
        double d0 = within;
        for (Node n : from.getTree().getNodesInGroup(new StringName(GROUP))) {
            if (n instanceof AmmoSupply a && GD.isInstanceValid(a) && a.stock > 0 && a.isInsideTree()) {
                double d = a.getGlobalPosition().distanceTo(at);
                if (d < d0) { d0 = d; best = a; }
            }
        }
        return best;
    }

    @Register public int stockNow() { return stock; }
    @Register public int restocksNow() { return restocks; }
    @Register public boolean restockNow(Node who) { return who instanceof Character c && restock(c); }
}
