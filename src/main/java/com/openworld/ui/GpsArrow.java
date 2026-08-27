package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.character.Player;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Camera3D;
import godot.api.Control;
import godot.core.Basis;
import godot.core.Color;
import godot.core.PackedVector2Array;
import godot.core.Vector2;
import godot.core.Vector3;

/**
 * World-space GPS direction arrow (PLAN.md I5): while the local player has a waypoint, a small arrow
 * orbits the crosshair pointing toward it — top = straight ahead, sides = left/right, bottom = behind —
 * so you can navigate without watching the minimap. Reuses {@link DamageIndicator}'s camera-relative
 * bearing (off the viewport's current camera, so it's correct on foot and in a vehicle). Hidden when no
 * waypoint or when the target is within {@link #arriveMeters}. Pure display; drawn procedurally (no
 * texture asset). Wired by {@code HUDManager.wirePlayer}.
 */
@Script(className = "GpsArrow")
public class GpsArrow extends Control {

    /** Distance (px) from the crosshair the arrow sits. */
    @Export public float radius = 70f;
    /** Arrow size in px. */
    @Export public float arrowSize = 14f;
    /** Hide the arrow when within this many metres of the waypoint (you've arrived). */
    @Export public float arriveMeters = 4f;

    private Player player;

    public void wirePlayer(Player p) { player = p; }

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
    }

    @Register
    @Override
    public void _process(double delta) {
        queueRedraw();
    }

    @Register
    @Override
    public void _draw() {
        if (player == null || !godot.global.GD.isInstanceValid(player)) return;
        Vector3 wp = player.getWaypoint();
        if (wp == null) return;
        Camera3D cam = getViewport() != null ? getViewport().getCamera3d() : null;
        if (cam == null) return;

        Vector3 d = wp.minus(cam.getGlobalPosition());
        d = new Vector3((float) d.getX(), 0f, (float) d.getZ());
        float planarLen = (float) Math.sqrt(d.getX() * d.getX() + d.getZ() * d.getZ());
        if (planarLen < arriveMeters) return;   // arrived — hide

        Basis b = cam.getGlobalBasis();
        Vector3 fwd = b.getZ().times(-1f);
        Vector3 right = b.getX();
        double fdot = d.getX() * fwd.getX() + d.getZ() * fwd.getZ();
        double rdot = d.getX() * right.getX() + d.getZ() * right.getZ();
        double bearing = Math.atan2(rdot, fdot);   // 0 = ahead (up), +pi/2 = right, ±pi = behind
        if (Double.isNaN(bearing)) return;

        Vector2 center = getSize().times(0.5f);
        // Screen direction for this bearing: up is (0,-1); rotate clockwise by `bearing`.
        float dirx = (float) Math.sin(bearing);
        float diry = (float) -Math.cos(bearing);
        Vector2 tipCenter = new Vector2((float) center.getX() + dirx * radius,
                                        (float) center.getY() + diry * radius);
        Vector2 dir = new Vector2(dirx, diry);
        Vector2 perp = new Vector2(-diry, dirx);

        float s = arrowSize;
        Vector2 tip  = add(tipCenter, mul(dir, s * 0.6f));
        Vector2 bl   = add(sub(tipCenter, mul(dir, s * 0.4f)), mul(perp, s * 0.5f));
        Vector2 br   = sub(sub(tipCenter, mul(dir, s * 0.4f)), mul(perp, s * 0.5f));
        PackedVector2Array tri = new PackedVector2Array();
        tri.pushBack(tip); tri.pushBack(bl); tri.pushBack(br);

        drawColoredPolygon(tri, player.getNameplateColor(), new PackedVector2Array(), null);
    }

    private static Vector2 add(Vector2 a, Vector2 b) { return new Vector2((float) (a.getX() + b.getX()), (float) (a.getY() + b.getY())); }
    private static Vector2 sub(Vector2 a, Vector2 b) { return new Vector2((float) (a.getX() - b.getX()), (float) (a.getY() - b.getY())); }
    private static Vector2 mul(Vector2 a, float s)   { return new Vector2((float) a.getX() * s, (float) a.getY() * s); }
}
