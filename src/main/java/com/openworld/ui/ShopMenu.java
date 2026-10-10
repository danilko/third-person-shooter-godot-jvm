package com.openworld.ui;

import com.openworld.character.Player;
import com.openworld.item.ShopCounter;
import com.openworld.item.WeaponGrant;
import com.openworld.weapon.WeaponCatalog;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CanvasLayer;
import godot.api.Control;
import godot.api.Font;
import godot.api.Input;
import godot.api.InputEvent;
import godot.api.InputEventMouseButton;
import godot.api.InputEventMouseMotion;
import godot.api.StyleBox;
import godot.api.Texture2D;
import godot.core.Color;
import godot.core.HorizontalAlignment;
import godot.core.Rect2;
import godot.core.Vector2;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * The shop counter's menu (PLAN.md W3; GTA SA's Ammu-Nation list): one row per item -- icon, name, and FREE (money
 * does not exist yet) or REFILL for a weapon already carried. Up/down or the mouse choose, {@code ui_accept} (Enter)
 * or a click takes the row; {@code interact} (E, the key that opened it) or {@code ui_cancel} (Esc) closes it, and so
 * does walking away from the counter (user, 2026-10-05: E must close what E opened, and Esc must not go on to open the
 * pause menu -- {@link MenuManager} hands Esc here first). While it is open the player's input is blocked and the
 * mouse is free (the debug console's rule).
 *
 * <p>One menu at a time, built in code on the scene's root and freed on close.
 */
@Script(className = "ShopMenu")
public class ShopMenu extends Control {

    static final String PANEL = "res://src/main/resources/com/openworld/ui/menu_panel.tres";
    static final String FONT = "res://assets/ui/Aldrich-Regular.ttf";
    static final String ICONS = "res://assets/ui/weapons/";
    public static final float W = 460f, ROW = 54f, HEAD = 56f, FOOT = 44f;

    private static ShopMenu open;
    private static CanvasLayer layer;
    /** The frame the menu opened / closed on: the E that opens it must not close it, nor the E that closes it reopen it. */
    private static long openedFrame = -1, closedFrame = -1;

    private ShopCounter counter;
    private Player buyer;
    private final List<String> ids = new ArrayList<>();
    private final List<String> names = new ArrayList<>();
    private final List<Texture2D> icons = new ArrayList<>();
    private int selected;
    private int bought;
    private StyleBox panel;
    private Font font;

    public static boolean isOpen() { return open != null && GD.isInstanceValid(open); }

    public static ShopMenu current() { return isOpen() ? open : null; }

    public static void open(ShopCounter counter, Player buyer) {
        if (isOpen() || counter.getTree() == null) return;
        layer = new CanvasLayer();
        layer.setLayer(60);
        ShopMenu m = new ShopMenu();
        m.counter = counter;
        m.buyer = buyer;
        layer.addChild(m);
        counter.getTree().getRoot().addChild(layer);
        open = m;
        com.openworld.audio.Sounds.ui(counter, com.openworld.audio.Sound.UI_CLICK);
        openedFrame = godot.api.Engine.INSTANCE.getProcessFrames();
    }

    /** The menu was closed by E and E has not been let go since. */
    private static boolean closedByInteract;

    /**
     * The key that just closed the menu must not reopen it. E opens the counter from the PHYSICS step
     * (control.Interactions) and closes it from this _process, so one press is "just pressed" in both. This used to be
     * one PROCESS frame of slack, which only covers a press when there is one process frame per physics step: above
     * 60 fps (a 144 Hz display, or an uncapped headless run) the next physics step came 2+ frames later and the same
     * press reopened the store -- E could not close it (probe_weapon_counter, found 2026-10-10). Now: refused for a
     * frame after any close, and after an E close until E is RELEASED, whatever the frame rate.
     */
    public static boolean closedThisFrame() {
        if (godot.api.Engine.INSTANCE.getProcessFrames() - closedFrame <= 1) return true;
        if (closedByInteract && Input.INSTANCE.isActionPressed("interact", false)) return true;
        closedByInteract = false;
        return false;
    }

    public static void closeFor(ShopCounter counter) {
        if (isOpen() && open.counter == counter) open.close();
    }

    @Register
    @Override
    public void _ready() {
        if (GD.load(PANEL) instanceof StyleBox sb) panel = sb;
        if (GD.load(FONT) instanceof Font f) font = f;
        for (String id : counter.rows()) {
            if (ShopCounter.TILL.equals(id)) {
                ids.add(id);
                names.add("Empty the till");
                icons.add(null);
                continue;
            }
            if (ShopCounter.DONATION.equals(id)) {
                ids.add(id);
                var g = com.openworld.game.GangSystem.get().gang(counter.clerk().gang());
                names.add("Donation" + (g != null ? " (" + g.name() + ")" : ""));
                icons.add(null);
                continue;
            }
            if (ShopCounter.isSupply(id)) {
                ids.add(id);
                names.add(com.openworld.item.SupplyCatalog.find(id).name());
                icons.add(GD.load(ICONS + "supply_" + com.openworld.item.SupplyCatalog.find(id).kind() + ".png")
                        instanceof Texture2D st ? st : null);
                continue;
            }
            WeaponItem w = WeaponCatalog.instantiate(id);
            String name = id;
            if (w != null) {
                if (w.weaponName != null && !w.weaponName.isEmpty()) name = w.weaponName;
                w.free();
            }
            ids.add(id);
            names.add(name);
            icons.add(GD.load(ICONS + id + ".png") instanceof Texture2D t ? t : null);
        }
        float h = HEAD + ROW * ids.size() + FOOT;
        setAnchor(godot.core.Side.LEFT, 0f, false, true);
        setAnchor(godot.core.Side.TOP, 0.5f, false, true);
        setAnchor(godot.core.Side.BOTTOM, 0.5f, false, true);
        setOffset(godot.core.Side.LEFT, 40f);
        setOffset(godot.core.Side.RIGHT, 40f + W);
        setOffset(godot.core.Side.TOP, -h * 0.5f);
        setOffset(godot.core.Side.BOTTOM, h * 0.5f);
        block(true);
    }

    private void block(boolean on) {
        if (buyer != null && GD.isInstanceValid(buyer)) buyer.inputContexts.set("shop", com.openworld.control.InputContext.MENU, on);
    }

    public void close() {
        closedFrame = godot.api.Engine.INSTANCE.getProcessFrames();
        if (open == this) com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        block(false);
        if (open == this) open = null;
        if (layer != null && GD.isInstanceValid(layer)) layer.queueFree();
        layer = null;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (ids.isEmpty()) { close(); return; }
        Input in = Input.INSTANCE;
        if (in.isActionJustPressed("ui_cancel", false)) { close(); return; }
        if (in.isActionJustPressed("interact", false)
                && godot.api.Engine.INSTANCE.getProcessFrames() != openedFrame) { closedByInteract = true; close(); return; }
        if (in.isActionJustPressed("ui_down", false) || in.isActionJustPressed("back", false)) move(1);
        if (in.isActionJustPressed("ui_up", false) || in.isActionJustPressed("forward", false)) move(-1);
        if (in.isActionJustPressed("ui_accept", false)) buySelected();
    }

    private void move(int d) {
        selected = Math.floorMod(selected + d, ids.size());
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK);
        queueRedraw();
    }

    private void buySelected() {
        counter.buy(buyer, ids.get(selected));
        com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CONFIRM);
        bought++;
        queueRedraw();
    }

    @Register
    @Override
    public void _guiInput(InputEvent e) {
        int row = -1;
        if (e instanceof InputEventMouseMotion mm) row = rowAt(mm.getPosition());
        else if (e instanceof InputEventMouseButton mb) row = rowAt(mb.getPosition());
        if (row >= 0 && row != selected) { selected = row; com.openworld.audio.Sounds.ui(this, com.openworld.audio.Sound.UI_CLICK); queueRedraw(); }
        if (row >= 0 && e instanceof InputEventMouseButton mb && mb.isPressed()
                && mb.getButtonIndex() == godot.core.MouseButton.LEFT) buySelected();
    }

    private int rowAt(Vector2 p) {
        int r = (int) Math.floor((p.getY() - HEAD) / ROW);
        return r >= 0 && r < ids.size() ? r : -1;
    }

    @Register
    @Override
    public void _draw() {
        float h = HEAD + ROW * ids.size() + FOOT;
        if (panel != null) drawStyleBox(panel, new Rect2(0.0, 0.0, W, h));
        if (font == null) return;
        var clerk = counter.clerk();
        boolean robbing = clerk != null && (clerk.robbable() || ids.contains(ShopCounter.TILL));
        drawString(font, new Vector2(20f, 38f), robbing ? counter.title + "  (ROBBERY)" : counter.title,
                HorizontalAlignment.LEFT, -1f, 26, robbing ? new Color(1f, 0.45f, 0.35f, 1f) : new Color(1f, 1f, 1f, 1f));
        if (buyer != null) drawString(font, new Vector2(W - 140f, 38f), "¥" + buyer.cash, HorizontalAlignment.RIGHT, 120f,
                18, new Color(1f, 0.9f, 0.5f, 1f));
        for (int i = 0; i < ids.size(); i++) {
            float y = HEAD + ROW * i;
            if (i == selected) drawRect(new Rect2(8.0, y + 2.0, W - 16.0, ROW - 4.0), new Color(1f, 1f, 1f, 0.16f));
            Texture2D t = icons.get(i);
            if (t != null) drawTextureRect(t, new Rect2(18.0, y + 9.0, 108.0, 36.0), false);
            else if (ShopCounter.isSupply(ids.get(i))) badge(com.openworld.item.SupplyCatalog.find(ids.get(i)).kind(), y);
            drawString(font, new Vector2(140f, y + 34f), names.get(i), HorizontalAlignment.LEFT, -1f, 20,
                    new Color(1f, 1f, 1f, i == selected ? 1f : 0.75f));
            String tag;
            boolean has;
            if (ShopCounter.TILL.equals(ids.get(i))) {
                var c = counter.clerk();
                has = c == null || !c.robbable();
                tag = has ? "EMPTY" : "¥" + (c != null ? c.till : 0);
            } else if (ShopCounter.DONATION.equals(ids.get(i))) {
                var gs = com.openworld.game.GangSystem.get();
                var c = counter.clerk();
                int fee = gs != null && c != null && buyer.getCharacterInfo() != null
                        ? gs.feeOf(buyer.getCharacterInfo().characterId, c.gang()) : 0;
                has = fee == 0 || buyer.cash < fee;
                tag = fee == 0 ? "NOTHING OWED" : (buyer.cash < fee ? "SHORT " : "") + "¥" + fee;
            } else if (ShopCounter.isSupply(ids.get(i))) {
                int n = buyer.supplyCountNow(ids.get(i));
                int max = com.openworld.item.SupplyCatalog.find(ids.get(i)).max();
                has = n >= max;
                tag = has ? "FULL" : "FREE  " + n + "/" + max;
            } else {
                has = WeaponGrant.carries(buyer, ids.get(i));
                tag = has ? "REFILL" : "FREE";
            }
            drawString(font, new Vector2(W - 140f, y + 34f), tag, HorizontalAlignment.RIGHT, 120f,
                    18, has ? new Color(0.55f, 0.85f, 1f, 1f) : new Color(0.55f, 1f, 0.55f, 1f));
        }
        footer(h);
    }

    private void footer(float h) {
        if (font == null) return;
        drawString(font, new Vector2(20f, h - 16f), "ENTER / CLICK  take     E / ESC  close",
                HorizontalAlignment.LEFT, W - 40f, 14, new Color(1f, 1f, 1f, 0.7f));
    }

    /** A supply has no weapon icon: a coloured badge by kind (food, medical cross, strange). */
    private void badge(String kind, float y) {
        Color c = switch (kind) {
            case "medical" -> new Color(0.9f, 0.2f, 0.2f, 1f);
            case "strange" -> new Color(0.7f, 0.35f, 0.95f, 1f);
            default -> new Color(1f, 0.78f, 0.25f, 1f);
        };
        drawRect(new Rect2(54.0, y + 9.0, 36.0, 36.0), c);
        if ("medical".equals(kind)) {
            drawRect(new Rect2(68.0, y + 14.0, 8.0, 26.0), new Color(1f, 1f, 1f, 1f));
            drawRect(new Rect2(59.0, y + 23.0, 26.0, 8.0), new Color(1f, 1f, 1f, 1f));
        } else if (font != null) {
            drawString(font, new Vector2(54f, y + 35f), "strange".equals(kind) ? "?" : "F",
                    HorizontalAlignment.CENTER, 36f, 22, new Color(0f, 0f, 0f, 0.8f));
        }
    }

    // ── probe surface ──
    @Register public int rowsNow() { return ids.size(); }
    @Register public int selectedNow() { return selected; }
    @Register public void selectNow(int i) { if (i >= 0 && i < ids.size()) { selected = i; queueRedraw(); } }
    @Register public void buyNow() { buySelected(); }
    @Register public int boughtNow() { return bought; }
}
