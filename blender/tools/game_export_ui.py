"""ONE button that exports a character to the game -- written into each character .blend.

N-panel > "Game" tab > "Export to Game". The artist never has to remember which switch goes where:
  1. every control-rig switch is turned OFF for the export -- Auto-Rig Pro's
     `c_pos["drive_game_rig"]`, and the `CTRL_root["ik_*"]` sliders of our own layer
     (blender/tools/add_control_rig.py) on bodies that still carry it
  2. blender/tools/export_character.py runs, unchanged -- it is still the ONE exporter, with its own
     guard that refuses a pose a live constraint is driving
  3. every switch is put back exactly as it was, whether the export succeeded or refused
  4. (optional, on by default) Godot is brought up to date: `--import` (a headless gate otherwise
     measures the PREVIOUS export), and -- when this file is the clip source -- the shared library is
     rebuilt and `check_character_anim.py` run. Step 4 takes about a minute and blocks Blender while
     it runs; the result is in the status bar and the console.

Installed by `blender/tools/install_game_export_ui.py` as a registered text block, so it loads with
the file (Blender asks once to allow the file's scripts). It finds the repository by walking up from
the .blend to `project.godot`, so it needs no configuration and works for every body.
"""
import os
import re
import runpy
import subprocess

import bpy

SWITCHES = ("drive_game_rig",)          # pose-bone properties that make a control rig drive the body
IK_PREFIX = "ik_"                       # our own layer: CTRL_root["ik_arm_l"] ...


def repo_root(start=None):
    d = os.path.dirname(os.path.abspath(start or bpy.data.filepath))
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "project.godot")):
            return d
        d = os.path.dirname(d)
    return None


def _switch_props():
    """Every (pose bone, property) that turns a control rig on, in this file."""
    out = []
    for ob in bpy.data.objects:
        if ob.type != 'ARMATURE' or ob.pose is None:
            continue
        for pb in ob.pose.bones:
            for k in pb.keys():
                if k in SWITCHES or (pb.name == "CTRL_root" and k.startswith(IK_PREFIX)):
                    out.append((pb, k))
    return out


def _update():
    """Make every driver see the switch just written. A custom property set from Python tags nothing
    for update, so the constraints' drivers kept their old value and the export was refused as if the
    rig were still on (measured: 0.889 m). Re-setting the current frame re-evaluates drivers."""
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE':
            ob.update_tag(refresh={'OBJECT', 'DATA'})
    bpy.context.evaluated_depsgraph_get().update()
    sc = bpy.context.scene
    sc.frame_set(sc.frame_current)
    bpy.context.view_layer.update()


def godot_binary(root):
    if os.environ.get("GODOT"):
        return os.environ["GODOT"]
    env = os.path.join(root, "blender", "tools", "env.sh")
    try:
        m = re.search(r'GODOT="\$\{GODOT:-([^}]+)\}"', open(env).read())
        if m:
            return m.group(1)
    except OSError:
        pass
    return "godot"


def clip_source(root):
    """The .glb the shared animation library is built from (build_character_anims.gd owns it)."""
    try:
        m = re.search(r'const SOURCE := "res://([^"]+)"',
                      open(os.path.join(root, "tools", "godot", "build_character_anims.gd")).read())
        return os.path.join(root, m.group(1)) if m else None
    except OSError:
        return None


