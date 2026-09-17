package com.openworld.weapon;

import com.openworld.world.manager.ImpactManager;
import com.openworld.item.Pickup;
import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.annotation.Visible;
import godot.api.AnimationPlayer;
import godot.api.AudioStreamPlayer3D;
import godot.api.AudioStreamWAV;
import godot.api.CharacterBody3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.RayCast3D;
import godot.api.Texture2D;
import godot.core.NodePath;
import godot.core.PackedStringArray;
import godot.core.Transform3D;
import godot.core.Vector3;

import static godot.global.GD.min;
import com.openworld.ai.AIBehaviorConfig;
import com.openworld.character.AICharacter;
import com.openworld.character.Character;
import com.openworld.movement.character.Stance;

@Script(className = "WeaponItem")
public class WeaponItem extends Pickup implements WeaponAction {

  // Internal identifier used for event bus payloads and save keys. No spaces.
  @Export public String weaponId = "";

  // Human-readable display name: HUD, kill feed, inventory, interact prompt.
  @Export public String weaponName = "";

  // WeaponSlotType ordinal: 0=PRIMARY 1=SECONDARY 2=MELEE 3=THROWABLE 4=CONSUMABLE 5=FIST
  @Export public int slotType = 0;

  // When false the weapon cannot be dropped (e.g. FistItem). Guards dropCurrentWeapon/dropAllWeapons.
  @Export public boolean isDroppable = true;

  // When true magazine/reserve checks are bypassed — weapon has unlimited uses (e.g. FistItem).
  @Export public boolean isInfiniteAmmo = false;

  // When true, picking this up while the character is unarmed (fist active) makes it
  // the active weapon immediately instead of stowing it in a holster slot — for
  // consumables like throwables where instant access matters more than a deliberate
  // weapon-switch choice. Default false: rifles/pistols/melee always require an
  // explicit slot switch, matching how players expect ranged/melee pickups to behave.
  @Export public boolean autoEquipOnPickup = false;

  /**
   * The grip archetype by NAME ({@link GripArchetype}, PLAN.md 2.8 item 8) — "pistol", "rifle", "sniper", ...
   * The AnimationTree blend index is DERIVED ({@link #weaponPoseIndex()}), so no scene stores a bare number
   * whose meaning depends on a list's order. Decoupled from slot: the same pose whichever slot holds it.
   */
  @Export public String weaponArchetype = "pistol";

  public String getWeaponArchetype() { return weaponArchetype; }
  public void setWeaponArchetype(String v) { weaponArchetype = v; }

  /**
   * Blend position on WeaponAim / WeaponHold / WeaponChangeAnimation for {@link #weaponArchetype}. An unknown
   * name is an authoring error: it is reported once and falls back to the pistol pose rather than to a blend
   * position with nothing at it (which leaves the branch silent and the skeleton at rest — W12).
   */
  @Register
  public int weaponPoseIndex() {
    GripArchetype a = GripArchetype.fromKey(weaponArchetype);
    if (a != null) return a.index();
    if (!warnedArchetype) {
      warnedArchetype = true;
      godot.global.GD.INSTANCE.printErr("WeaponItem " + weaponId + ": unknown weapon_archetype '" + weaponArchetype + "' — using pistol");
    }
    return GripArchetype.PISTOL.index();
  }

  private boolean warnedArchetype = false;

  // Icon shown in the kill feed and radial menu. Set in the inspector per weapon scene.
  @Export public Texture2D weaponIcon = null;

  // Name of the Marker3D socket to attach to when this weapon is the active (held) weapon.
  // Must match a node name registered in WeaponController.socketPaths.
  // ── How this weapon SITS in a socket, and how its own parts MOVE ──────────
  //
  // Both of these are facts about the WEAPON, and both used to have nowhere to live.

  /**
   * Child {@code Marker3D} naming the point this weapon is HELD by — where the hand's socket
   * should land on it. Empty (or missing) keeps the historical behaviour: the weapon's local
   * transform is zeroed, so its ORIGIN lands on the socket.
   *
   * <p><b>This inverts who owns the fit.</b> Zeroing meant the character's socket carried the whole
   * placement, so every weapon needed its own marker on the character rig
   * ({@code MarkerAR4}, {@code MarkerATL4}, ...) — adding a weapon meant editing the CHARACTER, the
   * fit could not travel with the weapon to another rig, and a weapon's own anatomy (where its grip
   * is) was written down nowhere. With a grip point the character needs one socket per GRIP
   * ARCHETYPE and each weapon aligns itself to it, which is the same split
   * {@code weaponPoseIndex} already makes for the pose.
   *
   * <p><b>A conforming weapon does not need one</b>, and none of the shipped weapons has one: the
   * weapon standard (blender/WEAPON_AUTHORING.md) puts the model ORIGIN on the grip, so identity
   * already lands the grip on the archetype socket ({@code SocketRifle}, {@code SocketPistol}, ...).
   * This marker is the escape hatch for an asset whose origin cannot be moved — keep it for that,
   * not as a second place to tune a fit.
   */
  @Export public String gripPoint = "GripPoint";

