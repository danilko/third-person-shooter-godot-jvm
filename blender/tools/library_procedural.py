"""The pieces kits/library models itself (imported by build_library.py --procedural). Ours, CC0.

Every function returns a mesh in the piece frame: Z up, origin at the footprint centre on the floor, the side a
person uses (or, for a platform, the TRACK side) facing -Y. Sizes are Japanese and stated where they are chosen:

* fridge wall: one 0.91 m door bay (the ken half-module), 2.1 m tall -- the reach-in drink wall of every konbini;
* gas canopy: 18.2 x 10.92 m (10 x 6 ken), 4.7 m clear underneath -- a design choice (PLATEAU does not record
  canopies), high enough for a truck;
* platform: 1.3 m above the ground, which with this track (rail top 0.36 m) is 0.94 m above the rail -- the JR
  conventional-line 920 mm class; the tactile strip is 0.8 m in from the edge with the white line at the edge;
* track: 1067 mm gauge (Japanese conventional lines), sleepers every 0.607 m (three per 1.82 m module).
"""
import math

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh
import bpy


class Builder:
    def __init__(self, name, material):
        self.name = name
        self.material = material
        self.bm = bmesh.new()
        self.mats = []

    def _mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def box(self, lo, hi, mat):
        """An axis-aligned box from corner `lo` to corner `hi` (metres)."""
        mi = self._mi(mat)
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        vs = [self.bm.verts.new(p) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                              (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            face = self.bm.faces.new([vs[i] for i in f])
            face.material_index = mi

    def wedge_x(self, x0, x1, y0, y1, z_at_x0, z_at_x1, mat):
        """A ramp: a solid on the ground whose top slopes along X from `z_at_x0` to `z_at_x1`."""
        mi = self._mi(mat)
        p = [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0),
             (x0, y0, z_at_x0), (x1, y0, z_at_x1), (x1, y1, z_at_x1), (x0, y1, z_at_x0)]
        vs = [self.bm.verts.new(q) for q in p]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            face = self.bm.faces.new([vs[i] for i in f])
            face.material_index = mi

    def frustum(self, cx, cy, z0, z1, hx0, hy0, hx1, hy1, mat):
        """A tapered box: half-sizes (hx0, hy0) at z0 to (hx1, hy1) at z1, centred on (cx, cy)."""
        mi = self._mi(mat)
        p = [(cx - hx0, cy - hy0, z0), (cx + hx0, cy - hy0, z0), (cx + hx0, cy + hy0, z0), (cx - hx0, cy + hy0, z0),
             (cx - hx1, cy - hy1, z1), (cx + hx1, cy - hy1, z1), (cx + hx1, cy + hy1, z1), (cx - hx1, cy + hy1, z1)]
        vs = [self.bm.verts.new(q) for q in p]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            face = self.bm.faces.new([vs[i] for i in f])
            face.material_index = mi

    def rounded(self, cx, cy, rx, ry_front, ry_back, z0, z1, mat, segs=24, shrink=0.0):
        """A solid from z0 to z1 whose plan is a half-ellipse at the FRONT (-Y, `ry_front` deep) and a half-ellipse
        (or, with `ry_back` 0, a straight edge) at the back: a toilet bowl, a seat. `shrink` narrows the top ring by
        that fraction (a tapered pedestal)."""
        mi = self._mi(mat)
        ring = []
        for k in range(segs + 1):                                   # front half: angle pi .. 2 pi
            a = math.pi + math.pi * k / segs
            ring.append((cx + rx * math.cos(a), cy + ry_front * math.sin(a)))
        if ry_back > 0:
            for k in range(1, segs):
                a = math.pi * k / segs
                ring.append((cx + rx * math.cos(a), cy + ry_back * math.sin(a)))
        # the ring runs counter-clockwise seen from above (left, round the front, right): top faces up, sides out
        s = 1.0 - shrink
        lo = [self.bm.verts.new((x, y, z0)) for x, y in ring]
        hi = [self.bm.verts.new((cx + (x - cx) * s, cy + (y - cy) * s, z1)) for x, y in ring]
        f = self.bm.faces.new(lo[::-1])
        f.material_index = mi
        f = self.bm.faces.new(hi)
        f.material_index = mi
        n = len(ring)
        for i in range(n):
            j = (i + 1) % n
            f = self.bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
            f.material_index = mi

    def beam(self, p0, p1, w, mat):
        """A square beam `w` wide from point p0 to point p1 (cables, legs, hangers)."""
        import mathutils
        a, b = mathutils.Vector(p0), mathutils.Vector(p1)
        d = b - a
        if d.length < 1e-6:
            return
        t = d.normalized()
        up = mathutils.Vector((0, 0, 1)) if abs(t.z) < 0.9 else mathutils.Vector((1, 0, 0))
        u = t.cross(up).normalized() * (w / 2)
        v = t.cross(u).normalized() * (w / 2)
        mi = self._mi(mat)
        corners = [-u - v, u - v, u + v, -u + v]
        vs = [self.bm.verts.new(a + c) for c in corners] + [self.bm.verts.new(b + c) for c in corners]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            face = self.bm.faces.new([vs[i] for i in f])
            face.material_index = mi

    def mesh(self):
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-5)
        me = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(self.material(m))
        me.update()
        return me


# ── konbini ──────────────────────────────────────────────────────────────────────────────────────────────────

def fridge_door(material):
    b = Builder("Shop_FridgeDoor", material)
    w, d, h = 0.91, 0.8, 2.1
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    # NO back panel (user, 2026-09-28): the bank is the front wall of the walk-in cooler ROOM, and staff restock
    # every door at once from behind; the back is a sill rail only
    b.box((x0, y1 - 0.05, 0), (x1, y1, 0.12), "MI_PaintedMetal")
    b.box((x0, y0, 0), (x0 + 0.04, y1, h), "MI_PaintedMetal")               # sides
    b.box((x1 - 0.04, y0, 0), (x1, y1, h), "MI_PaintedMetal")
    b.box((x0, y0, 0), (x1, y1, 0.12), "MI_PaintedMetalDark")               # plinth
    b.box((x0, y0, h - 0.25), (x1, y1, h), "MI_PaintedMetal")               # header
    b.box((x0 + 0.08, y0 + 0.02, h - 0.27), (x1 - 0.08, y0 + 0.1, h - 0.25), "MI_Light")
    for k in range(5):                                                       # shelves with goods
        z = 0.12 + 0.05 + k * 0.33
        b.box((x0 + 0.04, y0 + 0.08, z), (x1 - 0.04, y1 - 0.05, z + 0.02), "MI_Steel")
        b.box((x0 + 0.06, y0 + 0.12, z + 0.02), (x1 - 0.06, y1 - 0.12, z + 0.26), "MI_Goods")
    b.box((x0 + 0.04, y0, 0.12), (x1 - 0.04, y0 + 0.02, h - 0.25), "MI_GlassClear")   # the door pane
    b.box((x0 + 0.04, y0 - 0.01, 0.12), (x0 + 0.08, y0 + 0.03, h - 0.25), "MI_PaintedMetal")
    b.box((x1 - 0.08, y0 - 0.01, 0.12), (x1 - 0.04, y0 + 0.03, h - 0.25), "MI_PaintedMetal")
    b.box((x1 - 0.14, y0 - 0.05, 0.8), (x1 - 0.11, y0 - 0.01, 1.4), "MI_Steel")      # handle
    return "Shop_FridgeDoor", "interior", b.mesh()


