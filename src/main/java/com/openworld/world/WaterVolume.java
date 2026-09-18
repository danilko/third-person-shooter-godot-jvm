package com.openworld.world;

import com.openworld.character.Character;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.Area3D;
import godot.api.BoxMesh;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.GeometryInstance3D;
import godot.api.Material;
import godot.api.MeshInstance3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PlaneMesh;
import godot.core.MethodCallable;
import godot.core.StringName;
import godot.core.Vector2;
import godot.core.Vector3;

/**
 * A water volume (PLAN.md I1). Any {@link Character} body that overlaps switches to the SWIM
 * stance + swim physics while inside, and reverts on exit. Mirrors {@code AmmoRefill}'s
 * Area3D-detects-bodies pattern (rather than a per-character sensor) so it scales to streamed
 * AI with no extra wiring.
 *
 * <p>Set the area's {@code collision_mask} to include the character body layer so
 * {@code body_entered}/{@code body_exited} fire. Membership in group {@code "water"} is for
 * discovery by other systems (e.g. AI water avoidance later).
 */
@Script(className = "WaterVolume")
public class WaterVolume extends Area3D {

  public static final String WATER_GROUP = "water";

  /**
   * Half-size (m) of a flat FAR OCEAN laid round the surface box to the horizon (PLAN.md 3.7), or 0 for none.
   *
   * <p>The world is finite: the surface box ends a few kilometres out, and from any altitude its edge sits a few
   * degrees BELOW the horizontal line. Everything between is the sky shader's below-horizon colour (Sky3D's
   * {@code ground_color}), which read as a dark band under the horizon -- measured: painting that colour magenta
   * turned the whole band magenta. The industry answer is an ocean that reaches the horizon, not a repainted sky, so
   * this lays a ring (the box's top face extended outward, the same material, no collision -- nobody can swim 8 km
   * out past the {@link WorldBounds} wall anyway) out to this half-size. Match it to the camera's far plane (100 km):
   * the sky then shows below the horizon only past that, under 1 degree from 1.5 km up.
   */
  @Export
  public double farOceanExtent = 0.0;

  public double getFarOceanExtent() { return farOceanExtent; }

  public void setFarOceanExtent(double v) { farOceanExtent = v; }

  /** The ring's node name, so a probe can find it. */
  public static final String FAR_OCEAN = "FarOcean";

  @Register
  @Override
  public void _ready() {
	addToGroup(new StringName(WATER_GROUP));
	// godot-jvm registers @Register methods under their snake_case names.
	connect(new StringName("body_entered"), MethodCallable.createUnsafe(this, "on_body_entered"));
	connect(new StringName("body_exited"), MethodCallable.createUnsafe(this, "on_body_exited"));
	if (farOceanExtent > 0.0) buildFarOcean();
  }

  /** The far-ocean ring, in this area's frame, round the first box-mesh child (the surface). */
  private void buildFarOcean() {
	MeshInstance3D surface = null;
	for (Node child : getChildren()) {
	  if (child instanceof MeshInstance3D mi && mi.getMesh() instanceof BoxMesh) {
		surface = mi;
		break;
	  }
	}
	if (surface == null || getNodeOrNull(FAR_OCEAN) != null) return;
	Vector3 size = ((BoxMesh) surface.getMesh()).getSize();
	Vector3 c = surface.getPosition();
	double y = c.getY() + size.getY() * 0.5;
	double x0 = c.getX() - size.getX() * 0.5, x1 = c.getX() + size.getX() * 0.5;
	double z0 = c.getZ() - size.getZ() * 0.5, z1 = c.getZ() + size.getZ() * 0.5;
	double e = Math.max(farOceanExtent, Math.max(size.getX(), size.getZ()));
	double ex0 = c.getX() - e, ex1 = c.getX() + e, ez0 = c.getZ() - e, ez1 = c.getZ() + e;
	// four quads round the box: north and south full width, east and west between them, each (xa, za, xb, zb)
	double[][] quads = {{ex0, ez0, ex1, z0}, {ex0, z1, ex1, ez1}, {ex0, z0, x0, z1}, {x1, z0, ex1, z1}};
	Node3D ring = new Node3D();
	ring.setName(FAR_OCEAN);
	Material mat = surface.getSurfaceOverrideMaterial(0);
	for (double[] q : quads) {
	  PlaneMesh plane = new PlaneMesh();                 // faces +Y
	  plane.setSize(new Vector2(q[2] - q[0], q[3] - q[1]));
	  MeshInstance3D part = new MeshInstance3D();
	  part.setMesh(plane);
	  part.setPosition(new Vector3((q[0] + q[2]) * 0.5, y, (q[1] + q[3]) * 0.5));
	  if (mat != null) part.setSurfaceOverrideMaterial(0, mat);
	  part.setCastShadowsSetting(GeometryInstance3D.ShadowCastingSetting.OFF);
	  ring.addChild(part);
	}
	addChild(ring);
  }

  @Register
  public void onBodyEntered(Node3D body) {
	Character c = resolveCharacter(body);
	if (c != null) c.setInWater(true, getSurfaceY());
  }

  @Register
  public void onBodyExited(Node3D body) {
	Character c = resolveCharacter(body);
	if (c != null) c.setInWater(false, 0.0);
  }

  /**
   * World-space Y of the water surface — the top face of the first box collision shape. Used by
   * the swimmer's buoyancy spring so it settles at the water line. Falls back to the area's own
   * global Y if no box shape is found.
   */
  @Register
  public double getSurfaceY() {
	for (Node child : getChildren()) {
	  if (child instanceof CollisionShape3D cs && cs.getShape() instanceof BoxShape3D box) {
		return cs.getGlobalPosition().getY() + box.getSize().getY() * 0.5;
	  }
	}
	return getGlobalPosition().getY();
  }

  /**
   * True when {@code p} is inside this volume's water, i.e. inside one of its box shapes (the box's top face is the
   * surface). The screen's underwater tint asks it of the camera on screen ({@code ui.UnderwaterOverlay}).
   */
  public boolean containsPoint(godot.core.Vector3 p) {
	for (Node child : getChildren()) {
	  if (child instanceof CollisionShape3D cs && cs.getShape() instanceof BoxShape3D box) {
		godot.core.Vector3 l = cs.getGlobalTransform().affineInverse().times(p);
		godot.core.Vector3 h = box.getSize().times(0.5);
		if (Math.abs(l.getX()) <= h.getX() && Math.abs(l.getY()) <= h.getY() && Math.abs(l.getZ()) <= h.getZ()) return true;
	  }
	}
	return false;
  }

  /** Whether {@code p} is under water in any water volume of {@code tree}. */
  public static boolean isUnderwater(godot.api.SceneTree tree, godot.core.Vector3 p) {
	if (tree == null || p == null) return false;
	for (Node n : tree.getNodesInGroup(new StringName(WATER_GROUP))) {
	  if (n instanceof WaterVolume w && w.isInsideTree() && w.containsPoint(p)) return true;
	}
	return false;
  }

  private Character resolveCharacter(Node3D body) {
	if (body instanceof Character c) return c;
	Node owner = body.getOwner();
	return (owner instanceof Character c) ? c : null;
  }
}
