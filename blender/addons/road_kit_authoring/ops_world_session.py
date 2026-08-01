"""Panel-driven persistent whole-world editing session -- wraps tools/open_world_session.py and
tools/writeback_world_session.py (see AUTHORING_GUIDE.md "One file for the whole world") behind
one-click buttons, reusing ops_group_edit.py's proven background-subprocess + modal-timer
plumbing (`_bg_reader`) so the UI never blocks.

Unlike the "Multi-District Group" scoped session (ops_group_edit.py, for a deliberately small
named set of districts), this always targets EVERY registered piece in ONE stable file
(world_session.blend) -- open it once, travel anywhere, edit anything, and write back only what
actually changed (fingerprint-diffed). "Open World Session" / "Refresh World Session" are the
SAME operator: it saves first and refreshes in place if the current file already IS the session,
or just opens/creates it otherwise -- open_world_session.py's own refresh-vs-create logic already
unifies this, so the addon side doesn't need two code paths either.

Also owns the three piece-lifecycle operators that used to be split across a grid-only "Toggle
Void" mechanism and an ad-hoc "Place Piece Anchor": "Unload Piece" (session-local only, drop a
piece from THIS file to shrink a large scene, e.g. to dodge the depsgraph-scale crash a full
37-piece world_session.blend can hit under heavy Geometry Nodes editing -- nothing on disk
changes), "Remove Piece" (the real, permanent deletion -- .blend + pieces.json entry gone,
master rebuilt), and "Place Piece Anchor" (register a new one). There's no more grid-only "void"
toggle -- it never generalized to a freestanding piece anyway (no grid cell to mark void), and a
piece that's simply not registered already renders as the ordinary "not yet built" placeholder.
"""
import os
import queue
import subprocess

import bpy

from . import ops_group_edit as ge
from . import paths
import world_grid as wg  # lib/ already on sys.path via paths.py
import piece_registry as pr
import session_common as sc

SESSION_PATH = os.path.join(paths.WORLD_SOURCE, "world_session.blend")


