package com.openworld.game;

import com.openworld.camera.PlayerCameraController;
import com.openworld.camera.TPSCameraController;
import com.openworld.character.Player;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.AudioServer;
import godot.api.ConfigFile;
import godot.api.DirectionalLight3D;
import godot.api.Node;
import godot.core.StringName;
import godot.global.GD;

/**
 * The player's settings, the ONE owner (PLAN.md 1.3: F2's settings page + H3 "quality settings that cannot change
 * balance"). AutoLoad. Stored in {@code user://settings.cfg}; applied on load, on every change, and to each new scene /
 * new local player (a 1 s check). Only CLIENT-LOCAL knobs live here -- what this machine draws and how its human aims:
 * render scale, sun shadow distance, view distance, look sensitivity, pad look / invert / aim assist, master volume,
 * HUD mode. Nothing a co-op peer could fight over (enforcement, AI, damage, the promoted crowd, simulated traffic) is a
 * setting; those stay host-decided (H3). Two FAIRNESS FLOORS so a low preset is never an advantage or a blind spot:
 * the view distance never drops below {@link #MIN_VIEW_DISTANCE} (the engagement range) and the sun's shadows reach at
 * least {@link #MIN_SHADOW_DISTANCE} (a character's shadow round a corner must not be a high-settings advantage).
 */
@Script(className = "QualitySettings")
public class QualitySettings extends Node {

    public static final String PATH = "user://settings.cfg";
    public static final double MIN_VIEW_DISTANCE = 250.0;
    public static final double MIN_SHADOW_DISTANCE = 80.0;

    public enum Preset { LOW, MEDIUM, HIGH, CUSTOM }

    /** A preset's graphics values: render scale, shadow distance (m), view distance (m). */
    public record Graphics(double renderScale, double shadowDistance, double viewDistance) {}

    public static Graphics graphicsOf(Preset p) {
        return switch (p) {
            case LOW -> new Graphics(0.67, 150.0, 300.0);
            case MEDIUM -> new Graphics(0.85, 300.0, 400.0);
            default -> new Graphics(1.0, 600.0, 500.0);   // HIGH = what the game shipped with before F2
        };
    }

    // ── the values (defaults = HIGH, the shipped look) ──
    public Preset preset = Preset.HIGH;
    public double renderScale = 1.0;
    public double shadowDistance = 600.0;
    public double viewDistance = 500.0;
    public double lookSensitivity = 1.0;     // x the mouse's 0.07 deg / px
    public double padLookScale = 1.0;        // x PlayerCameraController's pad rates
    public boolean invertY = false;
    public boolean aimAssist = true;
    public double masterVolume = 1.0;        // linear 0..1
    public boolean hudMinimal = false;

    private static QualitySettings instance;
    public static QualitySettings get() { return instance; }

    private long appliedScene = -1;
    private long appliedPlayer = -1;
    private double recheck;
    private int applies;

    @Register
    @Override
    public void _ready() {
        instance = this;
        load();
        apply();
    }

    @Register
    @Override
    public void _exitTree() {
        if (instance == this) instance = null;
    }

    /** A new scene or a new local player gets the settings too (1 s check; a world loads its own sun). */
    @Register
    @Override
    public void _process(double delta) {
        if ((recheck -= delta) > 0) return;
        recheck = 1.0;
        Node scene = getTree() != null ? getTree().getCurrentScene() : null;
        long sceneId = scene == null ? -1 : scene.getInstanceId();
        Player me = localPlayer();
        long playerId = me == null ? -1 : me.getInstanceId();
        if (sceneId != appliedScene || playerId != appliedPlayer) apply();
    }

    // ── presets ──

    public void setPreset(Preset p) {
        preset = p;
        if (p != Preset.CUSTOM) {
            Graphics g = graphicsOf(p);
            renderScale = g.renderScale();
            shadowDistance = g.shadowDistance();
            viewDistance = g.viewDistance();
        }
    }

    /** A graphics value moved by hand: the preset becomes CUSTOM unless the values still match one. */
    public void graphicsChanged() {
        preset = Preset.CUSTOM;
        for (Preset p : new Preset[] {Preset.LOW, Preset.MEDIUM, Preset.HIGH}) {
            Graphics g = graphicsOf(p);
            if (Math.abs(g.renderScale() - renderScale) < 1e-3 && Math.abs(g.shadowDistance() - shadowDistance) < 0.5
                    && Math.abs(g.viewDistance() - viewDistance) < 0.5) preset = p;
        }
    }

    // ── apply ──

    /** Push every value to what it drives. Safe to call any time; the floors are enforced here. */
    public void apply() {
        if (getTree() == null) return;
        applies++;
        renderScale = clamp(renderScale, 0.5, 1.0);
        shadowDistance = Math.max(MIN_SHADOW_DISTANCE, shadowDistance);
        viewDistance = Math.max(MIN_VIEW_DISTANCE, viewDistance);
        getTree().getRoot().setScaling3dScale((float) renderScale);
        Node scene = getTree().getCurrentScene();
        appliedScene = scene == null ? -1 : scene.getInstanceId();
        if (scene != null) applyShadows(scene);
        com.openworld.world.ViewDistance vd = com.openworld.world.ViewDistance.get();
        if (vd != null && System.getenv("OW_VIEW_DISTANCE") == null) vd.streetDistance = viewDistance;
        int master = AudioServer.INSTANCE.getBusIndex(new StringName("Master"));
        if (master >= 0) AudioServer.INSTANCE.setBusVolumeDb(master, (float) (20.0 * Math.log10(Math.max(1e-4, masterVolume))));
        Player me = localPlayer();
        appliedPlayer = me == null ? -1 : me.getInstanceId();
        if (me != null) applyLook(me);
    }

