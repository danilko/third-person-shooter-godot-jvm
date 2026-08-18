"""Panel-driven multi-piece combined editing session -- wraps tools/open_district_group.py
and tools/writeback_district_group.py (see AUTHORING_GUIDE.md "When roads/geometry must be
edited across the seam together") behind one-click buttons, using the same background-subprocess
+ modal-timer pattern as ops_export.py (RKA_OT_export_to_godot) so the UI never blocks. Works
identically for a grid district or a freestanding piece (FREESTANDING_PIECES_PLAN.md §E) -- both
are just "a registered piece id" here, no branch.

"Open Group": runs from a grid-addressed piece .blend (Piece_<gx>_<gy>.blend). Presents a checkbox
per edge-adjacent neighbour (built districts only); on click, shells out to
tools/open_district_group.py to build a disposable scratch .blend appending this district + the
checked neighbours' content (roads AND ground/terrain) at true relative offsets, then opens that
scratch file directly in the current Blender window.

"Write Back Group": runs from an open scratch session (any file containing a `Piece__<id>`
wrapper collection, see lib/session_common.py). Saves, shells out to
tools/writeback_district_group.py (writes every piece's content back to its own file), then
chains tools/build_piece.sh per touched item and finally tools/check_seams.py for any touched
grid-district seam pair -- all in the background, one stage at a time, System Console progress,
exactly like "Export District to Godot".
"""
import os
import queue
import subprocess
import threading
import time

import bpy

from . import paths
import session_common as sc  # lib/ already on sys.path via paths.py
import piece_registry as pr
import world_grid as wg

NEIGHBOR_OFFSETS = (
    ("west", -1, 0),
    ("east", 1, 0),
    ("south", 0, -1),
    ("north", 0, 1),
)


def current_district_coords():
    """(gx, gy) of the currently open file's own piece, or None if it isn't a registered,
    grid-addressed piece -- a registry lookup on its own id (filename minus .blend), reading the
    `grid` field pieces.json stores explicitly (world_grid.grid_cell_of at registration time),
    not a filename regex."""
    my_id = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    piece = pr.piece_by_id(my_id)
    if piece is None or piece.get("grid") is None:
        return None
    return tuple(piece["grid"])


def neighbor_stem(gx, gy):
    """Built piece id at grid cell (gx,gy), or None if not built yet -- a registry lookup, not a
    theme-guessing filename construction (a cell's real piece might be suffixed, e.g. a nominal
    collision resolved to Piece_2_3_b, so this checks EVERY registered piece's own `grid` field
    rather than assuming `piece_id_for_cell(gx,gy)` is exactly right)."""
    for piece in pr.all_pieces():
        if piece.get("grid") == [gx, gy]:
            return piece["id"]
    return None


def _adjacent_pairs(stems):
    """Every edge-adjacent (dx+dy==1) pair among a group's piece ids, for check_seams.py -- which
    checks exactly ONE named pair per invocation (pieces/<id>.seam.json x2), not a whole-grid
    sweep. A piece with no `grid` field (or not registered at all) simply produces no pair, not
    an error -- works identically for a grid-shaped id or a freestanding one."""
    coords = {}
    for stem in stems:
        piece = pr.piece_by_id(stem)
        if piece is not None and piece.get("grid") is not None:
            coords[stem] = tuple(piece["grid"])
    pairs = []
    for i, a in enumerate(stems):
        if a not in coords:
            continue
        ax, ay = coords[a]
        for b in stems[i + 1:]:
            if b not in coords:
                continue
            bx, by = coords[b]
            if abs(ax - bx) + abs(ay - by) == 1:
                pairs.append((a, b))
    return pairs


def append_item_here(item, dest_scene):
    """In-process equivalent of tools/open_district_group.py's append_item, for pulling one more
    piece into an ALREADY-OPEN interactive group session (no subprocess/new file needed -- we're
    already running inside the target scene). Adds the "already in this session" duplicate check,
    which only matters for this incremental-add path (the CLI tool always starts from an empty
    file)."""
    piece, _abspath = sc.resolve_item(item)
    if piece is None:
        return None, "not a registered piece (see pieces.json)"
    if any(c.name == sc.wrapper_name(item) for c in bpy.data.collections):
        return None, "%s is already in this group session" % item
    return sc.append_piece_content(item, dest_scene)


def _parse_extra_stems(text):
    return [s.strip() for s in text.split(",") if s.strip()]


def _bg_reader(proc):
    q = queue.Queue()

    def _pump():
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                q.put(line)
        q.put(None)

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    return q, t


