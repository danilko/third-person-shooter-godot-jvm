package com.openworld.character;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.*;
import godot.core.*;
import godot.global.GD;
import java.util.HashMap;
import java.util.Map;
import com.openworld.ai.AILodLevel;
import com.openworld.movement.character.CombatState;
import com.openworld.movement.character.JumpState;
import com.openworld.movement.character.MovementState;
import com.openworld.movement.character.Stance;

@Script(className = "AnimationController")
public class AnimationController extends Node {

  @Export
  public AnimationTree animationTree;

  @Export
  public CharacterBody3D player;

  /**
   * The CHEST aim: a {@link ShoulderAimModifier} whose driven bone is its own reference,
   * {@code spine_03}. It was a stock {@code LookAtModifier3D}, and does the same thing — measured
   * identical — but the two aim mechanisms now share one implementation because they have to share
   * one pair of elevation limits, and the stock modifier cannot express them (symmetric, taken
   * from the rest pose, and it mixes the axes). See {@link ShoulderAimModifier}'s class doc.
   */
  @Export
  public ShoulderAimModifier aimSpineModifier;

  /** Shoulders/head aim, for stances whose body must not move — see {@link ShoulderAimModifier}. */
  @Export
  public ShoulderAimModifier shoulderAimModifier;

  /** Firing-arm IK seating a long gun's stock in the shoulder pocket — see {@link StockMountIKModifier}. */
  @Export
  public StockMountIKModifier stockMountModifier;

  /** The per-shot weapon kick — see {@link WeaponRecoilModifier}. */
  @Export
  public WeaponRecoilModifier recoilModifier;

  @Export
  public double animationBlendDuration = 0.25;

  @Export
  public double animationSpeedDuration = 0.7;

  @Export
  public double floorBlendSpeed = 10.0;

  /**
   * Faster floor-blend rate used the instant the body lands (going back to the grounded pose), so
   * locomotion shows promptly instead of lingering in the airborne pose. Higher than
   * {@link #floorBlendSpeed} (which governs the slower lift-off into the air).
   */
  @Export
  public double landBlendSpeed = 22.0;

  /**
   * The node whose facing the strafe blend is measured against — {@code MeshRoot}, the same node
   * {@link com.openworld.movement.character.MovementController} yaws. Wired from
   * {@link MeshConfig#meshRootPath} by {@code Character.wireFromMeshConfig}, exported so a scene
   * can name a different one.
   *
   * <p>A leg animation is relative to the BODY, so the frame is the body's own facing and nothing
   * else. Both previous frames were wrong and in different ways (AIM_PLAN.md W2): the player's
   * direction was used unrotated, so the corner was picked from the world compass — walking north
   * played the same clip whichever way the character faced — and the AI rotated by
   * {@code -camRotation}, the camera rig's LOCAL yaw under a {@code setAsTopLevel} frame, which
   * reads as correct only because {@code AICameraController} happens to drive that yaw to the AI's
   * aim yaw. Reading the mesh's own global basis needs no compensation term and is one owner for
   * both.
   *
   * <p>Left null the direction is used in world space, i.e. the old player behaviour.
   */
  @Export
  public Node3D meshRoot;

  // NodePath for the animation speed parameter never changes — build it once.
  private static final NodePath ANIM_SPEED_PATH = new NodePath("parameters/MovementAnimSpeed/scale");

  /**
   * {@link #player} as the JVM instance Godot bound the script to, when it is an AI.
   *
   * <p>A node reference exported through the scene is resolved at instantiate time, and
   * godot-jvm can hand back a SECOND JVM wrapper for that engine object — same
   * `get_instance_id()`, different Java object, none of the state its own `_ready()` wrote.
   * Engine calls are fine on either (which is why `player.isOnFloor()` above never noticed);
   * Java fields are not. Measured on this class: the exported reference IS the stale one, so
   * `getLodLevel()` read a fresh field and always came back ACTIVE — the PASSIVE/FROZEN skip
   * below, which is the dominant per-AI cost saving (PLAN.md Part D / D2), never once fired.
   * Whether a given export is stale depends on resolution order and cannot be reasoned about,
   * only measured, so re-resolve the path at runtime wherever Java state is read.
   */
  private AICharacter lodBody;
  private boolean lodBodyResolved;

