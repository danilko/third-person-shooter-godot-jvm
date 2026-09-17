package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.movement.character.MovementType;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.NodePath;
import godot.global.GD;
import godot.core.Vector3;
import java.util.ArrayList;
import java.util.List;

/**
 * Radial weapon-selection overlay — a WHEEL OF UPRIGHT CARDS (2026-09-16).
 *
 * One card (WeaponRadialCard.tscn) per weapon slot is placed on an ellipse around the centre, slot 0 at the top,
 * clockwise. The cards used to be textured pie wedges rotated into place, with hover detected by per-wedge click
 * masks; a slot's content (a 3:1 icon, its name, ammo, key) is rectangular, so wedges squeezed it toward the
 * centre and left dead spots between masks. Selection is now by the pointer's ANGLE from the centre past
 * {@link #deadZone} — the weapon-wheel convention — so it does not depend on the drawn shapes at all.
 *
 * References (character, weaponController, camera) are injected by HUDManager
 * via wireCharacter(). The menu is context-agnostic — robot, powered armour, or
 * player on foot all work without scene changes.
 */
@Script(className = "WeaponRadialMenu")
public class WeaponRadialMenu extends Control {

  @Export public Character character;

  /** Path to the container the cards are placed in (centred on screen; the Zoom animation scales it). */
  @Export
  public NodePath circleContainerPath = new NodePath("Panel/Circle");

  /** Scene used to instantiate each slot card: WeaponRadialCard.tscn (script WeaponRadialMenuItem). */
  @Export
  public PackedScene weaponItemTemplate;

  /**
   * The ellipse the card CENTRES sit on, canvas units. Wider than tall because the cards are: at 8 slots with
   * 150x84 cards, 260x180 keeps every neighbour pair clear horizontally or vertically.
   */
  @Export public float ringRadiusX = 260f;
  @Export public float ringRadiusY = 180f;

  /** Pointer distance from the centre below which the selection does not change, canvas units. */
  @Export public float deadZone = 48f;

  public float getRingRadiusX() { return ringRadiusX; }
  public void setRingRadiusX(float v) { ringRadiusX = v; }
  public float getRingRadiusY() { return ringRadiusY; }
  public void setRingRadiusY(float v) { ringRadiusY = v; }
  public float getDeadZone() { return deadZone; }
  public void setDeadZone(float v) { deadZone = v; }

  private final List<WeaponRadialMenuItem> cards = new ArrayList<>();
  private int selected = -1;

  private AnimationPlayer  animationPlayer;

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  /** Set or update the active character; rebuilds items for the new slot layout. */
  public void wireCharacter(Character c) {
    character = c;
    buildItems();
  }

  /** {@link #wireCharacter} for GDScript (a registered parameter must be a Node). */
  @Register
  public void wireCharacterNode(Node c) {
    if (c instanceof Character ch) wireCharacter(ch);
  }

  @Register
  @Override
  public void _ready() {
    animationPlayer = (AnimationPlayer) getNode("AnimationPlayer");
    buildItems();
    hide();
  }

  // ── Input / show / hide ───────────────────────────────────────────────────

  @Register
  @Override
  public void _input(InputEvent event) {
    if (getWeaponController() == null) return;
    if (event.isActionPressed("radialmenu") && !getWeaponController().isWeaponReloading()) {
      showRadialMenu();
    } else if (event.isActionReleased("radialmenu")) {
      hideRadialMenu();
    } else if (isVisible() && event instanceof InputEventMouseMotion mm) {
      selectFromPointer(mm.getPosition());
    } else if (isVisible() && event instanceof InputEventMouseButton mb && mb.isPressed()
        && mb.getButtonIndex() == godot.core.MouseButton.LEFT) {
      selectFromPointer(mb.getPosition());
      hideRadialMenu();
      getViewport().setInputAsHandled();
    }
  }

  /**
   * Pick the slot whose direction the pointer is in: slot 0 straight up, clockwise, each slot owning the
   * 360/N degrees centred on it. Selecting switches to that weapon live (the preview the wedges' hover gave);
   * releasing the key or clicking closes the wheel on it.
   */
  @Register
  public void selectFromPointer(godot.core.Vector2 pointer) {
    int n = cards.size();
    if (n == 0) return;
    godot.core.Vector2 c = menuCentre();
    double dx = pointer.getX() - c.getX(), dy = pointer.getY() - c.getY();
    if (Math.hypot(dx, dy) < deadZone) return;
    double angle = Math.atan2(dx, -dy);                    // 0 = up, clockwise (canvas y points down)
    int idx = Math.floorMod((int) Math.round(angle / (Math.PI * 2.0 / n)), n);
    select(idx, true);
  }

  /** The currently highlighted slot, -1 if none — the on-screen check reads it. */
  @Register
  public int selectedSlot() { return selected; }

  /** Open / close for scripts and checks (the key path calls the same methods). */
  @Register
  public void openMenu() { showRadialMenu(); }