  /** As {@link #gripPoint}, for the pose this weapon takes when HOLSTERED — a rifle hangs on a back
   *  socket by a different point than the one the hand grips. Empty falls back to the grip point. */
  @Export public String holsterPoint = "";

  /**
   * Optional {@code AnimationPlayer} inside this weapon's own scene, for MOVING PARTS — a shotgun
   * pump, a bolt, a revolver cylinder, a folding stock.
   *
   * <p>It is the weapon's own player on purpose. Putting those parts in the character's skeleton
   * would tie every weapon to one rig and one clip set, and the part has to keep moving while the
   * character is doing something else entirely. What the character and the weapon share is the
   * EVENT, not the animation: {@code WeaponController} plays both from the same fire/reload moment,
   * on the authority AND on a puppet, so a remote peer sees the pump cycle too.
   *
   * <p><b>The clips are authored in the weapon's .blend</b>, not keyed in the scene: each moving part is
   * its own object with its ORIGIN ON ITS PIVOT, its motion an action on an NLA track, and the glTF
   * import puts them on the model's own {@code AnimationPlayer} — which is where this points by default.
   * A part keyed in Godot has its origin on the weapon's grip, so a rotation about its real axis has to
   * be written as a rotation AND a compensating translation per key (SNR1's bolt was, until
   * 2026-09-16); with the pivot as the origin a lift is one rotation curve, editable against the model.
   * {@code blender/tools/build_weapon.py} refuses an export missing a clip the scene names, because
   * {@link #playMotion} is silent about it.
   */
  @Export public NodePath weaponAnimatorPath = new NodePath("Model/AnimationPlayer");

  /** Clip on {@link #weaponAnimatorPath} to play per shot. Empty = this weapon has no moving parts. */
  @Export public String fireAnimation = "";

  /** Clip on {@link #weaponAnimatorPath} to play on reload. Empty = none. */
  @Export public String reloadAnimation = "";

  private AnimationPlayer weaponAnimator;
  private boolean weaponAnimatorResolved = false;

  /**
   * The local transform this weapon takes when parented to {@code socketName}'s marker, so that its
   * grip (or holster) point coincides with the socket. Identity when it declares none.
   */
  @Register
  public Transform3D alignmentFor(boolean holstered) {
    String name = holstered && !holsterPoint.isEmpty() ? holsterPoint : gripPoint;
    if (name == null || name.isEmpty()) return new Transform3D();
    Node n = getNodeOrNull(new NodePath(name));
    if (!(n instanceof Node3D marker)) return new Transform3D();
    return marker.getTransform().affineInverse();
  }

  /**
   * Play one of this weapon's own motion clips, if it has an animator and the clip exists.
   *
   * <p>Silent about a missing clip by design — a weapon with no moving parts names none, and every
   * call site fires for every weapon.
   */
  public void playMotion(String clip) {
    if (clip == null || clip.isEmpty()) return;
    if (!weaponAnimatorResolved) {
      weaponAnimatorResolved = true;
      Node n = (weaponAnimatorPath == null || weaponAnimatorPath.isEmpty())
              ? null : getNodeOrNull(weaponAnimatorPath);
      if (n instanceof AnimationPlayer ap) weaponAnimator = ap;
    }
    if (weaponAnimator == null || !weaponAnimator.hasAnimation(clip)) return;
    weaponAnimator.stop();
    weaponAnimator.play(clip, -1.0, 1.0f, false);
  }

  @Export public String holdSocket = "";

  // Names of Marker3D sockets to try (in order) when parking this weapon in inventory.
  // Each name must match a node registered in WeaponController.socketPaths.
  // The first socket with no other weapon in it is used. Empty array = hide when inactive.
  @Export public PackedStringArray holsterSockets = new PackedStringArray();

  /**
   * This weapon's tuning table ({@link WeaponStats}, PLAN.md 2.8 item 1). Assigning it copies every value onto
   * the fields below, which are {@code @Visible} rather than exported: registered (so a probe or a debug tool
   * can still read or nudge one live) but no longer stored in the weapon scene, so the .tres is the one place
   * a weapon is balanced. A weapon with no stats keeps its field initialisers (and its constructor's values).
   */
  @Export public WeaponStats stats;

  public WeaponStats getStats() { return stats; }

  public void setStats(WeaponStats v) {
    stats = v;
    if (v != null) applyStats(v);
  }

  /** Copy {@code s} onto this weapon's tuning fields. Subclasses copy their own rows and call super. */
  protected void applyStats(WeaponStats s) {
    spread = s.spread; bloomPerShot = s.bloomPerShot; bloomDecaySpeed = s.bloomDecaySpeed; bloomMax = s.bloomMax;
    reloadSpeed = s.reloadSpeed; switchSpeed = s.switchSpeed; fireRate = s.fireRate; auto = s.auto;
    magazineSize = s.magazineSize; reserveMax = s.reserveMax; recoil = s.recoil; damage = s.damage;
    kickBack = s.kickBack; kickPitch = s.kickPitch; kickSpring = s.kickSpring; kickDamping = s.kickDamping;
    weaponRange = s.weaponRange;
  }