def coffee_machine(material):
    """The self-serve coffee machine on a konbini counter: a 0.45 x 0.5 x 0.7 m box, a dark front with a lit
    panel and a cup niche. Modelled here because the base mesh did not read as one."""
    b = Builder("Shop_CoffeeMachine", material)
    w, d, h = 0.45, 0.5, 0.7
    b.box((-w / 2, -d / 2, 0), (w / 2, d / 2, h), "MI_PlasticWhite")
    b.box((-w / 2 + 0.03, -d / 2 - 0.01, 0.3), (w / 2 - 0.03, -d / 2, h - 0.04), "MI_PlasticDark")
    b.box((-0.12, -d / 2 - 0.02, 0.5), (0.12, -d / 2 - 0.01, 0.62), "MI_Light")
    b.box((-0.1, -d / 2, 0.03), (0.1, -d / 2 + 0.2, 0.05), "MI_Steel")       # the drip tray in the niche
    return "Shop_CoffeeMachine", "interior", b.mesh()


# ── konbini sales floor, second round (user, 2026-09-28): PLACEHOLDERS for an artist ────────────────────────────

def open_case(material):
    """An OPEN multideck chiller (オープンケース) for bento, onigiri and sandwiches: one ken long, 0.85 m deep, 2.0 m tall,
    NO door and no glass -- the goods are taken straight off the shelves. The chilled air curtain is the top canopy."""
    b = Builder("Shop_OpenCase", material)
    x0, x1, y0, y1, h = -0.91, 0.91, -0.425, 0.425, 2.0
    b.box((x0, y1 - 0.08, 0), (x1, y1, h), "MI_PaintedMetal")               # back
    b.box((x0, y0, 0), (x0 + 0.04, y1, h), "MI_PaintedMetal")               # end panels
    b.box((x1 - 0.04, y0, 0), (x1, y1, h), "MI_PaintedMetal")
    b.box((x0, y0, 0), (x1, y1, 0.45), "MI_PaintedMetalDark")               # the low deck's base
    b.box((x0, y0 + 0.2, h - 0.2), (x1, y1, h), "MI_PaintedMetal")          # canopy
    b.box((x0 + 0.05, y0 + 0.22, h - 0.22), (x1 - 0.05, y0 + 0.3, h - 0.2), "MI_Light")
    for k, (z, dy) in enumerate(((0.45, 0.0), (0.85, 0.12), (1.2, 0.22), (1.52, 0.3))):
        b.box((x0 + 0.04, y0 + dy, z), (x1 - 0.04, y1 - 0.08, z + 0.03), "MI_Steel")
        b.box((x0 + 0.06, y0 + dy + 0.04, z + 0.03), (x1 - 0.06, y1 - 0.12, z + 0.2), "MI_Goods")
    b.box((x0, y0 - 0.01, 0.42), (x1, y0 + 0.02, 0.5), "MI_Sign")            # price rail
    return "Shop_OpenCase", "interior", b.mesh()


def cigarette_case(material):
    """The cigarette wall behind the counter (たばこ棚): one ken, 0.45 m deep, 2.1 m tall; a closed cabinet to 0.9 m and a
    glass-fronted display above it, numbered rows of packs."""
    b = Builder("Shop_CigaretteCase", material)
    x0, x1, y0, y1, h = -0.91, 0.91, -0.225, 0.225, 2.1
    b.box((x0, y0, 0), (x1, y1, 0.9), "MI_PaintedMetalDark")
    b.box((x0, y1 - 0.05, 0.9), (x1, y1, h), "MI_PaintedMetal")
    b.box((x0, y0, 0.9), (x0 + 0.04, y1, h), "MI_PaintedMetal")
    b.box((x1 - 0.04, y0, 0.9), (x1, y1, h), "MI_PaintedMetal")
    b.box((x0, y0, h - 0.1), (x1, y1, h), "MI_PaintedMetal")
    for k in range(5):
        z = 0.95 + k * 0.2
        b.box((x0 + 0.04, y0 + 0.05, z), (x1 - 0.04, y1 - 0.05, z + 0.02), "MI_Steel")
        b.box((x0 + 0.06, y0 + 0.08, z + 0.02), (x1 - 0.06, y1 - 0.1, z + 0.13), "MI_Goods")
    b.box((x0 + 0.04, y0, 0.92), (x1 - 0.04, y0 + 0.02, h - 0.1), "MI_GlassClear")
    return "Shop_CigaretteCase", "interior", b.mesh()


def bin_station(material):
    """A sorted bin station (分別ゴミ箱): 1.2 x 0.55 x 1.0 m, three bins in one cabinet -- burnable (燃えるゴミ, red),
    cans and bottles (缶・びん, blue), PET bottles (ペットボトル, yellow) -- each with its shaped opening."""
    b = Builder("Shop_BinStation", material)
    b.box((-0.6, -0.275, 0), (0.6, 0.275, 1.0), "MI_PlasticWhite")
    for k, mat in enumerate(("MI_FabricRed", "MI_Sign", "MI_PaintYellow")):
        x = -0.4 + 0.4 * k
        b.box((x - 0.18, -0.285, 0.72), (x + 0.18, -0.275, 0.95), mat)        # the coloured label band
        b.box((x - 0.08, -0.29, 0.78), (x + 0.08, -0.28, 0.86), "MI_PlasticDark")   # the opening
        b.box((x - 0.17, -0.285, 0.05), (x + 0.17, -0.278, 0.68), "MI_PlasticWhite")  # the bin's door
    return "Shop_BinStation", "interior", b.mesh()


def eat_in_counter(material):
    """One SEAT of an eat-in counter (イートイン): 0.91 m of worktop 0.45 m deep at 0.95 m, fixed to the wall at +Y on
    two brackets -- no legs. Repeat it along a wall, one stool (Shop_Stool) per unit."""
    b = Builder("Shop_EatInCounter", material)
    b.box((-0.455, -0.225, 0.92), (0.455, 0.225, 0.95), "MI_Wood")
    for x in (-0.4, 0.4):
        b.box((x - 0.015, 0.0, 0.6), (x + 0.015, 0.225, 0.92), "MI_PaintedMetal")
    b.box((-0.455, 0.2, 0.9), (0.455, 0.225, 0.92), "MI_PaintedMetal")      # the wall rail
    return "Shop_EatInCounter", "interior", b.mesh()


