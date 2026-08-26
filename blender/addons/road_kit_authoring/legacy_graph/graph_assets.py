"""graph_assets.py -- the ASSET REGISTRY: how a per-edge integer attribute selects which real
mesh a curb / median / pillar / railing / prop row is built from.

THE PROBLEM THIS SOLVES. A mesh attribute can hold an int, a float or a vector. It cannot hold a
pointer to an Object or a Collection. So "this edge uses the Jersey-barrier median, that one uses
the planted island" cannot be stored directly on the edge -- and Geometry Nodes cannot branch to
a different Object input per edge either, because a modifier's Object socket is one value for the
whole evaluation.

THE MECHANISM. Every role (curb, median, pillar, ...) has one REGISTRY COLLECTION holding the
candidate assets as child collections. In the node tree that becomes:

    Collection Info (Separate Children, Reset Children)
        -> Instance on Points  (Pick Instance = True, Instance Index = <role>_asset_idx)

`Pick Instance` exists precisely for this: it treats the incoming instance set as a PALETTE and
picks per point by index. So the per-edge integer IS the asset choice, and swapping which mesh a
whole road uses is one attribute stamp -- no rebuild, no per-piece object reference.

TWO MEASURED CONTRACTS THIS DEPENDS ON, both verified by `smoketest_graph_solve` rather than
assumed, and both silent-wrong-answer failures if broken:

  * `Separate Children` emits the registry's children in STORAGE (link) order. Blender does not
    sort collection children -- only the outliner displays them sorted -- so `catalog()` reports
    storage order and `_resort()` keeps that order alphabetical. Sorting in `catalog()` alone
    disagreed with the node tree for any palette not linked alphabetically.
  * `Instance Index` MUST BE LINKED to a real node, never assigned through
    `socket.default_value`. It is an implicit-field socket: unlinked, it falls back to the `Index`
    field and ignores the written default entirely. Measured -- probing indices 0/1/2 via
    `default_value` returned the same asset all three times.

WHY THE ASSETS ARE LINKED COLLECTIONS, NOT APPENDED OBJECTS. `assets/world_source/kit/*.blend`
already organises every kit piece as a Collection (`Kit_Curb_JerseyBarrier_L2`,
`Kit_Median_Island`, `Kit_Curb_StreetLamp_L1`, ...), often several objects each -- a visual mesh
plus its `-colonly` collision proxy. Linking (not appending) keeps the kit blend the single
origin of that mesh: reshape the barrier there, reopen any district, every road using it updates.
That is the "change their shape/origin mesh as needed" requirement, and it only holds as long as
nothing here ever copies asset geometry into the district file.

THE INDEX IS POSITIONAL, WHICH MAKES ORDER LOAD-BEARING. `Separate Children` emits the registry's
children in Blender's own storage order, which is alphabetical by name. `catalog()` sorts the
same way so Python and the node tree agree, and `smoketest_graph_assets.py` verifies that
agreement by picking index 1 and checking which mesh actually came through, rather than trusting
it. Consequence worth knowing: inserting an asset whose name sorts EARLIER shifts every later
index, so `rka.graph_assets_reindex` exists to restamp the edges that referenced them by name.
"""
import bpy

from . import paths

ROLE_CURB = 'curb'
ROLE_MEDIAN = 'median'
ROLE_SIDEWALK = 'sidewalk'
ROLE_PILLAR = 'pillar'
ROLE_RAIL = 'rail'
ROLE_PROP = 'prop'

#: (role, label, which kit blend it is usually linked from). The attribute a role reads is
#: "<role>_asset_idx" on the EDGE domain -- see `graph_attrs.ASSET_ROLES`.
ROLES = (
    (ROLE_CURB, "Curb", paths.CURB_KIT_BLEND),
    (ROLE_MEDIAN, "Median", paths.CURB_KIT_BLEND),
    (ROLE_SIDEWALK, "Sidewalk", paths.CURB_KIT_BLEND),
    (ROLE_PILLAR, "Pillar / Support", paths.CURB_KIT_BLEND),
    (ROLE_RAIL, "Railing / Barrier", paths.CURB_KIT_BLEND),
    (ROLE_PROP, "Props / Lights", paths.CURB_KIT_BLEND),
)