  @Visible public float spread = 0.0f;
  // Inaccuracy added per shot; decays at bloomDecaySpeed when not firing.
  // Set bloomDecaySpeed lower than (bloomPerShot × fireRate) for bloom to
  // accumulate during full-auto. Set it higher for semi-auto tap-fire weapons
  // where each shot clears before the next.
  @Visible public float bloomPerShot    = 0.0f;
  @Visible public float bloomDecaySpeed = 1.0f;
  @Visible public float bloomMax        = 0.25f;
  @Visible public float reloadSpeed = 0.8f;
  // switchSpeed is a rate: deploy time = 1/switchSpeed. 2.2 ⇒ ~0.45 s deploy (CS/PUBG-snappy); the
  // post-deploy fire lockout is a small fixed constant (WeaponController.DRAW_SETTLE_SECONDS), not a
  // second full 1/switchSpeed, so total switch ≈ deploy time.
  @Visible public float switchSpeed = 2.2f;
  @Visible public float fireRate = 8.0f;
  @Visible public boolean auto = true;
  @Export public int magazine = 40;
  @Visible public int magazineSize = 40;
  @Export public int reserve = 40;
  @Visible public int reserveMax = 40;
  @Visible public float recoil = 0.8f;
  @Visible public float damage = 25.0f;

  // ── The VISIBLE weapon kick (PLAN.md A3, character.WeaponRecoilModifier) ────────────────────
  // Separate from `recoil` above, which is the CAMERA kick (the aim), and from fireAnimation, which
  // is the weapon's own moving parts. These four are the spring the firing arm takes per shot: a
  // step of kickBack/kickPitch, returned by a spring of angular frequency kickSpring (settle ≈
  // 4/kickSpring seconds) and ratio kickDamping (1 = critically damped, no bounce). They are ZERO by
  // default, so a weapon that has not authored a kick does not kick — which is the right answer for
  // a fist, a knife and a thrown grenade, and makes an unauthored firearm visible rather than
  // silently inheriting a rifle's feel.
  /** Push-back along the bore per shot, metres. */
  @Visible public float kickBack = 0.0f;
  /** Muzzle rise per shot, degrees. No yaw term: a yaw kick would fight WeaponItem.pointsAtAim (W21). */
  @Visible public float kickPitch = 0.0f;
  /** The return spring's angular frequency, 1/s. Lower = a heavier gun that settles slower. */
  @Visible public float kickSpring = 22.0f;
  /** The return spring's damping ratio. 1 = critically damped; below 1 overshoots. */
  @Visible public float kickDamping = 1.0f;

  // Effective engagement distance in metres. AI uses this (via AICharacter.getEffectiveAttackRange)
  // to cap how far it will try to fight with this weapon — e.g. a melee AI closes to arm's
  // reach instead of standing at AIBehaviorConfig.attackRange and swinging at empty air.
  // MeleeItem overrides getEffectiveRange() to return its opening swing's reach, so the two stay in sync.
  @Visible public float weaponRange = 50.0f;
  @Export public AudioStreamWAV fireAudio;
  @Export public AudioStreamWAV reloadAudio;

  // ── Injected references (shared by all weapon subtypes) ─────────────────────
  // Populated by WeaponController.injectCharacterRefs() after discovery/pickup.
  // Cleared (set to null) when the weapon is returned to the world.
  protected WeaponController       weaponController;
  protected CharacterBody3D        owningCharacter;
  protected AudioStreamPlayer3D    weaponAudio;
  private   ImpactManager          impactManager;

  /** Called by WeaponController after discovery or pickup. Pass nulls to clear on world return. */
  public void setup(WeaponController controller, CharacterBody3D character, AudioStreamPlayer3D audio) {
    this.weaponController = controller;
    this.owningCharacter  = character;
    this.weaponAudio      = audio;
    this.impactManager    = null;
  }

  /** Lazily resolves and caches the world ImpactManager (single group lookup per weapon). */
  protected ImpactManager getImpactManager() {
    if (impactManager != null) return impactManager;
    Node found = getTree().getFirstNodeInGroup("impact_manager");
    if (found instanceof ImpactManager im) impactManager = im;
    return impactManager;
  }

  /** Attacker display name for kill-feed and event-bus payloads. */
  protected String resolveAttackerName() {
    if (owningCharacter instanceof Character c && c.characterInfo != null) return c.characterInfo.displayName;
    return owningCharacter != null ? owningCharacter.getName().toString() : "";
  }

  /** The attacker's characterId, for the hit marker's "was that me" (PLAN.md 2.8 item 9). "" when unknown. */
  protected String resolveAttackerId() {
    if (owningCharacter instanceof Character c && c.characterInfo != null && c.characterInfo.characterId != null) {
      return c.characterInfo.characterId;
    }
    return "";
  }

  /** Attacker faction string for faction/friendly-fire checks. */
  protected String resolveAttackerFaction() {
    if (owningCharacter instanceof Character c && c.characterInfo != null) return c.characterInfo.faction;
    return "";
  }