def stool(material):
    """A counter stool: a 0.38 m round-ish seat at 0.72 m on one post and a foot ring."""
    b = Builder("Shop_Stool", material)
    b.frustum(0, 0, 0.0, 0.03, 0.2, 0.2, 0.2, 0.2, "MI_PaintedMetalDark")     # base
    b.box((-0.025, -0.025, 0.03), (0.025, 0.025, 0.69), "MI_Steel")          # post
    b.box((-0.17, -0.17, 0.3), (0.17, 0.17, 0.32), "MI_Steel")               # foot ring
    b.frustum(0, 0, 0.69, 0.75, 0.19, 0.19, 0.18, 0.18, "MI_Fabric")        # seat
    return "Shop_Stool", "interior", b.mesh()


def freezer_case(material):
    """An upright reach-in FREEZER (リーチインフリーザー) for ice cream and frozen food: one ken, two glass doors,
    0.85 m deep, 2.1 m tall, a cold-white light. It replaces the open chest freezer."""
    b = Builder("Shop_FreezerCase", material)
    x0, x1, y0, y1, h = -0.91, 0.91, -0.425, 0.425, 2.1
    b.box((x0, y1 - 0.05, 0), (x1, y1, h), "MI_PlasticWhite")
    b.box((x0, y0, 0), (x0 + 0.05, y1, h), "MI_PlasticWhite")
    b.box((x1 - 0.05, y0, 0), (x1, y1, h), "MI_PlasticWhite")
    b.box((x0, y0, 0), (x1, y1, 0.15), "MI_PaintedMetalDark")
    b.box((x0, y0, h - 0.25), (x1, y1, h), "MI_PlasticWhite")
    b.box((x0 + 0.08, y0 - 0.01, h - 0.22), (x1 - 0.08, y0, h - 0.08), "MI_Sign")
    for k in range(5):
        z = 0.2 + k * 0.32
        b.box((x0 + 0.05, y0 + 0.08, z), (x1 - 0.05, y1 - 0.05, z + 0.02), "MI_Steel")
        b.box((x0 + 0.08, y0 + 0.12, z + 0.02), (x1 - 0.08, y1 - 0.12, z + 0.22), "MI_Goods")
    for x in (x0 + 0.05, 0.0):
        b.box((x, y0, 0.15), (x + 0.86, y0 + 0.02, h - 0.25), "MI_GlassClear")
        b.box((x + 0.02, y0 - 0.05, 0.9), (x + 0.05, y0 - 0.01, 1.5), "MI_Steel")
    b.box((-0.02, y0 - 0.01, 0.15), (0.02, y0 + 0.03, h - 0.25), "MI_PlasticWhite")
    return "Shop_FreezerCase", "interior", b.mesh()


def coffee_station(material):
    """The self-serve coffee corner (セルフコーヒー): one ken of 0.9 m counter, 0.6 m deep, with TWO coffee machines,
    a cup and lid rack between them and a waste slot."""
    b = Builder("Shop_CoffeeStation", material)
    b.box((-0.91, -0.3, 0), (0.91, 0.3, 0.88), "MI_PlasticWhite")
    b.box((-0.91, -0.3, 0.88), (0.91, 0.3, 0.9), "MI_Wood")
    for cx in (-0.55, 0.55):                                                 # the two machines, as Shop_CoffeeMachine
        b.box((cx - 0.225, -0.25, 0.9), (cx + 0.225, 0.25, 1.6), "MI_PlasticWhite")
        b.box((cx - 0.195, -0.26, 1.2), (cx + 0.195, -0.25, 1.56), "MI_PlasticDark")
        b.box((cx - 0.12, -0.27, 1.4), (cx + 0.12, -0.26, 1.52), "MI_Light")
    b.box((-0.2, 0.0, 0.9), (0.2, 0.28, 1.25), "MI_PaintedMetal")           # cups and lids
    b.box((-0.15, -0.301, 0.6), (0.15, -0.3, 0.7), "MI_PlasticDark")         # waste slot
    return "Shop_CoffeeStation", "interior", b.mesh()


# ── konbini back of house and the rest of the store (PLAN.md C0, 2026-09-25): PLACEHOLDERS for an artist ─────────
# Sizes are the Japanese konbini's; every one of these is a labelled block to be hand-modelled (PIECES.md lists them).

PARTITION_H = 2.7      # the ceiling of a one-storey store (the storey is 2.73 m + a band; the fascia hides the rest)
PARTITION_T = 0.12


def partition(material):
    """One ken (1.82 m) of interior wall, 0.12 m thick, PARTITION_H tall, centred on the origin along X: the
    back-of-house and the washroom are rooms made of these (placed as props, `collide` box)."""
    b = Builder("Wall_Partition", material)
    b.box((-0.91, -PARTITION_T / 2, 0), (0.91, PARTITION_T / 2, PARTITION_H), "MI_Plaster")
    b.box((-0.91, -PARTITION_T / 2 - 0.01, 0), (0.91, PARTITION_T / 2 + 0.01, 0.08), "MI_PaintedMetalDark")
    return "Wall_Partition", "interior", b.mesh()


def partition_door(material):
    """One ken of interior wall with a 0.85 x 2.0 m DOORWAY in the middle and no leaf (a leaf would stand in the
    capsule's way; the artist may model an open one). Its collider is the two jambs and the header
    (`PARTITION_DOOR_BOXES`, used by the building table's `collide`)."""
    b = Builder("Wall_PartitionDoor", material)
    t, w, h = PARTITION_T / 2, 0.425, 2.0
    b.box((-0.91, -t, 0), (-w, t, PARTITION_H), "MI_Plaster")
    b.box((w, -t, 0), (0.91, t, PARTITION_H), "MI_Plaster")
    b.box((-w, -t, h), (w, t, PARTITION_H), "MI_Plaster")
    for x in (-w, w):                                                      # the frame
        b.box((x - 0.03, -t - 0.01, 0), (x + 0.03, t + 0.01, h), "MI_PaintedMetal")
    b.box((-w, -t - 0.01, h), (w, t + 0.01, h + 0.05), "MI_PaintedMetal")
    return "Wall_PartitionDoor", "interior", b.mesh()


def walkin_cooler(material):
    """One ken (1.82 m wide, 1.82 m deep, 2.4 m tall) of WALK-IN COOLER (ウォークイン冷蔵庫): the insulated room behind
    the drink wall that staff restock from behind. Its FRONT (-Y) is where the reach-in doors (`Shop_FridgeDoor`)
    stand; the back has a staff door strip."""
    b = Builder("Shop_WalkInCooler", material)
    b.box((-0.91, -0.91, 0), (0.91, 0.91, 2.4), "MI_PlasticWhite")
    b.box((-0.91, 0.91, 0.1), (0.91, 0.93, 2.3), "MI_Steel")               # the staff side's panel seams
    b.box((-0.4, 0.93, 0.0), (0.4, 0.95, 2.0), "MI_PaintedMetal")          # a cooler door on the back
    return "Shop_WalkInCooler", "interior", b.mesh()


def locker(material):
    """A staff locker bank: 0.9 x 0.5 x 1.8 m, three doors."""
    b = Builder("Office_Locker", material)
    b.box((-0.45, -0.25, 0), (0.45, 0.25, 1.8), "MI_PaintedMetal")
    for k in range(3):
        x = -0.45 + 0.3 * k
        b.box((x + 0.01, -0.26, 0.05), (x + 0.29, -0.25, 1.75), "MI_PaintedMetalDark")
    return "Office_Locker", "interior", b.mesh()


