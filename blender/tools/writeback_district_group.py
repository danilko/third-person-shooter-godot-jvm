#!/usr/bin/env python3
"""
writeback_district_group.py -- after hand-editing a tools/open_district_group.py scratch
session, write each item's edited collections (whatever it actually contributed -- MANUAL,
STREET, OVERLAY, and anything else, found nested under its `Piece__<id>` wrapper, see
lib/session_common.py) back into that piece's own .blend (wholesale replace per collection -- not
a diff/merge, it's "these collections are now the authoritative content for this item", the same
relationship the road_kit_authoring addon's own hand-authoring already has with a piece file,
extended to ground/terrain now that nothing regenerates it either, AUTHORING_GUIDE.md §2).

Runs ONE Blender subprocess per affected item (same one-at-a-time pattern as tools/build_piece.sh)
so each file is only ever opened/saved by itself: for each <item> named on the command line (or
every `Piece__*` wrapper found in the scratch file if none are named), it looks the item up in
the piece registry (lib/session_common.py's resolve_item -- the SAME registered world position
every other tool in this pipeline uses, grid district or freestanding piece alike, no branch),
un-shifts every top-level object back to that offset, replaces the corresponding collection(s)
with the edited ones, and saves.

The scratch file itself is NEVER modified by this script and is safe to keep re-running against
(e.g. after further edits) or to discard once you're satisfied with the round trip.

After this runs, rebuild + re-validate each touched item the normal way:
  tools/build_piece.sh <id>            (any piece, grid district or freestanding)
  tools/check_seams.py                 (for any touched seam pair)

Usage:
  blender --background --python tools/writeback_district_group.py -- \\
      <scratch_name> [item1 item2 ...] [--dry-run]

  <scratch_name> is the same name passed to open_district_group.py's <out_name>. Each <itemN> is
  a registered piece id, same as open_district_group.py accepted. Omit item names to write back
  every `Piece__<id>` wrapper found in the scratch file.
  --dry-run reports the object-count delta for each item without writing/saving anything.
"""
import bpy, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_SRC = os.path.dirname(HERE)                                    # blender
ROOT = os.path.join(os.path.dirname(BLENDER_SRC), "assets", "world_source")  # data root
sys.path.insert(0, os.path.join(BLENDER_SRC, "lib"))
import session_common as sc
import piece_registry as pr

THIS_SCRIPT = os.path.abspath(__file__)


def _local_coll(name):
    for c in bpy.data.collections:
        if c.name == name and c.library is None:
            return c
    return None


_DOT_SUFFIX = re.compile(r"^(.*)\.\d{3}$")


def _clean_dot_suffixes(new_coll, new_objs):
    """Two pieces both authored via road_kit_authoring auto-number their pieces the same way
    (Segment_001, Intersection_4WAY_001, ...), so open_district_group.py appending several pieces
    into one scratch file routinely collides names -- Blender silently resolves this with its own
    '.001'/'.002' suffix. Positions/data are unaffected, but by the time we write back here the
    OLD same-named content has already been removed from this destination file, so the collision
    no longer applies -- strip the stray suffix back off wherever doing so doesn't collide with
    something else already in this file (best-effort; a rename is skipped, not forced, if the
    clean name is somehow already taken)."""
    existing_obj_names = {o.name for o in bpy.data.objects}
    existing_coll_names = {c.name for c in bpy.data.collections}
    for obj in new_objs:
        m = _DOT_SUFFIX.match(obj.name)
        if m and m.group(1) not in existing_obj_names:
            existing_obj_names.discard(obj.name)
            obj.name = m.group(1)
            existing_obj_names.add(obj.name)
    for coll in [new_coll] + list(new_coll.children_recursive):
        m = _DOT_SUFFIX.match(coll.name)
        if m and m.group(1) not in existing_coll_names:
            existing_coll_names.discard(coll.name)
            coll.name = m.group(1)
            existing_coll_names.add(coll.name)


def _remove_collection_recursive(coll):
    """Removes a collection and everything nested under it (objects + child collections)."""
    for child in list(coll.children):
        _remove_collection_recursive(child)
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(coll)