  /** World position of the shooter, for the HUD damage-direction indicator. Null when unknown. */
  protected godot.core.Vector3 resolveAttackerPosition() {
    return owningCharacter != null ? owningCharacter.getGlobalPosition() : null;
  }

  /**
   * The exported {@code slotType} ordinal as its enum. Not {@code getSlotType} — that shape
   * would bind the int field to an enum-typed accessor property (see AICharacter).
   */
  public WeaponSlotType resolveSlotType() {
    WeaponSlotType[] types = WeaponSlotType.values();
    if (slotType >= 0 && slotType < types.length) return types[slotType];
    return WeaponSlotType.PRIMARY;
  }

  /** Returns weaponName if set, otherwise the node name. Use everywhere a display name is needed. */
  public String getDisplayName() {
    return weaponName.isEmpty() ? getName().toString() : weaponName;
  }

  // ── Pickup callbacks ──────────────────────────────────────────────────────

  /**
   * Registers this weapon's kill-feed icon under its weaponName so the networked
   * kill feed can resolve it locally (textures never cross the wire — see
   * {@link IconRegistry}). MUST call super._ready() or the Pickup base never
   * registers for replication.
   */
  @Register
  @Override
  public void _ready() {
    super._ready();
    IconRegistry.register(weaponName, weaponIcon);
  }

  /**
   * Auto-pickup when the character's matching slot is free; otherwise show the
   * interact prompt so the player consciously chooses to swap their current weapon.
   */
  @Override
  protected boolean shouldAutoPickup(Node character) {
    Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
    if (wcNode instanceof WeaponController wc) return wc.isSlotFreeFor(resolveSlotType());
    return false;
  }

  @Override
  protected void onCharacterEntered(Node character) {
    Node wcNode = character.getNodeOrNull(WEAPON_CONTROLLER_PATH);
    if (wcNode instanceof WeaponController wc) {
      // Set equipped immediately to prevent re-triggering during the deferred frame,
      // then queue the actual equip so reparent() runs in _process (idle), not
      // inside the Area3D body_entered signal (physics callback).
      equipped = true;
      wc.requestEquip(this);
    }
  }

  @Override
  protected String getInteractLabel() {
    return getDisplayName();
  }

  // ── Replication hooks (Pickup base) ───────────────────────────────────────
  // MSG_PICKUP_TAKEN carries the item's magazine/reserve at take time so every peer's
  // copy of the weapon ends up byte-identical regardless of prior local drift.

  @Override public int getReplicatedMagazine() { return magazine; }
  @Override public int getReplicatedReserve()  { return reserve; }

  @Override
  protected void stampReplicatedAmmo(int replicatedMagazine, int replicatedReserve) {
    magazine = replicatedMagazine;
    reserve  = replicatedReserve;
  }

  // ── Two-stage ("2-way") resolution, shared by every weapon that aims ────────
  // Stage 1 (sight) — the camera AimRay (player) or the ray AttackState snapped onto its scatter
  //                   point (AI) says WHERE this attack is aimed.
  // Stage 2 (reach) — the attack itself is resolved from the CHARACTER toward that point: a
  //                   firearm traces from its Muzzle, a melee weapon sweeps from the chest. So
  //                   the camera decides the aim and the body decides what can actually be hit.
  // Both halves live here so a firearm and a melee weapon cannot come to disagree about either.

  /** Ignore stage-1 hits this close to the sight origin (camera near-plane / degenerate hits). */
  protected static final float SIGHT_MIN_DISTANCE = 0.1f;
  /** Ignore stage-2 hits this close to the origin. Small on purpose: a wall 10 cm from the barrel MUST block. */
  protected static final float MUZZLE_MIN_DISTANCE = 0.02f;

