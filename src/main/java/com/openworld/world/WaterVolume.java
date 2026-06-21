package com.openworld.world;

import com.openworld.character.Character;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.Area3D;
import godot.api.BoxShape3D;
import godot.api.CollisionShape3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.core.Callable;
import godot.core.StringName;

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
@RegisterClass(className = "WaterVolume")
public class WaterVolume extends Area3D {

  public static final String WATER_GROUP = "water";

  @RegisterFunction
  @Override
  public void _ready() {
    addToGroup(new StringName(WATER_GROUP));
    // godot-kotlin-jvm registers @RegisterFunction methods under their snake_case names.
    connect(new StringName("body_entered"), Callable.createUnsafe(this, new StringName("on_body_entered")));
    connect(new StringName("body_exited"), Callable.createUnsafe(this, new StringName("on_body_exited")));
  }

  @RegisterFunction
  public void onBodyEntered(Node3D body) {
    Character c = resolveCharacter(body);
    if (c != null) c.setInWater(true, getSurfaceY());
  }

  @RegisterFunction
  public void onBodyExited(Node3D body) {
    Character c = resolveCharacter(body);
    if (c != null) c.setInWater(false, 0.0);
  }

  /**
   * World-space Y of the water surface — the top face of the first box collision shape. Used by
   * the swimmer's buoyancy spring so it settles at the water line. Falls back to the area's own
   * global Y if no box shape is found.
   */
  @RegisterFunction
  public double getSurfaceY() {
    for (Node child : getChildren()) {
      if (child instanceof CollisionShape3D cs && cs.getShape() instanceof BoxShape3D box) {
        return cs.getGlobalPosition().getY() + box.getSize().getY() * 0.5;
      }
    }
    return getGlobalPosition().getY();
  }

  private Character resolveCharacter(Node3D body) {
    if (body instanceof Character c) return c;
    Node owner = body.getOwner();
    return (owner instanceof Character c) ? c : null;
  }
}
