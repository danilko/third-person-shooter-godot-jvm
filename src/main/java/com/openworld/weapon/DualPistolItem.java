package com.openworld.weapon;

import godot.annotation.Export;
import godot.annotation.Register;
import godot.annotation.Script;
import godot.api.BoneAttachment3D;
import godot.api.Node;
import godot.api.Node3D;
import godot.api.Skeleton3D;
import godot.core.Basis;
import godot.core.Transform3D;
import godot.core.Vector3;
import godot.global.GD;

/**
 * Dual pistols (CS's Dual Berettas, L4D's dual pistols): an ordinary {@link FirearmItem} in the right hand, plus a
 * second pistol that lives in the LEFT hand while the weapon is held.
 *
 * <p>The right gun is the item itself, placed by the right-hand socket like any pistol. The left gun is the
 * scene's {@code ModelLeft} subtree (the model + {@code MuzzleLeft}). While the item hangs from its hold socket,
 * a {@link BoneAttachment3D} is made on {@code hand_l} of the same skeleton and {@code ModelLeft} is moved under
 * it, at the RIGHT grip mirrored across the body. The mirror is taken in REST frames: the gun's relation to
 * {@code hand_r} is read live, re-expressed through both hands' rest poses and reflected across the skeleton's
 * X (the body's left/right), so it holds for any body the skeleton contract admits and needs no authored left
 * socket. Holstered, the second gun is hidden; lying in the world, it sits beside the first.
 *
 * <p>The pose that puts each hand in front of its own shoulder is the grip archetype's ({@code dual_pistol},
 * the pistol poses with the right arm X-flipped onto the left: {@code make_dual_pistol_clips.py}). The item
 * declares no {@code SupportPoint}, so the support-hand IK leaves the left arm as the clip authored it.
 *
 * <p>Shots are the right gun's (one trace, one tracer origin); the muzzle FLASH alternates between the two guns,
 * which is what reads as dual fire. Per-gun shot origins are a later step.
 */
@Script(className = "DualPistolItem")
public class DualPistolItem extends FirearmItem {

  @Export public String leftModelPath = "ModelLeft";
  @Export public String rightHandBone = "hand_r";
  @Export public String leftHandBone = "hand_l";
  /**
   * Keep the left barrel PARALLEL to the right one (both straight at what the body aims at). Without it the left
   * gun keeps the clip's mirrored hand orientation, and the aim modifiers turn both shoulders by the RIGHT gun's
   * correction, which the mirror doubles on the left: measured 9.7 deg outward. Off is probe_dual_pistol's control.
   */
  @Export public boolean alignLeftBore = true;
  /**
   * Degrees the LEFT barrel turns inward (toward the right gun) from parallel; 0 = both straight. Only the left
   * gun can: the right one is the bore the aim modifiers put on the aim line.
   */
  @Export public double toeInDeg = 0.0;
  /** Where the second gun sits, in the item's frame, while the pair lies in the world. */
  @Export public Vector3 worldPairOffset = new Vector3(0.05, 0.0, 0.0);

  private Node3D leftModel;
  private BoneAttachment3D leftHand;
  private Node3D leftGrip;
  private Skeleton3D leftSkeleton;
  private com.openworld.vfx.MuzzleFlashVfx leftFlash;
  private boolean nextFlashLeft = false;

  @Register
  @Override
  public void _process(double delta) {
    super._process(delta);
    placeLeft();
  }

  @Register
  public void _exitTree() {
    // the second gun may be parented under the character's skeleton; it must not outlive the item. Only on a
    // real delete: reparent() (every equip and holster) exits the tree too, and the pair must survive that.
    if (!isQueuedForDeletion()) return;
    if (leftHand != null && GD.INSTANCE.isInstanceValid(leftHand)) leftHand.queueFree();
    leftHand = null;
    leftGrip = null;
  }

  /** True while the pair is held: the item hangs from its own hold socket and is shown. */
  @Register
  public boolean inHandNow() {
    Node p = getParent();
    return p != null && isVisible() && p.getName().toString().equals(holdSocket);
  }

  private Node3D leftModel() {
    if (leftModel == null && getNodeOrNull(leftModelPath) instanceof Node3D n) leftModel = n;
    return leftModel;
  }

  private void placeLeft() {
    Node3D model = leftModel();
    if (model == null) return;
    Skeleton3D sk = inHandNow() ? skeletonAbove(getParent()) : null;
    if (sk != null) {
      attach(sk, model);
    } else {
      if (!model.getParent().equals(this)) {
        model.reparent(this, false);
      }
      model.setTransform(new Transform3D(Basis.Companion.getIDENTITY(), worldPairOffset));
      model.setVisible(getParent() instanceof com.openworld.item.PickupBody);
    }
  }

  private static Skeleton3D skeletonAbove(Node n) {
    for (Node p = n; p != null; p = p.getParent()) {
      if (p instanceof Skeleton3D s) return s;
    }
    return null;
  }

