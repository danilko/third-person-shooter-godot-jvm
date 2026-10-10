package com.openworld.game;

import com.openworld.character.Health;
import com.openworld.character.Player;
import com.openworld.control.InputContext;
import com.openworld.world.Places;
import com.openworld.world.ZoneManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Camera3D;
import godot.api.CanvasLayer;
import godot.api.ColorRect;
import godot.api.Control;
import godot.api.Input;
import godot.api.Label;
import godot.api.Node;
import godot.core.Color;
import godot.core.StringName;
import godot.core.Vector3;
import godot.global.GD;

import java.util.ArrayList;
import java.util.List;

/**
 * THE LOADING SCREEN AND ITS WARM-UP TOUR (user, 2026-10-10: "a pre-load screen after entering the game that covers
 * everything, quickly moves the camera to trigger the regions to load their materials, then back to the start").
 * Built in code by {@link FrontEnd} when the island comes up; removes itself when done.
 *
 * <p>While a black cover is up it (1) waits for this machine's player, (2) visits up to {@link #maxSites} region
 * centres of the places record: it sets {@code ZoneManager.setStreamFocus} there -- the streamer loads those zones
 * exactly as it would for a player standing there -- and turns a camera of its own through a full circle, so every
 * material in view is compiled and uploaded; a site is left when the streamer is quiet or after
 * {@link #perSiteMaxSeconds}; (3) clears the focus, hands the view back and waits for the streamer to go quiet round
 * the player, so the first frame the player sees has its world in place.
 *
 * <p><b>The PLAYER IS NEVER MOVED.</b> Only the streaming focus and a camera travel: a body carried across the
 * island would be clamped by the host as a speed hack in co-op, would fall, and would drag traffic and the crowd
 * after it (both follow players, not the focus). The body is held ({@code InputContext.HELD}) and invulnerable
 * while the cover is up. Local to each peer; nothing is replicated.
 *
 * <p>What it buys: shader / pipeline compilation and the first disk read happen behind the cover instead of as the
 * hitch on the first visit. What it does NOT: the toured zones are unloaded again, so their meshes and textures are
 * read back when the player really goes there (from the OS file cache, without the compile). Cancel / B / Esc skips
 * the tour. Never under a probe ({@code --script}); {@code OW_NO_WARMUP=1} turns it off.
 */
@Script(className = "WorldWarmup")
public class WorldWarmup extends Node {

    @Export public int maxSites = 8;
    public int getMaxSites() { return maxSites; }
    public void setMaxSites(int v) { maxSites = v; }
    /** Two sites are at least this far apart (m): one visit warms everything within a zone's load radius. */
    @Export public float minSeparation = 450f;
    public float getMinSeparation() { return minSeparation; }
    public void setMinSeparation(float v) { minSeparation = v; }
    @Export public float perSiteMinSeconds = 1.5f;
    public float getPerSiteMinSeconds() { return perSiteMinSeconds; }
    public void setPerSiteMinSeconds(float v) { perSiteMinSeconds = v; }
    @Export public float perSiteMaxSeconds = 10f;
    public float getPerSiteMaxSeconds() { return perSiteMaxSeconds; }
    public void setPerSiteMaxSeconds(float v) { perSiteMaxSeconds = v; }
    /** The whole tour ends after this long whatever is left (s). */
    @Export public float maxSeconds = 60f;
    public float getMaxSeconds() { return maxSeconds; }
    public void setMaxSeconds(float v) { maxSeconds = v; }
    @Export public float eyeHeight = 35f;
    public float getEyeHeight() { return eyeHeight; }
    public void setEyeHeight(float v) { eyeHeight = v; }

    private enum Phase { WAIT_PLAYER, TOUR, RETURN, DONE }

    private Phase phase = Phase.WAIT_PLAYER;
    private final List<Vector3> sites = new ArrayList<>();
    private int site = -1, toured;
    private double inPhase, total, yaw;
    private CanvasLayer cover;
    private Label status;
    private Camera3D tourCam, playerCam;
    private Player held;
    private boolean wasInvulnerable;

    /** The sites: region centres of the places record, in its order, at least {@code minSeparation} apart. */
    static List<Vector3> pickSites(List<Places.Region> regions, int max, double minSeparation) {
        List<Vector3> out = new ArrayList<>();
        for (Places.Region r : regions) {
            if (out.size() >= max) break;
            Vector3 c = new Vector3((r.x0() + r.x1()) * 0.5, 0, (r.z0() + r.z1()) * 0.5);
            boolean far = true;
            for (Vector3 o : out) if (Math.hypot(o.getX() - c.getX(), o.getZ() - c.getZ()) < minSeparation) far = false;
            if (far) out.add(c);
        }
        return out;
    }