  private AICharacter lodBody() {
    if (lodBodyResolved && (lodBody == null || GD.isInstanceValid(lodBody))) return lodBody;
    lodBodyResolved = true;
    lodBody = null;
    if (player == null) return null;
    Node live = getNodeOrNull(player.getPath());
    if (live instanceof AICharacter ai) lodBody = ai;
    else if (player instanceof AICharacter ai) lodBody = ai;
    return lodBody;
  }

  private double onFloorBlend = 1.0;
  private double onFloorBlendTarget = 1.0;
  private boolean wasOnFloor = true;
  private Tween tween;
  private String currentStanceName = "Upright";
  private Stance currentStance = null;
  // True while in the SWIM stance — keeps the locomotion blend grounded so the (placeholder Crawl)
  // swim pose plays fully instead of blending to the airborne/falling pose while floating off-floor.
  private boolean swimming = false;
  private boolean combat = false;

  /** WeaponTorsoBlend: where it is heading (0/1, set with the aim modifiers) and where it is. */
  private double torsoLayerTarget = 0.0;
  private boolean weaponPosed = true;

  private boolean isOneShotActive(String node) {
    java.lang.Object v = animationTree.get("parameters/" + node + "/active");
    return v instanceof Boolean b && b;
  }
  private double torsoLayer = 0.0;

  /** Seconds to ease the aim clip's torso in or out (PLAN.md A2.3) -- matches the stock mount's blend. */
  @Export
  public double torsoLayerBlendSeconds = 0.1;
  private Vector2 movementDirection = new Vector2();
  private Vector2 animationDirection = new Vector2();
  private MovementState currentMovementState = null;
  // Cached NodePaths for per-stance blend parameters — populated lazily (one allocation per stance).
  private final Map<String, NodePath> blendPathCache = new HashMap<>();


  @Register
  @Override
  public void _physicsProcess(double delta) {
    if (player == null || animationTree == null) return;
    // Skip for any non-ACTIVE LOD tier (PASSIVE or FROZEN): the AnimationTree JVM-bridge writes
    // are the most expensive per-AI work, so mid-range and distant AIs hold their last pose at
    // zero bridge cost (PLAN.md Part D / D2). Player/non-AI bodies are always ACTIVE.
    AICharacter ai = lodBody();
    if (ai != null && ai.getLodLevel() != AILodLevel.ACTIVE) return;

    // Landing edge: a jump/fall OneShot plays its FULL clip once fired, so after touchdown the
    // multi-second jump/falling pose keeps blending on top of locomotion — the "still airborne while
    // already running" lag. Fade those OneShots out the moment we regain the floor so walk/run shows.
    boolean onFloor = player.isOnFloor();
    if (onFloor && !wasOnFloor) {
      long fadeOut = AnimationNodeOneShot.OneShotRequest.FADE_OUT.getValue();
      animationTree.set("parameters/GroundJump/request", fadeOut);
      animationTree.set("parameters/AirJump/request", fadeOut);
    }
    wasOnFloor = onFloor;

    // The aim clip's torso (Stance.weaponTorsoLayer), eased so entering and leaving the aim does not
    // snap the spine. Written only while it moves, like the floor blend below.
    if (torsoLayer != torsoLayerTarget) {
      double step = torsoLayerBlendSeconds <= 0.0 ? 1.0 : delta / torsoLayerBlendSeconds;
      torsoLayer = torsoLayer < torsoLayerTarget
          ? Math.min(torsoLayerTarget, torsoLayer + step)
          : Math.max(torsoLayerTarget, torsoLayer - step);
      animationTree.set("parameters/WeaponTorsoBlend/blend_amount", torsoLayer);
    }

    // Is the held weapon POSED (no switch/draw, reload or attack one-shot moving it)? The aim modifiers only
    // trust its bore then, and the stock mount only seats it then -- a rifle being drawn points anywhere, and
    // aiming it spun the upper body up to 145 deg (probe_switch_spin.gd). Read only while aiming: three
    // bridge reads a frame is not free on an AI.
    if (combat) {
      boolean posed = !isOneShotActive("WeaponChange") && !isOneShotActive("Reload") && !isOneShotActive("Attack");
      if (posed != weaponPosed) {
        weaponPosed = posed;
        if (aimSpineModifier != null) aimSpineModifier.setWeaponPosed(posed);
        if (shoulderAimModifier != null) shoulderAimModifier.setWeaponPosed(posed);
        if (stockMountModifier != null && currentStance != null) {
          stockMountModifier.setEngaged(posed && currentStance.isStockMountEnabled());
        }
      }
    }

    // Treat swimming as grounded for the floor blend — a floating swimmer is off-floor, but the
    // placeholder swim pose should not blend toward the falling animation.
    onFloorBlendTarget = (swimming || onFloor) ? 1.0 : 0.0;
    // Snap to the grounded pose quickly on landing (landBlendSpeed), but lift off into the air at the
    // gentler floorBlendSpeed — asymmetric so touchdown reads as "grounded" without a slow fade.
    double blendRate = (onFloorBlendTarget > onFloorBlend) ? landBlendSpeed : floorBlendSpeed;
    double newBlend = GD.lerp(onFloorBlend, onFloorBlendTarget, blendRate * delta);
    // Only write to the AnimationTree when the value actually changes — eliminates
    // ~1,920 unconditional JVM bridge calls/sec for 32 grounded AIs at 60 Hz.
    if (Math.abs(newBlend - onFloorBlend) > 0.001) {
      onFloorBlend = newBlend;
      animationTree.set("parameters/OnFloorBlend/blend_amount", onFloorBlend);
    } else {
      onFloorBlend = newBlend;
    }
  }