  private void attach(Skeleton3D sk, Node3D model) {
    boolean fresh = leftHand == null || !GD.INSTANCE.isInstanceValid(leftHand) || !sk.equals(leftSkeleton);
    if (fresh) {
      if (leftHand != null && GD.INSTANCE.isInstanceValid(leftHand)) {
        if (model.getParent() != null && model.getParent().equals(leftGrip)) model.reparent(this, false);
        leftHand.queueFree();
      }
      leftHand = new BoneAttachment3D();
      leftHand.setName("DualPistolLeftHand");
      leftHand.setBoneName(leftHandBone);
      sk.addChild(leftHand);
      leftGrip = new Node3D();
      leftGrip.setName("Grip");
      leftHand.addChild(leftGrip);
      leftSkeleton = sk;
      Transform3D grip = mirroredGrip(sk);
      if (grip == null) return;
      leftGrip.setTransform(grip);
    }
    if (model.getParent() == null || !model.getParent().equals(leftGrip)) {
      model.reparent(leftGrip, false);
    }
    model.setTransform(new Transform3D());
    if (alignLeftBore) alignBore(model);
    model.setVisible(true);
  }

  /** Turn the left gun (about its own grip) so its barrel is parallel to the right gun's, toed in by toeInDeg. */
  private void alignBore(Node3D model) {
    Basis want = getGlobalTransform().getBasis().orthonormalized();
    if (toeInDeg != 0.0) {
      // in the gun's OWN frame (-Z barrel, +X its right, where the right gun is): a turn of -a about +Y takes the
      // barrel toward +X, i.e. inward
      want = want.times(new Basis(new Vector3(0, 1, 0), -Math.toRadians(toeInDeg)));
    }
    Basis parent = ((Node3D) model.getParent()).getGlobalTransform().getBasis().orthonormalized();
    model.setTransform(new Transform3D(parent.inverse().times(want), new Vector3()));
  }

  /**
   * The left grip in {@code hand_l}'s frame: this gun's live relation to {@code hand_r}, carried through both
   * hands' REST poses and reflected across skeleton X. Composed by hand from Basis and Vector3, because
   * godot-jvm's {@code Transform3D.times} writes into its receiver.
   */
  private Transform3D mirroredGrip(Skeleton3D sk) {
    int r = sk.findBone(rightHandBone), l = sk.findBone(leftHandBone);
    if (r < 0 || l < 0) return null;
    // relative to hand_r: the local transforms from the item up to the right hand's BoneAttachment3D (which
    // IS hand_r's frame). Not getBoneGlobalPose: that is the pose BEFORE the aim modifiers, the socket is after.
    Transform3D gripRel = new Transform3D();
    Node p = this;
    while (p != null && !(p instanceof BoneAttachment3D)) {
      if (p instanceof Node3D n3) gripRel = compose(n3.getTransform(), gripRel);
      p = p.getParent();
    }
    if (!(p instanceof BoneAttachment3D ba) || !ba.getBoneName().equals(rightHandBone)) return null;
    Transform3D gunRest = compose(sk.getBoneGlobalRest(r), gripRel);  // the same relation at rest
    Basis fx = new Basis(new Vector3(-1, 0, 0), new Vector3(0, 1, 0), new Vector3(0, 0, 1));
    // reflect the placement across the body (left of X) and the gun across its own side-to-side axis: the
    // product of two reflections is a proper rotation, so the model is turned, never mirrored inside out
    Transform3D mirrored = new Transform3D(fx.times(gunRest.getBasis()).times(fx), fx.times(gunRest.getOrigin()));
    return compose(inverse(sk.getBoneGlobalRest(l)), mirrored);
  }

  private static Transform3D compose(Transform3D a, Transform3D b) {
    Basis ab = a.getBasis(), bb = b.getBasis();
    return new Transform3D(ab.times(bb), ab.times(b.getOrigin()).plus(a.getOrigin()));
  }

  private static Transform3D inverse(Transform3D t) {
    Basis inv = t.getBasis().inverse();
    return new Transform3D(inv, inv.times(t.getOrigin()).times(-1.0));
  }

  /** The flash alternates between the two guns, which is what reads as dual fire. */
  @Override
  protected void playMuzzleFlash() {
    boolean left = nextFlashLeft && leftModel() != null && leftModel.isVisible();
    nextFlashLeft = !nextFlashLeft;
    if (!left) {
      super.playMuzzleFlash();
      return;
    }
    if (leftFlash == null && leftModel.getNodeOrNull("MuzzleLeft/MuzzleVFX") instanceof com.openworld.vfx.MuzzleFlashVfx f) {
      leftFlash = f;
    }
    if (leftFlash == null) return;
    leftFlash.setSpeedScale((float) Math.max(1.0, leftFlash.mainLength() * fireRate));
    leftFlash.play();
  }
}