class RKA_OT_open_world_session(bpy.types.Operator):
    bl_idname = "rka.open_world_session"
    bl_label = "Open/Refresh World Session"
    bl_description = (
        "Open the persistent whole-world session (world_session.blend) -- creates it from every "
        "built, non-void district on first run; on a later run, saves any pending edits here "
        "first, then adds newly-built districts and prunes stale ones without touching anything "
        "already present. Runs in the background, see System Console"
    )

    _timer = None
    _proc = None
    _out_queue = None

    def invoke(self, context, event):
        if bpy.data.filepath == SESSION_PATH:
            bpy.ops.wm.save_mainfile()

        script = os.path.join(paths.BLENDER_SRC, "tools", "open_world_session.py")
        self._proc = subprocess.Popen(
            [bpy.app.binary_path, "--background", "--python", script, "--"],
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        self._out_queue, _ = ge._bg_reader(self._proc)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Opening world session -- see System Console")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        done = False
        while True:
            try:
                line = self._out_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                done = True
                break
            print("[rka.open_world_session] %s" % line.rstrip())

        if not done:
            return {'RUNNING_MODAL'}

        context.window_manager.event_timer_remove(self._timer)
        ret = self._proc.wait()
        if ret != 0 or not os.path.exists(SESSION_PATH):
            self.report({'ERROR'}, "Open World Session failed (exit %d) -- see System Console"
                        % ret)
            return {'CANCELLED'}

        self.report({'INFO'}, "Opened world_session.blend")
        bpy.ops.wm.open_mainfile(filepath=SESSION_PATH)
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


class RKA_OT_writeback_world_session(bpy.types.Operator):
    bl_idname = "rka.writeback_world_session"
    bl_label = "Write Back World Session"
    bl_description = (
        "Fingerprint-diff every district in this session against its last-synced baseline and "
        "write back only what changed (rebuild + seam-check included) -- or every district "
        "present, if 'Write Back All' was used. Runs in the background, see System Console"
    )

    force_all: bpy.props.BoolProperty(default=False)

    _timer = None
    _proc = None
    _out_queue = None

    @classmethod
    def poll(cls, context):
        return bpy.data.filepath == SESSION_PATH

    def invoke(self, context, event):
        bpy.ops.wm.save_mainfile()

        script = os.path.join(paths.BLENDER_SRC, "tools", "writeback_world_session.py")
        cmd = [bpy.app.binary_path, "--background", bpy.data.filepath, "--python", script, "--"]
        if self.force_all:
            cmd.append("--force-all")
        self._proc = subprocess.Popen(
            cmd, cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        self._out_queue, _ = ge._bg_reader(self._proc)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Writing back world session (%s) -- see System Console"
                    % ("all districts" if self.force_all else "changed districts only"))
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        done = False
        while True:
            try:
                line = self._out_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                done = True
                break
            print("[rka.writeback_world_session] %s" % line.rstrip())

        if not done:
            return {'RUNNING_MODAL'}

        context.window_manager.event_timer_remove(self._timer)
        ret = self._proc.wait()
        # Reload regardless of exit code: a rebuild/seam-check failure for ONE district still
        # updates baselines for whichever others succeeded (writeback_world_session.py only
        # aborts the whole run before touching anything on a writeback_district_group.py
        # failure -- a build/seam failure downstream of that still completes+re-saves).
        bpy.ops.wm.revert_mainfile()
        if ret != 0:
            self.report({'ERROR'}, "Write Back World Session had failures (exit %d) -- see "
                                    "System Console" % ret)
            return {'CANCELLED'}

        self.report({'INFO'}, "Write Back World Session complete -- see System Console for "
                               "the per-district summary")
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


def _district_enum_items(self, context):
    items = []
    for gy in range(wg.GRID_N):
        for gx in range(wg.GRID_N):
            value = "%d:%d" % (gx, gy)
            if wg.is_void(gx, gy):
                items.append((value, "(void) %d,%d" % (gx, gy), "Deliberately empty cell"))
                continue
            theme = wg.theme_at(gx, gy)
            stem = wg.piece_id_for_cell(gx, gy)
            built = os.path.exists(os.path.join(paths.WORLD_SOURCE, "pieces", stem + ".blend"))
            label = stem if built else "(unbuilt) %s" % stem
            items.append((value, label, theme))
    return items


def _loaded_piece_enum_items(self, context):
    """Every piece id currently loaded (has a Piece__<id> wrapper) in THIS open file -- what
    "Unload Piece" can actually act on."""
    return [(pid, pid, "") for pid in sc.loaded_piece_ids()]


def _registered_piece_enum_items(self, context):
    """Every REGISTERED piece (pieces.json), loaded or not -- what "Remove Piece" can act on,
    since you may want to delete a piece you don't currently have open."""
    return [(p["id"], p["id"], "") for p in sorted(pr.all_pieces(), key=lambda p: p["id"])]


def _unloaded_piece_enum_items(self, context):
    """Every registered, built piece NOT currently loaded (no Piece__<id> wrapper) in THIS open
    file -- what "Load Piece" can actually act on, the mirror of _loaded_piece_enum_items."""
    loaded = set(sc.loaded_piece_ids())
    return [(p["id"], p["id"], "") for p in sorted(pr.all_pieces(), key=lambda p: p["id"])
            if p["id"] not in loaded
            and os.path.exists(os.path.join(pr.PIECES_DIR, p["id"] + ".blend"))]


class RKA_OT_jump_to_district(bpy.types.Operator):
    bl_idname = "rka.jump_to_district"
    bl_label = "Jump to District"
    bl_description = "Snap the 3D viewport to a district by name -- search all 36 grid cells"
    bl_property = "target"

    target: bpy.props.EnumProperty(items=_district_enum_items, name="District")

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

    def execute(self, context):
        gx, gy = (int(v) for v in self.target.split(":"))
        cx, cy = wg.district_center(gx, gy)
        elev = 0.0 if wg.is_void(gx, gy) else wg.elev_at(gx, gy)

        area = next((a for a in context.screen.areas if a.type == 'VIEW_3D'), None)
        if area is None:
            self.report({'WARNING'}, "No 3D Viewport visible to jump in")
            return {'CANCELLED'}
        rv3d = area.spaces.active.region_3d
        rv3d.view_location = (cx, cy, elev)
        rv3d.view_distance = wg.DISTRICT * 1.3

        self.report({'INFO'}, "Jumped to (%d, %d)" % (gx, gy))
        return {'FINISHED'}


class RKA_OT_load_piece(bpy.types.Operator):
    bl_idname = "rka.load_piece"
    bl_label = "Load Piece"
    bl_description = (
        "Append one specific registered, built piece into THIS open file only -- the mirror of "
        "'Unload Piece', for bringing back (or loading for the first time) just one piece "
        "without refreshing/re-adding everything else. Session-local: nothing on disk changes"
    )
    bl_property = "target"
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(items=_unloaded_piece_enum_items, name="Piece")

    @classmethod
    def poll(cls, context):
        loaded = set(sc.loaded_piece_ids())
        return any(p["id"] not in loaded and os.path.exists(
            os.path.join(pr.PIECES_DIR, p["id"] + ".blend")) for p in pr.all_pieces())

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

    def execute(self, context):
        if not self.target:
            self.report({'ERROR'}, "Pick a piece first")
            return {'CANCELLED'}
        wrapper, err = sc.append_piece_content(self.target, context.scene)
        if wrapper is None:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, "Loaded '%s' into this session (save to persist)" % self.target)
        return {'FINISHED'}


