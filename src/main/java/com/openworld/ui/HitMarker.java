package com.openworld.ui;

import com.openworld.character.Character;
import com.openworld.game.EventBus;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.AudioStreamPlayer;
import godot.api.AudioStreamWAV;
import godot.api.Control;
import godot.api.Node;
import godot.core.Color;
import godot.core.MethodCallable;
import godot.core.PackedByteArray;
import godot.core.Vector2;

/**
 * The hit marker (PLAN.md 2.8 item 9): a short X around the crosshair and a tick sound whenever damage
 * the LOCAL player dealt is confirmed — so a hit at 150 m is never read as a miss (the user's "it dies
 * afterward by itself"). Red and held longer on a kill; larger on a headshot.
 *
 * <p><b>Confirmed, never predicted.</b> It listens to {@code EventBus.damageDealt}, which fires where
 * damage is APPLIED: in single-player and on the host from {@code Health.applyDamage}, and on a client
 * from the host's {@code MSG_DAMAGE_BROADCAST}. A client's own pellet prediction draws nothing here.
 *
 * <p>Self-gated like {@link WeaponProgress}/{@link ScopeOverlay}, not in {@code HUDManager}'s
 * {@code BASE_LAYOUT}. Drawn at screen centre, which is where the reticle and the scope's centre are in
 * every on-foot view.
 */
@Script(className = "HitMarker")
public class HitMarker extends Control {

    @Export public Color hitColor = new Color(1f, 1f, 1f, 0.95f);
    @Export public Color killColor = new Color(1f, 0.15f, 0.1f, 1f);
    /** Seconds a hit stays up (a kill stays twice as long). */
    @Export public float showSeconds = 0.22f;
    /** Arm inner/outer radius at 1080p, px. */
    @Export public float innerRadius = 9f;
    @Export public float outerRadius = 20f;
    @Export public float lineWidth = 3f;
    @Export public boolean playSound = true;

    private Character character;
    private double left = 0.0;
    private boolean lastKill = false;
    private boolean lastHeadshot = false;
    private int shown = 0;
    private AudioStreamPlayer tick;

    @Register
    public void wireCharacter(Node c) {
        character = (c instanceof Character ch) ? ch : null;
    }

    @Register
    @Override
    public void _ready() {
        setMouseFilter(Control.MouseFilter.IGNORE);
        setVisible(false);
        if (getNodeOrNull("/root/EventBus") instanceof EventBus bus) {
            bus.damageDealt.connectUnsafe(MethodCallable.createUnsafe(this, "onDamageDealt"),
                    godot.api.Object.ConnectFlags.DEFAULT);
        }
        tick = new AudioStreamPlayer();
        tick.setStream(buildTick());
        tick.setVolumeDb(-8f);
        addChild(tick);
    }

    @Register
    public void onDamageDealt(String attackerId, float damage, boolean headshot, boolean killed) {
        if (character == null || !godot.global.GD.isInstanceValid(character) || character.characterInfo == null) return;
        if (attackerId == null || !attackerId.equals(character.characterInfo.characterId)) return;
        confirm(headshot, killed);
    }

    /** Show one confirmation. Registered so a gate can drive the widget without a damage path. */
    @Register
    public void confirm(boolean headshot, boolean killed) {
        lastKill = killed;
        lastHeadshot = headshot;
        left = killed ? showSeconds * 2.0 : showSeconds;
        shown++;
        setVisible(true);
        queueRedraw();
        if (playSound && tick != null && tick.isInsideTree()) tick.play();
    }

    /** Confirmations shown since start — the gate reads it. */
    @Register
    public int markersShown() { return shown; }

    @Register
    public boolean markerVisible() { return isVisible(); }

    @Register
    @Override
    public void _process(double delta) {
        if (left <= 0.0) {
            if (isVisible()) setVisible(false);
            return;
        }
        left -= delta;
        queueRedraw();
    }

    @Register
    @Override
    public void _draw() {
        Vector2 size = getSize();
        float w = (float) size.getX(), h = (float) size.getY();
        if (w <= 1f || h <= 1f) return;
        float scale = h / 1080f * (lastHeadshot ? 1.35f : 1f);
        float cx = w * 0.5f, cy = h * 0.5f;
        double total = lastKill ? showSeconds * 2.0 : showSeconds;
        float alpha = (float) Math.max(0.0, Math.min(1.0, left / Math.max(1e-3, total) * 1.6));
        Color base = lastKill ? killColor : hitColor;
        Color c = new Color(base.getR(), base.getG(), base.getB(), base.getA() * alpha);
        float r0 = innerRadius * scale, r1 = outerRadius * scale, lw = Math.max(1f, lineWidth * scale);
        float d = (float) Math.sqrt(0.5);
        for (int sx = -1; sx <= 1; sx += 2) {
            for (int sy = -1; sy <= 1; sy += 2) {
                drawLine(new Vector2(cx + sx * r0 * d, cy + sy * r0 * d), new Vector2(cx + sx * r1 * d, cy + sy * r1 * d),
                        c, lw, true);
            }
        }
    }

    /** A 45 ms 2.2 kHz tick with a fast decay — generated, so there is no audio asset to ship. */
    private static AudioStreamWAV buildTick() {
        int rate = 22050;
        int n = (int) (rate * 0.045);
        byte[] pcm = new byte[n * 2];
        for (int i = 0; i < n; i++) {
            double t = i / (double) rate;
            double env = Math.exp(-t * 90.0);
            short v = (short) (Math.sin(2 * Math.PI * 2200.0 * t) * env * 12000);
            pcm[2 * i] = (byte) (v & 0xff);
            pcm[2 * i + 1] = (byte) ((v >> 8) & 0xff);
        }
        AudioStreamWAV wav = new AudioStreamWAV();
        wav.setFormat(AudioStreamWAV.Format.FORMAT_16_BITS);
        wav.setMixRate(rate);
        wav.setStereo(false);
        wav.setData(new PackedByteArray(pcm));
        return wav;
    }

    public Color getHitColor() { return hitColor; }
    public void setHitColor(Color v) { hitColor = v; }
    public Color getKillColor() { return killColor; }
    public void setKillColor(Color v) { killColor = v; }
    public float getShowSeconds() { return showSeconds; }
    public void setShowSeconds(float v) { showSeconds = v; }
    public float getInnerRadius() { return innerRadius; }
    public void setInnerRadius(float v) { innerRadius = v; }
    public float getOuterRadius() { return outerRadius; }
    public void setOuterRadius(float v) { outerRadius = v; }
    public float getLineWidth() { return lineWidth; }
    public void setLineWidth(float v) { lineWidth = v; }
    public boolean getPlaySound() { return playSound; }
    public void setPlaySound(boolean v) { playSound = v; }
}
