"""One-click "Export to Godot" for a district .blend: regenerates the combined lane-kit sidecar
(`tools/save_lane_kit.py`) then runs the full export/bake/navmesh/binary-convert pipeline
(`tools/build_piece.sh <stem>`, stem form -- bake-only, never regenerates the .blend), exactly the
two-command sequence documented in road_blender_godot.md's "vehicles crash at a point" fix.

Both stages are real `blender --background`/bash subprocesses (mirroring what `build_piece.sh`
itself already shells out to for its own Godot bake steps), run via a modal timer so the Blender
UI stays responsive instead of freezing for the ~20-40s a full export/bake takes. Output streams
live to the System Console (Window > Toggle System Console on Windows; already visible on
Linux/macOS) and a final summary goes to the Status Bar / Info log.

Only meaningful for a STEM-named district file (`District_<theme>_<gx>_<gy>.blend`) -- that's the
only form `build_piece.sh` bakes without also trying to regenerate the .blend from a town config.
"""
import os
import queue
import subprocess
import threading

import bpy

from . import paths


class RKA_OT_export_to_godot(bpy.types.Operator):
    bl_idname = "rka.export_to_godot"
    bl_label = "Export District to Godot"
    bl_description = (
        "Save, regenerate this district's combined lanekit sidecar (tools/save_lane_kit.py), "
        "then export + bake it to Godot (tools/build_piece.sh) -- runs in the background, watch "
        "the System Console for progress"
    )

    _timer = None
    _proc = None
    _reader_thread = None
    _out_queue = None
    _stage = ""
    _stem = ""

    @classmethod
    def poll(cls, context):
        name = os.path.basename(bpy.data.filepath)
        return bool(bpy.data.filepath) and name.startswith("District_") and name.endswith(".blend")

    def invoke(self, context, event):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first -- export needs a real file path")
            return {'CANCELLED'}
        name = os.path.basename(bpy.data.filepath)
        if not (name.startswith("District_") and name.endswith(".blend")):
            self.report({'ERROR'}, "Export to Godot only supports a District_<theme>_<gx>_<gy>.blend "
                                    "(stem form) -- rename/save as one, or use "
                                    "tools/build_overlay.sh manually for a non-district file")
            return {'CANCELLED'}
        self._stem = name[:-len(".blend")]

        bpy.ops.wm.save_mainfile()
        self._stage = "lanekit"
        self._proc = self._start_lanekit()
        self._start_reader()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Exporting '%s' to Godot -- see System Console for progress" % self._stem)
        return {'RUNNING_MODAL'}

    def _start_lanekit(self):
        script = os.path.join(paths.WORLD_SOURCE, "tools", "save_lane_kit.py")
        return subprocess.Popen(
            [bpy.app.binary_path, bpy.data.filepath, "--background", "--python", script, "--"],
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)

    def _start_build(self):
        build_sh = os.path.join(paths.WORLD_SOURCE, "tools", "build_piece.sh")
        return subprocess.Popen(
            ["bash", build_sh, self._stem],
            cwd=paths.WORLD_SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)

    def _start_reader(self):
        # A plain readline() loop in modal() would block Blender's main thread whenever the
        # subprocess pauses between lines -- exactly the freeze this modal-timer approach is
        # meant to avoid. Read on a background thread instead; modal() only ever does a
        # non-blocking queue drain. The thread puts a `None` sentinel once the pipe hits EOF
        # (process exited) so modal() knows it's safe to call proc.wait() for the exit code.
        self._out_queue = queue.Queue()
        proc = self._proc
        q = self._out_queue

        def _pump():
            if proc.stdout is not None:
                for line in iter(proc.stdout.readline, ""):
                    q.put(line)
            q.put(None)

        self._reader_thread = threading.Thread(target=_pump, daemon=True)
        self._reader_thread.start()

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
            print("[rka.export_to_godot/%s] %s" % (self._stage, line.rstrip()))

        if not stage_done:
            return {'RUNNING_MODAL'}

        ret = self._proc.wait()
        if ret != 0:
            context.window_manager.event_timer_remove(self._timer)
            self.report({'ERROR'}, "Export failed at '%s' stage (exit %d) -- see System Console"
                         % (self._stage, ret))
            return {'CANCELLED'}

        if self._stage == "lanekit":
            self._stage = "build"
            self._proc = self._start_build()
            self._start_reader()
            return {'RUNNING_MODAL'}

        context.window_manager.event_timer_remove(self._timer)
        self.report({'INFO'}, "Exported '%s' to Godot -- full log in the System Console"
                     % self._stem)
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


CLASSES = (RKA_OT_export_to_godot,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
