#!/usr/bin/env python3
"""
session_common.py -- shared helpers for the multi-piece / whole-world Blender editing session
tools (tools/open_district_group.py, tools/writeback_district_group.py,
tools/open_world_session.py, tools/writeback_world_session.py, and the road_kit_authoring addon's
ops_group_edit.py/ops_world_session.py). See AUTHORING_GUIDE.md §4.

Unlike those, this is a PLAIN IMPORTABLE module -- no top-level `main()` call. The CLI tools are
__main__-style scripts and unsafe to import directly (they'd execute immediately on import),
which is exactly why this logic was duplicated three times (once per tool) before being pulled
out here. Import it the same way every piece-aware script already imports `world_grid`: add
`lib/` to `sys.path` first (every caller already does this), then `import session_common as sc`.

Needs `bpy` (append_piece_content touches live Blender data) -- unlike `world_grid.py` or
`piece_registry.py`, this module is NOT engine-free.

Every piece -- grid district or freestanding alike, no distinction (FREESTANDING_PIECES_PLAN.md
§B/§E) -- contributes ONE wrapper collection, `Piece__<id>` (WRAPPER_PREFIX), holding EVERY
top-level collection its own .blend actually has (their plain, unprefixed names -- nesting under a
uniquely-named-per-piece wrapper already disambiguates them across pieces, so there's no need to
rename them) as children, EXCEPT `EXCLUDE_COLLECTIONS` -- currently just `NEIGHBOR_REF`
(tools/link_neighbors.py's linked read-only reference content: it's other pieces' data viewed from
this one, structurally never "this piece's own content", so round-tripping it here would be wrong
regardless of what it's named). This is deliberately NOT a fixed include-list of collection names
(no more "just MANUAL and STREET" hardcoding, and no more "STREET vs. OVERLAY" branch either) --
whatever a piece's .blend actually contains is synced automatically, no code change needed here
when a new collection convention shows up. Every included collection is a real, appended
(link=False) copy, genuinely editable.

A piece's world offset always comes from `lib/piece_registry.py`'s `position` field -- the single
source of truth for where every piece sits, grid-derived district or freestanding alike (a
district's `position` happens to have been computed from `district_center`/`elev_at` at migration
time; a freestanding piece's is whatever it was registered with; the code here neither knows nor
cares which). This is what let the old district-vs-overlay branch (shift by `district_center` vs.
zero-shift "already in world space") collapse into one path: every piece's own registered position
already IS its true world position, so the offset math is unconditional.

`resolve_item()` is the shared classifier every tool that accepts a mix of piece ids on its
command line uses -- a registry lookup, not a regex/file-existence probe, so it works identically
for a coordinate-named district stem and an arbitrary freestanding piece id.

Change detection uses a live dirty FLAG (`DIRTY_PROP`, see the addon's `session_dirty.py`), not
content hashing: Blender's own `depsgraph_update_post` handler already tells you the instant a
genuine edit happens, the same native-change-notification mechanism a real engine's
world-partition/streaming-level editor relies on -- there is no need to reconstruct "did this
change" after the fact by comparing recomputed hashes. `session_dirty.py`'s handler marks a
wrapper dirty live, during interactive editing (regardless of which child collection was actually
touched -- one flag per wrapper, not per collection, since write-back always processes a whole
piece's wrapper together); this module and the write-back tools only ever READ that flag.
"""
import os

import bpy
import piece_registry as pr

GROUP_PROP = "rka_group_stem"    # stamped on every top-level object: which piece it came from
DIRTY_PROP = "rka_dirty"         # True once ANY edit has touched a Piece__<id> wrapper since it
                                  # was last synced (appended fresh, or written back) -- see
                                  # session_dirty.py, which is the only thing that ever sets it
                                  # True; append/write-back are the only things that set it False.

WRAPPER_PREFIX = "Piece__"
EXCLUDE_COLLECTIONS = frozenset({
    "NEIGHBOR_REF",   # linked read-only reference content -- never this piece's own data
    "Collection",     # Blender's always-empty default scene collection, confirmed 0 objects/0
                       # children in every sampled piece -- clutter, not content
})


def wrapper_name(piece_id):
    return f"{WRAPPER_PREFIX}{piece_id}"


def piece_id_from_wrapper(wrapper_coll_name):
    """Inverse of wrapper_name -- None if the name isn't a Piece__<id> wrapper."""
    if not wrapper_coll_name.startswith(WRAPPER_PREFIX):
        return None
    return wrapper_coll_name[len(WRAPPER_PREFIX):]


