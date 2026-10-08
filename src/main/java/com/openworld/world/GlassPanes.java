package com.openworld.world;

import godot.api.Node;
import godot.api.StaticBody3D;
import godot.core.RID;
import godot.core.StringName;
import godot.core.Vector3;

/**
 * Breakable window glass in buildings (PLAN.md 1g g): every pane is a plain body under a {@link PaneSet}. It obeys the
 * CAR's glass rule (carrier.vehicle.VehicleDamageRules, user 2026-10-07: "update the glass behaviour like car"):
 * ordinary glass gives ONE hit of protection -- a light round, a melee blow, a crash or a blast breaks it and stops
 * there -- while a round of at least {@code VehicleDamageRules.PANE_PIERCE_AT} breaks it and carries on at full damage;
 * a broken one lets everything through. The bullet half lives in {@code WeaponItem.throughGlass}, beside the car's.
 */
public final class GlassPanes {

    private GlassPanes() {}

    /** One pane: its set and index. */
    public record Pane(PaneSet set, int index, StaticBody3D body) {
        public boolean broken() { return set.isBroken(index); }

        /** Authority: break it (a client's call does nothing; the host's break replicates). */
        public void hit(Vector3 at) { set.hit(index, at); }

        public RID rid() { return body.getRid(); }
    }

    /** The pane {@code n} is (or is part of), or null. */
    public static Pane paneOf(Node n) {
        for (Node x = n; x != null; x = x.getParent()) {
            if (x instanceof StaticBody3D sb && x.getParent() instanceof PaneSet set) return new Pane(set, x.getIndex(), sb);
            if (x instanceof godot.api.PhysicsBody3D) return null;   // another body: not glass
        }
        return null;
    }

    /** Break every intact pane within {@code radius} of a blast (the authority's ExplosionManager calls it). */
    public static int blast(Node any, Vector3 center, double radius) {
        if (any == null || any.getTree() == null) return 0;
        int n = 0;
        for (Node node : any.getTree().getNodesInGroup(new StringName(PaneSet.GROUP))) {
            if (!(node instanceof PaneSet set)) continue;
            if (set.getGlobalPosition().distanceTo(center) > radius + 400.0) continue;   // cheap reject: a far building
            for (Node c : set.getChildren()) {
                if (!(c instanceof StaticBody3D p) || set.isBroken(c.getIndex())) continue;
                Vector3 at = p.getNodeOrNull("Glass") instanceof godot.api.Node3D g ? g.getGlobalPosition() : p.getGlobalPosition();
                if (at.distanceTo(center) > radius) continue;
                set.hit(c.getIndex(), center);
                n++;
            }
        }
        return n;
    }
}
