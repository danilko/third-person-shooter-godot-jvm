package com.openworld.item;

import com.openworld.character.Character;
import com.openworld.character.Player;
import com.openworld.util.CollisionLayers;
import com.openworld.weapon.WeaponCatalog;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Area3D;
import godot.api.BaseMaterial3D;
import godot.api.CollisionShape3D;
import godot.api.CylinderMesh;
import godot.api.CylinderShape3D;
import godot.api.Label3D;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.StandardMaterial3D;
import godot.core.MethodCallable;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.HashMap;
import java.util.Map;

/**
 * A "get point" pad (user, 2026-09-22): stand on it and you are handed one catalog weapon, for free for now. It
 * replaces the loose weapons that used to lie at the spawn point, and it lives in a shop -- the island's weapon
 * counter is a row of these inside the konbini beside the safe house ({@code tools/island_buildings.py} places
 * them from the building it anchored, so they move with it).
 *
 * <p>The grant is the ordinary pickup path the debug console's {@code give} uses: a fresh catalog instance is
 * put in the tree and queued into the inventory with {@code requestEquip}, so slot choice, displacement and the
 * HUD are the weapon controller's, not this pad's. A weapon the player already carries is REFILLED instead
 * (magazine and reserve), so the pad is also the ammo counter. A pad re-arms for a character only after that
 * character has stepped OFF it and {@link #cooldownSeconds} have passed, so standing on it hands nothing twice.
 *
 * <p>Only the authoritative peer grants (single player or host), the rule every spawned weapon here follows: a
 * weapon spawned on a client would exist on that peer alone. Not measured across two processes yet.
 */
@Script(className = "WeaponPad")
public class WeaponPad extends Area3D {

    /** The catalog id this pad hands out ({@code weapon_catalog.json}). */
    @Export public String weaponId = "";
    /** Seconds after stepping off before the pad serves the same character again. */
    @Export public double cooldownSeconds = 2.0;
    @Export public double radius = 0.5;
    /** The pad disc's glow; the label above it says what it gives. */
    @Export public Color padColor = new Color(0.25f, 0.85f, 1.0f, 1.0f);

    private final Map<Long, Double> offAt = new HashMap<>();   // instance id -> time it stepped off
    private Node3D display;
    private double time = 0.0;
    private int grants = 0;

    /** How many grants this pad has made (probe readout). */
    @Register
    public int grantsNow() { return grants; }

    @Register
    @Override
    public void _ready() {
        String id = WeaponCatalog.find(weaponId);
        if (id == null) {
            GD.INSTANCE.printErr("WeaponPad: no catalog weapon '" + weaponId + "' at " + getPath().getPath());
            return;
        }
        weaponId = id;
        setCollisionLayer(0);
        setCollisionMask(CollisionLayers.CHARACTER);
        setMonitoring(true);
        setMonitorable(false);

        CylinderShape3D shape = new CylinderShape3D();
        shape.setRadius((float) radius);
        shape.setHeight(1.8f);
        CollisionShape3D cs = new CollisionShape3D();
        cs.setShape(shape);
        cs.setPosition(new Vector3(0, 0.9, 0));
        addChild(cs);

        StandardMaterial3D mat = new StandardMaterial3D();
        mat.setAlbedo(new Color(padColor.getR(), padColor.getG(), padColor.getB(), 0.85f));
        mat.setTransparency(BaseMaterial3D.Transparency.ALPHA);
        mat.setFeature(BaseMaterial3D.Feature.EMISSION, true);
        mat.setEmission(padColor);
        mat.setEmissionEnergyMultiplier(1.6f);
        mat.setShadingMode(BaseMaterial3D.ShadingMode.UNSHADED);
        CylinderMesh disc = new CylinderMesh();
        disc.setTopRadius((float) radius);
        disc.setBottomRadius((float) radius);
        disc.setHeight(0.03f);
        disc.setRadialSegments(32);
        disc.setMaterial(mat);
        MeshInstance3D m = new MeshInstance3D();
        m.setMesh(disc);
        m.setPosition(new Vector3(0, 0.02, 0));
        addChild(m);

        // What it gives: the weapon's own model, hovering and turning, and its name.
        WeaponItem item = WeaponCatalog.instantiate(weaponId);
        String label = weaponId;
        if (item != null) {
            label = item.weaponName == null || item.weaponName.isEmpty() ? weaponId : item.weaponName;
            Node model = item.getNodeOrNull("Model");
            if (model instanceof Node3D m3) {
                item.removeChild(m3);
                m3.setOwner(null);
                display = new Node3D();
                display.setPosition(new Vector3(0, 1.05, 0));
                addChild(display);
                display.addChild(m3);
                m3.setPosition(Vector3.Companion.getZERO());
            }
            item.free();
        }
        Label3D text = new Label3D();
        text.setText(label + "\nFREE");
        text.setBillboardMode(BaseMaterial3D.BillboardMode.ENABLED);
        text.setFontSize(40);
        text.setPixelSize(0.004f);
        text.setOutlineSize(8);
        text.setPosition(new Vector3(0, 1.55, 0));
        addChild(text);

        connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
        connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_body_exited"));
    }

    @Register
    @Override
    public void _process(double delta) {
        time += delta;
        if (display != null) display.rotateY((float) (delta * 1.2));
    }

    @Register
    public void onBodyExited(Node body) {
        offAt.put(body.getInstanceId(), time);
    }

    @Register
    public void onBodyEntered(Node body) {
        if (!(body instanceof Player p) || p.weaponController == null || !authoritative()) return;
        Double left = offAt.get(p.getInstanceId());
        if (left != null && time - left < cooldownSeconds) return;
        grant(p);
    }

    private boolean authoritative() {
        return !(getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager net)
                || !net.isNetworked() || net.isServer();
    }

    private void grant(Character c) {
        var wc = c.weaponController;
        for (int i = 0; i < wc.slotCount(); i++) {
            WeaponItem w = wc.getWeaponItem(i);
            if (w == null || !weaponId.equals(w.weaponId)) continue;
            w.magazine = w.magazineSize;
            w.reserve = w.reserveMax;
            WeaponItem cur = wc.getCurrentWeaponItem();
            if (cur != null) wc.ammoChanged.emit(cur.magazine, cur.reserve);
            grants++;
            return;
        }
        WeaponItem item = WeaponCatalog.instantiate(weaponId);
        if (item == null) return;
        getTree().getCurrentScene().addChild(item);
        item.setGlobalPosition(c.getGlobalPosition());
        wc.requestEquip(item);
        grants++;
    }
}