  @Register
  public void closeMenu() { hideRadialMenu(); }

  private void select(int idx, boolean switchWeapon) {
    if (idx == selected) return;
    selected = idx;
    for (WeaponRadialMenuItem card : cards) card.setHighlighted(card.index == idx);
    if (switchWeapon && character != null) character.setWeapon(idx);
  }

  /** Centre of the wheel in canvas coordinates (the Circle container is centred in the full-screen menu). */
  private godot.core.Vector2 menuCentre() {
    godot.core.Rect2 r = getGlobalRect();
    return new godot.core.Vector2(r.getPosition().getX() + r.getSize().getX() * 0.5,
        r.getPosition().getY() + r.getSize().getY() * 0.5);
  }

  public void showRadialMenu() {
    if (character == null) return;
    // Move to front so GUI input hits this menu before any sibling HUD Controls.
    // FootHUD, WeaponSlotsUI etc. default to mouse_filter=STOP and sit in front
    // of the radial menu in the original scene order, blocking all button events.
    Node parent = getParent();
    if (parent != null) parent.moveChild(this, parent.getChildCount() - 1);
    Input.setMouseMode(Input.MouseMode.VISIBLE);
    character.inputBlocked = true;
    character.setMovementDirection(Vector3.Companion.getZERO());
    character.setMovementState(MovementType.IDLE);
    Node cam = getCamera();
    if (cam != null) cam.setProcessInput(false);
    refreshItems();
    selected = -1;
    select(getWeaponController().getWeapon(), false);      // start on the weapon in hand
    show();
    getViewport().warpMouse(menuCentre());                  // neutral: the first flick picks, not the old cursor
    animationPlayer.play("Zoom");
  }

  public void hideRadialMenu() {
    if (character == null) return;
    Input.setMouseMode(Input.MouseMode.CAPTURED);
    character.inputBlocked = false;
    character.setMovementState(MovementType.IDLE);
    Node cam = getCamera();
    if (cam != null) cam.setProcessInput(true);
    hide();
  }

  // ── Dynamic item building ─────────────────────────────────────────────────

  /**
   * Builds one card per slot on the {@link #ringRadiusX} x {@link #ringRadiusY} ellipse, slot 0 at the top,
   * clockwise. Called on _ready() and whenever wireCharacter() provides a new controller.
   */
  public void buildItems() {
    WeaponController wc = getWeaponController();
    if (wc == null || weaponItemTemplate == null) return;

    Node circleNode = getNodeOrNull(circleContainerPath);
    if (!(circleNode instanceof Control circle)) return;

    // Remove existing cards synchronously so the child list is clean before adding new ones
    for (WeaponRadialMenuItem old : new ArrayList<>(cards)) {
      if (GD.isInstanceValid(old)) {
        circle.removeChild(old);
        old.queueFree();
      }
    }
    cards.clear();
    for (int i = circle.getChildCount() - 1; i >= 0; i--) {
      Node child = circle.getChild(i);
      if (child instanceof WeaponRadialMenuItem) { circle.removeChild(child); child.queueFree(); }
    }

    int slotCount = wc.getSlotCount();
    double step = (Math.PI * 2.0) / slotCount;
    double cx = circle.getSize().getX() * 0.5, cy = circle.getSize().getY() * 0.5;
    for (int i = 0; i < slotCount; i++) {
      Node instance = weaponItemTemplate.instantiate();
      if (!(instance instanceof WeaponRadialMenuItem card)) { instance.queueFree(); continue; }
      card.index = i;
      godot.core.Vector2 size = card.getCustomMinimumSize();
      double a = i * step;
      double x = cx + ringRadiusX * Math.sin(a) - size.getX() * 0.5;
      double y = cy - ringRadiusY * Math.cos(a) - size.getY() * 0.5;
      circle.addChild(card);
      card.setPosition(new godot.core.Vector2(x, y));
      cards.add(card);
    }
    selected = -1;
  }

  // ── Accessors ─────────────────────────────────────────────────────────────

  public Character getCharacter() { return character; }

  /** Setter half of the exported {@code character} property. */
  public void setCharacter(Character value) {
    this.character = value;
  }

  public int getWeaponCount() {
    WeaponController wc = getWeaponController();
    return wc != null ? wc.getWeaponCount() : 0;
  }

  public WeaponItem getWeaponItem(int idx) {
    WeaponController wc = getWeaponController();
    return wc != null ? wc.getWeaponItem(idx) : null;
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private void refreshItems() {
    WeaponController wc = getWeaponController();
    for (WeaponRadialMenuItem card : cards) card.refresh(wc != null ? wc.getWeaponItem(card.index) : null);
  }

  private WeaponController getWeaponController() {
    return character != null ? character.weaponController : null;
  }

  private Node getCamera() {
    return character != null ? character.getCameraRoot() : null;
  }
}