def desk(material):
    """An office desk, 1.2 x 0.7 x 0.72 m, with a monitor."""
    b = Builder("Office_Desk", material)
    b.box((-0.6, -0.35, 0.68), (0.6, 0.35, 0.72), "MI_Wood")
    for x in (-0.57, 0.57):
        b.box((x - 0.03, -0.32, 0), (x + 0.03, 0.32, 0.68), "MI_PaintedMetal")
    b.box((-0.25, 0.1, 0.72), (0.25, 0.13, 1.05), "MI_PlasticDark")
    return "Office_Desk", "interior", b.mesh()


def safe(material):
    """A floor safe, 0.6 x 0.6 x 1.0 m."""
    b = Builder("Office_Safe", material)
    b.box((-0.3, -0.3, 0), (0.3, 0.3, 1.0), "MI_PaintedMetalDark")
    b.box((-0.05, -0.31, 0.55), (0.05, -0.3, 0.65), "MI_Steel")
    return "Office_Safe", "interior", b.mesh()


def atm(material):
    """A konbini ATM, 0.7 x 0.8 x 1.6 m, screen and slot on the front."""
    b = Builder("Shop_ATM", material)
    b.box((-0.35, -0.4, 0), (0.35, 0.4, 1.6), "MI_PlasticWhite")
    b.box((-0.25, -0.41, 1.05), (0.25, -0.4, 1.4), "MI_PlasticDark")
    b.box((-0.3, -0.5, 0.95), (0.3, -0.4, 1.0), "MI_PlasticDark")          # the ledge
    b.box((-0.34, -0.41, 1.45), (0.34, -0.4, 1.58), "MI_Sign")
    return "Shop_ATM", "interior", b.mesh()


def hot_case(material):
    """The hot-snack case on the counter's end (fried chicken, nikuman): 0.9 x 0.6 x 1.2 m, glass box on a base."""
    b = Builder("Shop_HotCase", material)
    b.box((-0.45, -0.3, 0), (0.45, 0.3, 0.8), "MI_PaintedMetal")
    b.box((-0.45, -0.3, 0.8), (0.45, 0.3, 1.2), "MI_GlassClear")
    b.box((-0.4, -0.25, 0.85), (0.4, 0.25, 0.95), "MI_Goods")
    b.box((-0.44, -0.29, 1.18), (0.44, 0.29, 1.2), "MI_Light")
    return "Shop_HotCase", "interior", b.mesh()


def magazine_rack(material):
    """The magazine rack along the front glass: one ken, 0.4 m deep, 1.2 m tall, sloped shelves of goods."""
    b = Builder("Shop_MagazineRack", material)
    b.box((-0.91, 0.1, 0), (0.91, 0.2, 1.2), "MI_PaintedMetal")
    for k in range(3):
        z = 0.3 + 0.3 * k
        b.box((-0.9, -0.2 + 0.05 * k, z), (0.9, 0.1, z + 0.04), "MI_Steel")
        b.box((-0.88, -0.15 + 0.05 * k, z + 0.04), (0.88, 0.05, z + 0.26), "MI_Goods")
    return "Shop_MagazineRack", "interior", b.mesh()


def copier(material):
    """The multi-copier (マルチコピー機), 1.2 x 0.7 x 1.1 m, a touch screen on top."""
    b = Builder("Shop_Copier", material)
    b.box((-0.6, -0.35, 0), (0.6, 0.35, 1.0), "MI_PlasticWhite")
    b.box((-0.2, -0.35, 1.0), (0.2, -0.05, 1.12), "MI_PlasticDark")
    return "Shop_Copier", "interior", b.mesh()


def fascia(material, name, mat, h, d):
    """A fascia band one ken long, `h` tall, `d` deep, its face at -Y and its bottom at the origin."""
    b = Builder(name, material)
    b.box((-0.91, -d, 0), (0.91, 0, h), mat)
    return name, "facade", b.mesh()


def washlet_toilet(material):
    """A Japanese toilet with a WASHLET (温水洗浄便座, user 2026-09-28): a smooth ROUNDED one-piece bowl, no exposed
    plumbing, a low tank / washlet housing at the back, a seat and a closed lid, and the control panel on the RIGHT side
    of the seat (the armrest-style remote). 0.40 m wide (0.52 with the panel), 0.75 m deep, seat at 0.42 m. The user
    sits facing -Y; the back (+Y) goes against the wall."""
    b = Builder("WC_Toilet", material)
    yb, yf = 0.375, -0.375
    # the one-piece bowl: a rounded pedestal tapering in to the floor, the bowl above it
    b.rounded(0.0, 0.0, 0.17, 0.33, 0.0, 0.0, 0.18, "MI_PlasticWhite", shrink=-0.12)
    b.rounded(0.0, 0.0, 0.19, 0.37, 0.0, 0.18, 0.38, "MI_PlasticWhite")
    # the back: tank + washlet housing, one rounded-top block from the bowl to the wall
    b.box((-0.2, 0.0, 0.0), (0.2, yb, 0.38), "MI_PlasticWhite")
    b.box((-0.2, 0.17, 0.38), (0.2, yb, 0.72), "MI_PlasticWhite")
    b.rounded(0.0, 0.27, 0.2, 0.1, 0.1, 0.72, 0.8, "MI_PlasticWhite")
    # seat and closed lid (a slightly smaller rounded slab each)
    b.rounded(0.0, -0.02, 0.19, 0.34, 0.0, 0.38, 0.41, "MI_PlasticWhite")
    b.rounded(0.0, -0.03, 0.18, 0.33, 0.0, 0.41, 0.44, "MI_PlasticWhite")
    b.box((-0.18, 0.02, 0.38), (0.18, 0.17, 0.46), "MI_PlasticWhite")       # the washlet unit under the lid hinge
    # the control panel on the right side of the seat, its buttons on top
    b.box((0.2, -0.12, 0.40), (0.3, 0.12, 0.47), "MI_PlasticWhite")
    b.box((0.21, -0.1, 0.47), (0.29, 0.08, 0.475), "MI_PlasticDark")
    for k, mat in enumerate(("MI_Sign", "MI_FabricRed", "MI_Light")):
        b.box((0.23, -0.08 + k * 0.05, 0.475), (0.27, -0.05 + k * 0.05, 0.48), mat)
    # the flush lever on the tank's side
    b.box((-0.22, 0.28, 0.66), (-0.2, 0.34, 0.68), "MI_Steel")
    return "WC_Toilet", "fixtures", b.mesh()