class RKA_OT_unload_piece(bpy.types.Operator):
    bl_idname = "rka.unload_piece"
    bl_label = "Unload Piece"
    bl_description = (
        "Remove one piece's content from THIS open file only -- for trimming a large session "
        "(e.g. world_session.blend with all 37+ pieces loaded) down to just what you're "
        "actively editing, to avoid the kind of depsgraph-scale crash a very large scene can "
        "hit under heavy Geometry Nodes editing. Does NOT delete anything -- the piece's own "
        ".blend, its pieces.json entry, and the game world are all untouched; re-load it any "
        "time via 'Refresh' or 'Add District(s)'. Different from 'Remove Piece', which deletes "
        "the piece for real"
    )
    bl_property = "target"
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(items=_loaded_piece_enum_items, name="Piece")

    @classmethod
    def poll(cls, context):
        return any(sc.is_wrapper(c.name) for c in bpy.data.collections)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}

    def execute(self, context):
        was_dirty = sc.unload_piece(self.target)
        if was_dirty is None:
            self.report({'ERROR'}, "'%s' is not currently loaded in this file" % self.target)
            return {'CANCELLED'}
        sc.purge_orphans()
        msg = "Unloaded '%s' from this session (save to persist)" % self.target
        if was_dirty:
            msg += " -- WARNING: it had unsynced edits, now discarded from this file only " \
                   "(its own .blend on disk is untouched)"
        self.report({'WARNING' if was_dirty else 'INFO'}, msg)
        return {'FINISHED'}