ROLE_NAMES = tuple(r for r, _l, _b in ROLES)
ROLE_LABEL = {r: l for r, l, _b in ROLES}
ROLE_BLEND = {r: b for r, _l, b in ROLES}

ROOT_COLLECTION = "RKA_ASSETS"


def _root(create=True):
    coll = bpy.data.collections.get(ROOT_COLLECTION)
    if coll is None and create:
        coll = bpy.data.collections.new(ROOT_COLLECTION)
        # Deliberately NOT linked into any scene: the palette must be reachable by Collection
        # Info without also rendering a pile of loose kit pieces at the world origin.
        coll["rka_asset_root"] = True
    return coll


def registry_name(role):
    return "%s_%s" % (ROOT_COLLECTION, role)


def registry(role, create=True):
    """The palette collection for `role`. Its children are the assets, indexed by `catalog`."""
    name = registry_name(role)
    coll = bpy.data.collections.get(name)
    if coll is None and create:
        coll = bpy.data.collections.new(name)
        coll["rka_asset_role"] = role
        root = _root(create=True)
        if root is not None and name not in root.children:
            root.children.link(coll)
    return coll


def catalog(role):
    """Asset names for `role`, in the SAME order `Collection Info (Separate Children)` emits them.

    MEASURED, NOT ASSUMED. `Separate Children` walks the registry's `children` in STORAGE order,
    which is link order -- Blender does NOT sort collection children, it only displays them
    sorted in the outliner. Returning `sorted(...)` here therefore disagreed with the node tree
    for any palette not linked in alphabetical order, and every per-edge asset index selected the
    wrong mesh (caught by `smoketest_graph_solve`, which evaluates a real Pick Instance tree and
    checks which mesh came through). So this reports storage order, and `_resort` keeps storage
    order alphabetical -- the two are made to agree rather than assumed to."""
    coll = registry(role, create=False)
    return [c.name for c in coll.children] if coll else []


def _resort(reg):
    """Re-link every child in name order, so storage order (what the node tree indexes) matches
    the alphabetical order the outliner shows and an artist reasons about.

    Blender offers no reorder API for collection children, so this unlinks and relinks -- cheap
    (a palette is tens of entries) and the only way to make the index stable under insertion."""
    names = sorted(c.name for c in reg.children)
    if names == [c.name for c in reg.children]:
        return
    colls = [bpy.data.collections[n] for n in names]
    for c in colls:
        reg.children.unlink(c)
    for c in colls:
        reg.children.link(c)


def index_of(role, name):
    cat = catalog(role)
    return cat.index(name) if name in cat else -1


def name_at(role, index):
    cat = catalog(role)
    return cat[index] if 0 <= index < len(cat) else ""


def add_asset(role, collection):
    """Put an existing Collection into a role's palette. Idempotent."""
    reg = registry(role, create=True)
    if collection.name not in reg.children:
        reg.children.link(collection)
        _resort(reg)
    return index_of(role, collection.name)