def square_basin(material):
    """A plain SQUARE wall-hung wash basin (user 2026-09-28: square and simple): a flat rim at 0.84 m, the underside
    sloping back up into the wall, a recessed bowl and a single-lever tap at the back. 0.65 x 0.566 m, wall at +Y."""
    b = Builder("WC_Basin", material)
    x0, x1, y0, y1 = -0.325, 0.325, -0.283, 0.283
    # the body: a wedge -- deep at the wall, thin at the front (the sloping underside)
    mi = b._mi("MI_PlasticWhite")
    p = [(x0, y0, 0.80), (x1, y0, 0.80), (x1, y1, 0.72), (x0, y1, 0.72),
         (x0, y0, 0.84), (x1, y0, 0.84), (x1, y1, 0.84), (x0, y1, 0.84)]
    vs = [b.bm.verts.new(q) for q in p]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        face = b.bm.faces.new([vs[i] for i in f])
        face.material_index = mi
    b.box((x0 + 0.05, y0 + 0.05, 0.842), (x1 - 0.05, y1 - 0.12, 0.845), "MI_TileWhite")   # the bowl's opening
    b.box((-0.02, y1 - 0.1, 0.84), (0.02, y1 - 0.06, 1.0), "MI_Steel")                      # the tap
    b.box((-0.02, y1 - 0.2, 0.97), (0.02, y1 - 0.06, 1.0), "MI_Steel")
    b.box((-0.01, y1 - 0.08, 1.0), (0.01, y1 - 0.02, 1.08), "MI_Steel")                     # its lever
    return "WC_Basin", "fixtures", b.mesh()


def wc_partition(material):
    b = Builder("WC_Partition", material)
    b.box((-0.015, -0.75, 0.12), (0.015, 0.75, 2.02), "MI_PlasticWhite")
    b.box((-0.03, -0.75, 0), (0.03, -0.69, 0.12), "MI_Steel")                 # the two feet
    b.box((-0.03, 0.69, 0), (0.03, 0.75, 0.12), "MI_Steel")
    return "WC_Partition", "fixtures", b.mesh()


# ── rooms: restrooms, back of house and a restaurant kitchen (user, 2026-09-27): PLACEHOLDERS for an artist ───────
# Sizes are Japanese: an accessible toilet (多機能トイレ) wants a 1.0 m clear doorway with a SLIDING door and a room
# of ~2 x 2 m; a commercial kitchen is stainless at 0.85 m worktop height.

def partition_half(material):
    """HALF a ken (0.91 m) of interior wall, so a room can be a ken and a half wide."""
    b = Builder("Wall_PartitionHalf", material)
    b.box((-0.455, -PARTITION_T / 2, 0), (0.455, PARTITION_T / 2, PARTITION_H), "MI_Plaster")
    b.box((-0.455, -PARTITION_T / 2 - 0.01, 0), (0.455, PARTITION_T / 2 + 0.01, 0.08), "MI_PaintedMetalDark")
    return "Wall_PartitionHalf", "interior", b.mesh()


def partition_door_wide(material):
    """One ken of interior wall with a 1.0 x 2.0 m DOORWAY in the middle: the accessible toilet's (a wheelchair
    needs 0.85 m clear, 1.0 m with the leaf's own edge). Its SLIDING leaf is built by the scene builder
    (`door.style = "slide"`) and runs along the wall beside it, so the wall must continue that side."""
    b = Builder("Wall_PartitionDoorWide", material)
    t, w, h = PARTITION_T / 2, 0.5, 2.0
    b.box((-0.91, -t, 0), (-w, t, PARTITION_H), "MI_Plaster")
    b.box((w, -t, 0), (0.91, t, PARTITION_H), "MI_Plaster")
    b.box((-w, -t, h), (w, t, PARTITION_H), "MI_Plaster")
    for x in (-w, w):
        b.box((x - 0.03, -t - 0.01, 0), (x + 0.03, t + 0.01, h), "MI_PaintedMetal")
    b.box((-w, -t - 0.01, h), (w, t + 0.01, h + 0.05), "MI_PaintedMetal")
    return "Wall_PartitionDoorWide", "interior", b.mesh()


def pass_window(material):
    """One ken of the kitchen's serving wall (パントリー / 料理受け渡し口): a lower wall, a stainless pass shelf at
    0.95 m reaching out both sides, an open slot to 1.45 m for the plates, then a glass panel to 2.1 m and wall above."""
    b = Builder("Wall_PassWindow", material)
    t = PARTITION_T / 2
    b.box((-0.91, -t, 0), (0.91, t, 0.95), "MI_Plaster")
    b.box((-0.91, -0.3, 0.95), (0.91, 0.3, 1.0), "MI_Steel")
    for x in (-0.91, 0.87):
        b.box((x, -t, 1.0), (x + 0.04, t, 2.1), "MI_PaintedMetal")
    b.box((-0.87, -t, 1.45), (0.87, t, 1.49), "MI_PaintedMetal")
    b.box((-0.87, -0.01, 1.49), (0.87, 0.01, 2.1), "MI_GlassClear")
    b.box((-0.91, -t, 2.1), (0.91, t, PARTITION_H), "MI_Plaster")
    return "Wall_PassWindow", "interior", b.mesh()


def grab_rail(material):
    """An L-shaped grab rail beside an accessible toilet, on the wall at +Y: 0.7 m along, up from 0.7 to 1.5 m."""
    b = Builder("WC_GrabRail", material)
    b.box((-0.35, -0.08, 0.68), (0.35, -0.04, 0.72), "MI_Steel")
    b.box((0.31, -0.08, 0.7), (0.35, -0.04, 1.5), "MI_Steel")
    for x in (-0.35, 0.31):
        b.box((x, -0.04, 0.68), (x + 0.04, 0.0, 0.72), "MI_Steel")
    return "WC_GrabRail", "fixtures", b.mesh()


def baby_table(material):
    """A fold-down baby changing table (ベビーシート), folded against the wall at +Y: 0.85 x 0.12 x 0.55 m."""
    b = Builder("WC_BabyTable", material)
    b.box((-0.425, -0.12, 0.8), (0.425, 0.0, 1.35), "MI_PlasticWhite")
    b.box((-0.15, -0.13, 1.15), (0.15, -0.12, 1.25), "MI_Sign")
    return "WC_BabyTable", "fixtures", b.mesh()


def kitchen_sink(material):
    """A stainless two-bowl sink (シンク), 1.8 x 0.75 x 0.85 m, a backsplash at +Y."""
    b = Builder("Kitchen_Sink", material)
    b.box((-0.9, -0.375, 0), (0.9, 0.375, 0.82), "MI_Steel")
    b.box((-0.9, -0.375, 0.82), (0.9, 0.375, 0.85), "MI_Steel")
    for x in (-0.45, 0.35):
        b.box((x - 0.3, -0.25, 0.84), (x + 0.3, 0.2, 0.851), "MI_PaintedMetalDark")
    b.box((-0.9, 0.345, 0.85), (0.9, 0.375, 1.1), "MI_Steel")
    b.box((-0.05, 0.25, 0.85), (0.05, 0.33, 1.15), "MI_Steel")               # the tap
    return "Kitchen_Sink", "interior", b.mesh()