  /**
   * Stage 1 — where this attack is AIMED: the world point the sight ray is currently on. This is the
   * same point the crosshair sits on and (via UserCommand.aimTargetPosition) the point the spine IK
   * and the visible gun converge on, so what you see aimed at is what the bullet is sent toward.
   * Falls back to the ray's far end when it hits nothing.
   */
  protected Vector3 resolveSightPoint(RayCast3D ray) {
    // A SEATED shooter aims through the carrier's firing sector, not through the camera. The camera
    // is free to look anywhere (it is a chase camera; in third person it may be behind the car
    // entirely), so its ray is not this shot's direction -- the clamped aim point is, and it is
    // already the point the gun is visibly pointing at (Character.applySeatedAimTarget). Reading it
    // here is what makes the two agree; before this the gun stopped at the seat's limit and the
    // bullet carried on to whatever the camera had found, which is the drive-by bug.
    if (owningCharacter instanceof Character c && c.isSeatedAimAnchored()) {
      Vector3 seated = c.getAimTargetPosition();
      // getAimTargetPosition falls back to the body origin when the marker is missing; a shot
      // toward our own feet is worse than the camera ray, so fall through on a degenerate point.
      if (seated.minus(c.getGlobalPosition()).lengthSquared() > 0.25) return seated;
    }
    // An AI aims a shot by pointing its ray at the chosen point on the frame it presses fire
    // (AttackState -> AICharacter.snapAimRay). The fire gate can hold that press a frame or two
    // (pointsAtAim), and the snap is in the RAY's local space, so by the time the shot resolves the
    // camera rig has carried the ray somewhere else -- measured on the AimWorkbench bench: a shot
    // held 2 frames after the target swung behind the AI went nowhere. Re-point it at the aim point
    // the command still carries (AttackState sends the same point every frame), which is exactly the
    // original snap whenever the shot was not held. Only for weapons the gate can hold: melee is
    // never held, so its sight leg is left exactly as it was.
    if (launchesTowardAim() && owningCharacter instanceof AICharacter ai) {
      Vector3 aimAt = ai.getAimTargetPosition();
      // getAimTargetPosition falls back to the body origin without a marker; never aim at our feet.
      if (aimAt.minus(ai.getGlobalPosition()).lengthSquared() > 0.25) ai.snapAimRay(aimAt);
    }
    ray.forceRaycastUpdate();
    Vector3 origin = ray.getGlobalPosition();
    Vector3 far = ray.toGlobal(ray.getTargetPosition());
    boolean hit = ray.isColliding() && ray.getCollisionPoint().minus(origin).length() > SIGHT_MIN_DISTANCE;
    Vector3 end = hit ? ray.getCollisionPoint() : far;
    // The RayCast3D is one long Jolt query and can step over a small hitbox far away (util.RayWindows):
    // the sight point would land on the ground BEHIND the target, and a muzzle leg converging there
    // passes beside it. Ask the bodies near the line again with short rays.
    Vector3 toFar = far.minus(origin);
    double len = toFar.length();
    if (len > 1e-3) {
      TraceHit near = nearerSmallShape(ray, origin, toFar.div(len), (float) end.minus(origin).length(), null);
      if (near != null && near.point.minus(origin).length() > SIGHT_MIN_DISTANCE) return near.point;
    }
    return end;
  }

  /** Immutable result of one trace — read after the borrowed RayCast3D has been put back. */
  protected static final class TraceHit {
    final Node node;
    final Vector3 point;
    final Vector3 normal;
    TraceHit(Node node, Vector3 point, Vector3 normal) {
      this.node = node; this.point = point; this.normal = normal;
    }
  }

  /**
   * Traces from an arbitrary world origin along {@code dir} with the AimRay's SETTINGS — its collision mask,
   * body/area flags and self-exceptions — as a stateless space query (PLAN.md 2.8 item 6). It used to borrow
   * the ray node itself (move it, force an update, put it back), which moved the {@code AimTarget} hanging off
   * it for the duration and would leave both displaced if anything in between threw. The exceptions come from
   * {@code util.RayExclusions}, the one owner that also adds them to the node.
   */
  protected TraceHit trace(RayCast3D ray, Vector3 origin, Vector3 dir, float range) {
    if (ray == null || !ray.isInsideTree() || ray.getWorld3d() == null) return null;
    godot.api.PhysicsDirectSpaceState3D space = ray.getWorld3d().getDirectSpaceState();
    if (space == null) return null;
    TraceHit hit = query(space, ray, origin, origin, origin.plus(dir.times(range)));
    float reached = hit != null ? (float) hit.point.minus(origin).length() : range;
    return nearerSmallShape(ray, origin, dir, reached, hit);
  }

  /** One ray query from {@code from} to {@code to} with the AimRay's settings; distances measured from {@code origin}. */
  private static TraceHit query(godot.api.PhysicsDirectSpaceState3D space, RayCast3D ray, Vector3 origin,
                                Vector3 from, Vector3 to) {
    godot.core.VariantArray<godot.core.RID> exclude = com.openworld.util.RayExclusions.of(ray);
    if (ray.getExcludeParentBody() && ray.getParent() instanceof godot.api.CollisionObject3D parent) {
      exclude.add(parent.getRid());
    }
    godot.api.PhysicsRayQueryParameters3D q = godot.api.PhysicsRayQueryParameters3D.Companion.create(
        from, to, ray.getCollisionMask(), exclude);
    q.setCollideWithBodies(ray.isCollideWithBodiesEnabled());
    q.setCollideWithAreas(ray.isCollideWithAreasEnabled());
    q.setHitFromInside(ray.isHitFromInsideEnabled());
    q.setHitBackFaces(ray.isHitBackFacesEnabled());
    godot.core.Dictionary<java.lang.Object, java.lang.Object> hit = space.intersectRay(q);
    if (hit.isEmpty()) return null;
    if (!(hit.get("position") instanceof Vector3 point)) return null;
    if (point.minus(origin).length() <= MUZZLE_MIN_DISTANCE) return null;
    Vector3 normal = hit.get("normal") instanceof Vector3 n ? n : Vector3.Companion.getZERO();
    return new TraceHit(hit.get("collider") instanceof Node nd ? nd : null, point, normal);
  }