def is_wrapper(coll_name):
    """True for a Piece__<id> wrapper name -- for callers (session_dirty.py, the addon panel)
    that just need to recognize "is this a synced session unit"."""
    return coll_name.startswith(WRAPPER_PREFIX)


def remove_collection_recursive(coll):
    """Removes a collection and everything nested under it (objects + child collections) --
    shared by every tool that prunes/unloads a wrapper (previously duplicated across
    open_world_session.py, writeback_district_group.py, ...)."""
    for child in list(coll.children):
        remove_collection_recursive(child)
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(coll)


def loaded_piece_ids():
    """Every piece id currently loaded (has a Piece__<id> wrapper) in the CURRENT file --
    distinct from piece_registry.all_pieces() (every REGISTERED piece, loaded or not)."""
    return sorted(piece_id_from_wrapper(c.name) for c in bpy.data.collections
                  if c.library is None and is_wrapper(c.name))


def purge_orphans():
    """Free every 0-user datablock (mesh/material/image/... -- everything a removed object's
    OWN datablock referenced) left behind after `remove_collection_recursive`/`unload_piece`.
    `bpy.data.objects.remove()` only frees the OBJECT datablock; the mesh/material/etc it
    pointed at becomes an orphan (0 users) and stays resident in `bpy.data` -- and therefore in
    the depsgraph and the saved file -- until explicitly purged (2026-08-01, user-reported:
    Blender stayed slow in a live session after repeatedly loading/unloading large pieces --
    each piece is 1000+ objects, so orphaned mesh data accumulates fast across cycles). Callers
    purge ONCE after a whole batch of removals (a single unload, or a bulk unload-all/prune
    loop), not per-collection inside the recursive helper itself -- `orphans_purge` scans every
    datablock in the file, so calling it once per removed piece in a 37-piece bulk unload would
    itself become the next perf problem."""
    bpy.data.orphans_purge(do_recursive=True)


def unload_piece(piece_id):
    """Remove `piece_id`'s wrapper from the CURRENT file only -- an in-memory scene edit, not a
    world/game decision (contrast the addon's "Remove Piece", which deletes the piece's .blend
    and its pieces.json entry for real and rebuilds the master). Used to trim a large session (e.g.
    world_session.blend with all 37 pieces loaded) down to just what's actively being edited,
    to avoid the depsgraph-scale/crash risk a very large scene can hit under heavy Geometry Nodes
    editing -- the piece's own .blend file, its pieces.json entry, and the game world are all
    completely untouched; re-loading it later (Refresh / Add District(s)) is unaffected.
    Returns True if something was removed, False if it wasn't loaded to begin with. If the
    wrapper was dirty (unsynced edits), those edits are discarded from THIS file -- the caller
    is responsible for surfacing that to the user (this function only returns whether it was
    dirty, it doesn't warn/print itself, same convention as the rest of this module)."""
    wrapper = bpy.data.collections.get(wrapper_name(piece_id))
    if wrapper is None:
        return None
    was_dirty = is_dirty(wrapper)
    remove_collection_recursive(wrapper)
    return was_dirty


def resolve_item(name):
    """Look up a bare name from a command line / typed-in id list against the piece registry --
    the single source of truth, so this works identically for a coordinate-named district stem or
    an arbitrary freestanding piece id, with no regex/file-existence probing. Returns (piece_dict,
    abspath), or (None, None) if `name` isn't a registered piece."""
    piece = pr.piece_by_id(name)
    if piece is None:
        return None, None
    return piece, os.path.join(pr.PIECES_DIR, name + ".blend")


def all_objects_recursive(coll, seen=None):
    """A piece collection (MANUAL or STREET) holds its content as nested child collections in
    places (e.g. MANUAL's road pieces, one per intersection/segment/transition), not always as
    direct members -- `coll.objects` alone misses everything. Walk the whole child-collection
    tree and return every object once."""
    if seen is None:
        seen = set()
    result = []
    for o in coll.objects:
        if o.name not in seen:
            seen.add(o.name)
            result.append(o)
    for child in coll.children:
        result.extend(all_objects_recursive(child, seen))
    return result