    @Register
    @Override
    public void _ready() {
        setProcessMode(ProcessMode.ALWAYS);
        sites.addAll(pickSites(Places.regions(), Math.max(0, maxSites), minSeparation));
        cover = new CanvasLayer();
        cover.setLayer(120);
        ColorRect black = new ColorRect();
        black.setColor(new Color(0.02, 0.02, 0.03, 1.0));
        black.setAnchorsPreset(Control.LayoutPreset.PRESET_FULL_RECT);
        black.setMouseFilter(Control.MouseFilter.STOP);
        cover.addChild(black);
        status = new Label();
        status.setAnchorsPreset(Control.LayoutPreset.PRESET_CENTER);
        status.setText("LOADING");
        cover.addChild(status);
        addChild(cover);
    }

    private ZoneManager zones() { return getNodeOrNull("/root/ZoneManager") instanceof ZoneManager z ? z : null; }

    private Player localPlayer() {
        for (Player p : PlayerRegistry.getPlayers()) if (GD.isInstanceValid(p) && p.isLocalOwnedPlayer()) return p;
        return null;
    }

    @Register
    @Override
    public void _process(double delta) {
        inPhase += delta;
        total += delta;
        ZoneManager zm = zones();
        switch (phase) {
            case WAIT_PLAYER -> {
                Player p = localPlayer();
                if (p == null && inPhase < 10.0) return;
                if (p != null) hold(p);
                if (zm == null || sites.isEmpty() || p == null) { enter(Phase.RETURN); return; }
                playerCam = getViewport() != null ? getViewport().getCamera3d() : null;
                tourCam = new Camera3D();
                tourCam.setFar(900f);
                addChild(tourCam);
                tourCam.makeCurrent();
                nextSite(zm);
            }
            case TOUR -> {
                if (zm == null) { enter(Phase.RETURN); return; }
                yaw += delta * Math.PI * 2.0 / Math.max(0.5, perSiteMinSeconds * 2.0);
                tourCam.setRotation(new Vector3(-0.12, yaw, 0));
                boolean quiet = inPhase >= perSiteMinSeconds && zm.streamingPendingNow() == 0;
                boolean skip = Input.INSTANCE.isActionJustPressed(new StringName("ui_cancel"));
                if (skip || total >= maxSeconds) { enter(Phase.RETURN); return; }
                if (quiet || inPhase >= perSiteMaxSeconds) {
                    toured++;
                    nextSite(zm);
                }
            }
            case RETURN -> {
                if (tourCam != null || (zm != null && zm.hasStreamFocusNow())) backToPlayer(zm);
                boolean quiet = zm == null || (inPhase >= 0.5 && zm.streamingPendingNow() == 0);
                if (quiet || inPhase >= 20.0) finish();
            }
            default -> { }
        }
    }

    private void enter(Phase p) {
        phase = p;
        inPhase = 0;
    }

    private void nextSite(ZoneManager zm) {
        site++;
        if (site >= sites.size()) { enter(Phase.RETURN); return; }
        Vector3 s = sites.get(site);
        zm.setStreamFocus(s);
        tourCam.setGlobalPosition(new Vector3(s.getX(), eyeHeight, s.getZ()));
        status.setText("LOADING  " + (site + 1) + " / " + sites.size());
        enter(Phase.TOUR);
    }

    private void backToPlayer(ZoneManager zm) {
        if (zm != null) zm.setStreamFocus(null);
        if (playerCam != null && GD.isInstanceValid(playerCam)) playerCam.makeCurrent();
        if (tourCam != null && GD.isInstanceValid(tourCam)) tourCam.queueFree();
        tourCam = null;
        status.setText("LOADING");
    }

    /** The body waits behind the cover: no commands, nothing can hurt it. */
    private void hold(Player p) {
        held = p;
        p.inputContexts.push("warmup", InputContext.HELD);
        if (p.getNodeOrNull("Health") instanceof Health h) {
            wasInvulnerable = h.invulnerable;
            h.invulnerable = true;
        }
    }

    private void finish() {
        if (held != null && GD.isInstanceValid(held)) {
            held.inputContexts.pop("warmup");
            if (held.getNodeOrNull("Health") instanceof Health h) h.invulnerable = wasInvulnerable;
        }
        held = null;
        GD.print("WorldWarmup: " + toured + " of " + sites.size() + " sites in "
                + String.format(java.util.Locale.ROOT, "%.1f", total) + " s");
        phase = Phase.DONE;
        queueFree();
    }

    @Register
    @Override
    public void _exitTree() {
        ZoneManager zm = zones();
        if (zm != null) zm.setStreamFocus(null);
        if (held != null && GD.isInstanceValid(held)) {
            held.inputContexts.pop("warmup");
            if (held.getNodeOrNull("Health") instanceof Health h) h.invulnerable = wasInvulnerable;
        }
    }

    // ── probe surface ──
    @Register public String phaseNow() { return phase.name(); }
    @Register public int sitesNow() { return sites.size(); }
    @Register public int touredNow() { return toured; }
    @Register public int siteIndexNow() { return site; }
    @Register public Vector3 siteNow() { return site >= 0 && site < sites.size() ? sites.get(site) : new Vector3(); }
    @Register public boolean coverUpNow() { return cover != null && GD.isInstanceValid(cover) && cover.isVisible(); }
}
