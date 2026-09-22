package com.openworld.character;

import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BaseMaterial3D;
import godot.api.BoneAttachment3D;
import godot.api.Image;
import godot.api.ImageTexture;
import godot.api.Material;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.ResourceLoader;
import godot.api.Shader;
import godot.api.ShaderMaterial;
import godot.api.Skeleton3D;
import godot.api.StandardMaterial3D;
import godot.api.Texture2D;
import godot.core.Basis;
import godot.core.Color;
import godot.core.NodePath;
import godot.core.StringName;
import godot.core.Vector3;

import java.util.HashMap;
import java.util.Map;

/**
 * Puts a character in the toon look (PLAN.md 6.10): every surface's imported material is swapped for the
 * character toon shader (assets/vfx/toon/), and the face mesh's normal is pulled toward the head's forward
 * each frame. Opt-in ({@code Character.toonLook}); whether the game ships in this look is PLAN.md 3.14's.
 *
 * <p>ONE ShaderMaterial per SOURCE material, shared by every character wearing it (a crowd of Shinos is
 * one material per surface, not one per body): what differs per character -- the face direction -- is an
 * {@code instance uniform}, set on the face MeshInstance3D only. The cache holds Godot resources in a
 * static, so {@link #clear()} is called from GameManager._exitTree (the IconRegistry leak rule).
 */
@Script
public class ToonLook extends Node {

    private static final String OPAQUE = "res://assets/vfx/toon/toon_character.gdshader";
    private static final String CUTOUT = "res://assets/vfx/toon/toon_character_cutout.gdshader";
    private static final Map<Material, ShaderMaterial> CACHE = new HashMap<>();
    private static Texture2D white;

    private static final StringName FACE_FORWARD = new StringName("face_forward");
    private static final StringName FACE_WEIGHT = new StringName("face_weight");

    private MeshInstance3D face;
    private BoneAttachment3D head;
    /** The head bone's own axis that points where the face looks, found from the rest pose. */
    private Vector3 headForwardLocal;
    private int surfacesConverted;

    /** Converts every surface under {@code visuals}; {@code faceMesh} (may be null) gets the face control. */
    public void apply(Node visuals, MeshInstance3D faceMesh, Skeleton3D skeleton, Node3D meshRoot) {
        convertTree(visuals);
        face = faceMesh;
        if (face == null || skeleton == null || meshRoot == null) return;
        String bone = skeleton.findBone("head_2") >= 0 ? "head_2" : "head";
        int b = skeleton.findBone(bone);
        if (b < 0) return;
        head = new BoneAttachment3D();
        skeleton.addChild(head);
        head.setBoneName(bone);
        // which of the bone's local axes is the face's forward: the one the rest pose points along the mesh's
        // forward (-Z of MeshRoot; the rig faces -Z). Derived, never assumed -- W1's rule for this rig.
        Basis rest = skeleton.getGlobalTransform().getBasis().times(skeleton.getBoneGlobalRest(b).getBasis());
        Vector3 fwd = meshRoot.getGlobalTransform().getBasis().getColumn(2).times(-1.0f).normalized();
        Vector3[] axes = {rest.getColumn(0), rest.getColumn(1), rest.getColumn(2)};
        int best = 0;
        double bestDot = 0.0;
        for (int i = 0; i < 3; i++) {
            double d = axes[i].normalized().dot(fwd);
            if (Math.abs(d) > Math.abs(bestDot)) { bestDot = d; best = i; }
        }
        headForwardLocal = new Vector3(best == 0 ? 1 : 0, best == 1 ? 1 : 0, best == 2 ? 1 : 0)
                .times((float) Math.signum(bestDot));
        face.setInstanceShaderParameter(FACE_WEIGHT, 1.0);
    }

    @Override
    public void _process(double delta) {
        if (face == null || head == null || headForwardLocal == null || !head.isInsideTree()) return;
        Vector3 f = head.getGlobalTransform().getBasis().times(headForwardLocal).normalized();
        face.setInstanceShaderParameter(FACE_FORWARD, f);
    }

    private void convertTree(Node n) {
        if (n instanceof MeshInstance3D mi && mi.getMesh() != null) {
            for (int i = 0; i < mi.getMesh().getSurfaceCount(); i++) {
                Material src = mi.getActiveMaterial(i);
                ShaderMaterial toon = toonFor(src);
                if (toon != null) {
                    mi.setSurfaceOverrideMaterial(i, toon);
                    surfacesConverted++;
                }
            }
        }
        for (Node c : n.getChildren()) convertTree(c);
    }

    private static ShaderMaterial toonFor(Material src) {
        if (!(src instanceof BaseMaterial3D m)) return null;
        ShaderMaterial hit = CACHE.get(src);
        if (hit != null) return hit;
        boolean cutout = m.getTransparency() != BaseMaterial3D.Transparency.DISABLED
                || m.getCullMode() == BaseMaterial3D.CullMode.DISABLED;
        ShaderMaterial sm = new ShaderMaterial();
        sm.setShader((Shader) ResourceLoader.load(cutout ? CUTOUT : OPAQUE));
        Texture2D tex = m.getTexture(BaseMaterial3D.TextureParam.ALBEDO);
        sm.setShaderParameter(new StringName("albedo_texture"), tex != null ? tex : white());
        sm.setShaderParameter(new StringName("albedo_color"), m.getAlbedo());
        if (cutout) {
            double scissor = m.getTransparency() == BaseMaterial3D.Transparency.ALPHA_SCISSOR
                    ? m.getAlphaScissorThreshold() : 0.5;
            sm.setShaderParameter(new StringName("alpha_scissor"), scissor);
        }
        CACHE.put(src, sm);
        return sm;
    }

    private static Texture2D white() {
        if (white == null) {
            Image img = Image.Companion.createEmpty(1, 1, false, Image.Format.RGBA8);
            img.fill(new Color(1, 1, 1, 1));
            white = ImageTexture.Companion.createFromImage(img);
        }
        return white;
    }

    /** Release the shared materials (a static cache of Godot resources outlives the engine otherwise). */
    public static void clear() {
        CACHE.clear();
        white = null;
    }

    /** How many surfaces this character now draws with the toon shader. For probes. */
    @Register
    public int surfacesConvertedNow() { return surfacesConverted; }
}