def _top_level_collection_names(abspath):
    """Root-level collection names in a library .blend -- the ones the file's own scene links
    directly into its master collection, i.e. exactly what `bpy.context.scene.collection.children`
    would give if that file were opened directly (the same definition writeback_district_group.py
    uses on the district-file side). `bpy.data.libraries.load`'s `src.collections` lists EVERY
    named collection in the file flat, with no nesting info (verified empirically: a district's
    `Base Kit` collection nested under `MANUAL` showed up as its own top-level sibling once
    appended -- corrupting the wrapper with content that was never actually the district's own
    top-level authoring surface), so it can't answer this directly.

    Read-only (link=True) linking just the file's Scene ID is the cheapest way to ask the
    question without a full load: a Scene pulls in its whole collection tree as indirectly-linked
    data, `scene.collection.children` gives the true root set, and removing that one Scene ID
    again cleanly orphans everything it pulled in (objects, materials, meshes, nested
    collections) in one sweep -- `orphans_purge(do_recursive=True)` then sweeps all of it. This
    matters because the real (link=False) load happens right after: any leftover linked
    datablock with the same name would either force a spurious '.001' rename on the real copy or
    (worse, seen with a per-collection removal instead of removing the whole Scene) get silently
    reused *as a still-linked reference* instead of a real local copy."""
    with bpy.data.libraries.load(abspath, link=True) as (src, dst):
        dst.scenes = list(src.scenes)
    scene_src = dst.scenes[0] if dst.scenes else None
    names = [c.name for c in scene_src.collection.children] if scene_src is not None else []
    if scene_src is not None:
        bpy.data.scenes.remove(scene_src)
    bpy.data.orphans_purge(do_local_ids=False, do_linked_ids=True, do_recursive=True)
    return names


def _append_top_level_content(abspath, dest_scene, wrapper_coll_name, tag_value, offset):
    """Shared APPEND core for append_piece_content: every top-level collection `abspath`'s own
    .blend has (except EXCLUDE_COLLECTIONS) into `dest_scene`, nested under a new
    `wrapper_coll_name` collection, offsetting every top-level (unparented) object by `offset`
    (the piece's registered world position, lib/piece_registry.py). Stamps the wrapper's
    DIRTY_PROP False (freshly synced) and GROUP_PROP=tag_value on every shifted object
    (provenance). Returns (wrapper_collection, error_message) -- exactly one is None. Does not
    print anything itself -- callers decide how to surface the message."""
    if not os.path.exists(abspath):
        return None, f"{abspath} does not exist"

    top_names = set(_top_level_collection_names(abspath)) - EXCLUDE_COLLECTIONS
    with bpy.data.libraries.load(abspath, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c in top_names]
    found = {c.name: c for c in dst.collections if c is not None}
    if not found:
        return None, f"{tag_value} has no syncable collections"

    wrapper = bpy.data.collections.new(wrapper_coll_name)
    dest_scene.collection.children.link(wrapper)
    for coll in found.values():
        wrapper.children.link(coll)

    ox, oy, oz = offset
    for coll in found.values():
        for obj in all_objects_recursive(coll):
            if obj.parent is not None:
                continue                          # children move with their parent
            obj.location.x += ox
            obj.location.y += oy
            obj.location.z += oz
            obj[GROUP_PROP] = tag_value

    wrapper[DIRTY_PROP] = False
    return wrapper, None


def append_piece_content(piece_id, dest_scene, pieces_dir=None):
    """APPEND `piece_id`'s own .blend into `dest_scene` under a new `Piece__<id>` wrapper, shifted
    to its registered world position (lib/piece_registry.py's `position` field -- see module
    docstring: every piece uses this same unconditional offset, grid district or freestanding
    alike, no branch). A piece with nothing syncable at all (shouldn't happen -- every district
    has at least STREET) is an error, as is a piece_id that isn't registered. See
    _append_top_level_content for the shared mechanics."""
    piece = pr.piece_by_id(piece_id)
    if piece is None:
        return None, f"{piece_id} is not a registered piece (see pieces.json)"
    abspath = os.path.join(pieces_dir or pr.PIECES_DIR, piece_id + ".blend")
    return _append_top_level_content(abspath, dest_scene, wrapper_name(piece_id), piece_id,
                                      tuple(piece["position"]))


def is_dirty(coll):
    """Whether a wrapper (Piece__<id>) has unsynced edits -- defaults to True (safer to
    over-write-back an ambiguous collection than silently skip a real change) if DIRTY_PROP is
    somehow missing entirely, e.g. a collection that predates this mechanism."""
    return bool(coll.get(DIRTY_PROP, True))


def mark_synced(coll):
    """Call after a wrapper's content has been written back to its own piece file (or freshly
    appended) so it correctly reports clean again."""
    coll[DIRTY_PROP] = False
