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
    /** The loading screen's warm-up TOUR when the island comes up (game.WorldWarmup). Off = the world starts at once
     *  (user, 2026-10-10: "so I do not wait for the tour every time when testing"); the first minutes then stream
     *  and compile shaders in play, which is what the tour is there to hide. Client-local: it changes nobody's world. */
    public boolean loadingTour = true;
    /** How much the HOST simulates (cars, promoted peds, attackers at once): {@link WorldDensity}. Host-decided. */
    public WorldDensity worldDensity = WorldDensity.NORMAL;
    /** Added to every on-foot and vehicle camera FOV (deg), never to a scope's declared FOV. -10..+20. */
    public double fovOffset = 0.0;
    public static final double FOV_OFFSET_MIN = -10.0, FOV_OFFSET_MAX = 20.0;
    /** The window: WINDOWED (at {@link #resolution}, "" = leave the size alone), FULLSCREEN (borderless), EXCLUSIVE. */
    public enum WindowMode { WINDOWED, FULLSCREEN, EXCLUSIVE }
    public WindowMode windowMode = WindowMode.WINDOWED;
    public String resolution = "";
    public boolean vsync = true;
    /** The windowed sizes the page offers (a 16:9 ladder up to 1440p; the Deck's 1280x800 panel). */
    public static final String[] RESOLUTIONS = {"1280x720", "1280x800", "1600x900", "1920x1080", "2560x1440"};

    /** The FOV offset the cameras add (0 before the AutoLoad is up). */
    public static double fovOffsetDeg() {
        return instance == null ? 0.0 : clamp(instance.fovOffset, FOV_OFFSET_MIN, FOV_OFFSET_MAX);
    }

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
        applyDensity();
        applyWindow();
    }

    private boolean probeRun() {
        for (String a : godot.api.OS.getCmdlineArgs()) if ("--script".equals(a) || "-s".equals(a)) return true;
        return false;
    }

    /**
     * World density reaches the systems it scales -- on the AUTHORITY only (single player or the host): a client's
     * value changes nothing in someone else's session. Not under a probe (--script): probes set their own budgets
     * and must not inherit the player's settings.cfg; {@link #setWorldDensityNow} is their door.
     */
    private void applyDensity() {
        // OW_WORLD_DENSITY=HIGH runs this session (a perf run, a probe, a debug session) at a level, whatever
        // settings.cfg says and without writing it
        String env = godot.api.OS.getEnvironment("OW_WORLD_DENSITY");
        if (env != null && !env.isEmpty()) {
            worldDensity = WorldDensity.of(env);
            densityForced = true;
        }
        if (!densityForced && probeRun()) return;
        if (getNodeOrNull("/root/NetworkManager") instanceof com.openworld.net.NetworkManager n
                && n.isNetworked() && !n.isServer()) return;
        WorldDensity.Row d = (worldDensity == null ? WorldDensity.NORMAL : worldDensity).row();
        if (getNodeOrNull("/root/ZoneManager") instanceof com.openworld.world.ZoneManager zm) {
            zm.trafficBudget = d.traffic();
            zm.walkerBudget = d.walkers();
            zm.fighterBudget = d.fighters();
        }
        EnforcementDispatch.attackTokenBonus = d.attackTokens();
    }

    private boolean densityForced;

    /** Probe / console: set the density and apply it now (also under --script). */
    @Register public void setWorldDensityNow(String name) {
        worldDensity = WorldDensity.of(name);
        densityForced = true;
        applyDensity();
    }
    @Register public String worldDensityNow() { return worldDensity.name(); }

    private String windowApplied = "";

    /** The window mode / size / vsync -- only when they change (a re-apply on every scene must not re-centre the
     *  window), and never on the headless display server. */
    private void applyWindow() {
        if ("headless".equalsIgnoreCase(godot.api.DisplayServer.getName())) return;
        String want = windowMode + "|" + resolution + "|" + vsync;
        if (want.equals(windowApplied)) return;
        windowApplied = want;
        godot.api.DisplayServer.windowSetVsyncMode(vsync ? godot.api.DisplayServer.VSyncMode.VSYNC_ENABLED
                : godot.api.DisplayServer.VSyncMode.VSYNC_DISABLED, 0);
        switch (windowMode) {
            case FULLSCREEN -> godot.api.DisplayServer.windowSetMode(godot.api.DisplayServer.WindowMode.FULLSCREEN, 0);
            case EXCLUSIVE -> godot.api.DisplayServer.windowSetMode(godot.api.DisplayServer.WindowMode.EXCLUSIVE_FULLSCREEN, 0);
            default -> {
                godot.api.DisplayServer.windowSetMode(godot.api.DisplayServer.WindowMode.WINDOWED, 0);
                int[] wh = parseResolution(resolution);
                if (wh != null) {
                    godot.api.DisplayServer.windowSetSize(new godot.core.Vector2i(wh[0], wh[1]), 0);
                    godot.core.Vector2i screen = godot.api.DisplayServer.screenGetSize(-1);
                    godot.api.DisplayServer.windowSetPosition(new godot.core.Vector2i(
                            Math.max(0, (screen.getX() - wh[0]) / 2), Math.max(0, (screen.getY() - wh[1]) / 2)), 0);
                }
            }
        }
    }

    /** "1920x1080" -> {1920, 1080}; null for "" or anything unreadable. */
    public static int[] parseResolution(String r) {
        if (r == null) return null;
        String[] p = r.trim().toLowerCase().split("x");
        if (p.length != 2) return null;
        try {
            int w = Integer.parseInt(p[0].trim()), h = Integer.parseInt(p[1].trim());
            return w >= 640 && h >= 360 ? new int[] {w, h} : null;
        } catch (NumberFormatException e) {
            return null;
        }
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
            if (c instanceof TPSCameraController cam) cam.refreshFov();   // the FOV offset reaches the camera now
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
        com.openworld.control.KeyBindings.init();   // read project.godot's keys before any user binding lands
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
        loadingTour = bool(cf, "world", "loading_tour", loadingTour);
        hudMinimal = "minimal".equals(String.valueOf(cf.getValue("hud", "mode", hudMinimal ? "minimal" : "full")));
        fovOffset = num(cf, "view", "fov_offset", fovOffset);
        worldDensity = WorldDensity.of(String.valueOf(cf.getValue("world", "density", worldDensity.name())));
        try { windowMode = WindowMode.valueOf(String.valueOf(cf.getValue("display", "window_mode", windowMode.name()))); }
        catch (IllegalArgumentException e) { windowMode = WindowMode.WINDOWED; }
        resolution = String.valueOf(cf.getValue("display", "resolution", resolution));
        vsync = bool(cf, "display", "vsync", vsync);
        com.openworld.control.KeyBindings.load(cf);
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
        cf.setValue("view", "fov_offset", fovOffset);
        cf.setValue("world", "density", worldDensity.name());
        cf.setValue("world", "loading_tour", loadingTour);
        cf.setValue("display", "window_mode", windowMode.name());
        cf.setValue("display", "resolution", resolution);
        cf.setValue("display", "vsync", vsync);
        com.openworld.control.KeyBindings.save(cf);
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
    @Register public boolean loadingTourNow() { return loadingTour; }
    @Register public void setLoadingTourNow(boolean on) { loadingTour = on; }
    @Register public boolean hudMinimalNow() { return hudMinimal; }
    @Register public void setHudMinimalNow(boolean on) { hudMinimal = on; }
    @Register public void setFovOffsetNow(double deg) { fovOffset = clamp(deg, FOV_OFFSET_MIN, FOV_OFFSET_MAX); apply(); }
    @Register public boolean rebindNow(String row, String spec) { return com.openworld.control.KeyBindings.rebind(row, spec); }
    @Register public String bindingNow(String row) { return com.openworld.control.KeyBindings.specNow(row); }
    @Register public void resetBindingsNow() { com.openworld.control.KeyBindings.resetDefaults(); com.openworld.control.KeyBindings.resetPadDefaults(); }
    @Register public boolean rebindPadNow(String row, String spec) { return com.openworld.control.KeyBindings.rebindPad(row, spec); }
    @Register public String padBindingNow(String row) { return com.openworld.control.KeyBindings.padSpecNow(row); }
    @Register public boolean saveNow() { return save(); }
    @Register public void reloadNow() { load(); apply(); }
}
