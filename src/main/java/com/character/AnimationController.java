package com.character;

import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.api.AnimationNodeOneShot;
import godot.api.AnimationTree;
import godot.api.CharacterBody3D;
import godot.api.Node;
import godot.api.Tween;
import godot.annotation.Export;
import godot.annotation.RegisterProperty;
import godot.core.NodePath;
import godot.global.GD;

@RegisterClass(className = "AnimationController")
public class AnimationController extends Node {

  @RegisterProperty
  @Export
  public AnimationTree animationTree;

  @RegisterProperty
  @Export
  public CharacterBody3D player;

  private double onFloorBlend = 1.0;
  private double onFloorBlendTarget = 1.0;
  private Tween tween;
  private String currentStanceName = "Upright";

  @RegisterFunction
  @Override
  public void _physicsProcess(double delta) {
    if (player == null || animationTree == null) return;

    // Calculate floor blend target
    onFloorBlendTarget = player.isOnFloor() ? 1.0 : 0.0;

    // Smoothly interpolate the blend value
    onFloorBlend = GD.lerp(onFloorBlend, onFloorBlendTarget, 10.0 * delta);

    // Access AnimationTree parameters using set() with a NodePath
    animationTree.set("parameters/OnFloorBlend/blend_amount", onFloorBlend);
  }

  @RegisterFunction
  public void jump(JumpState jumpState) {
    if (animationTree == null) return;

    // Request a OneShot animation fire
    String path = "parameters/" + jumpState.getAnimationName() + "/request";
    animationTree.set(path, AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @RegisterFunction
  public void onSetMovementState(MovementState movementState) {
    if (animationTree == null) return;

    // Clean up previous tween
    if (tween != null && tween.isValid()) {
      tween.kill();
    }

    tween = createTween();

    // Tween the blend position (id)
    String blendPath = "parameters/" + currentStanceName + "MovementBlend/blend_position";
    tween.tweenProperty(animationTree, new NodePath(blendPath), movementState.id, 0.25);

    // Tween the animation speed scale in parallel
    String speedPath = "parameters/MovementAnimSpeed/scale";
    tween.parallel().tweenProperty(animationTree, new NodePath(speedPath), movementState.animationSpeed, 0.7);
  }

  @RegisterFunction
  public void onSetStance(Stance stance) {
    if (animationTree == null) return;

    // Update the transition and keep track of the current stance name
    animationTree.set("parameters/StanceTransition/transition_request", stance.getName().toString());
    this.currentStanceName = stance.getName().toString();
  }
}