    private void applyShadows(Node n) {
        if (n instanceof DirectionalLight3D sun && sun.getName().toString().equals("SunLight"))
            sun.setParam(godot.api.Light3D.Param.SHADOW_MAX_DISTANCE, (float) shadowDistance);
        for (Node c : n.getChildren()) applyShadows(c);
    }

    private void applyLook(Player me) {
        for (Node c : me.getChildren()) {
            if (c instanceof TPSCameraController cam) {
                cam.yawSensitivity = TPS_BASE_SENSITIVITY * lookSensitivity;
                cam.pitchSensitivity = TPS_BASE_SENSITIVITY * lookSensitivity;
            }
            if (c instanceof PlayerCameraController pc) {
                pc.padYawRate = PAD_YAW_BASE * padLookScale;
                pc.padPitchRate = PAD_PITCH_BASE * padLookScale;
                pc.padInvertY = invertY;
                pc.aimAssist = aimAssist;
            }
        }
    }

    /** The shipped defaults the multipliers scale (TPSCameraController 0.07 deg/px, pad 220 / 150 deg/s). */
    public static final double TPS_BASE_SENSITIVITY = 0.07;
    public static final double PAD_YAW_BASE = 220.0;
    public static final double PAD_PITCH_BASE = 150.0;

    private static Player localPlayer() {
        for (Player p : PlayerRegistry.getPlayers())
            if (GD.isInstanceValid(p) && p.isLocalOwnedPlayer()) return p;
        return null;
    }

    // ── file ──

    public void load() {
        ConfigFile cf = new ConfigFile();
        if (cf.load(PATH) != godot.core.Error.OK) return;
        try { preset = Preset.valueOf(String.valueOf(cf.getValue("graphics", "preset", preset.name()))); }
        catch (IllegalArgumentException e) { preset = Preset.HIGH; }
        renderScale = num(cf, "graphics", "render_scale", renderScale);
        shadowDistance = num(cf, "graphics", "shadow_distance", shadowDistance);
        viewDistance = num(cf, "graphics", "view_distance", viewDistance);
        lookSensitivity = num(cf, "controls", "look_sensitivity", lookSensitivity);
        padLookScale = num(cf, "controls", "pad_look_scale", padLookScale);
        invertY = bool(cf, "controls", "invert_y", invertY);
        aimAssist = bool(cf, "controls", "aim_assist", aimAssist);
        masterVolume = num(cf, "audio", "master", masterVolume);
        hudMinimal = "minimal".equals(String.valueOf(cf.getValue("hud", "mode", hudMinimal ? "minimal" : "full")));
    }

    public boolean save() {
        ConfigFile cf = new ConfigFile();
        cf.setValue("graphics", "preset", preset.name());
        cf.setValue("graphics", "render_scale", renderScale);
        cf.setValue("graphics", "shadow_distance", shadowDistance);
        cf.setValue("graphics", "view_distance", viewDistance);
        cf.setValue("controls", "look_sensitivity", lookSensitivity);
        cf.setValue("controls", "pad_look_scale", padLookScale);
        cf.setValue("controls", "invert_y", invertY);
        cf.setValue("controls", "aim_assist", aimAssist);
        cf.setValue("audio", "master", masterVolume);
        cf.setValue("hud", "mode", hudMinimal ? "minimal" : "full");
        return cf.save(PATH) == godot.core.Error.OK;
    }

    private static double num(ConfigFile cf, String s, String k, double def) {
        Object v = cf.getValue(s, k, def);
        return v instanceof Number n ? n.doubleValue() : def;
    }

    private static boolean bool(ConfigFile cf, String s, String k, boolean def) {
        Object v = cf.getValue(s, k, def);
        return v instanceof Boolean b ? b : def;
    }

    private static double clamp(double v, double lo, double hi) { return Math.max(lo, Math.min(hi, v)); }

    // ── probe readouts ──
    @Register public int appliesNow() { return applies; }
    @Register public String presetNow() { return preset.name(); }
    @Register public double viewDistanceNow() { return viewDistance; }
    @Register public double shadowDistanceNow() { return shadowDistance; }
    @Register public void setPresetNow(String p) { setPreset(Preset.valueOf(p)); apply(); }
    @Register public void setViewDistanceNow(double m) { viewDistance = m; graphicsChanged(); apply(); }
    @Register public void setShadowDistanceNow(double m) { shadowDistance = m; graphicsChanged(); apply(); }
    @Register public boolean hudMinimalNow() { return hudMinimal; }
    @Register public void setHudMinimalNow(boolean on) { hudMinimal = on; }
}
