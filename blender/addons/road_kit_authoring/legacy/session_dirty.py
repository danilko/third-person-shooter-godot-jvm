"""Marks a Piece__<id> wrapper collection (holding that piece's appended content, see
lib/session_common.py) dirty the instant a genuine edit happens
anywhere inside it -- Blender's own depsgraph change-notification, the same mechanism a real
engine's world-partition/streaming-level editor relies on to know what needs saving, instead of
reconstructing "did this change" after the fact by comparing recomputed content hashes. See
lib/session_common.py's module docstring and AUTHORING_GUIDE.md's "One file for the whole world".

Follows the exact two hard-won rules live_edit.py's depsgraph handler already established (see
that file's docstring for the full history):
  1. The handler MUST be @bpy.app.handlers.persistent, or Blender silently drops it on ANY file
     load/reopen (including the addon's own already-"enabled" state surviving a file open) --
     without this, dirty-tracking would appear to work once, then silently stop.
  2. The handler must NEVER mutate bpy.data directly -- only record plain Python names in a set
     here; the actual `rka_dirty` property write happens in a debounced bpy.app.timers callback
     (_flush), safely outside the depsgraph evaluation. A modal drag fires this handler on nearly
     every mouse-move step, so debounce+re-arm (not a fire-once timer) on every dirtying tick.
  3. Match collections by scanning bpy.data.collections + name membership, NOT
     obj.users_collection -- confirmed (by live_edit.py) to read back stale/empty inside this
     exact callback even for a genuinely-member object.
"""
import bpy

import session_common as sc  # lib/ already on sys.path via paths.py (every addon module here
                              # imports it the same bare way)

DIRTY_PROP = "rka_dirty"
_DEBOUNCE_SECONDS = 0.3   # matches live_edit.py's convention (0.2s) with a little more slack --
                          # long enough that a drag has released control back before this fires

_pending = set()
_timer_scheduled = False


def _wrapper_ancestor_names():
    """{child_or_self_collection_name: top_wrapper_name} for every local Piece__<id> wrapper
    currently in the file -- built fresh each tick (cheap: at most a few dozen collections even in
    the whole-world session) so a dirtied object anywhere in a wrapper's own nested collections
    (Segment_001, Intersection_4WAY_001, a terrain mesh, an OVERLAY collection, ...) resolves back
    to the owning wrapper -- ONE dirty flag per piece, not per collection, since write-back always
    processes a whole item together regardless of which of its pieces was actually touched."""
    owner = {}
    for coll in bpy.data.collections:
        if coll.library is not None or not sc.is_wrapper(coll.name):
            continue
        owner[coll.name] = coll.name
        for child in coll.children_recursive:
            owner[child.name] = coll.name
    return owner


@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph):
    global _timer_scheduled

    dirty_obj_names = set()
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object) and (update.is_updated_transform
                                                    or update.is_updated_geometry):
            dirty_obj_names.add(obj.name)
        elif isinstance(obj, (bpy.types.Mesh, bpy.types.Curve)) and update.is_updated_geometry:
            for o in bpy.data.objects:
                if o.data == obj:
                    dirty_obj_names.add(o.name)

    if not dirty_obj_names:
        return

    owner_by_coll_name = _wrapper_ancestor_names()
    if not owner_by_coll_name:
        return                                     # not a session/scratch file -- nothing to do

    newly_dirty = set()
    for coll_name, owner_name in owner_by_coll_name.items():
        if owner_name in _pending or owner_name in newly_dirty:
            continue
        coll = bpy.data.collections.get(coll_name)
        if coll is not None and any(name in coll.objects for name in dirty_obj_names):
            newly_dirty.add(owner_name)

    if not newly_dirty:
        return
    _pending.update(newly_dirty)

    # Re-arm on EVERY dirtying tick (not just the first) -- a modal drag fires this handler on
    # nearly every mouse-move step; a fire-once timer from the first tick would land mid-drag.
    if bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
    bpy.app.timers.register(_flush, first_interval=_DEBOUNCE_SECONDS)
    _timer_scheduled = True


def _flush():
    """Runs OUTSIDE the depsgraph callback, once activity has settled -- the only place that
    actually writes the rka_dirty property."""
    global _timer_scheduled
    names = set(_pending)
    _pending.clear()
    _timer_scheduled = False
    for name in names:
        coll = bpy.data.collections.get(name)
        if coll is not None and coll.library is None:
            coll[DIRTY_PROP] = True
    return None                                   # one-shot -- do not repeat


def register():
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    global _timer_scheduled
    if _timer_scheduled and bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
    _timer_scheduled = False