def prep_table(material):
    """A stainless worktable (作業台), 1.8 x 0.75 x 0.85 m, an undershelf."""
    b = Builder("Kitchen_PrepTable", material)
    b.box((-0.9, -0.375, 0.81), (0.9, 0.375, 0.85), "MI_Steel")
    b.box((-0.87, -0.345, 0.15), (0.87, 0.345, 0.18), "MI_Steel")
    for x in (-0.87, 0.84):
        for y in (-0.345, 0.315):
            b.box((x, y, 0), (x + 0.03, y + 0.03, 0.81), "MI_Steel")
    b.box((-0.7, -0.25, 0.18), (0.6, 0.25, 0.45), "MI_Goods")
    return "Kitchen_PrepTable", "interior", b.mesh()


def fryer(material):
    """A twin-basket fryer (フライヤー), 0.6 x 0.75 x 0.9 m."""
    b = Builder("Kitchen_Fryer", material)
    b.box((-0.3, -0.375, 0), (0.3, 0.375, 0.88), "MI_Steel")
    b.box((-0.26, -0.3, 0.88), (0.26, 0.25, 0.9), "MI_PaintedMetalDark")
    b.box((-0.3, 0.3, 0.88), (0.3, 0.375, 1.15), "MI_Steel")
    b.box((-0.25, -0.38, 0.6), (0.25, -0.375, 0.78), "MI_PlasticDark")
    return "Kitchen_Fryer", "interior", b.mesh()


def kitchen_fridge(material):
    """A reach-in stainless refrigerator (業務用冷蔵庫), 1.2 x 0.8 x 1.9 m, two doors facing -Y."""
    b = Builder("Kitchen_Fridge", material)
    b.box((-0.6, -0.4, 0), (0.6, 0.4, 1.9), "MI_Steel")
    for x in (-0.59, 0.01):
        b.box((x, -0.41, 0.12), (x + 0.58, -0.4, 1.85), "MI_Steel")
        b.box((x + 0.5 if x > 0 else x + 0.05, -0.45, 0.9), (x + 0.53 if x > 0 else x + 0.08, -0.41, 1.5),
              "MI_PaintedMetalDark")
    b.box((-0.2, -0.411, 1.7), (0.2, -0.41, 1.8), "MI_Light")
    return "Kitchen_Fridge", "interior", b.mesh()


# ── gas station ──────────────────────────────────────────────────────────────────────────────────────────────

def gas_canopy(material):
    b = Builder("Gas_Canopy", material)
    W, D, clear, slab, band = 18.2, 10.92, 4.7, 0.3, 0.9
    b.box((-W / 2, -D / 2, clear), (W / 2, D / 2, clear + slab), "MI_PaintedMetal")
    t = 0.12
    top = clear + band
    for (lo, hi) in (((-W / 2, -D / 2 - t, clear - 0.05), (W / 2, -D / 2, top)),
                     ((-W / 2, D / 2, clear - 0.05), (W / 2, D / 2 + t, top)),
                     ((-W / 2 - t, -D / 2 - t, clear - 0.05), (-W / 2, D / 2 + t, top)),
                     ((W / 2, -D / 2 - t, clear - 0.05), (W / 2 + t, D / 2 + t, top))):
        b.box(lo, hi, "MI_FasciaGas")
    for i in range(6):                                                       # light panels in the soffit
        for j in range(3):
            cx = -W / 2 + W * (i + 0.5) / 6
            cy = -D / 2 + D * (j + 0.5) / 3
            b.box((cx - 0.6, cy - 0.3, clear - 0.03), (cx + 0.6, cy + 0.3, clear), "MI_Light")
    return "Gas_Canopy", "gas", b.mesh()


def gas_column(material):
    b = Builder("Gas_Column", material)
    b.box((-0.3, -0.3, 0), (0.3, 0.3, 0.15), "MI_ConcreteSmooth")
    b.box((-0.22, -0.22, 0.15), (0.22, 0.22, 4.7), "MI_PaintedMetal")
    return "Gas_Column", "gas", b.mesh()


def gas_island(material):
    b = Builder("Gas_Island", material)
    L, w, h = 5.46, 1.2, 0.18
    b.box((-w / 2, -L / 2, 0), (w / 2, L / 2, h), "MI_ConcreteSmooth")
    b.box((-w / 2 - 0.02, -L / 2 - 0.02, 0), (w / 2 + 0.02, -L / 2 + 0.06, h + 0.01), "MI_PaintYellow")
    b.box((-w / 2 - 0.02, L / 2 - 0.06, 0), (w / 2 + 0.02, L / 2 + 0.02, h + 0.01), "MI_PaintYellow")
    for s in (-1, 1):
        y = s * (L / 2 - 0.3)
        b.box((-0.08, y - 0.08, h), (0.08, y + 0.08, h + 0.9), "MI_PaintYellow")
    return "Gas_Island", "gas", b.mesh()


# ── paving ───────────────────────────────────────────────────────────────────────────────────────────────────

def apron_tile(material):
    """One ken of forecourt paving, its top flush with the ground (0.02 m thick, below it)."""
    b = Builder("Apron_Tile", material)
    b.box((-0.91, -0.91, -0.02), (0.91, 0.91, 0.0), "MI_AsphaltLot")
    return "Apron_Tile", "paving", b.mesh()


def parking_line(material):
    """A parking bay line: 0.1 m wide, 5.0 m long (the Japanese standard bay is 2.5 x 5.0 m), along -Y."""
    b = Builder("Parking_Line", material)
    b.box((-0.05, -2.5, 0.0), (0.05, 2.5, 0.005), "MI_PaintWhite")
    return "Parking_Line", "paving", b.mesh()


def parking_stop(material):
    """A concrete wheel stop (車止め), 1.8 m long, 0.12 m tall."""
    b = Builder("Parking_Stop", material)
    b.box((-0.9, -0.08, 0.0), (0.9, 0.08, 0.12), "MI_ConcreteSmooth")
    return "Parking_Stop", "paving", b.mesh()


# ── container terminal (PLAN.md 3.8 step 5) ─────────────────────────────────────────────────────────────────
# The containers themselves are Quaternius' (blender/tools/build_zombie_yard.py). A ship-to-shore crane
# on a 30.48 m (100 ft) rail gauge, portal clear 18 m, boom hinge at 45 m; modelled with its boom RAISED to 88 deg (the
# stowed position at an idle berth), so nothing overhangs the quay. The quay face is the piece's -Y (the sea).