  @Register
  public void jump(JumpState jumpState) {
    if (animationTree == null) return;
    // Do not kill the movement blend tween — the jump OneShot plays on top of the
    // movement blend, so we want the blend to continue smoothly while airborne.
    String path = "parameters/" + jumpState.getAnimationName() + "/request";
    animationTree.set(path, AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @Register
  public void onSetMovementState(MovementState movementState) {
    currentMovementState = movementState;
    updateAnimationBlend(movementState);
  }

  /**
   * Story/cutscene hook: forces WeaponBlend to 0 (no weapon pose) or restores it to 1.
   * Not called during normal slot switching — all weapons including fist use WeaponBlend = 1.
   */
  public void setHolster(boolean holster) {
    if (animationTree == null) return;
    // blend_amount: WeaponBlend is a Blend2. This wrote `blend_position` (a BlendSpace parameter),
    // which AnimationTree.set ignores silently, so the hook had never done anything.
    animationTree.set("parameters/WeaponBlend/blend_amount", holster ? 0 : 1);
  }

  public void onWeaponEquip(int animationWeaponIndex) {
    animationTree.set("parameters/WeaponAim/blend_position", animationWeaponIndex);
    // The torso layer's own copy of the aim branch: a blend-tree node's output can feed ONE input
    // (Godot refuses the second connection and the whole tree stops evaluating -- measured, every
    // stance read the rest pose), so WeaponTorsoBlend cannot share CombatTransition with WeaponBlend.
    animationTree.set("parameters/WeaponAimTorso/blend_position", animationWeaponIndex);
    animationTree.set("parameters/WeaponHold/blend_position", animationWeaponIndex);
    animationTree.set("parameters/WeaponChangeAnimation/blend_position", animationWeaponIndex);
    animationTree.set("parameters/WeaponChange/request", AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  // ── Melee attack one-shot ─────────────────────────────────────────────────
  //
  // Same shape as WeaponChange and Reload: an upper-body-filtered OneShot on the chain, fed by a
  // TimeScale, fed here by a Transition whose inputs are named after their clips. By NAME rather
  // than by weapon index: a step names the clip it plays (MeleeAttackStep.animation), so a new
  // weapon or a new step is one Transition input and one action in the .blend, with no index table
  // to keep in step with weapon_archetypes.json.

  private static final String ATTACK_CLIP    = "parameters/AttackClip/transition_request";
  private static final String ATTACK_SCALE   = "parameters/AttackScale/scale";
  private static final String ATTACK_REQUEST = "parameters/Attack/request";
  /** The time-warp of the swing now playing, remembered so a hitstop can freeze it and give it back. */
  private float attackScale = 1f;

  /**
   * Play {@code clip} as the attack one-shot, time-warped so its WHOLE length spans
   * {@code durationSeconds} — the code owns the swing's timing and the clip is fitted to it (see
   * {@code MeleeAttackStep}). Returns false when the clip does not exist, which is otherwise silent:
   * an unknown Transition input simply plays nothing.
   */
  public boolean playMeleeAttack(String clip, double durationSeconds) {
    if (animationTree == null || clip == null || clip.isEmpty()) return false;
    StringName name = new StringName(clip);
    if (!animationTree.hasAnimation(name)) return false;
    double length = animationTree.getAnimation(name).getLength();
    attackScale = (float) (durationSeconds > 1e-3 ? length / durationSeconds : 1.0);
    animationTree.set(ATTACK_CLIP, clip);
    animationTree.set(ATTACK_SCALE, attackScale);
    animationTree.set(ATTACK_REQUEST, AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
    return true;
  }

  /**
   * Hitstop: freeze the swing on the pose it connected in, then give it back its time-warp. Only
   * the attack one-shot stops — the legs keep walking and the world keeps running, which is what
   * makes this safe in multiplayer where a global Engine.time_scale freeze would stall every peer.
   */
  public void setMeleeAttackFrozen(boolean frozen) {
    if (animationTree == null) return;
    animationTree.set(ATTACK_SCALE, frozen ? 0f : attackScale);
  }

  @Register
  public void onWeaponReload() {
    animationTree.set("parameters/Reload/request", AnimationNodeOneShot.OneShotRequest.FIRE.getValue());
  }

  @Register
  public void onSetStance(Stance stance) {
    if (animationTree == null) return;

    // Use the stance's animation-key override when set (e.g. SWIM → "Crawl" placeholder, I1);
    // otherwise the stance's node name drives the AnimationTree transition + movement blend.
    swimming = "Swim".equals(stance.getName().toString());
    String key = stance.getAnimationStanceKey();
    if (key == null || key.isEmpty()) key = stance.getName().toString();

    animationTree.set("parameters/StanceTransition/transition_request", key);
    this.currentStanceName = key;
    this.currentStance = stance;

    updateAimModifiers();
  }

  @Register
  public void onSetCombatState(CombatState combatState) {
    if (animationTree == null) return;
    combat = combatState.isCombat();
    animationTree.set("parameters/CombatTransition/transition_request", combat ? "Combat" : "NoCombat");
    animationTree.set("parameters/NeckFront/blend_amount", combat ? 1 : 0);
    updateAimModifiers();
  }

  /**
   * One shot's visible weapon kick (PLAN.md A3). Called by {@code WeaponController} at the two sites
   * W13 uses for the weapon's own moving parts — {@code onWeaponFire} on the owner and
   * {@code playRemoteFireCue} on a puppet — so a remote peer sees the same kick with no new message.
   * A weapon that authors no kick passes zeros and nothing happens.
   */
  @Register
  public void onWeaponKick(double back, double pitchDeg, double spring, double damping) {
    if (recoilModifier == null || (back == 0.0 && pitchDeg == 0.0)) return;
    recoilModifier.kick(back, pitchDeg, spring, damping);
  }

  private void updateAimModifiers() {
    if (currentStance == null) return;
    // A stance either aims its chest at the target or it does not. Before W1a this read a float
    // (spineAimMaxAngle) as an on/off flag, which is why crouch and crawl were completely inert --
    // they held whatever their clip authored, whatever the player looked at. W1a made that float a
    // real angle limit and then MEASURED it: see Stance.spineAimEnabled for why the limit went away
    // again and a boolean is the honest owner. The modifier's own use_angle_limitation is left at
    // its default (off, i.e. the engine's 360-degree limits), so nothing clips the aim.
    //
    // THE TWO MODIFIERS COMPOSE, so a stance may run BOTH and spend the aim in STAGES — torso
    // first, then shoulders and neck, which is how a person turns to look behind them. They do not
    // double up: the shoulder modifier measures its delta from `spine_03`'s CURRENT forward, and it
    // runs after the spine modifier in tree order, so whatever the torso has already covered is
    // simply not there to cover again. (Run the spine UNCAPPED and this is provable: it reaches the
    // target, the shoulders then compute a delta of ~0 and add nothing.) That is what makes a
    // seated aim reach past what collarbones alone can sell: `Stance.aimYawLimit` is the TOTAL
    // reach and `Stance.spineAimYawLimit` is the torso's share of it.
    boolean spine = combat && currentStance.isSpineAimEnabled();
    boolean shoulder = combat && currentStance.isShoulderAimEnabled();
    boolean staged = spine && shoulder;
    // Staged: the spine is capped at the torso's share and the shoulders carry the total, so the
    // remainder — and only the remainder — lands on the collarbones and neck. Single-modifier
    // stances are untouched: whichever one is on gets the stance's own total, exactly as before.
    applyAimLimits(aimSpineModifier, spine, currentStance,
        staged ? currentStance.getSpineAimYawLimit() : currentStance.getAimYawLimit());
    applyAimLimits(shoulderAimModifier, shoulder, currentStance, currentStance.getAimYawLimit());
    // The stock mount eases itself in and out (and does nothing for a weapon with no StockPoint), so
    // it only needs to know whether this is a shouldered aim at all.
    if (stockMountModifier != null) {
      stockMountModifier.setEngaged(combat && weaponPosed && currentStance.isStockMountEnabled());
    }
    torsoLayerTarget = (combat && currentStance.isWeaponTorsoLayer()) ? 1.0 : 0.0;
  }

  private void applyAimLimits(ShoulderAimModifier m, boolean active, Stance stance, float yawLimit) {
    if (m == null) return;
    m.setActive(active);
    if (!active) return;
    m.setYawLimitDegrees(yawLimit);
    m.setPitchLimitMax((float) stance.getAimPitchMax());
    m.setPitchLimitMin((float) stance.getAimPitchMin());
  }

  /**
   * Below this fraction of the (normalised) movement direction an axis reads as zero, so a
   * cardinal input picks a cardinal corner.
   *
   * <p>{@code sin(22.5 deg)}: the boundary of the eight-way quantisation the blendspace's own
   * {@code snap = (1, 1)} implies, so each corner owns a 45-degree wedge. A bare sign test cannot
   * do this — in combat the mesh faces the AIM point and the camera sits off the shoulder, so
   * walking straight forward leaves a few degrees of lateral component whose SIGN is perfectly
   * definite. That would pick a diagonal clip for a straight-ahead walk, and flip it left/right as
   * the parallax changed sides.
   */
  private static final double AXIS_DEADZONE = 0.3827;

  @Register
  public void onSetMovementDirection(Vector3 movementDirection) {
    // The direction is always world-space (AI writes it directly; PlayerController rotates WASD by
    // the view at the source). The frame a leg animation belongs in is the MESH's own facing, so
    // project onto the mesh's world axes -- global, so the body's yaw and the mesh's local yaw are
    // both accounted for with no compensation term. See meshRoot for the two frames this replaced.
    double dx = movementDirection.getX();
    double dz = movementDirection.getZ();
    double len = Math.sqrt(dx * dx + dz * dz);
    double right, forward;
    if (len < 1e-4) {
      right = 0.0;
      forward = 0.0;
    } else {
      dx /= len;
      dz /= len;
      if (meshRoot != null) {
        Basis b = meshRoot.getGlobalTransform().getBasis();
        Vector3 r = b.getX();                       // the mesh's right
        Vector3 f = b.getZ().times(-1.0f);          // the mesh's forward: this rig is -Z FORWARD
        right = dx * r.getX() + dz * r.getZ();
        forward = dx * f.getX() + dz * f.getZ();
      } else {
        right = dx;                                 // no mesh: world axes, -Z forward
        forward = -dz;
      }
    }
    // Blendspace convention (CharacterVisuals_GodotChan.tscn): +X is walk_right, +Y is
    // walk_forward. So the stored pair IS the blend position and updateAnimationBlend needs no
    // sign flip of its own.
    this.movementDirection.setX(quantize(right));
    this.movementDirection.setY(quantize(forward));

    updateAnimationBlend(currentMovementState);
  }

  private static float quantize(double component) {
    if (component > AXIS_DEADZONE) return 1.0f;
    if (component < -AXIS_DEADZONE) return -1.0f;
    return 0.0f;
  }


  private void updateAnimationBlend(MovementState movementState) {
    if (animationTree == null || currentMovementState == null) return;

    if (tween != null && tween.isValid()) tween.kill();
    tween = createTween();

    if (combat) {
      // Walk and sprint share the +/-1 ring; only IDLE (id 0) collapses to the centre. The stored
      // pair is already in the blendspace's own frame -- see onSetMovementDirection.
      int id = Math.min(movementState.getId(), 1);
      animationDirection.setX(id * movementDirection.getX());
      animationDirection.setY(id * movementDirection.getY());
    } else {
      animationDirection.setX(0.0f);
      animationDirection.setY(movementState.getId());
    }

    NodePath blendPath = blendPathCache.computeIfAbsent(currentStanceName,
        name -> new NodePath("parameters/" + name + "MovementBlend/blend_position"));
    tween.tweenProperty(animationTree, blendPath, animationDirection, animationBlendDuration);
    tween.parallel().tweenProperty(animationTree, ANIM_SPEED_PATH, movementState.animationSpeed, animationSpeedDuration);
  }
}