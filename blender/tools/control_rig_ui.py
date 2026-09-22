"""The character control rig's sidebar UI and its IK/FK snaps (PLAN.md 6.17).

`blender/tools/add_control_rig.py` writes this file INTO each body's .blend as the text block
`control_rig_ui.py`, marked Register, so it loads with the file -- Rigify ships its `rig_ui.py` the
same way. Blender asks once to allow the file's scripts; allow it, or run this block by hand
(Text editor > Run Script). The builder also IMPORTS this file for its own self-test, so the buttons
an artist presses are exactly the code the test measured: one owner of every snap.

N-panel > "Rig" tab, with the armature selected:
  * one IK slider per limb (0 = the clip's own FK, 1 = the arm/leg follows its IK control)
  * "to IK": put the hand/foot control and the pole where the limb IS, then switch the limb to IK --
    nothing moves on screen
  * "to FK": write what the IK produced into the limb's own bones, then switch the limb to FK --
    nothing moves on screen, and the pose is ordinary keys on the 53 contract bones again
  * show/hide the bone collections

The IK sliders must be 0 to export (export_character.py refuses otherwise) and to play the library:
an IK limb IGNORES its clip, which is the point while posing and the defect while playing.
"""
import bpy
from mathutils import Vector

MCH = "MCH_"
PROP = "ik_"
# limb -> its bones. `dir` is the way the joint bends, in the body's frame (it faces -Y): an elbow
# bends BACK (+Y), a knee FORWARD (-Y). Used only where the limb is straight and has no bend plane.
LIMBS = {
    "arm_l": {"label": "Arm L", "upper": "upperarm_l", "lower": "lowerarm_l", "tip": "hand_l",
              "ctrl": "CTRL_hand_l", "pole": "CTRL_elbow_l", "dir": (0.0, 1.0, 0.0)},
    "arm_r": {"label": "Arm R", "upper": "upperarm_r", "lower": "lowerarm_r", "tip": "hand_r",
              "ctrl": "CTRL_hand_r", "pole": "CTRL_elbow_r", "dir": (0.0, 1.0, 0.0)},
    "leg_l": {"label": "Leg L", "upper": "thigh_l", "lower": "calf_l", "tip": "foot_l",
              "ctrl": "CTRL_foot_l", "pole": "CTRL_knee_l", "dir": (0.0, -1.0, 0.0)},
    "leg_r": {"label": "Leg R", "upper": "thigh_r", "lower": "calf_r", "tip": "foot_r",
              "ctrl": "CTRL_foot_r", "pole": "CTRL_knee_r", "dir": (0.0, -1.0, 0.0)},
}
COLLECTIONS = ("CTRL", "Body", "Fingers", "Extras")


def is_rig(ob):
    return ob is not None and ob.type == 'ARMATURE' and "CTRL_root" in ob.pose.bones


def _update():
    bpy.context.evaluated_depsgraph_get().update()
    bpy.context.view_layer.update()


def world(arm, name):
    """The EVALUATED world matrix -- constraints applied, which is the whole point."""
    dg = bpy.context.evaluated_depsgraph_get()
    return arm.matrix_world @ arm.evaluated_get(dg).pose.bones[name].matrix


def set_ik(arm, limb, value):
    """THE ONE WRITER of a limb's IK state: every constraint of the limb is driven by this property."""
    arm.pose.bones["CTRL_root"][PROP + limb] = float(value)
    _update()


def ik_value(arm, limb):
    r = arm.pose.bones["CTRL_root"]
    return float(r[PROP + limb]) if PROP + limb in r else 0.0


def _put(arm, name, world_matrix):
    arm.pose.bones[name].matrix = arm.matrix_world.inverted() @ world_matrix
    _update()


