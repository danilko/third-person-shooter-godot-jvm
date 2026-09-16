package com.openworld.weapon;

import com.openworld.character.AnimationController;
import com.openworld.character.Character;
import com.openworld.net.NetworkManager;
import com.openworld.world.HitInfo;
import com.openworld.world.manager.ImpactManager;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.CapsuleShape3D;
import godot.api.CollisionObject3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.PhysicsDirectSpaceState3D;
import godot.api.PhysicsShapeQueryParameters3D;
import godot.api.RayCast3D;
import godot.api.Time;
import godot.core.Basis;
import godot.core.Dictionary;
import godot.core.RID;
import godot.core.Transform3D;
import godot.core.VariantArray;
import godot.core.Vector3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Base class for every melee weapon (fist, knife, axe) — the Left 4 Dead model, not the Souls one.
 *
 * <p><b>What decides a hit.</b> A generous capsule swept from the CHARACTER'S CHEST, resolved on a
 * short window a few frames after the press, gathering EVERY target in it (cleave) and hitting each
 * once. The swing animation is decorative — it plays, it decides nothing — which is exactly why L4D's
 * melee feels reliable and GTA's does not: nothing is animation-committed, nothing guesses a target
 * for the player, and contact happens at a fixed, readable moment.
 *
 * <p><b>Two legs, like the firearm</b> ({@code WeaponItem.resolveSightPoint} / {@code trace}, shared):
 * <ol>
 *   <li><b>Intent</b> — the camera AimRay says what the player is looking at.</li>
 *   <li><b>Reach</b> — the swing is resolved from the chest toward it, capped at the step's range,
 *       and every target must have a clear line from the chest (cover blocks a swing the same way
 *       it blocks a bullet).</li>
 * </ol>
 * So the camera decides the AIM and the body decides what can be HIT, in FPS and TPS alike. This
 * replaces a 5-ray cone cast from the camera itself — a TPS boom behind and over the shoulder — whose
 * two patches (a range measured from the torso, and a filter rejecting upward normals so a downward
 * camera did not hit the floor) are gone with it.
 *
 * <p><b>The chain.</b> {@link #attackSteps} is walked in order while swings keep coming within
 * {@link #comboResetSeconds}, then starts over — {@code [light, heavy]} is "light first, big second".
 * Subclasses may choose steps differently ({@code KnifeItem}: tap vs hold) through
 * {@link #beginSwing}; the step never knows how it was chosen.
 *
 * <p><b>Feel.</b> On the first contact of a swing: hitstop (the attack one-shot freezes on the pose
 * that connected, and the swing's clock holds with it) and a camera kick. Local and cosmetic —
 * never a global time scale, which in multiplayer would stall every peer for one player's hit.
 */
@Script(className = "MeleeItem")
public class MeleeItem extends WeaponItem {

  /** The bone a swing is measured from. Stance-correct for free: it rides the animated skeleton,
   *  so a crouched swing starts at a crouched chest. */
  private static final String CHEST_BONE = "spine_03";
  /** Fallback when the character has no ragdoll bone to read: an upright chest. */
  private static final Vector3 TORSO_OFFSET = new Vector3(0, 1.2f, 0);
  /** Overlap results per sweep. Own colliders are excluded from the query, so these are all others. */
  private static final int MAX_OVERLAPS = 32;
  /** Cadence is owned by the swing's own phases (canUse), so WeaponController's timer is one frame. */
  private static final double ONE_FRAME = 1.0 / 60.0;

  /** The swings of this weapon's chain, in order. Empty = one swing built from {@code damage}. */
  @Export
  public VariantArray<MeleeAttackStep> attackSteps = new VariantArray<>(MeleeAttackStep.class);

  /** A swing that starts within this many seconds of the previous one ending continues the chain;
   *  a longer pause starts it over from the first step. */
  @Export public float comboResetSeconds = 0.6f;

  /** How long a press that lands mid-swing is remembered and fired the moment the swing frees up —
   *  so a tapped combo is never eaten by recovery. See WeaponController's input buffer. */
  @Export public float inputBufferSeconds = 0.2f;

  private enum Phase { IDLE, WINDUP, ACTIVE, RECOVERY }

  private Phase phase = Phase.IDLE;
  private MeleeAttackStep step;              // the swing in progress
  private int stepIndex = -1;                // its index in steps()
  private boolean cosmetic;                  // a puppet's replay: same timing, no sweep, no damage
  private float phaseLeft;
  private float hitstopLeft;
  private boolean connected;                 // this swing has hit a target (hitstop + kick once)
  private boolean surfaceStruck;             // ...or struck world geometry (one impact)
  private final Set<Long> hitThisSwing = new HashSet<>();
  private int chainCursor = 0;
  private long lastSwingEndMs = -1;

  private MeleeAttackStep fallbackStep;
  private CapsuleShape3D sweepShape;
  private PhysicsShapeQueryParameters3D sweepQuery;
  private VariantArray<RID> ownRids;
  private Node ownRidsFor;

  @Register
  @Override
  public void _ready() {
    super._ready();  // Pickup._ready — group + pickupId registration for replication
    fallbackStep = new MeleeAttackStep();
    fallbackStep.damage = damage;
  }

  // ── The chain ────────────────────────────────────────────────────────────

  /** The steps this weapon swings through — its authored table, or one swing built from {@code damage}. */
  protected final List<MeleeAttackStep> steps() {
    List<MeleeAttackStep> out = new ArrayList<>();
    for (MeleeAttackStep s : attackSteps) if (s != null) out.add(s);
    if (out.isEmpty() && fallbackStep != null) out.add(fallbackStep);
    return out;
  }

  /**
   * Which step the next swing plays, advancing the chain. A swing that starts within
   * {@link #comboResetSeconds} of the previous one ending continues it; otherwise it starts over.
   */
  protected int selectStep() {
    int n = Math.max(1, steps().size());
    long now = Time.INSTANCE.getTicksMsec();
    if (lastSwingEndMs < 0 || now - lastSwingEndMs > (long) (comboResetSeconds * 1000f)) chainCursor = 0;
    int i = chainCursor % n;
    chainCursor = i + 1;
    return i;
  }

  /** How many steps the chain has (the host validates a client's step index against it, N2). */
  public int stepCount() { return Math.max(1, steps().size()); }

  /** The shortest step's whole duration, seconds — the fastest this weapon can legitimately swing (N2). */
  public double shortestStepSeconds() {
    double best = Double.MAX_VALUE;
    for (MeleeAttackStep s : steps()) best = Math.min(best, s.totalDuration());
    return best == Double.MAX_VALUE ? 0.5 : best;
  }

  /** Index of the swing in progress, or -1 when idle. */
  public int currentStepIndex() { return phase == Phase.IDLE ? -1 : stepIndex; }

  /** True from the press until the swing's recovery has finished. */
  public boolean isSwinging() { return phase != Phase.IDLE; }

  // ── WeaponAction ─────────────────────────────────────────────────────────

  @Override
  public void useWeapon() {
    playSwingAudio();
    beginSwing(selectStep(), false);
  }

  /**
   * Puppet replay: the SAME swing — same step, same timing, same animation — minus the sweep, so a
   * remote peer sees and hears the swing while damage stays authority-only. The step is the OWNER's,
   * carried in the snapshot beside {@code fireSeq}, because a puppet's own chain cursor cannot
   * reproduce a knife's tap-vs-hold (not a chain position at all) and drifts from the owner's the
   * moment a swing is dropped or a chain resets at a different time.
   */
  @Override
  public void playRemoteFireCue() {
    playSwingAudio();
    int step = weaponController != null ? weaponController.getReplicatedFireStep() : -1;
    if (step >= 0 && step < Math.max(1, steps().size())) {
      chainCursor = step + 1;          // keep the puppet's own cursor in step with the owner's
      beginSwing(step, true);
    } else {
      beginSwing(selectStep(), true);
    }
  }

  @Override public void stopUseWeapon() {}
  @Override public WeaponType getWeaponType() { return WeaponType.MELEE; }

  /** A new swing may start only once the last one has fully recovered. */
  @Override
  public boolean canUse() { return phase == Phase.IDLE; }

  @Override public double fireInterval() { return ONE_FRAME; }
  @Override public double fireBufferSeconds() { return inputBufferSeconds; }

  /** A swing announces itself when it STARTS (see {@link #beginSwing}), carrying which step it was —
   *  the knife's swing does not even happen on the press. */
  @Override public boolean deferFireEvent() { return true; }

  /** The AI's approach distance: the reach of the swing a fight opens with. */
  @Override
  public float getEffectiveRange() {
    List<MeleeAttackStep> s = steps();
    return s.isEmpty() ? weaponRange : s.get(0).range;
  }

  protected final void playSwingAudio() {
    if (weaponAudio != null && fireAudio != null) {
      weaponAudio.stop();
      weaponAudio.setStream(fireAudio);
      weaponAudio.play();
    }
  }

  /** Start swing {@code index} of {@link #steps()}: its animation, its windup, a clean hit set. */
  protected final void beginSwing(int index, boolean cosmeticOnly) {
    List<MeleeAttackStep> s = steps();
    if (s.isEmpty()) return;
    stepIndex = Math.floorMod(index, s.size());
    step = s.get(stepIndex);
    cosmetic = cosmeticOnly;
    phase = Phase.WINDUP;
    phaseLeft = step.windup;
    hitstopLeft = 0f;
    connected = false;
    surfaceStruck = false;
    hitThisSwing.clear();
    // Announce the swing the instant it starts, with its step — never on a puppet, which is
    // replaying an announcement rather than making one.
    if (!cosmeticOnly && weaponController != null) weaponController.reportFireEvent(stepIndex);
    AnimationController ac = animation();
    if (ac != null) ac.playMeleeAttack(step.animation, step.totalDuration());
  }

  private AnimationController animation() {
    return weaponController != null ? weaponController.animation() : null;
  }

  // ── The swing's clock ────────────────────────────────────────────────────

  @Register
  @Override
  public void _physicsProcess(double delta) {
    if (!serverSwings.isEmpty()) processServerSwings((float) delta);
    if (phase == Phase.IDLE || step == null) return;
    // Hitstop holds the clock as well as the pose, so the rest of the swing keeps the timing the
    // (frozen) animation is showing.
    if (hitstopLeft > 0f) {
      hitstopLeft -= (float) delta;
      if (hitstopLeft <= 0f) {
        AnimationController ac = animation();
        if (ac != null) ac.setMeleeAttackFrozen(false);
      }
      return;
    }
    phaseLeft -= (float) delta;
    if (phase == Phase.WINDUP && phaseLeft <= 0f) {
      phase = Phase.ACTIVE;
      phaseLeft += step.active;
      if (!cosmetic && isNetworkedClient()) sendSwingToHost();
    }
    if (phase == Phase.ACTIVE) {
      // At least one sweep per swing even at active = 0: the frame the window opens always resolves.
      // On a networked client the sweep PREDICTS (impacts, hitstop, kick) and the host applies the damage.
      if (!cosmetic) sweep();
      if (phaseLeft <= 0f) {
        phase = Phase.RECOVERY;
        phaseLeft += step.recovery;
      }
    }
    if (phase == Phase.RECOVERY && phaseLeft <= 0f) {
      phase = Phase.IDLE;
      step = null;
      lastSwingEndMs = Time.INSTANCE.getTicksMsec();
    }
  }

  // ── Networked: the host resolves a client's swing (PLAN.md N2) ────────────────

  /** A client's swing the host is resolving: its step, where it started, where the body was, its aim. */
  private static final class ServerSwing {
    final MeleeAttackStep step; final Vector3 chest0; final Vector3 body0; final Vector3 aim; final long seq;
    final boolean debug; final Set<Long> hits = new HashSet<>(); final List<String> names = new ArrayList<>();
    float left; boolean swept;
    ServerSwing(MeleeAttackStep step, Vector3 chest0, Vector3 body0, Vector3 aim, long seq, boolean debug) {
      this.step = step; this.chest0 = chest0; this.body0 = body0; this.aim = aim; this.seq = seq; this.debug = debug;
      this.left = step.active;
    }
  }

  private final List<ServerSwing> serverSwings = new ArrayList<>();

  /**
   * Host: resolve a client's swing on this copy — the SAME sweep a local swing runs, over the same active
   * window, from the reported chest (carried along with the host copy's body as it moves during the window)
   * along the reported aim, applying damage. The inputs were validated by {@code MeleeValidationPolicy}. The
   * attack's animation and sound already play from the snapshot's fire cue; this adds only the contact.
   */
  public void resolveServerSwing(Vector3 chest, Vector3 aim, int stepIndex, long seq, boolean debug) {
    List<MeleeAttackStep> s = steps();
    if (s.isEmpty() || owningCharacter == null) return;
    MeleeAttackStep st = s.get(Math.floorMod(stepIndex, s.size()));
    serverSwings.add(new ServerSwing(st, chest, owningCharacter.getGlobalPosition(), aim, seq, debug));
    processServerSwings(0f);   // the frame the window opens always resolves, as a local swing does
  }

  private void processServerSwings(float delta) {
    for (java.util.Iterator<ServerSwing> it = serverSwings.iterator(); it.hasNext(); ) {
      ServerSwing sw = it.next();
      if (sw.swept) sw.left -= delta;
      Vector3 chest = sw.chest0.plus(owningCharacter.getGlobalPosition().minus(sw.body0));
      sweepFrom(chest, sw.aim, sw.step, sw.hits, true, false, sw.names);
      sw.swept = true;
      if (sw.left <= 0f) {
        for (int i = 0; i < sw.names.size(); i++) com.openworld.net.NetStats.increment("melee_resolved_hits");
        if (sw.debug) godot.global.GD.INSTANCE.print("[melee] host resolved #" + sw.seq + " -> " + sw.names
            + " chest " + chest + " aim " + sw.aim + " body " + owningCharacter.getGlobalPosition());
        it.remove();
      }
    }
  }

  /** Client: send the swing starting its active window to the host — chest, aim and step (N2). */
  private void sendSwingToHost() {
    if (!(owningCharacter instanceof Character c) || c.characterInfo == null || weaponController == null) return;
    RayCast3D ray = weaponController.getAimRay();
    if (ray == null) return;
    Vector3 chest = chestPoint();
    Vector3 dir = swingDirection(ray, chest);
    Node netNode = getNodeOrNull("/root/NetworkManager");
    if (netNode instanceof NetworkManager net) {
      net.sendMelee(c.characterInfo.characterId, weaponController.getWeapon(), weaponController.nextShotSeq(),
          stepIndex, chest, dir);
    }
  }

  /** True on a networked non-host peer — its swings are predicted locally and resolved by the host. */
  private boolean isNetworkedClient() {
    Node netNode = getNodeOrNull("/root/NetworkManager");
    return netNode instanceof NetworkManager net && net.isNetworked() && !net.isServer();
  }

  // ── The sweep ────────────────────────────────────────────────────────────

  /**
   * One frame of the contact window. Everything the reach capsule overlaps is grouped by the target
   * it belongs to (ImpactManager.resolveTarget — the same walk the damage takes, so ten ragdoll bones
   * of one character are ONE target), and each target not yet hit this swing is traced to from the
   * chest: a clear line connects, anything else in the way blocks.
   */
  private void sweep() {
    if (owningCharacter == null || !owningCharacter.isInsideTree()) return;
    RayCast3D ray = weaponController != null ? weaponController.getAimRay() : null;
    if (ray == null) return;
    Vector3 chest = chestPoint();
    sweepFrom(chest, swingDirection(ray, chest), step, hitThisSwing, !isNetworkedClient(), true, null);
  }

  /**
   * One frame of a contact window from {@code chest} along {@code dir}: {@code authoritative} applies the damage
   * (host / single-player), otherwise only the impact plays (a client's prediction); {@code feel} runs this
   * swing's hitstop and kick on first contact (never on a host resolving someone else's swing). Hit names go to
   * {@code hitsOut} when given.
   */
  private void sweepFrom(Vector3 chest, Vector3 dir, MeleeAttackStep st, Set<Long> hitSet, boolean authoritative,
                         boolean feel, List<String> hitsOut) {
    ImpactManager im = getImpactManager();
    RayCast3D ray = weaponController != null ? weaponController.getAimRay() : null;
    if (im == null || ray == null || owningCharacter == null || !owningCharacter.isInsideTree()) return;
    float range = Math.max(0.1f, st.range);
    Vector3 tip = chest.plus(dir.times(range));

    // 1. Everything in reach.
    PhysicsDirectSpaceState3D space = owningCharacter.getWorld3d().getDirectSpaceState();
    VariantArray<Dictionary<Object, Object>> overlaps = space.intersectShape(sweepQuery(chest, dir, range, st, ray), MAX_OVERLAPS);

    Node vehicle = owningCharacter instanceof Character c ? c.currentVehicleNode : null;
    Map<Long, Node3D> nearest = new HashMap<>();
    Map<Long, Double> nearestDist = new HashMap<>();
    for (Dictionary<Object, Object> hit : overlaps) {
      if (!(hit.get("collider") instanceof Node3D collider) || isOwnBody(collider)) continue;
      Node target = ImpactManager.resolveTarget(collider);
      if (target == null || target.equals(vehicle)) continue;   // world geometry, or our own ride
      long key = target.getInstanceId();
      if (hitSet.contains(key)) continue;
      double d = distanceToSegment(collider.getGlobalPosition(), chest, tip);
      Double best = nearestDist.get(key);
      if (best == null || d < best) { nearest.put(key, collider); nearestDist.put(key, d); }
    }

    // 2. Each one must be reachable from the chest.
    for (Map.Entry<Long, Node3D> e : nearest.entrySet()) {
      Node3D aimAt = e.getValue();
      Vector3 to = aimAt.getGlobalPosition().minus(chest);
      float len = (float) to.length();
      HitInfo info = null;
      if (len < 1e-3f) {
        info = new HitInfo(aimAt, aimAt.getGlobalPosition(), dir.times(-1f));
      } else {
        TraceHit line = trace(ray, chest, to.normalized(), len + st.radius);
        if (line == null) {
          // Nothing reported between us: the chest is already inside the target (point blank). A
          // blocker would have been hit on the way, so a clear line is exactly what this means.
          info = new HitInfo(aimAt, aimAt.getGlobalPosition(), dir.times(-1f));
        } else if (line.node != null
            && e.getKey() == instanceIdOf(ImpactManager.resolveTarget(line.node))) {
          info = new HitInfo(line.node, line.point, line.normal);
        }
      }
      if (info != null) {
        hitSet.add(e.getKey());
        if (hitsOut != null) hitsOut.add(ImpactManager.resolveTarget(info.hitNode).getName().toString());
        connect(im, info, st, authoritative, feel);
      }
      // else: something else is in the way — this target stays live and may connect next frame.
    }

    // 3. A swing into a wall with nothing to hit still lands: one impact on the surface in front.
    if (feel && !connected && !surfaceStruck) {
      TraceHit wall = trace(ray, chest, dir, range);
      if (wall != null && wall.node != null && ImpactManager.resolveTarget(wall.node) == null) {
        surfaceStruck = true;
        im.processVisualHit(new HitInfo(wall.node, wall.point, wall.normal));
      }
    }
  }

  private void connect(ImpactManager im, HitInfo info, MeleeAttackStep st, boolean authoritative, boolean feel) {
    if (authoritative) {
      im.processHit(info, st.damage, getDisplayName(), weaponIcon,
          resolveAttackerName(), resolveAttackerFaction(), resolveAttackerPosition(), resolveAttackerId());
    } else {
      im.processVisualHit(info);
      com.openworld.net.NetStats.increment("melee_predicted_hits");   // a client's own prediction (N2)
    }
    if (!feel || connected) return;
    connected = true;
    if (step.hitstop > 0f) {
      hitstopLeft = step.hitstop;
      AnimationController ac = animation();
      if (ac != null) ac.setMeleeAttackFrozen(true);
    }
    if (step.cameraKick != 0f && owningCharacter instanceof Character c) c.applyRecoil(step.cameraKick, 0.0);
  }

  /**
   * Where this swing goes: from the chest toward what the camera is looking at — unless that point
   * is not ahead of the chest along the view (the camera ray found something BETWEEN the camera and
   * the character, which in third person is behind them), in which case along the view itself.
   * Judged along the VIEW, not the body's facing, so it needs no knowledge of how far the mesh has
   * turned toward the aim yet.
   */
  private Vector3 swingDirection(RayCast3D ray, Vector3 chest) {
    Vector3 view = ray.toGlobal(ray.getTargetPosition()).minus(ray.getGlobalPosition());
    view = view.lengthSquared() > 1e-6 ? view.normalized() : new Vector3(0, 0, -1);
    Vector3 toSight = resolveSightPoint(ray).minus(chest);
    if (toSight.lengthSquared() < 1e-4 || toSight.dot(view) <= 0.0) return view;
    return toSight.normalized();
  }

  /** The attacker's chest: the {@link #CHEST_BONE} ragdoll bone when there is one, else an estimate. */
  private Vector3 chestPoint() {
    if (owningCharacter instanceof Character c) {
      Node3D bone = c.getPhysicalBoneNode(CHEST_BONE);
      if (bone != null) return bone.getGlobalPosition();
    }
    return owningCharacter.getGlobalPosition().plus(TORSO_OFFSET);
  }

  /** A capsule spanning [chest, chest + dir*range], on the AimRay's mask, blind to our own body. */
  private PhysicsShapeQueryParameters3D sweepQuery(Vector3 chest, Vector3 dir, float range, MeleeAttackStep st, RayCast3D ray) {
    if (sweepShape == null) sweepShape = new CapsuleShape3D();
    if (sweepQuery == null) sweepQuery = new PhysicsShapeQueryParameters3D();
    float radius = Math.max(0.05f, st.radius);
    sweepShape.setRadius(radius);
    sweepShape.setHeight(Math.max(2f * radius, range));   // a capsule's height INCLUDES its caps
    // Capsule axis is local +Y: build a basis whose Y is the swing direction.
    Vector3 up = Math.abs(dir.getY()) > 0.95 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0);
    Vector3 x = up.cross(dir).normalized();
    Vector3 z = x.cross(dir).normalized();
    sweepQuery.setShape(sweepShape);
    sweepQuery.setTransform(new Transform3D(new Basis(x, dir, z), chest.plus(dir.times(range * 0.5f))));
    sweepQuery.setCollisionMask(ray.getCollisionMask());
    sweepQuery.setCollideWithAreas(false);
    sweepQuery.setCollideWithBodies(true);
    sweepQuery.setExclude(ownRids());
    return sweepQuery;
  }

  /** RIDs of every collider in the attacker's own subtree — capsule and ragdoll bones — cached per owner. */
  private VariantArray<RID> ownRids() {
    if (ownRids != null && owningCharacter != null && owningCharacter.equals(ownRidsFor)) return ownRids;
    ownRids = new VariantArray<>(RID.class);
    ownRidsFor = owningCharacter;
    if (owningCharacter != null) collectRids(owningCharacter, ownRids);
    return ownRids;
  }

  private static void collectRids(Node n, VariantArray<RID> out) {
    if (n instanceof CollisionObject3D co) out.append(co.getRid());
    for (Node child : n.getChildren()) collectRids(child, out);
  }

  private static long instanceIdOf(Node n) { return n == null ? -1L : n.getInstanceId(); }

  private static double distanceToSegment(Vector3 p, Vector3 a, Vector3 b) {
    Vector3 ab = b.minus(a);
    double t = ab.lengthSquared() < 1e-9 ? 0.0 : p.minus(a).dot(ab) / ab.lengthSquared();
    t = Math.max(0.0, Math.min(1.0, t));
    return p.minus(a.plus(ab.times((float) t))).length();
  }

  /**
   * True when {@code hitNode} is the attacker's own body — the CharacterBody3D itself or anything
   * under it. The query excludes our own RIDs already; this is the backstop for anything it missed.
   */
  private boolean isOwnBody(Node hitNode) {
    if (hitNode == null || owningCharacter == null) return false;
    for (Node n = hitNode; n != null; n = n.getParent()) {
      if (n.equals(owningCharacter)) return true;
    }
    return false;
  }
}