def link_from_library(blend_path, role, names=None, prefix=None):
    """LINK collections out of `blend_path` into `role`'s palette, keeping that blend as their
    origin mesh. `names` selects explicitly; `prefix` selects by name prefix (the kit's own
    convention, e.g. 'Kit_Curb_'); with neither, every collection in the file is linked.

    Returns the names actually linked. Already-linked collections are skipped rather than
    duplicated -- re-running is safe and is how you pick up newly authored kit pieces."""
    with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):
        available = list(data_from.collections)
        if names is not None:
            want = [n for n in available if n in set(names)]
        elif prefix:
            want = [n for n in available if n.startswith(prefix)]
        else:
            want = available
        # `want` is EVERY name this call should end up registering; `to_load` is the subset not
        # already in the file. Keeping them apart is what lets a second role claim a collection
        # the first role already pulled in -- with one shared kit blend, `sidewalk` and `rail`
        # both match names `curb` loaded first, and folding the two together left their palettes
        # empty.
        to_load = [n for n in want if bpy.data.collections.get(n) is None]
        # PASS A COPY. `bpy.data.libraries.load` fills the list you assign IN PLACE with the
        # loaded datablocks when the context exits -- so handing it the same list turns it from
        # names into Collections behind your back, and every name lookup below then raises
        # `key must be a string ... not Collection`. The operator caught that and reported it as
        # a warning, which is why every palette silently stayed empty.
        data_to.collections = list(to_load)
    reg = registry(role, create=True)
    linked = []
    # `want` holds only what this call had to pull in; anything already in `bpy.data` (linked by
    # an earlier run, or by another role sharing the same kit piece) still needs registering with
    # THIS role, so every matched name goes through the same link step.
    for n in sorted(set(want) | set(names or [])):
        coll = bpy.data.collections.get(n)
        if coll is not None and n not in reg.children:
            reg.children.link(coll)
            linked.append(n)
    _resort(reg)
    return sorted(linked)


def role_enum_items(role):
    """Enum items for a picker dropdown: '-1 = None (parametric)' plus every catalogued asset.

    The identifier is the INDEX as a string, because that is what gets stamped on the edge -- the
    label carries the name so the artist never sees a bare number."""
    items = [("-1", "None (parametric)", "Build this band from its width/height numbers instead "
              "of an asset mesh")]
    for i, n in enumerate(catalog(role)):
        items.append((str(i), n, "Asset %d in the %s palette" % (i, role)))
    return items


# ------------------------------------------------------------------------------------- operators

class RKA_OT_graph_assets_link_kit(bpy.types.Operator):
    """Link the standard kit collections into every role's palette."""
    bl_idname = "rka.graph_assets_link_kit"
    bl_label = "Link Kit Assets"
    bl_options = {'REGISTER', 'UNDO'}

    #: Prefix per role -- the kit's own naming convention is already role-shaped.
    PREFIXES = {
        ROLE_CURB: "Kit_Curb_",
        ROLE_MEDIAN: "Kit_Median_",
        ROLE_SIDEWALK: "Kit_Curb_Sidewalk",
        ROLE_PILLAR: "Kit_Pillar_",
        ROLE_RAIL: "Kit_Curb_Fence",
        ROLE_PROP: "Kit_Traffic",
    }

    def execute(self, context):
        import os
        total = []
        for role in ROLE_NAMES:
            blend = ROLE_BLEND[role]
            if not os.path.exists(blend):
                continue
            try:
                got = link_from_library(blend, role, prefix=self.PREFIXES.get(role))
            except Exception as exc:                       # noqa: BLE001 -- reported, not hidden
                self.report({'WARNING'}, "%s: %s" % (role, exc))
                continue
            total.extend("%s/%s" % (role, n) for n in got)
        self.report({'INFO'}, "Linked %d asset(s): %s"
                    % (len(total), ", ".join(total[:6]) + ("..." if len(total) > 6 else "")))
        return {'FINISHED'}


class RKA_OT_graph_assets_add_selected(bpy.types.Operator):
    """Add the active object's own collection to a role palette -- for assets authored locally in
    this file rather than linked from the kit."""
    bl_idname = "rka.graph_assets_add_selected"
    bl_label = "Add Active Collection To Role"
    bl_options = {'REGISTER', 'UNDO'}

    role: bpy.props.EnumProperty(
        name="Role", items=[(r, ROLE_LABEL[r], "") for r in ROLE_NAMES])

    def execute(self, context):
        obj = context.active_object
        if obj is None or not obj.users_collection:
            self.report({'WARNING'}, "No active object in a collection")
            return {'CANCELLED'}
        idx = add_asset(self.role, obj.users_collection[0])
        self.report({'INFO'}, "%s -> %s index %d"
                    % (obj.users_collection[0].name, self.role, idx))
        return {'FINISHED'}


CLASSES = (RKA_OT_graph_assets_link_kit, RKA_OT_graph_assets_add_selected)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
