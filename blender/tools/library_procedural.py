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
    b.box((x0, y1 - 0.05, 0), (x1, y1, h), "MI_PaintedMetal")              # back
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


def wc_partition(material):
    b = Builder("WC_Partition", material)
    b.box((-0.015, -0.75, 0.12), (0.015, 0.75, 2.02), "MI_PlasticWhite")
    b.box((-0.03, -0.75, 0), (0.03, -0.69, 0.12), "MI_Steel")                 # the two feet
    b.box((-0.03, 0.69, 0), (0.03, 0.75, 0.12), "MI_Steel")
    return "WC_Partition", "fixtures", b.mesh()


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


# ── rural station ────────────────────────────────────────────────────────────────────────────────────────────

PLATFORM_H = 1.3


def platform_module(material):
    b = Builder("Platform_Module", material)
    L, D, h = 1.82, 3.64, PLATFORM_H
    b.box((-L / 2, -D / 2, 0), (L / 2, D / 2, h), "MI_ConcreteSmooth")
    b.box((-L / 2, -D / 2, h), (L / 2, -D / 2 + 0.08, h + 0.004), "MI_PaintWhite")          # edge line
    b.box((-L / 2, -D / 2 + 0.8, h), (L / 2, -D / 2 + 1.1, h + 0.006), "MI_Tactile")         # 0.8 m in
    b.box((-L / 2, -D / 2 - 0.02, h - 0.12), (L / 2, -D / 2, h), "MI_PaintYellow")           # coping face
    return "Platform_Module", "station", b.mesh()


def platform_ramp(material):
    """The platform's end: a 1:2.8 slope down to the ground over two ken, the width of a module."""
    b = Builder("Platform_Ramp", material)
    L, D, h = 3.64, 3.64, PLATFORM_H
    b.wedge_x(-L / 2, L / 2, -D / 2, D / 2, h, 0.02, "MI_ConcreteSmooth")
    return "Platform_Ramp", "station", b.mesh()


def platform_fence(material):
    b = Builder("Platform_Fence", material)
    for x in (-0.89, 0.89):
        b.box((x - 0.03, -0.03, 0), (x + 0.03, 0.03, 1.2), "MI_PaintedMetal")
    for z in (0.35, 0.75, 1.15):
        b.box((-0.91, -0.02, z), (0.91, 0.02, z + 0.05), "MI_PaintedMetal")
    return "Platform_Fence", "station", b.mesh()


def platform_shelter(material):
    """A platform shelter (上屋): corrugated roof on two posts at the back, 3.64 m long, 2.7 m to the eaves."""
    b = Builder("Platform_Shelter", material)
    L, D = 3.64, 2.4
    for x in (-1.3, 1.3):
        b.box((x - 0.06, 0.55, 0), (x + 0.06, 0.67, 2.75), "MI_PaintedMetal")
    b.box((-L / 2, -D / 2, 2.75), (L / 2, D / 2, 2.82), "MI_Corrugated")
    b.box((-L / 2, -D / 2, 2.7), (L / 2, -D / 2 + 0.05, 2.82), "MI_PaintedMetal")
    b.box((-0.6, -D / 2 + 0.3, 2.62), (0.6, -D / 2 + 0.5, 2.7), "MI_Light")
    return "Platform_Shelter", "station", b.mesh()


def name_board(material):
    """The station name board (駅名標): white, a coloured band along the bottom, on two posts."""
    b = Builder("Station_NameBoard", material)
    for x in (-0.65, 0.65):
        b.box((x - 0.03, -0.03, 0), (x + 0.03, 0.03, 1.6), "MI_PaintedMetal")
    b.box((-0.8, -0.04, 1.6), (0.8, 0.02, 2.1), "MI_PaintWhite")
    b.box((-0.8, -0.05, 1.6), (0.8, -0.04, 1.7), "MI_Sign")
    return "Station_NameBoard", "station", b.mesh()


def track_module(material):
    b = Builder("Track_Module", material)
    L = 1.82
    b.box((-L / 2, -1.4, 0), (L / 2, 1.4, 0.1), "MI_Ballast")
    for k in range(3):
        x = -L / 2 + L * (k + 0.5) / 3
        b.box((x - 0.1, -1.0, 0.1), (x + 0.1, 1.0, 0.22), "MI_ConcreteSmooth")
    g = 1.067 / 2
    for s in (-1, 1):
        y = s * (g + 0.035)
        b.box((-L / 2, y - 0.035, 0.22), (L / 2, y + 0.035, 0.36), "MI_Steel")
    return "Track_Module", "station", b.mesh()


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
EDIT_NOTES = {
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
    "ShuriCastle": "Shuri castle (library_landmarks.shuri_castle): the Ryukyu-limestone platform is SH_PLAT_H (25 m) "
                   "tall because the measured site's ground rises 24 m under it (tools/island_sites.py); its top must "
                   "clear the uphill ground. The Seiden faces -Y (the front, towards downtown). Collider = its mesh.",
}


def build_all(material):
    return [
        fridge_door(material),
        coffee_machine(material),
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
        gas_canopy(material),
        gas_column(material),
        gas_island(material),
        platform_module(material),
        platform_ramp(material),
        platform_fence(material),
        platform_shelter(material),
        name_board(material),
        track_module(material),
        apron_tile(material),
        parking_line(material),
        parking_stop(material),
        harbour_crane(material),
        harbour_bollard(material),
        harbour_fender(material),
        harbour_light_mast(material),
        harbour_apron(material),
    ] + __import__("library_landmarks").build_all(material, Builder)