  /** The precise small-shape pass below; registered only so a probe can switch it off as its control
   *  ({@code probe_sniper_world.gd -- --control}). Always on in play. */
  @Visible public boolean smallShapeWindows = true;

  /** Grid cells this far either side of a ray are searched for bodies: REACH plus a quarter second of a
   *  fast vehicle between two grid updates. */
  private static final float WINDOW_SEARCH_RADIUS = (float) com.openworld.util.RayWindows.REACH + 12f;

  /**
   * The nearest hit on a small shape the long query from {@code origin} may have stepped over before
   * {@code reached}, else {@code best}. Jolt's ray-vs-capsule test fails when the ray starts far from a
   * small capsule — a 5.6 cm thigh hitbox from ~230 m — so every character or vehicle standing near the
   * line is asked again with a short ray that starts a few metres before it ({@code util.RayWindows} has
   * the measurement and the window rule). Bodies come from {@code SpatialEntityGrid}, or the "characters"
   * group where the AutoLoad is absent.
   */
  private TraceHit nearerSmallShape(RayCast3D ray, Vector3 origin, Vector3 dir, float reached, TraceHit best) {
    if (!smallShapeWindows || reached <= com.openworld.util.RayWindows.SAFE_START) return best;
    godot.api.PhysicsDirectSpaceState3D space = ray.getWorld3d() != null ? ray.getWorld3d().getDirectSpaceState() : null;
    if (space == null) return best;
    java.util.Collection<Node> bodies = new java.util.LinkedHashSet<>();
    var grid = com.openworld.world.SpatialEntityGrid.get();
    if (grid != null) {
      grid.querySegment(origin, origin.plus(dir.times(reached)), WINDOW_SEARCH_RADIUS, bodies);
    } else if (isInsideTree()) {
      for (Object o : getTree().getNodesInGroup(new godot.core.StringName("characters"))) {
        if (o instanceof Node n) bodies.add(n);
      }
    }
    java.util.List<double[]> roots = new java.util.ArrayList<>();
    for (Node n : bodies) {
      if (n == owningCharacter || !(n instanceof Node3D n3) || !godot.global.GD.INSTANCE.isInstanceValid(n3)
          || !n3.isInsideTree()) continue;
      Vector3 p = n3.getGlobalPosition();
      roots.add(new double[] {p.getX(), p.getY(), p.getZ()});
    }
    if (roots.isEmpty()) return best;
    double bestDist = best != null ? best.point.minus(origin).length() : reached;
    for (double[] w : com.openworld.util.RayWindows.windows(
        new double[] {origin.getX(), origin.getY(), origin.getZ()},
        new double[] {dir.getX(), dir.getY(), dir.getZ()}, reached, roots)) {
      if (w[0] >= bestDist) break;
      TraceHit h = query(space, ray, origin, origin.plus(dir.times(w[0])), origin.plus(dir.times(Math.min(w[1], bestDist))));
      if (h != null) {
        double d = h.point.minus(origin).length();
        if (d < bestDist) { best = h; bestDist = d; }
      }
    }
    return best;
  }

  /** Current holder (set by WeaponController.setup), or null while in the world — used for the late-join pickup baseline. */
  public CharacterBody3D getOwningCharacter() { return owningCharacter; }

  // ── WeaponAction defaults — concrete subclasses override what they need ───
  // Semi-auto lock: set true in useWeapon() after a shot, cleared on stopUseWeapon()
  // (i.e. on trigger release). Subclasses gate canUse() on isSemiAutoReady() so that a
  // non-auto weapon produces exactly one use per trigger pull regardless of fireRate.
  protected boolean isWeaponFired = false;

  /**
   * True when the trigger may produce another use: full-auto weapons (auto) always,
   * semi-auto weapons only after the trigger was released since the last shot.
   */
  protected boolean isSemiAutoReady() { return !isWeaponFired || auto; }

  @Override public void useWeapon() {}
  // Trigger released — clear the semi-auto lock so the next pull can fire.
  @Override public void stopUseWeapon() { isWeaponFired = false; }
  @Override public void onReloadComplete() {}
  @Override public boolean canUse() { return false; }
  @Override public WeaponType getWeaponType() { return WeaponType.RANGED; }
  @Override public float getCurrentSpreadDeg() { return 0f; }

  /**
   * Crosshair openness for the CURRENT accuracy state, as a 0..1 fraction of this weapon's own
   * worst-case spread envelope — a purely cosmetic, weapon-normalized signal for the HUD reticle
   * (the real bullet cone is {@link #getCurrentSpreadDeg()}). Normalizing per weapon means the
   * crosshair uses the same fixed pixel range for every gun (no per-weapon crosshair tuning, never
   * runs off-screen), while still reflecting movement/bloom/stance changes within that range.
   * Default 0 (weapons with no spread keep a tight reticle).
   */
  public float getCrosshairFraction() { return 0f; }

  @Override public void onSetStance(Stance stance) {}

