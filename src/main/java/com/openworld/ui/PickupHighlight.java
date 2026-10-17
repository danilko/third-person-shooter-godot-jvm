package com.openworld.ui;

import com.openworld.control.Interactions;
import com.openworld.item.Pickup;
import com.openworld.weapon.WeaponItem;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Camera3D;
import godot.api.GeometryInstance3D;
import godot.api.Material;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Makes a weapon lying in the world FINDABLE (user, 2026-10-16: "drop weapon fall ground or barely able to see"). Two
 * layers, after GTA IV / V and Left 4 Dead, local to this peer and never replicated (cosmetic):
 * <ul>
 *   <li><b>GLINT</b> -- every weapon lying within {@link #GLINT_RANGE} of the camera wears
 *       {@code assets/vfx/outline/pickup_glint.tres} as its material_overlay: a periodic sweep of light, staggered per
 *       item, fading out by 26 m in the shader. Additive: between sweeps it adds nothing.</li>
 *   <li><b>FOCUS</b> -- the one the interact key would take now ({@link Interactions#newestOffer}, i.e. what the
 *       "[E] Pick up" prompt names) wears the L4D rim instead ({@code pickup_focus.tres}, the target outline's
 *       inverted hull in warm white), so with three guns at your feet you see which one E grabs.</li>
 * </ul>
 * No through-wall glow and nothing floats: a dropped weapon is a physics object other players see and fight over.
 *
 * <p>Cost: one overlay draw per mesh of each weapon in range -- a few to a few dozen. The scan of the {@code pickups}
 * group runs every {@link #SCAN_SECONDS}; a highlighted item that is picked up loses its overlay on the very next frame
 * (the per-frame pass over the highlighted ones), so a gun never glints in a hand. Only the item's {@code Model} is
 * dressed: the muzzle-flash Glow quad under {@code Muzzle} is a visible mesh too. A child of GameManager (built in
 * code, like the WorldJanitor), so every scene with a camera has it.
 */
@Script(className = "PickupHighlight")
public class PickupHighlight extends Node {

    public static final String GLINT = "res://assets/vfx/outline/pickup_glint.tres";
    public static final String FOCUS = "res://assets/vfx/outline/pickup_focus.tres";
    /** m from the camera; the shader's own fade ends at 26 m. */
    public static final double GLINT_RANGE = 26.0;
    static final double SCAN_SECONDS = 0.15;
    private static final StringName PICKUPS = new StringName(Pickup.PICKUPS_GROUP);

    private enum Look { GLINT, FOCUS }

    private static final class Dressed {
        final Pickup item;
        final List<GeometryInstance3D> meshes = new ArrayList<>();
        Look look;
        Dressed(Pickup item) { this.item = item; }
    }

    private final Map<Long, Dressed> dressed = new HashMap<>();
    private Material glint, focus;
    private double untilScan;
    /** False turns it all off (console `glint 0`). */
    private boolean enabled = true;

    @Register
    @Override
    public void _process(double delta) {
        // every frame: drop any dressed item that is no longer lying in the world (picked up, freed, hidden)
        for (Iterator<Dressed> it = dressed.values().iterator(); it.hasNext(); ) {
            Dressed d = it.next();
            if (!lying(d.item)) { undress(d); it.remove(); }
        }
        untilScan -= delta;
        if (untilScan > 0) return;
        untilScan = SCAN_SECONDS;
        scan();
    }

    private void scan() {
        Camera3D cam = getViewport() == null ? null : getViewport().getCamera3d();
        if (!enabled || cam == null || getTree() == null) { clearAll(); return; }
        if (glint == null) {
            glint = GD.INSTANCE.load(GLINT) instanceof Material m ? m : null;
            focus = GD.INSTANCE.load(FOCUS) instanceof Material m ? m : null;
            if (glint == null || focus == null) return;
        }
        Vector3 eye = cam.getGlobalPosition();
        Node offer = Interactions.newestOffer();
        double r2 = GLINT_RANGE * GLINT_RANGE;
        Map<Long, Look> want = new HashMap<>();
        for (Node n : getTree().getNodesInGroup(PICKUPS)) {
            if (!(n instanceof WeaponItem w) || !lying(w)) continue;
            boolean focused = w.equals(offer);
            if (!focused && w.getGlobalPosition().distanceSquaredTo(eye) > r2) continue;
            want.put(w.getInstanceId(), focused ? Look.FOCUS : Look.GLINT);
            Dressed d = dressed.get(w.getInstanceId());
            Look look = focused ? Look.FOCUS : Look.GLINT;
            if (d == null) {
                d = new Dressed(w);
                collectModel(w, d.meshes);
                dressed.put(w.getInstanceId(), d);
            }
            if (d.look != look) {
                d.look = look;
                Material m = look == Look.FOCUS ? focus : glint;
                for (GeometryInstance3D g : d.meshes) if (GD.isInstanceValid(g)) g.setMaterialOverlay(m);
            }
        }
        for (Iterator<Map.Entry<Long, Dressed>> it = dressed.entrySet().iterator(); it.hasNext(); ) {
            Map.Entry<Long, Dressed> e = it.next();
            if (!want.containsKey(e.getKey())) { undress(e.getValue()); it.remove(); }
        }
    }

    /** A weapon lying in the world: in its PickupBody, in the tree, shown. */
    private static boolean lying(Pickup p) {
        return GD.isInstanceValid(p) && p.isInsideTree() && p.worldBody() != null && p.isVisibleInTree();
    }

    private static void undress(Dressed d) {
        for (GeometryInstance3D g : d.meshes) if (GD.isInstanceValid(g)) g.setMaterialOverlay(null);
        d.meshes.clear();
    }

    private void clearAll() {
        for (Dressed d : dressed.values()) undress(d);
        dressed.clear();
    }

    /** The item's visible model meshes: its {@code Model} child if it has one, never the Muzzle's flash quad. */
    private static void collectModel(Node3D item, List<GeometryInstance3D> out) {
        Node model = item.getNodeOrNull("Model");
        collect(model != null ? model : item, out);
    }

    private static void collect(Node n, List<GeometryInstance3D> out) {
        for (Node ch : n.getChildren(false)) {
            String name = ch.getName().toString();
            if ("MuzzleVFX".equals(name) || "Muzzle".equals(name)) continue;
            if (ch instanceof MeshInstance3D mi && mi.isVisibleInTree()) out.add(mi);
            collect(ch, out);
        }
    }

    @Register
    @Override
    public void _exitTree() { clearAll(); }

    // ── console / probe surface ──

    @Register public void setEnabledNow(boolean on) { enabled = on; if (!on) clearAll(); untilScan = 0; }
    @Register public boolean isEnabledNow() { return enabled; }
    /** "GLINT", "FOCUS" or "" for {@code item} as of the last scan. */
    @Register public String lookOf(Node item) {
        Dressed d = item == null ? null : dressed.get(item.getInstanceId());
        return d == null || d.look == null ? "" : d.look.name();
    }
    @Register public int dressedCount() { return dressed.size(); }
    @Register public void scanNow() { untilScan = 0; scan(); }
}