class RKA_OT_open_district_group(bpy.types.Operator):
    bl_idname = "rka.open_district_group"
    bl_label = "Open Group"
    bl_description = (
        "Append this district + the checked neighbours' MANUAL content into one disposable "
        "scratch file at their true relative offsets, then open it -- for hand-editing road "
        "geometry that spans a shared seam together (see AUTHORING_GUIDE.md)"
    )

    _timer = None
    _proc = None
    _out_queue = None
    _out_path = ""

    @classmethod
    def poll(cls, context):
        return current_district_coords() is not None

    def invoke(self, context, event):
        coords = current_district_coords()
        if coords is None:
            self.report({'ERROR'}, "Open a registered, grid-addressed piece .blend first "
                                    "(see pieces.json)")
            return {'CANCELLED'}
        gx, gy = coords
        rka = context.scene.rka

        stems = [os.path.basename(bpy.data.filepath)[:-len(".blend")]]
        for key, dx, dy in NEIGHBOR_OFFSETS:
            if not getattr(rka, "group_include_%s" % key):
                continue
            stem = neighbor_stem(gx + dx, gy + dy)
            if stem:
                stems.append(stem)
        for stem in _parse_extra_stems(rka.group_extra_stems):
            if stem not in stems:
                stems.append(stem)

        if len(stems) < 2:
            self.report({'ERROR'}, "Check at least one built neighbour, or type a district stem "
                                    "under 'Other Districts', first")
            return {'CANCELLED'}

        out_name = "_group_%d_%d_%d" % (gx, gy, int(time.time()))
        self._out_path = os.path.join(paths.WORLD_SOURCE, out_name + ".blend")
        script = os.path.join(paths.BLENDER_SRC, "tools", "open_district_group.py")
        self._proc = subprocess.Popen(
            [bpy.app.binary_path, "--background", "--python", script, "--", out_name] + stems,
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        self._out_queue, _ = _bg_reader(self._proc)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Opening group (%s) -- see System Console" % ", ".join(stems))
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
            print("[rka.open_district_group] %s" % line.rstrip())

        if not done:
            return {'RUNNING_MODAL'}

        context.window_manager.event_timer_remove(self._timer)
        ret = self._proc.wait()
        if ret != 0 or not os.path.exists(self._out_path):
            self.report({'ERROR'}, "Open Group failed (exit %d) -- see System Console" % ret)
            return {'CANCELLED'}

        out_path = self._out_path
        self.report({'INFO'}, "Opened %s -- edit freely, then 'Write Back Group' when done" %
                    os.path.basename(out_path))
        bpy.ops.wm.open_mainfile(filepath=out_path)
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


class RKA_OT_add_district_to_group(bpy.types.Operator):
    bl_idname = "rka.add_district_to_group"
    bl_label = "Add District(s)/Overlay(s)"
    bl_description = (
        "Pull one or more additional districts and/or overlays (typed under 'Other Districts / "
        "Overlays', comma-separated -- any district or overlay in the world, not just adjacent "
        "ones) into THIS already-open group session, at their true relative position, without "
        "restarting -- for when editing reveals the fix needs to reach further than what you "
        "started with"
    )

    @classmethod
    def poll(cls, context):
        return any(sc.is_wrapper(c.name) for c in bpy.data.collections)

    def invoke(self, context, event):
        rka = context.scene.rka
        items = _parse_extra_stems(rka.group_extra_stems)
        if not items:
            self.report({'ERROR'}, "Type a piece id under 'Other Districts / Overlays' first")
            return {'CANCELLED'}

        added, errors = [], []
        for item in items:
            wrapper, err = append_item_here(item, context.scene)
            if err:
                errors.append("%s: %s" % (item, err))
            else:
                added.append(item)

        if added:
            self.report({'INFO'}, "Added to group: %s" % ", ".join(added))
        if errors:
            self.report({'WARNING'}, "; ".join(errors))
        return {'FINISHED'} if added else {'CANCELLED'}


class RKA_OT_writeback_district_group(bpy.types.Operator):
    bl_idname = "rka.writeback_district_group"
    bl_label = "Write Back Group"
    bl_description = (
        "Save, write every piece's content in this scratch session back into its own .blend, "
        "rebuild each touched item, and check the seam between any touched district pair -- "
        "runs in the background, see System Console"
    )

    _timer = None
    _proc = None
    _out_queue = None
    _stage = ""
    _stems = ()
    _build_index = 0
    _pairs = ()
    _pair_index = 0
    _seam_warnings = 0

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath) and any(
            sc.is_wrapper(c.name) for c in bpy.data.collections)

    def invoke(self, context, event):
        self._stems = sorted(sc.piece_id_from_wrapper(c.name) for c in bpy.data.collections
                              if sc.is_wrapper(c.name))
        if not self._stems:
            self.report({'ERROR'}, "Not a group session here (open one via 'Open Group' first)")
            return {'CANCELLED'}

        # A piece with no registered `grid` field is simply excluded from pairing -- works
        # uniformly for a grid-addressed piece or a genuinely freestanding one.
        self._pairs = _adjacent_pairs(self._stems)
        self._seam_warnings = 0

        bpy.ops.wm.save_mainfile()
        self._stage = "writeback"
        self._proc = self._start_writeback()
        self._out_queue, _ = _bg_reader(self._proc)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Writing back (%s) -- see System Console" %
                    ", ".join(self._stems))
        return {'RUNNING_MODAL'}

    def _start_writeback(self):
        script = os.path.join(paths.BLENDER_SRC, "tools", "writeback_district_group.py")
        return subprocess.Popen(
            [bpy.app.binary_path, "--background", "--python", script, "--",
             bpy.data.filepath] + list(self._stems),
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)

    def _start_build(self, item):
        build_sh = os.path.join(paths.BLENDER_SRC, "tools", "build_piece.sh")
        return subprocess.Popen(
            ["bash", build_sh, item],
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)

    def _start_check_seams(self, stem_a, stem_b):
        script = os.path.join(paths.BLENDER_SRC, "tools", "check_seams.py")
        seam_a = os.path.join(paths.WORLD_SOURCE, "pieces", stem_a + ".seam.json")
        seam_b = os.path.join(paths.WORLD_SOURCE, "pieces", stem_b + ".seam.json")
        return subprocess.Popen(
            ["python3", script, seam_a, seam_b], cwd=paths.WORLD_SOURCE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        stage_done = False
        while True:
            try:
                line = self._out_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                stage_done = True
                break
            print("[rka.writeback_district_group/%s] %s" % (self._stage, line.rstrip()))

        if not stage_done:
            return {'RUNNING_MODAL'}

        ret = self._proc.wait()

        # A non-zero exit from check_seams means "found a real mismatch" (a legitimate,
        # useful finding), not a broken script -- don't hard-abort the whole operation over
        # it like a writeback/build failure would; just note it and keep checking.
        if ret != 0 and self._stage != "check_seams":
            context.window_manager.event_timer_remove(self._timer)
            self.report({'ERROR'}, "Write Back failed at '%s' stage (exit %d) -- see System "
                                    "Console" % (self._stage, ret))
            return {'CANCELLED'}
        if ret != 0 and self._stage == "check_seams":
            self._seam_warnings += 1

        if self._stage == "writeback":
            self._stage = "build"
            self._build_index = 0
            self._proc = self._start_build(self._stems[self._build_index])
            self._out_queue, _ = _bg_reader(self._proc)
            return {'RUNNING_MODAL'}

        if self._stage == "build":
            self._build_index += 1
            if self._build_index < len(self._stems):
                self._proc = self._start_build(self._stems[self._build_index])
                self._out_queue, _ = _bg_reader(self._proc)
                return {'RUNNING_MODAL'}
            self._stage = "check_seams"
            self._pair_index = 0
            if self._pairs:
                self._proc = self._start_check_seams(*self._pairs[self._pair_index])
                self._out_queue, _ = _bg_reader(self._proc)
                return {'RUNNING_MODAL'}
            # no adjacent pairs in this group -- nothing to check, fall through to done below

        elif self._stage == "check_seams":
            self._pair_index += 1
            if self._pair_index < len(self._pairs):
                self._proc = self._start_check_seams(*self._pairs[self._pair_index])
                self._out_queue, _ = _bg_reader(self._proc)
                return {'RUNNING_MODAL'}

        context.window_manager.event_timer_remove(self._timer)
        if self._seam_warnings:
            self.report({'WARNING'}, "Wrote back + rebuilt %s -- %d seam pair(s) still "
                                      "disagree, see System Console" %
                        (", ".join(self._stems), self._seam_warnings))
        else:
            self.report({'INFO'}, "Wrote back + rebuilt %s -- every checked seam agrees, full "
                                   "log in the System Console" % ", ".join(self._stems))
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


CLASSES = (RKA_OT_open_district_group, RKA_OT_add_district_to_group,
           RKA_OT_writeback_district_group)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