def to_ik(arm, limb):
    """Snap the IK controls onto the limb as it is posed, then switch the limb to IK.

    Returns how far the elbow/knee and the hand/foot moved (metres) -- both should be ~0."""
    L = LIMBS[limb]
    set_ik(arm, limb, 0.0)
    up, lo, tip = world(arm, L["upper"]), world(arm, L["lower"]), world(arm, L["tip"])
    root, elbow, wrist = up.translation.copy(), lo.translation.copy(), tip.translation.copy()
    # the hidden solving chain starts where the limb is, so the solver has nothing to jump over
    for b in (L["upper"], L["lower"]):
        d = arm.data.bones[b].matrix_local
        m = arm.data.bones[MCH + b].matrix_local
        _put(arm, MCH + b, world(arm, b) @ d.inverted() @ m)
    # the pole goes out along the limb's own bend, one limb-length from the joint: far enough that
    # moving the hand does not swing the elbow round it (a near pole flips the elbow as the hand
    # passes it), near enough to grab
    axis = wrist - root
    bend = Vector((0.0, 0.0, 0.0))
    if axis.length > 1e-6:
        a = axis.normalized()
        bend = elbow - (root + a * (elbow - root).dot(a))
    if bend.length < 1e-3:                    # a straight limb: keep the side the pole was on
        bend = world(arm, L["pole"]).translation - elbow
        if bend.length < 1e-3:
            bend = arm.matrix_world.to_3x3() @ Vector(L["dir"])
    reach = (elbow - root).length + (wrist - elbow).length
    pm = world(arm, L["pole"]).copy()
    pm.translation = elbow + bend.normalized() * reach
    _put(arm, L["pole"], pm)
    _put(arm, L["ctrl"], tip)                 # position AND orientation: the hand turns with it
    set_ik(arm, limb, 1.0)
    return ((world(arm, L["lower"]).translation - elbow).length,
            (world(arm, L["tip"]).translation - wrist).length)


def to_fk(arm, limb):
    """Write what the IK produced into the limb's own bones, then switch the limb to FK."""
    L = LIMBS[limb]
    names = (L["upper"], L["lower"], L["tip"])
    want = {n: world(arm, n).copy() for n in names}   # read BEFORE the switch changes it
    set_ik(arm, limb, 0.0)
    for n in names:                                    # parents first
        _put(arm, n, want[n])
    return max((world(arm, n).translation - want[n].translation).length for n in names)


def _autokey(context, arm, limb):
    if not context.scene.tool_settings.use_keyframe_insert_auto:
        return
    L = LIMBS[limb]
    for n in (L["upper"], L["lower"], L["tip"]):
        pb = arm.pose.bones[n]
        rot = "rotation_quaternion" if pb.rotation_mode == 'QUATERNION' else "rotation_euler"
        pb.keyframe_insert(rot)
        pb.keyframe_insert("location")


class OW_OT_ik_switch(bpy.types.Operator):
    """Snap and switch a limb (or all four) between IK and FK without moving it"""
    bl_idname = "pose.ow_ik_switch"
    bl_label = "Switch IK/FK"
    bl_options = {'REGISTER', 'UNDO'}

    limb: bpy.props.StringProperty(default="ALL")
    to: bpy.props.EnumProperty(items=[('IK', "IK", ""), ('FK', "FK", "")], default='IK')

    @classmethod
    def poll(cls, context):
        return is_rig(context.object)

    def execute(self, context):
        arm = context.object
        limbs = list(LIMBS) if self.limb == "ALL" else [self.limb]
        for limb in limbs:
            if self.to == 'IK':
                to_ik(arm, limb)
            else:
                to_fk(arm, limb)
                _autokey(context, arm, limb)
        return {'FINISHED'}


class OW_PT_rig(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Rig"
    bl_label = "Character Rig"

    @classmethod
    def poll(cls, context):
        return is_rig(context.object)

    def draw(self, context):
        arm = context.object
        root = arm.pose.bones["CTRL_root"]
        col = self.layout.column(align=True)
        for limb, L in LIMBS.items():
            row = col.row(align=True)
            if PROP + limb in root:
                row.prop(root, '["%s%s"]' % (PROP, limb), text=L["label"] + " IK", slider=True)
            for to in ('IK', 'FK'):
                op = row.operator(OW_OT_ik_switch.bl_idname, text="to " + to)
                op.limb, op.to = limb, to
        row = col.row(align=True)
        for to in ('IK', 'FK'):
            op = row.operator(OW_OT_ik_switch.bl_idname, text="All limbs to " + to)
            op.limb, op.to = "ALL", to
        if any(ik_value(arm, limb) > 0.0 for limb in LIMBS):
            self.layout.label(text="IK is on: set every limb to FK before exporting", icon='ERROR')
        box = self.layout.box()
        box.label(text="Bone collections")
        for name in COLLECTIONS:
            c = next((c for c in arm.data.collections_all if c.name == name), None)
            if c is not None:
                box.prop(c, "is_visible", text=name)


_CLASSES = (OW_OT_ik_switch, OW_PT_rig)


def register():
    for cls in _CLASSES:
        old = getattr(bpy.types, cls.__name__, None)
        if old is not None:
            try:
                bpy.utils.unregister_class(old)
            except Exception:
                pass
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


register()