def harbour_crane(material):
    b = Builder("Harbour_Crane", material)
    gauge, span, clear, hinge = 30.48, 17.0, 18.0, 45.0
    ys, yl = -gauge / 2, gauge / 2                    # seaside and landside rails
    for x in (-span / 2, span / 2):
        for y in (ys, yl):
            b.box((x - 1.0, y - 1.5, 0), (x + 1.0, y + 1.5, 1.2), "MI_PaintedMetalDark")     # bogie
            b.box((x - 0.8, y - 0.8, 1.2), (x + 0.8, y + 0.8, hinge), "MI_CraneRed")        # leg
    for y in (ys, yl):                                                                     # sill and portal beams
        b.box((-span / 2 - 0.8, y - 0.8, clear), (span / 2 + 0.8, y + 0.8, clear + 2.0), "MI_CraneRed")
    for x in (-span / 2, span / 2):
        b.box((x - 0.8, ys - 0.8, clear), (x + 0.8, yl + 0.8, clear + 2.0), "MI_CraneRed")
        b.box((x - 0.8, ys - 0.8, hinge - 2.0), (x + 0.8, yl + 12.0, hinge), "MI_CraneRed")   # girder + backreach
    b.box((-4.0, yl - 2.0, hinge), (4.0, yl + 8.0, hinge + 6.0), "MI_PaintWhite")            # machinery house
    for x in (-span / 2, span / 2):                                                         # A-frame
        b.beam((x, ys, hinge), (x * 0.6, yl - 4.0, hinge + 25.0), 1.2, "MI_CraneRed")
        b.beam((x, yl, hinge), (x * 0.6, yl - 4.0, hinge + 25.0), 1.2, "MI_CraneRed")
    b.box((-span * 0.3 - 0.8, yl - 4.8, hinge + 24.0), (span * 0.3 + 0.8, yl - 3.2, hinge + 26.0), "MI_CraneRed")
    # the boom, raised to 88 degrees over the seaside rail: 50 m long, two box girders
    import math as _m
    L, a = 50.0, _m.radians(88.0)
    for x in (-3.0, 3.0):
        b.beam((x, ys, hinge), (x, ys - L * _m.cos(a), hinge + L * _m.sin(a)), 1.4, "MI_PaintWhite")
    for x in (-span / 2 + 0.8, span / 2 - 0.8):                                             # stays to the apex
        b.beam((x * 0.6, yl - 4.0, hinge + 25.0), (x * 0.35, ys - L * _m.cos(a), hinge + L * _m.sin(a)), 0.3,
               "MI_Steel")
    return "Harbour_Crane", "harbour", b.mesh()


def harbour_bollard(material):
    """A mooring bollard (係船柱): cast iron, 0.6 m tall, on the quay edge."""
    b = Builder("Harbour_Bollard", material)
    b.box((-0.35, -0.35, 0), (0.35, 0.35, 0.08), "MI_PaintedMetalDark")
    b.box((-0.2, -0.2, 0.08), (0.2, 0.2, 0.5), "MI_PaintedMetalDark")
    b.box((-0.3, -0.36, 0.5), (0.3, 0.3, 0.6), "MI_PaintedMetalDark")       # the head, leaning to the sea (-Y)
    return "Harbour_Bollard", "harbour", b.mesh()


def harbour_fender(material):
    """A rubber fender (防舷材) on the quay face, 1.0 m wide, 1.5 m tall, standing 0.6 m proud of the face (-Y)."""
    b = Builder("Harbour_Fender", material)
    b.box((-0.5, -0.6, -1.8), (0.5, 0.0, -0.3), "MI_PlasticDark")
    return "Harbour_Fender", "harbour", b.mesh()


def harbour_light_mast(material):
    """A yard light mast: 30 m, a 4-lamp head."""
    b = Builder("Harbour_LightMast", material)
    b.box((-0.6, -0.6, 0), (0.6, 0.6, 0.4), "MI_ConcreteSmooth")
    b.frustum(0, 0, 0.4, 30.0, 0.35, 0.35, 0.2, 0.2, "MI_PaintedMetal")
    b.box((-1.6, -1.6, 30.0), (1.6, 1.6, 30.3), "MI_PaintedMetal")
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box((sx * 1.2 - 0.3, sy * 1.2 - 0.3, 29.7), (sx * 1.2 + 0.3, sy * 1.2 + 0.3, 30.0), "MI_Light")
    return "Harbour_LightMast", "harbour", b.mesh()


def harbour_apron(material):
    """One 20-ken (36.4 m) square of terminal paving, its top flush with the ground (0.02 m thick, below it): the
    container yard's apron, tiled by the composite like `Apron_Tile` but 400 times fewer."""
    b = Builder("Harbour_Apron", material)
    h = 36.4 / 2
    b.box((-h, -h, -0.02), (h, h, 0.0), "MI_ConcreteSmooth")
    b.box((-h, -h, 0.0), (h, -h + 0.15, 0.004), "MI_PaintYellow")          # a yard line along one edge
    return "Harbour_Apron", "harbour", b.mesh()


#: What the game assumes about a piece, shown on it in Blender (`edit_note`) so an artist editing it knows what else
#: moves with it. Keep the frame (Z up, origin at the footprint centre on the ground, the used side facing -Y) and the
#: real size unless the note says otherwise; then run tools/building_kit/build_buildings.sh.
EDIT_NOTE_DEFAULT = ("Placeholder, ours (CC0). Keep the frame: Z up, origin at the footprint centre on the ground, the side "
                     "a person uses facing -Y; real size in metres. After editing: tools/building_kit/build_buildings.sh.")
EDIT_NOTES = {  # (+ library_civic.CIVIC_NOTES, merged below)
    "Wall_PartitionDoorWide": "Placeholder accessible doorway: one ken, a 1.0 x 2.0 m hole in the middle. The SLIDING "
                              "leaf is built at runtime and runs 1.0 m along the wall on the prop's `slide_dir` side "
                              "(building_types.json), so the wall must continue there. Its collider is the jamb boxes "
                              "in building_types.json.",
    "Wall_PassWindow": "Placeholder kitchen serving wall, one ken: lower wall to 0.95, pass shelf, open slot to 1.45, "
                       "glass to 2.1. Its collider is the boxes in building_types.json (lower wall + glass and above).",
    "Wall_Partition": "Placeholder interior wall, ONE KEN (1.82 m) long along X, 0.12 m thick, 2.7 m tall. Konbini back "
                      "of house and washroom rooms are rows of these (building_types.json props). Keep the length.",
    "Wall_PartitionDoor": "Placeholder interior wall with a 0.85 x 2.0 m doorway, no leaf. Its COLLIDER is the jambs and "
                          "header written in building_types.json (`collide: boxes`), not its mesh: move them with the "
                          "doorway. A leaf, if modelled, must stand OPEN (the capsule walks through).",
    "Shop_WalkInCooler": "Placeholder walk-in cooler, one ken square, 2.4 m tall. The reach-in drink doors "
                         "(Shop_FridgeDoor) stand on its -Y face; staff restock from +Y.",
    "Harbour_Crane": "Placeholder ship-to-shore crane: rails 30.48 m apart along Y (the sea is -Y), legs 17 m apart along "
                     "X, portal clear 18 m, boom hinge 45 m, boom raised (nothing may overhang -Y past the seaside "
                     "rail + 2 m: the quay line). Its COLLIDER is not its mesh: CRANE_BOXES in "
                     "tools/building_kit/site_container_terminal.py (bogies, legs, portal beams, girders) -- update them "
                     "with the model, or trucks will hit air / drive through legs. The probe checks the portal is open.",
    "Harbour_LightMast": "30 m yard mast. Its collider is MAST_BOXES in site_container_terminal.py (base + pole).",
    "Harbour_Apron": "One 36.4 m (20 ken) paving slab, top flush with the ground at Z 0. The terminal tiles it 10 x 6: "
                     "the size must stay 36.4 m square.",
    "Harbour_Bollard": "Mooring bollard, the head leaning to the sea (-Y). Stood on the quay edge.",
    "Harbour_Fender": "Rubber fender, hangs BELOW the quay edge (Z -1.8..-0.3), face to the sea (-Y). Not in the "
                      "terminal yet (the site probe's height check); for a quay face piece.",
    "Rail_CrossingSignal": "Placeholder 踏切 signal + barrier (boom up). Placed by point_furniture.crossing_signals, TWO per "
    "level crossing (the left of each approach), facing the traffic (-Y); its collider is the post only "
    "(furniture.json collide_pole). Keep the post at the origin.",
    "Signal_Pedestrian": "Placeholder pedestrian signal. The two lenses' centres (red 3.025, green 2.675 m, 0.38 m in "
    "front of the pole) are furniture.json `lamps` -- move a lens here, move it there. Faces -Y across the crosswalk.",
    "ShuriCastle": "Shuri castle (library_landmarks.shuri_castle): the Ryukyu-limestone platform is SH_PLAT_H (25 m) "
                   "tall because the measured site's ground rises 24 m under it (tools/island_sites.py); its top must "
                   "clear the uphill ground. The Seiden faces -Y (the front, towards downtown). Collider = its mesh.",
}


