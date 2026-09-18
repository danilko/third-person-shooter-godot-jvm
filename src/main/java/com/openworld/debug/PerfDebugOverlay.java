package com.openworld.debug;

import com.openworld.character.Character;
import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.game.PlayerRegistry;
import com.openworld.net.NetworkManager;
import com.openworld.weapon.WeaponController;
import com.openworld.weapon.WeaponItem;
import com.openworld.world.ZoneManager;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CanvasLayer;
import godot.api.Control;
import godot.api.Label;
import godot.api.Node;
import godot.api.Performance;
import godot.api.RayCast3D;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Vector2;
import godot.core.Vector3;
import godot.global.GD;

/**
 * The debug HUD (Shift+F3 via {@code DebugHarness} cycles it, the console's {@code hud 0-3} sets it). Levelled the
 * way CS's {@code net_graph 1/2/3} is, so the cheap view costs nothing to leave on:
 * <ul>
 *   <li><b>1</b> — FPS and frame time in the top-right corner (the Steam overlay counter).</li>
 *   <li><b>2</b> — the engine performance monitors (FPS, frame/physics time, draw calls, primitives, objects drawn,
 *       video/static memory, object/node/orphan counts) plus the JVM heap (all game logic lives there; the engine's
 *       MEMORY_STATIC never sees it), {@link ZoneManager#debugStatsLine} (streaming is this project's dominant perf
 *       variable), and a {@link FrameTimeGraph} with avg / 1%-low / max over the last 240 frames.</li>
 *   <li><b>3</b> — adds what the game is doing right now for the local player (the {@code cl_showpos} idea):
 *       position, speed, floor, stance, combat/view/scope, health, vehicle; the held weapon, its ammo, state and
 *       spread; what the crosshair ray is on and how far; and {@link NetworkManager#debugNetLine}.</li>
 * </ul>
 * Built in code (the procedural-UI convention of {@code ZoneDebugOverlay}, which it stacks under at y=40).
 *
 * <p>The orphan-node count doubles as a live leak check: repeated zone hot-reloads (Shift+F5) with a climbing
 * orphan count = a staged-children/pool leak regression.
 */
@Script(className = "PerfDebugOverlay")
public class PerfDebugOverlay extends CanvasLayer {

    public static final int LEVELS = 4;          // 0 off, 1 fps, 2 perf, 3 perf + game

    private Label corner;
    private Label panel;
    private FrameTimeGraph graph;
    private int level = 2;
    private double refreshTimer = 0.0;
    private static final double REFRESH_INTERVAL = 0.25;
    private static final double MIB = 1024.0 * 1024.0;

    @Register
    @Override
    public void _ready() {
        setLayer(100);
        corner = label();
        corner.setAnchorsPreset(Control.LayoutPreset.PRESET_TOP_RIGHT);
        corner.setHorizontalAlignment(godot.core.HorizontalAlignment.RIGHT);
        corner.setPosition(new Vector2(-236, 8));
        corner.setSize(new Vector2(220, 24));
        panel = label();
        panel.setPosition(new Vector2(16, 40));
        graph = new FrameTimeGraph();
        graph.setMouseFilter(Control.MouseFilter.IGNORE);
        graph.setSize(new Vector2(360, 60));
        addChild(graph);
        applyLevel();
    }

    private Label label() {
        Label l = new Label();
        l.addThemeColorOverride(new StringName("font_color"), new Color(1.0, 1.0, 1.0, 0.9));
        l.addThemeColorOverride(new StringName("font_shadow_color"), new Color(0.0, 0.0, 0.0, 0.9));
        l.addThemeConstantOverride(new StringName("shadow_offset_x"), 1);
        l.addThemeConstantOverride(new StringName("shadow_offset_y"), 1);
        l.setMouseFilter(Control.MouseFilter.IGNORE);
        addChild(l);
        return l;
    }

    /** 0 off, 1 corner FPS, 2 perf panel + graph, 3 + game state. */
    @Register
    public void setLevel(int l) {
        level = Math.floorMod(l, LEVELS);
        if (corner != null) applyLevel();
    }

    @Register
    public int levelNow() { return level; }

    /** The next level, wrapping to off (Shift+F3). */
    public void cycle() { setLevel(level + 1); }

    private void applyLevel() {
        setVisible(level > 0);
        corner.setVisible(level == 1);
        panel.setVisible(level >= 2);
        graph.setVisible(level >= 2);
        refreshTimer = 0.0;
    }

    @Register
    @Override
    public void _process(double delta) {
        if (level == 0) return;
        refreshTimer -= delta;
        if (refreshTimer > 0.0) return;
        refreshTimer = REFRESH_INTERVAL;
        if (level == 1) {
            corner.setText(String.format("FPS %.0f  %.1f ms", Performance.getMonitor(Performance.Monitor.TIME_FPS),
                    Performance.getMonitor(Performance.Monitor.TIME_PROCESS) * 1000.0));
            return;
        }
        String text = perfText() + (level >= 3 ? System.lineSeparator() + gameText() : "");
        panel.setText(text);
        // the graph sits under the text, wherever the text ends
        graph.setPosition(new Vector2(16, 40 + panel.getMinimumSize().getY() + 6));
    }

    @Register
    public String textNow() { return level <= 1 ? corner.getText() : panel.getText(); }