  /**
   * Seconds this weapon is busy after one use — WeaponController holds the next onWeaponFire off for
   * this long. A gun's cadence is its fire rate; a melee weapon's is the swing it just started, which
   * differs step to step (MeleeItem overrides). A method, not an override of getFireRate(): that
   * accessor is half of the exported fireRate property, and a derived value there would rewrite it.
   */
  public double fireInterval() { return 1.0 / Math.max(0.01f, getFireRate()); }

  /**
   * How long a press that arrives while this weapon is still busy is remembered and fired as soon as
   * it frees up. 0 (the default) disables buffering — for a gun a buffered shot is a shot the player
   * did not ask for. Melee buffers, so a tapped combo is not eaten by recovery.
   */
  public double fireBufferSeconds() { return 0.0; }

  /**
   * How far (yaw, degrees) the held weapon may point away from its aim point and still fire. The
   * steady-state gap is 1-3 degrees (the aim pose), so this only bites during a turn.
   */
  public static final double FIRE_AIM_TOLERANCE_DEG = 15.0;

  /**
   * True for a weapon whose shot or projectile LEAVES THE WEAPON toward the aim point (a gun's
   * muzzle trace, a launched rocket, a thrown grenade), so the weapon must be pointing at that
   * point before it fires. False for melee, which resolves from the chest (W16).
   */
  protected boolean launchesTowardAim() { return false; }

  /**
   * This weapon's scope, or null for a weapon with none (PLAN.md 2.8 item 4). A composed {@link ScopeConfig}
   * rather than four base-class hooks returning 0/false: any firearm that references one is scoped, with
   * no subclass. A config whose {@code fov} is 0 counts as no scope.
   *
   * <p>Named as a question-ish reader, not {@code getScope}, so godot-jvm cannot merge it into a
   * getter-only registered property (CLAUDE.md, "A Java field and its JavaBean accessors are ONE property").
   */
  public ScopeConfig scopeConfig() { return null; }

  /**
   * Whether the aim modifiers should aim this weapon's BORE (its -Z) rather than the chest
   * ({@code ShoulderAimModifier}, PLAN.md A2.1): exactly the weapons the fire gate holds, because
   * those are the ones whose shot leaves the weapon. Public view of {@link #launchesTowardAim()} for
   * the character package; named as a question so it is not merged into a registered property.
   */
  public boolean aimsAlongBore() { return launchesTowardAim(); }

  /**
   * Whether the held weapon points at the aim point closely enough to fire ({@link
   * #FIRE_AIM_TOLERANCE_DEG}, yaw only). Named as a question, not {@code isX}: a getter-shaped
   * method would be merged into a registered property.
   *
   * <p><b>Why (PLAN.md 0.2):</b> every view traces the shot from the animated gun, so a shot fired
   * while the body is still turning after a flick leaves a gun pointing the old way and crosses the
   * shooter's own body. {@code MovementController.keepAimWithinReach} keeps the body within the aim
   * reach, which leaves one frame — the camera has moved, the body has not been updated yet — where
   * this gate holds the press ({@code WeaponController.onWeaponFire}). Measured with
   * {@code tools/godot/probe_self_hit.gd}.
   *
   * <p>Yaw only, on purpose: the elevation gap at the top of a stance's view range is a documented
   * gun-vs-reticle difference (W5), and gating on it would refuse shots there outright. A seated
   * occupant is exempt — the carrier clamps that aim point itself ({@code Vehicle.clampSeatAim}).
   */
  public boolean pointsAtAim() {
    if (!launchesTowardAim() || !(owningCharacter instanceof Character c)) return true;
    if (c.currentVehicleNode != null) return true;
    Vector3 toAim = c.getAimTargetPosition().minus(getGlobalPosition());
    Vector3 forward = getGlobalBasis().getZ().times(-1f);
    toAim = new Vector3(toAim.getX(), 0f, toAim.getZ());
    forward = new Vector3(forward.getX(), 0f, forward.getZ());
    // An aim point on top of the weapon, or a weapon pointing straight up or down, has no yaw.
    if (toAim.lengthSquared() < 0.25f || forward.lengthSquared() < 1e-4f) return true;
    return Math.toDegrees(forward.angleTo(toAim)) <= FIRE_AIM_TOLERANCE_DEG;
  }

  /**
   * True when this weapon announces its own fire event rather than having {@code WeaponController}
   * bump the counter on the press. A gun fires when the trigger is pulled, so the press IS the shot;
   * a melee weapon's swing may start later (a knife charges on the press and swings on the release)
   * and carries WHICH swing it was. See {@code WeaponController.reportFireEvent}.
   */
  public boolean deferFireEvent() { return false; }

  /**
   * Whether dropping this weapon should create a world pickup.
   * Default: matches isDroppable. ThrowableItem overrides to block empty drops.
   */
  public boolean shouldDropToWorld() { return isDroppable; }

  /**
   * Called by WeaponController immediately after useWeapon() empties the magazine.
   * Default is a no-op. ThrowableItem overrides to auto-clear the slot so any
   * other throwable type can be picked up without needing an interact-to-swap.
   */
  public void onMagazineEmpty() {}