class RKA_OT_unload_all_pieces(bpy.types.Operator):
    bl_idname = "rka.unload_all_pieces"
    bl_label = "Unload All Pieces"
    bl_description = (
        "Drop EVERY piece currently loaded in this file (session-local only, same as 'Unload "
        "Piece' but all at once) -- for starting a big edit from an empty/near-empty session "
        "instead of dropping pieces one at a time, or just to free up memory/depsgraph load. "
        "Nothing on disk changes; re-add everything any time with 'Refresh' (it re-adds every "
        "registered piece missing from this file) or individual pieces via 'Add District(s)'"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(sc.is_wrapper(c.name) for c in bpy.data.collections)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        ids = sc.loaded_piece_ids()
        dirty_ids = [pid for pid in ids if sc.unload_piece(pid)]
        sc.purge_orphans()
        msg = "Unloaded %d piece(s) from this session (save to persist)" % len(ids)
        if dirty_ids:
            shown = ", ".join(dirty_ids[:5]) + (", ..." if len(dirty_ids) > 5 else "")
            msg += " -- WARNING: %d had unsynced edits, now discarded from this file only " \
                   "(their own .blend files on disk are untouched): %s" % (len(dirty_ids), shown)
        self.report({'WARNING' if dirty_ids else 'INFO'}, msg)
        return {'FINISHED'}


class RKA_OT_remove_piece(bpy.types.Operator):
    bl_idname = "rka.remove_piece"
    bl_label = "Remove Piece (Permanent)"
    bl_description = (
        "Permanently delete a piece: its own .blend (+ .seam.json/.lanekit.json sidecars) and "
        "its pieces.json registry entry, then rebuild world_master.blend (and refresh "
        "world_session.blend if it currently exists). Does NOT delete already-baked Godot "
        "output files (res://.../world/districts/<id>.*) -- those go stale until the next full "
        "cleanup. This is NOT 'Unload Piece' (session-local, non-destructive) -- this cannot be "
        "undone unless the .blend was already committed to git. Runs in the background, see "
        "System Console"
    )
    bl_options = {'REGISTER'}

    target: bpy.props.EnumProperty(items=_registered_piece_enum_items, name="Piece")
    confirm: bpy.props.BoolProperty(
        name="Yes, permanently delete this piece's .blend file", default=False)

    _timer = None
    _proc = None
    _out_queue = None
    _stage = ""
    _removed_id = ""
    _removed_files = ()

    def invoke(self, context, event):
        self.confirm = False
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target")
        layout.separator()
        col = layout.column(align=True)
        col.label(text="Permanently deletes pieces/%s.blend (+ seam/lanekit sidecars)" %
                  (self.target or "<pick above>"), icon='ERROR')
        col.label(text="and its pieces.json entry. Cannot be undone unless already")
        col.label(text="committed to git. Baked Godot output files are left stale.")
        layout.prop(self, "confirm")

    def execute(self, context):
        if not self.target:
            self.report({'ERROR'}, "Pick a piece first")
            return {'CANCELLED'}
        if not self.confirm:
            self.report({'ERROR'}, "Check the confirm box to actually delete -- nothing removed")
            return {'CANCELLED'}

        pid = self.target
        pieces_dir = os.path.join(paths.WORLD_SOURCE, "pieces")
        removed = []
        for suffix in (".blend", ".blend1", ".seam.json", ".lanekit.json"):
            p = os.path.join(pieces_dir, pid + suffix)
            if os.path.exists(p):
                os.remove(p)
                removed.append(os.path.basename(p))
        pr.remove_piece(pid)
        sc.unload_piece(pid)   # drop it from the CURRENT file too, if it happened to be loaded

        self._removed_id = pid
        self._removed_files = removed

        script = os.path.join(paths.BLENDER_SRC, "tools", "build_world.py")
        self._proc = subprocess.Popen(
            [bpy.app.binary_path, "--background", "--python", script, "--"],
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        self._out_queue, _ = ge._bg_reader(self._proc)
        self._stage = "master"

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Removed %s (%s) -- rebuilding world_master.blend, see System "
                    "Console" % (pid, ", ".join(removed) or "no files found"))
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        done = False
        while True:
            try:
                line = self._out_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                done = True
                break
            print("[rka.remove_piece/%s] %s" % (self._stage, line.rstrip()))

        if not done:
            return {'RUNNING_MODAL'}

        ret = self._proc.wait()
        if ret != 0:
            context.window_manager.event_timer_remove(self._timer)
            self.report({'ERROR'}, "Remove Piece failed at '%s' stage (exit %d) -- see System "
                                    "Console (the piece's files/registry entry are already "
                                    "removed regardless)" % (self._stage, ret))
            return {'CANCELLED'}

        if self._stage == "master" and os.path.exists(SESSION_PATH):
            self._stage = "session"
            script = os.path.join(paths.BLENDER_SRC, "tools", "open_world_session.py")
            self._proc = subprocess.Popen(
                [bpy.app.binary_path, "--background", "--python", script, "--"],
                cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
            self._out_queue, _ = ge._bg_reader(self._proc)
            return {'RUNNING_MODAL'}

        context.window_manager.event_timer_remove(self._timer)
        refreshed_session = self._stage == "session"
        self.report({'INFO'}, "'%s' removed -- world_master.blend rebuilt%s" %
                    (self._removed_id,
                     " + world_session.blend refreshed" if refreshed_session else ""))
        if refreshed_session and bpy.data.filepath == SESSION_PATH:
            bpy.ops.wm.revert_mainfile()          # pick up the just-refreshed on-disk state
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


class RKA_OT_place_piece_anchor(bpy.types.Operator):
    bl_idname = "rka.place_piece_anchor"
    bl_label = "Place Piece Anchor"
    bl_description = (
        "Drop a new freestanding piece anchor at the 3D cursor and register it in pieces.json -- "
        "the one way to author any piece now, grid district or not: no district-vs-overlay "
        "decision, no grid cell needed (FREESTANDING_PIECES_PLAN.md §B). Footprint/radii can be "
        "left at their defaults and hand-tuned later via the anchor's own Custom Properties"
    )
    bl_options = {'REGISTER', 'UNDO'}

    piece_id: bpy.props.StringProperty(
        name="Piece Id", description="Filename stem this piece's own .blend will be saved as, "
                                      "e.g. Piece_HanedaIsland")
    footprint_x: bpy.props.FloatProperty(name="Footprint X", default=60.0, min=1.0, unit='LENGTH')
    footprint_height: bpy.props.FloatProperty(name="Footprint Height (Y)", default=40.0, min=1.0,
                                               unit='LENGTH')
    footprint_z: bpy.props.FloatProperty(name="Footprint Z (depth)", default=60.0, min=1.0,
                                          unit='LENGTH')
    load_radius: bpy.props.FloatProperty(
        name="Load Radius (0 = size-based default)", default=0.0, min=0.0, unit='LENGTH')
    unload_radius: bpy.props.FloatProperty(
        name="Unload Radius (0 = size-based default)", default=0.0, min=0.0, unit='LENGTH')
    theme: bpy.props.StringProperty(
        name="Theme (optional)", description="Leave blank for a themeless piece -- WorldBaker "
                                              "falls back to sane defaults (see build_world.py)")

    def invoke(self, context, event):
        loc = context.scene.cursor.location
        gx, gy = wg.grid_cell_of(loc[0], loc[1])
        self.piece_id = wg.suggest_piece_id(loc[0], loc[1])
        self.theme = wg.theme_at(gx, gy)
        collider = next((p for p in pr.all_pieces()
                          if p.get("grid") == [gx, gy] and p["id"] != self.piece_id), None)
        if collider is not None:
            self.report({'WARNING'}, "Grid cell (%d, %d) already belongs to '%s' -- that's fine "
                        "for a large/oddly-shaped piece (an address, not a containment boundary), "
                        "but rename Piece Id below if you meant a different spot"
                        % (gx, gy, collider["id"]))
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        pid = self.piece_id.strip()
        if not pid:
            self.report({'ERROR'}, "Piece Id is required")
            return {'CANCELLED'}
        if pr.piece_by_id(pid) is not None:
            self.report({'ERROR'}, "'%s' is already registered" % pid)
            return {'CANCELLED'}

        loc = tuple(context.scene.cursor.location)
        gx, gy = wg.grid_cell_of(loc[0], loc[1])
        footprint = (self.footprint_x, self.footprint_height, self.footprint_z)

        anchor = bpy.data.objects.new(pid, None)
        anchor.empty_display_type = 'ARROWS'
        anchor.empty_display_size = max(self.footprint_x, self.footprint_z) / 2.0
        anchor.location = loc
        anchor["rka_piece_id"] = pid
        anchor["rka_piece_footprint"] = list(footprint)
        anchor["rka_piece_grid"] = [gx, gy]
        if self.load_radius > 0.0:
            anchor["rka_piece_load_radius"] = self.load_radius
        if self.unload_radius > 0.0:
            anchor["rka_piece_unload_radius"] = self.unload_radius
        if self.theme.strip():
            anchor["rka_piece_theme"] = self.theme.strip()
        context.scene.collection.objects.link(anchor)

        pr.set_piece(pid, footprint=footprint, position=loc,
                     load_radius=(self.load_radius or None),
                     unload_radius=(self.unload_radius or None),
                     theme=(self.theme.strip() or None), grid=(gx, gy))

        self.report({'INFO'}, "Registered '%s' in pieces.json at %s -- author its content, save "
                    "as pieces/%s.blend, then rebuild the master (Refresh World Session picks it "
                    "up automatically)." % (pid, tuple(round(v, 1) for v in loc), pid))
        return {'FINISHED'}


CLASSES = (RKA_OT_open_world_session, RKA_OT_writeback_world_session, RKA_OT_jump_to_district,
           RKA_OT_load_piece, RKA_OT_unload_piece, RKA_OT_unload_all_pieces, RKA_OT_remove_piece,
           RKA_OT_place_piece_anchor)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