EDIT_NOTES.update(__import__("library_civic").CIVIC_NOTES)
EDIT_NOTES.update(__import__("library_interiors").notes())


def crossing_signal(material):
    """A level-crossing signal (踏切警報機) with its barrier (遮断機), for the road side of a 踏切 (PLAN.md R4). The
    person / driver side faces -Y: the crossbuck (踏切警標, yellow and black) at the top, the two red flashing lamps
    under it, a yellow-and-black striped post on a concrete plinth, and beside it the barrier machine with its boom
    RAISED (a static prop: the barriers-down state machine is tier D, with the trains). The origin is the post's foot;
    the boom stands at +X. Post 3.6 m, boom 4.0 m (a two-lane road's half: the far side has its own unit)."""
    b = Builder("Rail_CrossingSignal", material)
    b.box((-0.25, -0.25, 0.0), (0.25, 0.25, 0.2), "MI_ConcreteSmooth")
    z, k = 0.2, 0
    while z < 3.6 - 1e-6:                      # the post, 0.3 m bands (the 虎柄 of every Japanese crossing)
        top = min(3.6, z + 0.3)
        b.box((-0.06, -0.06, z), (0.06, 0.06, top), "MI_PaintYellow" if k % 2 == 0 else "MI_PlasticDark")
        z, k = top, k + 1
    # the crossbuck: two 1.0 m arms crossing at 3.35 m, in the post's front plane
    for s_ in (-1.0, 1.0):
        b.beam((-0.42, -0.09, 3.35 - s_ * 0.24), (0.42, -0.09, 3.35 + s_ * 0.24), 0.13, "MI_PaintYellow")
    # the lamp bar with two red lamps and their black hoods
    b.box((-0.45, -0.1, 2.55), (0.45, -0.04, 2.65), "MI_PlasticDark")
    for x in (-0.36, 0.36):
        b.box((x - 0.13, -0.12, 2.45), (x + 0.13, -0.06, 2.75), "MI_PlasticDark")
        b.box((x - 0.1, -0.14, 2.48), (x + 0.1, -0.12, 2.72), "MI_CraneRed")
    # the barrier machine and its boom, raised
    b.box((0.18, -0.16, 0.2), (0.48, 0.16, 1.15), "MI_PaintYellow")
    z, k = 1.15, 0
    while z < 5.15 - 1e-6:
        top = min(5.15, z + 0.5)
        b.box((0.29, -0.04, z), (0.37, 0.04, top), "MI_PaintYellow" if k % 2 == 0 else "MI_PlasticDark")
        z, k = top, k + 1
    return "Rail_CrossingSignal", "station", b.mesh()


def pedestrian_signal(material):
    """A pedestrian signal (歩行者用信号機) for a crosswalk end (PLAN.md R4 / user 2026-09-26 "enable both pedestrian +
    traffic light"): a 3.2 m grey pole, and at 2.5-3.2 m the Japanese two-lamp head -- red man above, green man below
    -- facing -Y across the crosswalk, each lens behind a short hood. Lenses are dark here; world.TrafficSignals
    lights them (their centres are `LENSES` below and `furniture.json`'s `lamps` for the asset). Origin: the pole's
    foot."""
    b = Builder("Signal_Pedestrian", material)
    b.box((-0.18, -0.18, 0.0), (0.18, 0.18, 0.12), "MI_ConcreteSmooth")
    b.box((-0.055, -0.055, 0.12), (0.055, 0.055, 3.25), "MI_PaintedMetal")
    b.box((-0.08, -0.08, 3.25), (0.08, 0.08, 3.3), "MI_PaintedMetal")
    b.box((-0.2, -0.36, 2.48), (0.2, -0.06, 3.22), "MI_PaintedMetalDark")        # the head body
    b.box((-0.03, -0.1, 2.6), (0.03, 0.0, 3.1), "MI_PaintedMetal")                 # its bracket to the pole
    for z0 in (2.52, 2.87):                                                         # two lenses + hoods
        b.box((-0.16, -0.38, z0), (0.16, -0.36, z0 + 0.31), "MI_PlasticDark")
        b.box((-0.18, -0.46, z0 + 0.29), (0.18, -0.36, z0 + 0.33), "MI_PaintedMetalDark")
    return "Signal_Pedestrian", "station", b.mesh()


def build_all(material):
    return [
        fridge_door(material),
        coffee_machine(material),
        open_case(material),
        cigarette_case(material),
        bin_station(material),
        eat_in_counter(material),
        stool(material),
        freezer_case(material),
        coffee_station(material),
        fascia(material, "Fascia_Shop", "MI_FasciaKonbini", 0.9, 0.12),
        partition(material),
        partition_door(material),
        walkin_cooler(material),
        locker(material),
        desk(material),
        safe(material),
        atm(material),
        hot_case(material),
        magazine_rack(material),
        copier(material),
        wc_partition(material),
        washlet_toilet(material),
        square_basin(material),
        partition_half(material),
        partition_door_wide(material),
        pass_window(material),
        grab_rail(material),
        baby_table(material),
        kitchen_sink(material),
        prep_table(material),
        fryer(material),
        kitchen_fridge(material),
        gas_canopy(material),
        gas_column(material),
        gas_island(material),
        crossing_signal(material),
        pedestrian_signal(material),
        apron_tile(material),
        parking_line(material),
        parking_stop(material),
        harbour_crane(material),
        harbour_bollard(material),
        harbour_fender(material),
        harbour_light_mast(material),
        harbour_apron(material),
    ] + __import__("library_landmarks").build_all(material, Builder) + __import__("library_civic").build_all(material,
                                                                                                          Builder) + \
        __import__("library_interiors").build_all(material, Builder)