  /**
   * Whether the shot that empties the magazine should START THE RELOAD BY ITSELF — the default in
   * every modern shooter (CS, PUBG, COD): a player who has just fired their last round should not
   * have to press a dead trigger to discover it, and on a slow weapon (a bolt rifle, a launcher)
   * that discovery costs a whole reload's worth of time.
   *
   * <p><b>It cannot loop, by construction.</b> The worry is a weapon that is empty AND dry
   * re-triggering a reload for ever, so the reload itself is the gate rather than the caller:
   * {@code WeaponController.onWeaponReload} returns immediately when the reserve is 0 or a reload is
   * already running, so this hook can fire as often as it likes and a dry weapon does nothing at
   * all. There is no timer, no retry and no state to get stuck in — the only thing that can start a
   * reload is ammo actually being available.
   */
  @Export public boolean autoReloadOnEmpty = true;

  public void setAutoReloadOnEmpty(boolean v) { autoReloadOnEmpty = v; }

  public boolean isAutoReloadOnEmpty() { return autoReloadOnEmpty; }

  /**
   * The derived answer the controller asks. Named as a question so godot-jvm does not merge it into
   * the exported property above (the {@code resolveX()}/{@code deferFireEvent()} idiom): an
   * infinite-ammo weapon has no magazine to fill, and {@code ThrowableItem} overrides it to false
   * because an emptied grenade stack CLEARS ITS SLOT ({@link #onMagazineEmpty}) instead of reloading.
   */
  public boolean autoReloadsOnEmpty() { return autoReloadOnEmpty && !isInfiniteAmmo; }

  /**
   * Cosmetic remote replay on non-authority peers (puppets), invoked by
   * WeaponController.playRemoteFireCue when the snapshot's fireSeq counter advances.
   * Default no-op; FirearmItem replays muzzle/tracer, throwable/projectile weapons spawn a
   * non-damaging projectile so every peer sees the shot/throw + explosion. Never consumes
   * ammo or applies damage — those stay authority-side.
   */
  public void playRemoteFireCue() {}

  public void decrementMagazine() {
    if (magazine > 0) magazine--;
  }

  public void fillMagazine() {
    int emptySpace = magazineSize - magazine;
    magazine += min(emptySpace, reserve);
    reserve -= min(emptySpace, reserve);
  }

  public void fillAmmo() {
    reserve = reserveMax;
    magazine = magazineSize;
  }

  public float getSpread() { return spread; }
  public void setSpread(float spread) { this.spread = spread; }

  public float getBloomPerShot()    { return bloomPerShot; }
  public void  setBloomPerShot(float v)    { bloomPerShot    = v; }
  public float getBloomDecaySpeed() { return bloomDecaySpeed; }
  public void  setBloomDecaySpeed(float v) { bloomDecaySpeed = v; }
  public float getBloomMax()        { return bloomMax; }
  public void  setBloomMax(float v)        { bloomMax        = v; }

  public float getReloadSpeed() { return reloadSpeed; }
  public void setReloadSpeed(float reloadSpeed) { this.reloadSpeed = reloadSpeed; }

  public float getSwitchSpeed() { return switchSpeed; }
  public void setSwitchSpeed(float switchSpeed) { this.switchSpeed = switchSpeed; }

  public float getFireRate() { return fireRate; }
  public void setFireRate(float fireRate) { this.fireRate = fireRate; }

  public boolean isAuto() { return auto; }
  public void setAuto(boolean auto) { this.auto = auto; }

  public int getMagazine() { return magazine; }
  public void setMagazine(int magazine) { this.magazine = magazine; }

  public int getMagazineSize() { return magazineSize; }
  public void setMagazineSize(int magazineSize) { this.magazineSize = magazineSize; }

  public int getReserve() { return reserve; }
  public void setReserve(int reserve) { this.reserve = reserve; }

  public int getReserveMax() { return reserveMax; }
  public void setReserveMax(int reserveMax) { this.reserveMax = reserveMax; }

  public float getRecoil() { return recoil; }
  public void setRecoil(float recoil) { this.recoil = recoil; }

  public float getKickBack() { return kickBack; }
  public void setKickBack(float kickBack) { this.kickBack = kickBack; }

  public float getKickPitch() { return kickPitch; }
  public void setKickPitch(float kickPitch) { this.kickPitch = kickPitch; }

  public float getKickSpring() { return kickSpring; }
  public void setKickSpring(float kickSpring) { this.kickSpring = kickSpring; }

  public float getKickDamping() { return kickDamping; }
  public void setKickDamping(float kickDamping) { this.kickDamping = kickDamping; }

  /** Effective engagement distance in metres — MeleeItem returns its opening swing's reach. */
  public float getEffectiveRange() { return weaponRange; }

  public AudioStreamWAV getFireAudio() { return fireAudio; }
  public void setFireAudio(AudioStreamWAV fireAudio) { this.fireAudio = fireAudio; }

  public AudioStreamWAV getReloadAudio() { return reloadAudio; }
  public void setReloadAudio(AudioStreamWAV reloadAudio) { this.reloadAudio = reloadAudio; }
}