def _run(cmd, root, timeout):
    print("[game-export] $ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-6:])
    print(tail)
    return r.returncode, tail


def load_arp_clips(root=None):
    """blender/tools/arp_clips.py, loaded from the repository: the ONE owner of moving a clip to the ARP
    controls and baking it back. This block is a copy inside the .blend; that module is not."""
    import importlib.util
    root = root or repo_root()
    spec = importlib.util.spec_from_file_location("arp_clips", os.path.join(root, "blender", "tools", "arp_clips.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def export_to_game(root=None, update_godot=True):
    """Returns (ok, message). The switches are restored in every case."""
    root = root or repo_root()
    if root is None:
        return False, "this .blend is not inside the game repository (no project.godot above it)"
    # export_character.py itself bakes the ARP clips and switches the rig off and back -- one path for
    # the button and the command line alike
    baked = [a.name[4:] for a in bpy.data.actions if a.name.startswith("ARP_")]
    try:
        runpy.run_path(os.path.join(root, "blender", "tools", "export_character.py"), run_name="__main__")
    except SystemExit as exc:              # the exporter's own guard refused
        return False, str(exc) or "export_character.py refused"
    out = os.path.splitext(bpy.data.filepath)[0] + ".glb"
    msg = "exported %s%s" % (os.path.relpath(out, root),
                              " (%d clip(s) on the rig, changed ones baked in)" % len(baked) if baked else "")
    if not update_godot:
        return True, msg
    g = godot_binary(root)
    code, _ = _run([g, "--headless", "--path", ".", "--import"], root, 1800)
    if code != 0:
        return False, msg + "; Godot --import FAILED (see console)"
    msg += "; Godot re-imported"
    # the body's generated scene carries its hand sockets: regenerate it, so a socket moved in this file
    # (<body>.sockets.json, written by the export) reaches the game. The reference body is hand-authored.
    stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    if os.path.exists(os.path.join(os.path.dirname(bpy.data.filepath), stem + ".body.json")):
        code, _ = _run([g, "--headless", "--path", ".", "--script", "tools/godot/build_character_visuals.gd",
                        "--", "--body=" + stem], root, 900)
        if code != 0:
            return False, msg + "; regenerating the body scene FAILED (see console)"
        msg += "; body scene regenerated"
    src = clip_source(root)
    if src and os.path.abspath(src) == os.path.abspath(out):
        code, _ = _run([g, "--headless", "--path", ".", "--script", "tools/godot/build_character_anims.gd"],
                       root, 1800)
        if code != 0:
            return False, msg + "; animation library rebuild FAILED (see console)"
        code, tail = _run(["python3", "blender/tools/check_character_anim.py"], root, 600)
        msg += "; library rebuilt; check_character_anim " + ("PASS" if code == 0 else "FAILED (see console)")
        if code != 0:
            return False, msg
    return True, msg


class OW_OT_export_to_game(bpy.types.Operator):
    """Export this character to the game: control rigs off, export, switches back, update Godot"""
    bl_idname = "wm.ow_export_to_game"
    bl_label = "Export to Game"

    update_godot: bpy.props.BoolProperty(name="Update Godot", default=True)
    repo: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        context.window.cursor_set('WAIT') if context.window else None
        ok, msg = export_to_game(self.repo or None, self.update_godot)
        context.window_manager.ow_last_export = msg
        self.report({'INFO'} if ok else {'ERROR'}, msg)
        print("[game-export] %s: %s" % ("OK" if ok else "FAILED", msg))
        return {'FINISHED'} if ok else {'CANCELLED'}


_CLIP_ITEMS = []          # Blender needs the enum items kept alive (a callback's list is otherwise freed)


def _game_clips(self, context):
    """Every clip by its PLAIN name: the exported ones (the game armature's NLA tracks) and any made on the
    rig that has not been exported yet. The `ARP_` prefix is internal to arp_clips.py; an artist never
    has to know which is which."""
    names = set()
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE' and "arp_rig_type" not in ob.keys() and ob.animation_data:
            for tr in ob.animation_data.nla_tracks:
                for st in tr.strips:
                    if st.action is not None and not st.action.name.startswith("ARP_"):
                        names.add(st.action.name)
    names |= {a.name[4:] for a in bpy.data.actions if a.name.startswith("ARP_")}
    _CLIP_ITEMS[:] = [(n, n, "") for n in sorted(names)] or [("", "(no clips)", "")]
    return _CLIP_ITEMS


def _show_on_rig(context, arp_mod, clip):
    """Put `ARP_<clip>` on the ARP rig, switch the rig ON and set the frame range: ready to pose."""
    rig, game = arp_mod.rigs()
    act = bpy.data.actions[arp_mod.PREFIX + clip]
    arp_mod._bind(rig, act)
    arp_mod._drive(rig, 1.0)
    sc = context.scene
    sc.frame_start, sc.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    sc.frame_set(sc.frame_start)
    context.window_manager.ow_editing = clip


class OW_OT_edit_clip(bpy.types.Operator):
    """Load the chosen clip on the Auto-Rig Pro controls, ready to pose. A clip that is not on the rig yet
    is copied there first (exact, in FK). The game clip changes only when you Export"""
    bl_idname = "wm.ow_edit_clip"
    bl_label = "Edit on Rig"

    clip: bpy.props.StringProperty(default="")
    ik: bpy.props.BoolProperty(default=False)
    repo: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        clip = self.clip or context.window_manager.ow_clip
        if not clip:
            self.report({'ERROR'}, "pick a clip first")
            return {'CANCELLED'}
        mod = load_arp_clips(self.repo or None)
        if (mod.PREFIX + clip) not in bpy.data.actions:
            try:
                mod.move_to_arp(clip, to_ik=self.ik)
            except Exception as exc:
                self.report({'ERROR'}, "putting %s on the rig failed: %s" % (clip, exc))
                return {'CANCELLED'}
        _show_on_rig(context, mod, clip)
        msg = "%s is on the rig -- pose and key, then Export to Game" % clip
        context.window_manager.ow_last_export = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class OW_OT_new_clip(bpy.types.Operator):
    """Make a new clip on the rig, holding the current pose. It becomes a game clip at the next Export"""
    bl_idname = "wm.ow_new_clip"
    bl_label = "New Clip"

    name: bpy.props.StringProperty(name="Name", default="new_clip")
    frames: bpy.props.IntProperty(name="Frames", default=30, min=1)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        mod = load_arp_clips()
        try:
            mod.new_clip(self.name, 0, self.frames)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _show_on_rig(context, mod, self.name[4:] if self.name.startswith("ARP_") else self.name)
        context.window_manager.ow_clip = context.window_manager.ow_editing
        return {'FINISHED'}


class OW_OT_to_ik(bpy.types.Operator):
    """Snap every limb of the clip being edited to IK over its whole range. Joints stay within
    millimetres; the export keeps each limb's own twist, so check the result"""
    bl_idname = "wm.ow_clip_to_ik"
    bl_label = "Limbs to IK"

    def execute(self, context):
        mod = load_arp_clips()
        clip = context.window_manager.ow_editing
        act = bpy.data.actions.get(mod.PREFIX + clip)
        if act is None:
            self.report({'ERROR'}, "no clip is being edited")
            return {'CANCELLED'}
        rig, _ = mod.rigs()
        mod.to_ik_over_range(rig, int(act.frame_range[0]), int(act.frame_range[1]))
        return {'FINISHED'}


class OW_OT_remove_arp_clip(bpy.types.Operator):
    """Take this clip off the rig. The game clip stays as it was at the last Export"""
    bl_idname = "wm.ow_remove_arp_clip"
    bl_label = "Take off the Rig"
    clip: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        act = bpy.data.actions.get("ARP_" + self.clip)
        if act is not None:
            for ob in bpy.data.objects:
                if ob.animation_data and ob.animation_data.action is act:
                    ob.animation_data.action = None
            bpy.data.actions.remove(act)
        return {'FINISHED'}


class OW_PT_game_export(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Game"
    bl_label = "Export to Game"

    def draw(self, context):
        wm = context.window_manager
        col = self.layout.column()
        col.prop(wm, "ow_update_godot", text="Update Godot afterwards")
        op = col.operator(OW_OT_export_to_game.bl_idname, icon='EXPORT')
        op.update_godot = wm.ow_update_godot
        on = [(pb.id_data.name, pb.name, k) for pb, k in _switch_props() if float(pb[k]) > 0.0]
        if on:
            col.label(text="Posing with Auto-Rig Pro -- Export switches it off and back", icon='INFO')
        if wm.ow_last_export:
            col.label(text=wm.ow_last_export[:120])

        if not any(o.type == 'ARMATURE' and "arp_rig_type" in o.keys() for o in bpy.data.objects):
            return
        box = self.layout.box()
        box.label(text="Clips (every clip is edited on the rig)", icon='ARMATURE_DATA')
        box.prop(wm, "ow_clip", text="Clip")
        row = box.row(align=True)
        op = row.operator(OW_OT_edit_clip.bl_idname, icon='POSE_HLT')
        op.clip = wm.ow_clip
        row.operator(OW_OT_new_clip.bl_idname, icon='ADD')
        if wm.ow_editing:
            r = box.row(align=True)
            r.label(text="Editing: " + wm.ow_editing)
            r.operator(OW_OT_to_ik.bl_idname)
            r.operator(OW_OT_remove_arp_clip.bl_idname, text="", icon='X').clip = wm.ow_editing


from bpy.app.handlers import persistent


@persistent
def arp_on_at_load(*_):
    """THE FILE OPENS IN ARP. Posing always goes through the Auto-Rig Pro controls; the export is what
    switches the rig off (export_character.py) and back. An artist never sets the switch by hand."""
    for ob in bpy.data.objects:
        if ob.type == 'ARMATURE' and "arp_rig_type" in ob.keys() and "c_pos" in ob.pose.bones \
                and "drive_game_rig" in ob.pose.bones["c_pos"]:
            ob.pose.bones["c_pos"]["drive_game_rig"] = 1.0
            ob.update_tag(refresh={'OBJECT', 'DATA'})
    try:
        bpy.context.evaluated_depsgraph_get().update()
    except Exception:
        pass                               # no depsgraph yet this early in a load: the first redraw does it


@persistent
def keep_arp_clips(*_):
    """AN ARP CLIP IS NEVER DROPPED ON SAVE. Blender does not write a datablock nothing uses, and an ARP
    clip that is not on the rig at that moment uses nothing -- measured, `ARP_upright_aim_shotgun-loop`
    was lost that way when the rifle clip was put back on the rig and the file saved. Every `ARP_*`
    action gets a fake user before each save."""
    for a in bpy.data.actions:
        if a.name.startswith("ARP_") and not a.use_fake_user:
            a.use_fake_user = True
    # ...and the rig switch is never kept as a key in them (keying "everything" keys it)
    try:
        load_arp_clips().strip_switch_keys()
    except Exception:
        pass


_CLASSES = (OW_OT_export_to_game, OW_OT_edit_clip, OW_OT_new_clip, OW_OT_to_ik, OW_OT_remove_arp_clip,
            OW_PT_game_export)
# retired by the all-clips-on-the-rig change: unregistered if an older copy of this block left them
_RETIRED = ("OW_OT_move_clip_to_arp", "OW_OT_edit_arp_clip")


def register():
    bpy.types.WindowManager.ow_last_export = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.ow_update_godot = bpy.props.BoolProperty(default=True)
    bpy.types.WindowManager.ow_clip = bpy.props.EnumProperty(items=_game_clips, name="Clip")
    bpy.types.WindowManager.ow_editing = bpy.props.StringProperty(default="")
    for name in _RETIRED:
        old = getattr(bpy.types, name, None)
        if old is not None:
            try:
                bpy.utils.unregister_class(old)
            except Exception:
                pass
    for cls in _CLASSES:
        old = getattr(bpy.types, cls.__name__, None)
        if old is not None:
            try:
                bpy.utils.unregister_class(old)
            except Exception:
                pass
        bpy.utils.register_class(cls)
    for h in [h for h in bpy.app.handlers.load_post if getattr(h, "__name__", "") == "arp_on_at_load"]:
        bpy.app.handlers.load_post.remove(h)
    bpy.app.handlers.load_post.append(arp_on_at_load)
    for h in [h for h in bpy.app.handlers.save_pre if getattr(h, "__name__", "") == "keep_arp_clips"]:
        bpy.app.handlers.save_pre.remove(h)
    bpy.app.handlers.save_pre.append(keep_arp_clips)
    arp_on_at_load()                       # this block itself runs as the file loads


register()