def _write_one_item(scratch_path, item, dry_run):
    """Runs INSIDE the item's own .blend (invoked as a subprocess against it, opened directly by
    the caller). Un-shifts by the piece's registered world position (lib/piece_registry.py) --
    the same source every other tool in this pipeline uses, grid district or freestanding piece
    alike, no branch."""
    piece = pr.piece_by_id(item)
    if piece is None:
        print(f"ERROR: {item} is not a registered piece (see pieces.json)")
        return False
    cx, cy, elev = piece["position"]
    wrapper_coll_name = sc.wrapper_name(item)

    # Remove OLD top-level content BEFORE appending the new content -- hand-authored pieces are
    # named the same way in every piece (Segment_001, Intersection_4WAY_001, ...), so if the old
    # collections/objects are still around when we append, Blender silently renames the incoming
    # ones to "*.001" to avoid the collision, corrupting the round trip's names (positions stay
    # correct, but every name picks up a stray suffix -- and it compounds on repeated round
    # trips). Every top-level LOCAL collection except EXCLUDE_COLLECTIONS (this item's OWN
    # NEIGHBOR_REF, if any -- completely unrelated to this write-back, must survive untouched) is
    # a sync target, same dynamic-discovery rule session_common.py's append side uses -- not a
    # fixed list of collection names.
    old_names = [c.name for c in list(bpy.context.scene.collection.children)
                 if c.name not in sc.EXCLUDE_COLLECTIONS]
    old_counts = {}
    for name in old_names:
        old = _local_coll(name)
        old_counts[name] = len(sc.all_objects_recursive(old)) if old else 0
        if not dry_run and old is not None:
            _remove_collection_recursive(old)

    with bpy.data.libraries.load(scratch_path, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == wrapper_coll_name]
    new_wrapper = dst.collections[0] if dst.collections else None
    if new_wrapper is None:
        print(f"ERROR: {wrapper_coll_name} not found in {scratch_path}")
        return False

    changed = sc.is_dirty(new_wrapper)
    print(f"[{item}] dirty: {'CHANGED' if changed else 'unchanged'}")

    new_pieces = {c.name: c for c in new_wrapper.children}
    for coll in new_pieces.values():
        for obj in sc.all_objects_recursive(coll):
            if obj.parent is not None:
                continue                          # children move with their parent
            obj.location.x -= cx
            obj.location.y -= cy
            obj.location.z -= elev
            if sc.GROUP_PROP in obj.keys():
                del obj[sc.GROUP_PROP]

    for name, coll in new_pieces.items():
        new_count = len(sc.all_objects_recursive(coll))
        print(f"[{item}] {name}: {old_counts.get(name, 0)} objects -> {new_count} objects "
              f"({len(coll.children)} pieces)")

    if dry_run:
        print(f"[{item}] --dry-run: not saved (old content not removed, so this preview run's "
              f"own append may show *.001-suffixed names internally -- harmless, nothing saved)")
        return True

    for name, coll in new_pieces.items():
        # _clean_dot_suffixes may rename coll (e.g. "STREET.001" -> "STREET") -- `name` above is
        # only the pre-cleanup dict key, so it must NOT be reapplied afterward (a `coll.name =
        # name` here previously stomped the cleaned name straight back to the stale one).
        _clean_dot_suffixes(coll, sc.all_objects_recursive(coll))
        # coll's parent is always new_wrapper here -- it's exactly what new_pieces was built from
        # (new_wrapper.children) two blocks up. (Collection has no `.users_collection` --
        # that's an Object attribute; using it here raised AttributeError, silently swallowed by
        # Blender's background-mode script error handling since no --python-exit-code was set --
        # the write-back never reached save_mainfile().)
        new_wrapper.children.unlink(coll)
        if coll.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)

    _remove_collection_recursive(new_wrapper)         # the now-empty wrapper itself, not its
                                                       # children (already relinked above)

    bpy.ops.wm.save_mainfile()
    print(f"[{item}] saved {bpy.data.filepath}")
    return True


def _discover_items(scratch_path):
    with bpy.data.libraries.load(scratch_path, link=True) as (src, _dst):
        names = [c for c in src.collections if sc.is_wrapper(c)]
    return [sc.piece_id_from_wrapper(n) for n in names]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    dry_run = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]

    if "--apply-one" in argv:
        # invoked as a subprocess with a single piece .blend open
        i = argv.index("--apply-one")
        scratch_path, item = argv[i + 1], argv[i + 2]
        ok = _write_one_item(scratch_path, item, dry_run)
        sys.exit(0 if ok else 1)

    if len(argv) < 1:
        print(__doc__)
        sys.exit(2)
    scratch_name = argv[0]
    scratch_path = scratch_name if os.path.isabs(scratch_name) else \
        os.path.join(ROOT, scratch_name + ".blend")
    if not os.path.exists(scratch_path):
        print(f"ERROR: scratch file not found: {scratch_path}")
        sys.exit(1)

    items = argv[1:] or _discover_items(scratch_path)
    if not items:
        print(f"ERROR: no {sc.WRAPPER_PREFIX}<id> collections found in scratch file")
        sys.exit(1)

    blender_bin = bpy.app.binary_path
    failures = []
    for item in items:
        piece, abspath = sc.resolve_item(item)
        if piece is None:
            print(f"ERROR: {item} is not a registered piece -- skipping")
            failures.append(item)
            continue
        if not os.path.exists(abspath):
            print(f"ERROR: {abspath} does not exist -- skipping {item}")
            failures.append(item)
            continue
        cmd = [blender_bin, "--background", abspath, "--python", THIS_SCRIPT, "--",
               "--apply-one", scratch_path, item]
        if dry_run:
            cmd.append("--dry-run")
        print(f"--- applying to {item} ---")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            failures.append(item)

    if failures:
        print(f"FAILED for: {', '.join(failures)}")
        sys.exit(1)
    print(f"{'Dry-run complete' if dry_run else 'Write-back complete'} for: {', '.join(items)}")
    if not dry_run:
        print("Next: rebuild each touched item (tools/build_piece.sh <id>), then re-run "
              "tools/check_seams.py on any touched seam pair.")


main()
