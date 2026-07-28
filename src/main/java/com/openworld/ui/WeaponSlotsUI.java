package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Callable;
import godot.core.MethodCallable;
import godot.core.NodePath;
import godot.core.StringNames;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * Persistent bottom-right weapon indicator (display only, no input).
 *
 * Root is a PanelContainer whose size is fixed by scene anchors/offsets, so
 * the inner VBoxContainer and its WeaponSlotItem children always scale to fit
 * within the declared width rather than expanding to match icon sizes.
 *
 * Layout (in WeaponSlotsUI.tscn):
 *   PanelContainer  ← this node; fixed bottom-right anchor
 *     Slots (VBoxContainer) ← auto-filled by PanelContainer
 *       WeaponSlotItem × 5  ← instantiated at runtime from slotItemScene
 *
 * Active slot: full brightness. Inactive: dimmed. Empty: very dim.
 *
 * Wired by HUDManager.wirePlayer() via wireCharacter(). Connects to:
 *   WeaponController.ammoChanged  → refreshAllSlots()
 *   Character.changedWeapon       → onWeaponSwitched()
 */
@RegisterClass(className = "WeaponSlotsUI")
public class WeaponSlotsUI extends PanelContainer {

    private static final int   SLOT_COUNT            = 7;
    private static final String SLOT_ITEM_SCENE_PATH =
            "res://src/main/resources/com/openworld/ui/WeaponSlotItem.tscn";

    /** Slot item scene to instantiate. Wired automatically from SLOT_ITEM_SCENE_PATH. */
    @Export @RegisterProperty
    public PackedScene slotItemScene;

    /** Path to the VBoxContainer that holds slot rows. */
    @Export @RegisterProperty
    public NodePath slotsPath = new NodePath("Slots");

    private Character        character;
    private WeaponController weaponController;
    private int              activeSlot = 0;

    private final List<WeaponSlotItem> slotItems = new ArrayList<>();
    private final String[]             keyTexts  = new String[SLOT_COUNT];

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        // Display-only: never intercept mouse events regardless of screen coverage.
        setMouseFilter(Control.MouseFilter.IGNORE);
        resolveKeyTexts();
        buildSlots();
    }

    // ── Wiring ────────────────────────────────────────────────────────────────

    /** Called by HUDManager when the active player spawns or changes. */
    public void wireCharacter(Character c) {
        character        = c;
        weaponController = (c != null)
                ? (WeaponController) c.getNodeOrNull("WeaponController")
                : null;

        if (weaponController != null) {
            weaponController.ammoChanged.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onAmmoChanged"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
        if (c != null) {
            c.changedWeapon.connectUnsafe(
                    MethodCallable.createUnsafe(this, "onWeaponSwitched"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }

        activeSlot = (weaponController != null) ? weaponController.getWeapon() : 0;
        refreshAllSlots();
        setVisible(c != null);
    }

    // ── Signal receivers ──────────────────────────────────────────────────────

    @RegisterFunction
    public void onAmmoChanged(int magazine, int reserve) {
        refreshAllSlots();
    }

    @RegisterFunction
    public void onWeaponSwitched(int slotIndex) {
        activeSlot = slotIndex;
        updateHighlights();
    }

    // ── Slot construction ─────────────────────────────────────────────────────

    private void resolveKeyTexts() {
        // Slot 0 (fist) → weapon_unequip binding
        keyTexts[0] = resolveKeyText("weapon_unequip", "0");
        // Slots 1–6 → weapon_slot_1 through weapon_slot_6 (keys 1–6)
        for (int i = 1; i < SLOT_COUNT; i++) {
            keyTexts[i] = resolveKeyText("weapon_slot_" + i, String.valueOf(i));
        }
    }

    private String resolveKeyText(String action, String fallback) {
        try {
            for (InputEvent ev : InputMap.INSTANCE.actionGetEvents(action)) {
                if (ev instanceof InputEventKey iek) {
                    String text = iek.asTextPhysicalKeycode();
                    return text.isEmpty() ? fallback : text;
                }
            }
        } catch (Exception ignored) {
            // Action not registered yet — happens in editor headless runs.
        }
        return fallback;
    }

    private void buildSlots() {
        slotItems.clear();

        Node slotsNode = getNodeOrNull(slotsPath);
        if (!(slotsNode instanceof VBoxContainer slots)) return;

        PackedScene scene = resolveSlotItemScene();
        if (scene == null) return;

        for (int i = 0; i < SLOT_COUNT; i++) {
            Node instance = scene.instantiate();
            if (!(instance instanceof WeaponSlotItem item)) {
                if (instance != null) instance.queueFree();
                continue;
            }
            slots.addChild(item);
            slotItems.add(item);
        }
    }

    // ── Refresh helpers ───────────────────────────────────────────────────────

    private void refreshAllSlots() {
        if (weaponController == null) return;
        int active = weaponController.getWeapon();
        activeSlot = active;

        for (int i = 0; i < slotItems.size(); i++) {
            WeaponItem weapon = weaponController.getWeaponItem(i);
            slotItems.get(i).update(weapon, i == active, keyTexts[i]);
        }
    }

    private void updateHighlights() {
        if (weaponController == null) return;
        for (int i = 0; i < slotItems.size(); i++) {
            WeaponItem weapon = weaponController.getWeaponItem(i);
            slotItems.get(i).update(weapon, i == activeSlot, keyTexts[i]);
        }
    }

    private PackedScene resolveSlotItemScene() {
        if (slotItemScene != null) return slotItemScene;
        godot.api.Object loaded = GD.load(SLOT_ITEM_SCENE_PATH);
        return (loaded instanceof PackedScene ps) ? ps : null;
    }
}