    private String perfText() {
        double fps = Performance.getMonitor(Performance.Monitor.TIME_FPS);
        double frameMs = Performance.getMonitor(Performance.Monitor.TIME_PROCESS) * 1000.0;
        double physMs = Performance.getMonitor(Performance.Monitor.TIME_PHYSICS_PROCESS) * 1000.0;
        double drawCalls = Performance.getMonitor(Performance.Monitor.RENDER_TOTAL_DRAW_CALLS_IN_FRAME);
        double prims = Performance.getMonitor(Performance.Monitor.RENDER_TOTAL_PRIMITIVES_IN_FRAME);
        double objsDrawn = Performance.getMonitor(Performance.Monitor.RENDER_TOTAL_OBJECTS_IN_FRAME);
        double vram = Performance.getMonitor(Performance.Monitor.RENDER_VIDEO_MEM_USED) / MIB;
        double memStatic = Performance.getMonitor(Performance.Monitor.MEMORY_STATIC) / MIB;
        double memStaticMax = Performance.getMonitor(Performance.Monitor.MEMORY_STATIC_MAX) / MIB;
        double objCount = Performance.getMonitor(Performance.Monitor.OBJECT_COUNT);
        double nodeCount = Performance.getMonitor(Performance.Monitor.OBJECT_NODE_COUNT);
        double orphanCount = Performance.getMonitor(Performance.Monitor.OBJECT_ORPHAN_NODE_COUNT);
        Runtime rt = Runtime.getRuntime();
        double jvmUsed = (rt.totalMemory() - rt.freeMemory()) / MIB;
        double jvmMax = rt.maxMemory() / MIB;
        double[] ft = graph.stats();

        StringBuilder sb = new StringBuilder(256);
        sb.append(String.format("FPS %.0f   frame %.1fms  phys %.1fms   avg %.1f  1%%low %.1f  max %.1f ms%n",
                fps, frameMs, physMs, ft[0], ft[1], ft[2]));
        sb.append(String.format("draw %s  prim %s  objs %s   vram %.0f MiB%n",
                compact(drawCalls), compact(prims), compact(objsDrawn), vram));
        sb.append(String.format("mem %.0f/%.0f MiB  jvm %.0f/%.0f MiB%n",
                memStatic, memStaticMax, jvmUsed, jvmMax));
        sb.append(String.format("obj %s  nodes %s  orphans %.0f",
                compact(objCount), compact(nodeCount), orphanCount));
        ZoneManager mgr = ZoneManager.get();
        if (mgr != null) sb.append(System.lineSeparator()).append(mgr.debugStatsLine());
        return sb.toString();
    }

    private String gameText() {
        StringBuilder sb = new StringBuilder(256);
        Player p = null;
        for (Player c : PlayerRegistry.getPlayers()) {
            if (GD.isInstanceValid(c) && c.isLocallyOwnedPlayer()) { p = c; break; }
        }
        if (p == null) {
            sb.append("player: none");
        } else {
            Vector3 pos = p.getGlobalPosition();
            Vector3 v = p.getVelocity();
            double hs = Math.hypot(v.getX(), v.getZ());
            String stance = com.openworld.movement.character.StanceName.values()[p.getStanceOrdinal()].name();
            float hp = p.getNodeOrNull("Health") instanceof Health h ? h.healthNow() : Float.NaN;
            sb.append(String.format("pos %.1f %.1f %.1f   speed %.1f m/s (v %.1f)  %s%n",
                    pos.getX(), pos.getY(), pos.getZ(), hs, v.getY(), p.isOnFloor() ? "floor" : "air"));
            sb.append(String.format("stance %s  %s  %s%s   hp %.0f%s%n", stance, p.isCombat() ? "combat" : "relaxed",
                    p.isFirstPersonView() ? "FPS" : "TPS", p.isScoped() ? " scoped" : "", hp,
                    p.currentVehicleNode != null ? "   in " + p.currentVehicleNode.getName() : ""));
            WeaponController wc = p.weaponController;
            WeaponItem w = wc != null ? wc.getCurrentWeaponItem() : null;
            if (w != null) {
                sb.append(String.format("weapon %s  %d/%d  %s  spread %.2f deg%n", w.weaponId, w.magazine, w.reserve,
                        wc.weaponStateNow(), wc.getCurrentSpreadDeg()));
            }
            RayCast3D ray = wc != null ? wc.getAimRay() : null;
            if (ray != null && ray.isColliding() && ray.getCollider() instanceof Node hit) {
                double d = ray.getCollisionPoint().distanceTo(ray.getGlobalPosition());
                Node owner = hit;
                while (owner != null && !(owner instanceof Character) && owner.getNodeOrNull("Health") == null) owner = owner.getParent();
                sb.append(String.format("aim %s  %.1f m%s", hit.getName(), d,
                        owner != null && owner != hit ? "  (" + owner.getName() + ")" : ""));
            } else {
                sb.append("aim: nothing");
            }
        }
        if (getNodeOrNull("/root/NetworkManager") instanceof NetworkManager net) {
            sb.append(System.lineSeparator()).append(net.debugNetLine());
        }
        return sb.toString();
    }

    /** 12345 → "12.3k", 2100000 → "2.1M" — keeps the panel narrow at open-world counts. */
    private static String compact(double v) {
        if (v >= 1_000_000) return String.format("%.1fM", v / 1_000_000.0);
        if (v >= 10_000) return String.format("%.1fk", v / 1_000.0);
        return String.format("%.0f", v);
    }
}
