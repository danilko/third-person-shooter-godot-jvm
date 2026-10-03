"""EMU1 -- a Japanese commuter EMU (通勤形電車) built to the LARGEST standard conventional-line size, so every station,
track spacing and clearance measured against it holds for any real train that runs on the 1067 mm lines.

    blender -b --python-exit-code 1 --python blender/tools/make_train.py [-- --force]

Writes `assets/vehicles/trains/EMU1.blend` (it OWNS the model afterwards: a regenerate refuses to overwrite an edited
file without `--force`), `EMU1_Tc.glb` (the cab car) and `EMU1_M.glb` (the middle car, with a pantograph), and
`EMU1.train.json` -- every number MEASURED off the built meshes, which the stations and the gauge checks read
(`tools/godot/probe_train_fit.gd`). A 4-car set is Tc + M + M + Tc (turned).

THE SIZE (user, 2026-09-29: "assume the largest Japan metro/rail train width to be on the safe side"). Numbers are the
published norms for a 20 m, 4-door, wide-body commuter car on the 1067 mm gauge (the JR East E231/E233 family and the
private lines built to the same envelope); no line's livery, logo or name is copied:
  * car body 19.5 m long, 20.0 m over the couplers; bogie centres 13.8 m apart, 2.1 m wheelbase, 0.86 m wheels;
  * WIDE BODY 2.95 m at the waist (the widest standard car; a subway car is 2.8-2.85 m), narrowing to 2.80 m at the
    side sill below the floor -- the curve that lets the car overhang a platform whose top is at its floor;
  * floor 1.13 m over the rail head (a platform is 1.10: a 3 cm step), roof 3.62 m, roof equipment to 3.98 m, the
    pantograph folded to 4.05 m (the conventional-line vehicle gauge is 3.0 m wide, 4.1 m high);
  * four 1.3 m doors a side on a 4.82 m pitch.
Blender frame (the vehicle convention, blender/VEHICLE_AUTHORING.md): the car FACES +Y (Godot -Z), X across, Z up;
origin at the car's centre on the RAIL HEAD plane between the two rails.
"""
import json
import math
import os
import sys

import bmesh
import bpy

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "assets", "vehicles", "trains")
BLEND = os.path.join(OUT, "EMU1.blend")

BODY_L = 19.5
COUPLED_L = 20.0
BOGIE_C = 13.8 / 2.0
WHEELBASE = 2.1
WHEEL_R = 0.43
GAUGE = 1.067
FLOOR_Z = 1.13
DOOR_W = 1.3
DOOR_H = 1.85
DOOR_Y = (-7.23, -2.41, 2.41, 7.23)
# the body's cross-section, (half width, z over the rail head) from the sill up to the roof's crown: the wide body
PROFILE = [(1.40, 0.95), (1.44, 1.10), (1.465, 1.30), (1.475, 1.60), (1.475, 2.20), (1.465, 2.60), (1.44, 3.00),
           (1.40, 3.20), (1.30, 3.36), (1.10, 3.50), (0.80, 3.58), (0.40, 3.615), (0.0, 3.62)]
MATS = {"stainless": (0.72, 0.74, 0.76, 1.0), "band": (0.10, 0.55, 0.45, 1.0), "glass": (0.05, 0.07, 0.09, 0.35),
        "under": (0.12, 0.12, 0.13, 1.0), "roof": (0.35, 0.36, 0.38, 1.0), "door": (0.68, 0.70, 0.72, 1.0),
        "light": (1.0, 0.95, 0.80, 1.0), "sign": (0.02, 0.02, 0.02, 1.0), "rubber": (0.08, 0.08, 0.08, 1.0),
        # the interior (a placeholder set for an artist to replace -- assets/vehicles/trains/ARTIST_NOTES.md)
        "lining": (0.88, 0.87, 0.82, 1.0), "ceiling": (0.93, 0.93, 0.91, 1.0), "floor": (0.42, 0.43, 0.45, 1.0),
        "seat": (0.12, 0.28, 0.62, 1.0), "seat_priority": (0.72, 0.28, 0.20, 1.0), "partition": (0.84, 0.83, 0.79, 1.0),
        "pole": (0.82, 0.83, 0.85, 1.0), "pole_priority": (0.95, 0.75, 0.10, 1.0), "strap": (0.92, 0.92, 0.90, 1.0),
        "strap_priority": (0.96, 0.78, 0.12, 1.0), "rack": (0.60, 0.61, 0.63, 1.0), "screen": (0.03, 0.05, 0.08, 1.0),
        "warning": (0.95, 0.80, 0.10, 1.0), "cab": (0.24, 0.25, 0.27, 1.0), "vent": (0.80, 0.80, 0.79, 1.0)}
METAL = ("stainless", "door", "pole", "pole_priority", "rack")
EMISSIVE = {"light": 3.0, "screen": 0.6}
WALL_T = 0.05          # the body wall: outer skin to inner lining
CEIL_Z = 3.36          # the ceiling inside (2.23 m over the floor)
WIN_Z = (1.95, 2.75)   # the window band
DOOR_TOP = FLOOR_Z + DOOR_H
DOOR_OPEN = 0.62       # each leaf slides this far into its pocket
GANG_W = 0.55          # half width of the gangway (貫通路) opening between cars
GANG_TOP = 2.95
CAB_D = 1.7            # the driving cab's depth behind the front


def mat(name):
    m = bpy.data.materials.get("M_Train_" + name)
    if m is None:
        m = bpy.data.materials.new("M_Train_" + name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes["Principled BSDF"]
        col = MATS[name]
        bsdf.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
        bsdf.inputs["Metallic"].default_value = 0.8 if name in METAL else 0.0
        bsdf.inputs["Roughness"].default_value = 0.35 if name in METAL + ("glass",) else 0.7
        if name in EMISSIVE:
            bsdf.inputs["Emission Color"].default_value = (col[0], col[1], col[2], 1.0)
            bsdf.inputs["Emission Strength"].default_value = EMISSIVE[name]
        if col[3] < 1.0:
            # an unlinked Alpha under 1 exports as glTF alphaMode BLEND (see-through windows)
            bsdf.inputs["Alpha"].default_value = col[3]
        m.diffuse_color = col
    # double-sided: the car is seen from inside as well as out (glTF doubleSided)
    m.use_backface_culling = False
    return m


def x_out(z):
    """The body's outer half width at height z (PROFILE, linear between its points)."""
    if z <= PROFILE[0][1]:
        return PROFILE[0][0]
    for (xa, za), (xb, zb) in zip(PROFILE, PROFILE[1:]):
        if za <= z <= zb:
            return xa + (xb - xa) * (z - za) / max(1e-9, zb - za)
    return 0.0


class Mesh:
    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def box(self, lo, hi, m):
        vs = [self.bm.verts.new((x, y, z)) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
        k = self.mi(m)
        for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            self.bm.faces.new([vs[i] for i in f]).material_index = k

    def cyl_x(self, cx, cy, cz, r, w, m, n=16):
        """A cylinder along X (a wheel), centred at (cx, cy, cz)."""
        k = self.mi(m)
        rings = []
        for x in (cx - w / 2, cx + w / 2):
            rings.append([self.bm.verts.new((x, cy + r * math.cos(2 * math.pi * i / n),
                                             cz + r * math.sin(2 * math.pi * i / n))) for i in range(n)])
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new([rings[0][i], rings[0][j], rings[1][j], rings[1][i]]).material_index = k
        self.bm.faces.new(rings[0][::-1]).material_index = k
        self.bm.faces.new(rings[1]).material_index = k

    def prism_y(self, prof, y0, y1, m, cap0=True, cap1=True):
        """The closed section `prof` [(x, z)] extruded along Y from y0 to y1."""
        k = self.mi(m)
        a = [self.bm.verts.new((x, y0, z)) for x, z in prof]
        b = [self.bm.verts.new((x, y1, z)) for x, z in prof]
        n = len(prof)
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new([a[i], a[j], b[j], b[i]]).material_index = k
        if cap0:
            self.bm.faces.new(a[::-1]).material_index = k
        if cap1:
            self.bm.faces.new(b).material_index = k

    def wall(self, sg, y0, y1, z0, z1, mo, mi):
        """A piece of the side wall on side `sg` (+1 / -1) from y0 to y1 and z0 to z1: its outer face on the body's
        PROFILE, its inner face WALL_T inside it (the lining)."""
        ko, ki = self.mi(mo), self.mi(mi)
        xo0, xo1 = sg * x_out(z0), sg * x_out(z1)
        xi0, xi1 = xo0 - sg * WALL_T, xo1 - sg * WALL_T
        v = {}
        for (k, x0, x1) in (("o", xo0, xo1), ("i", xi0, xi1)):
            v[k] = [self.bm.verts.new((x0, y0, z0)), self.bm.verts.new((x0, y1, z0)),
                    self.bm.verts.new((x1, y1, z1)), self.bm.verts.new((x1, y0, z1))]
        o, i = v["o"], v["i"]
        self.bm.faces.new(o).material_index = ko
        self.bm.faces.new(i[::-1]).material_index = ki
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            self.bm.faces.new((o[a], i[a], i[b], o[b])).material_index = ko

    def cyl(self, axis, c, r, length, m, n=8):
        """A cylinder of radius r along `axis` ('x', 'y' or 'z'), centred at c."""
        k = self.mi(m)
        ax = "xyz".index(axis)
        u, w = [a for a in range(3) if a != ax]
        rings = []
        for t in (-length / 2, length / 2):
            ring = []
            for i in range(n):
                p = list(c)
                p[ax] += t
                p[u] += r * math.cos(2 * math.pi * i / n)
                p[w] += r * math.sin(2 * math.pi * i / n)
                ring.append(self.bm.verts.new(p))
            rings.append(ring)
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new([rings[0][i], rings[0][j], rings[1][j], rings[1][i]]).material_index = k
        self.bm.faces.new(rings[0][::-1]).material_index = k
        self.bm.faces.new(rings[1]).material_index = k

    def ring_yz(self, cy, cz, x, r, t, m, n=10):
        """A strap handle: a ring of radius r in the car's YZ plane (square tube of half size t), centred (x, cy, cz)."""
        k = self.mi(m)
        secs = []
        for i in range(n):
            a = 2 * math.pi * i / n
            dy, dz = math.sin(a), math.cos(a)
            sec = []
            for (sx, sr) in ((-t, -t), (t, -t), (t, t), (-t, t)):
                rr = r + sr
                sec.append(self.bm.verts.new((x + sx, cy + rr * dy, cz + rr * dz)))
            secs.append(sec)
        for i in range(n):
            a, b = secs[i], secs[(i + 1) % n]
            for q in range(4):
                p = (q + 1) % 4
                self.bm.faces.new((a[q], a[p], b[p], b[q])).material_index = k

    def done(self, coll, loc=None):
        me = bpy.data.meshes.new(self.name)
        bmesh.ops.recalc_face_normals(self.bm, faces=list(self.bm.faces))
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(mat(m))
        ob = bpy.data.objects.new(self.name, me)
        if loc is not None:
            ob.location = loc
        coll.objects.link(ob)
        return ob


def roof_section():
    """The roof's closed section (x, z) above the ceiling line: the profile over the crown, closed at CEIL_Z."""
    top = [(x, z) for x, z in PROFILE if z >= CEIL_Z]
    right = [(x_out(CEIL_Z), CEIL_Z)] + [p for p in top if p[1] > CEIL_Z]
    left = [(-x, z) for x, z in reversed(right[:-1])]
    return right + left


def side_spans(half):
    """The side wall cut along Y into (y0, y1, kind): 'door' (an opening), 'window' (a glazed bay) or 'pier'."""
    bs = [-half, -half + 0.9]
    for y in DOOR_Y:
        d0, d1 = y - DOOR_W / 2, y + DOOR_W / 2
        bs += [d0 - 0.35, d0, d1, d1 + 0.35]
    bs += [half - 0.9, half]
    kinds = ["pier"] + ["window", "pier", "door", "pier"] * len(DOOR_Y) + ["window", "pier"]
    return [(y0, y1, k) for y0, y1, k in zip(bs, bs[1:], kinds) if y1 - y0 > 1e-6]


def body(cab):
    """The body shell, with real DOOR OPENINGS (the leaves are their own objects, door_leaves) and see-through windows,
    lined inside. `cab`: a driving cab at +Y."""
    m = Mesh("Body")
    half = BODY_L / 2.0
    # under the floor: the side sill and the underside, and the floor itself
    m.box((-1.42, -half, 0.95), (1.42, half, FLOOR_Z - 0.02), "stainless")
    xin = x_out(FLOOR_Z) - WALL_T
    m.box((-xin, -half + 0.05, FLOOR_Z - 0.02), (xin, half - 0.05, FLOOR_Z), "floor")
    # the roof over the ceiling, its grey top and the ceiling inside
    m.prism_y(roof_section(), -half, half, "stainless")
    m.box((-1.25, -half + 0.3, 3.50), (1.25, half - 0.3, 3.63), "roof")
    m.box((-x_out(CEIL_Z) + WALL_T, -half + 0.05, CEIL_Z - 0.02), (x_out(CEIL_Z) - WALL_T, half - 0.05, CEIL_Z),
          "ceiling")
    for sg in (-1.0, 1.0):
        # the skirt under the floor line
        m.wall(sg, -half, half, 0.95, FLOOR_Z, "stainless", "stainless")
        for y0, y1, kind in side_spans(half):
            if kind == "door":
                m.wall(sg, y0, y1, DOOR_TOP, CEIL_Z, "stainless", "lining")
                # the doorway's frame, proud of the skin (the door's guide and seal)
                f0, f1 = sorted((sg * 1.476, sg * 1.491))
                for ya, yb in ((y0 - 0.06, y0), (y1, y1 + 0.06)):
                    m.box((f0, ya, FLOOR_Z), (f1, yb, DOOR_TOP + 0.06), "door")
                m.box((f0, y0, DOOR_TOP), (f1, y1, DOOR_TOP + 0.06), "door")
            elif kind == "window":
                m.wall(sg, y0, y1, FLOOR_Z, WIN_Z[0], "stainless", "lining")
                m.wall(sg, y0, y1, WIN_Z[1], CEIL_Z, "stainless", "lining")
                x0, x1 = sorted((sg * (x_out(2.3) - WALL_T / 2 - 0.004), sg * (x_out(2.3) - WALL_T / 2 + 0.004)))
                m.box((x0, y0, WIN_Z[0]), (x1, y1, WIN_Z[1]), "glass")
            else:
                m.wall(sg, y0, y1, FLOOR_Z, CEIL_Z, "stainless", "lining")
        # the colour band under the windows, outside
        x = sg * (x_out(1.75) + 0.004)
        for y0, y1, kind in side_spans(half):
            if kind != "door":
                m.box((min(x, x - sg * 0.01), y0, 1.70), (max(x, x - sg * 0.01), y1, 1.80), "band")
    for end in (-1.0, 1.0):
        y = end * half
        ya, yb = sorted((y, y - end * WALL_T))
        if cab and end > 0:
            # the cab front: a full-width windscreen in a frame, the destination sign over it, two headlights under it
            m.box((-1.42, ya, FLOOR_Z), (1.42, yb, WIN_Z[0]), "stainless")
            m.box((-1.42, ya, 2.85), (1.42, yb, 3.0), "stainless")
            for sx in (-1.0, 1.0):
                m.box((min(sx * 1.25, sx * 1.42), ya, WIN_Z[0]), (max(sx * 1.25, sx * 1.42), yb, 2.85), "stainless")
            m.box((-1.28, ya, 3.0), (1.28, yb, CEIL_Z), "stainless")
            m.box((-1.25, y - 0.01, WIN_Z[0]), (1.25, y + 0.01, 2.85), "glass")
            m.box((-0.80, y, 2.88), (0.80, y + 0.04, 2.99), "sign")
            for sx in (-1.0, 1.0):
                m.box((sx * 1.0 - 0.18, y, 1.45), (sx * 1.0 + 0.18, y + 0.05, 1.60), "light")
            m.box((-1.40, y, 1.10), (1.40, y + 0.12, 1.30), "band")
        else:
            # an end wall with the gangway (貫通路) opening, and the bellows' frame and footplate out to the next car
            for sx in (-1.0, 1.0):
                m.box((min(sx * GANG_W, sx * 1.42), ya, FLOOR_Z), (max(sx * GANG_W, sx * 1.42), yb, 3.0), "lining")
            m.box((-1.28, ya, 3.0), (1.28, yb, CEIL_Z), "lining")
            m.box((-GANG_W, ya, GANG_TOP), (GANG_W, yb, 3.0), "lining")
            b0, b1 = sorted((y, y + end * 0.25))
            for sx in (-1.0, 1.0):
                m.box((min(sx * GANG_W, sx * (GANG_W + 0.1)), b0, FLOOR_Z), (max(sx * GANG_W, sx * (GANG_W + 0.1)), b1,
                      GANG_TOP + 0.1), "rubber")
            m.box((-GANG_W - 0.1, b0, GANG_TOP), (GANG_W + 0.1, b1, GANG_TOP + 0.1), "rubber")
            m.box((-GANG_W, b0, FLOOR_Z - 0.04), (GANG_W, b1, FLOOR_Z), "under")
    return m


def door_leaves(coll):
    """Every door's two leaves as their OWN objects, so the game can slide them: `Door_<P|N><i><a|b>` -- P on the +X
    side, i counting along +Y, a the leaf toward -Y (it opens toward -Y), b toward +Y. Each leaf's origin is its centre
    closed, inside the wall's thickness, so it slides into the pocket beside the doorway (戸袋) out of sight."""
    obs = []
    lw, hz = DOOR_W / 4.0, DOOR_H / 2.0
    for sg, sd in ((1.0, "P"), (-1.0, "N")):
        xc = sg * (x_out(2.0) - WALL_T / 2)
        for i, y in enumerate(DOOR_Y):
            for leaf, dy in (("a", -lw), ("b", lw)):
                m = Mesh("Door_%s%d%s" % (sd, i, leaf))
                t = 0.012
                m.box((-t, -lw, -hz), (t, lw, hz), "door")
                m.box((-t - 0.003, -lw + 0.08, WIN_Z[0] - FLOOR_Z - hz), (t + 0.003, lw - 0.08, 2.70 - FLOOR_Z - hz),
                      "glass")
                e0, e1 = (lw - 0.012, lw) if leaf == "a" else (-lw, -lw + 0.012)    # the meeting edge's rubber
                m.box((-t - 0.004, e0, -hz), (t + 0.004, e1, hz), "rubber")
                obs.append(m.done(coll, loc=(xc, y + dy, FLOOR_Z + hz)))
    return obs


SEAT_W = 0.46           # one seat's width on a long bench (ロングシート)
SEAT_D = 0.55           # cushion depth from the wall
SEAT_H = 0.43           # cushion top over the floor
RAIL_Z = 3.20           # the ceiling grab rails (2.07 m over the floor), at x = +-RAIL_X
RAIL_X = 0.78
STRAP_PITCH = 0.32
STRAP_LOW = 2.86        # a strap ring's centre (its bottom ~1.67 m over the floor)


def bays(cab):
    """The bench bays along the car (y0, y1, priority, wheelchair_side), between the doors and at the ends."""
    half = BODY_L / 2.0
    edges = [(-half + WALL_T, DOOR_Y[0] - DOOR_W / 2)]
    for a, b in zip(DOOR_Y, DOOR_Y[1:]):
        edges.append((a + DOOR_W / 2, b - DOOR_W / 2))
    end = (half - CAB_D) if cab else (half - WALL_T)
    edges.append((DOOR_Y[-1] + DOOR_W / 2, end))
    out = []
    for i, (y0, y1) in enumerate(edges):
        if y1 - y0 < 1.0:
            continue
        # 優先席 at the -Y end of every car; a wheelchair space (one side, no bench) at a middle car's +Y end
        out.append((y0, y1, i == 0, -1.0 if (not cab and i == len(edges) - 1) else 0.0))
    return out


def interior(cab):
    """A Japanese commuter car's saloon (placeholders, to be replaced by an artist): long bench seats with priority
    seats, partitions at the doors, poles, luggage racks, grab rails with hanging straps, LED ceiling lights, a door-top
    screen over every door, and on a cab car the cab behind its partition."""
    m = Mesh("Interior")
    half = BODY_L / 2.0
    fz = FLOOR_Z
    xw = x_out(fz + 0.4) - WALL_T                     # the wall's inner face at seat height
    for y0, y1, prio, wc in bays(cab):
        seat = "seat_priority" if prio else "seat"
        for sg in (-1.0, 1.0):
            if wc == sg:
                # the wheelchair / free space: a padded wall and a handrail
                m.box((sg * (xw - 0.03) - 0.001, y0 + 0.2, fz + 0.55), (sg * xw + 0.001, y1 - 0.2, fz + 1.05), "partition")
                m.cyl("y", (sg * (xw - 0.08), (y0 + y1) / 2, fz + 0.85), 0.016, y1 - y0 - 0.5, "pole")
                continue
            near_door0 = y0 > -half + 0.2
            near_door1 = y1 < half - CAB_D - 0.05 if cab else y1 < half - 0.2
            s0 = y0 + (0.06 if near_door0 else 0.02)
            s1 = y1 - (0.06 if near_door1 else 0.02)
            n = max(1, int((s1 - s0) // SEAT_W))
            w = (s1 - s0) / n
            x0, x1 = sorted((sg * xw, sg * (xw - SEAT_D)))
            m.box((x0 + (0.05 if sg < 0 else 0), s0, fz + 0.08), (x1 - (0.05 if sg > 0 else 0), s1, fz + SEAT_H - 0.08),
                  "cab")                                              # the bench base (heater under it)
            for k in range(n):
                m.box((x0, s0 + k * w + 0.01, fz + SEAT_H - 0.08), (x1, s0 + (k + 1) * w - 0.01, fz + SEAT_H), seat)
            bx0, bx1 = sorted((sg * xw, sg * (xw - 0.10)))
            m.box((bx0, s0, fz + SEAT_H), (bx1, s1, fz + 1.02), seat)  # the backrest
            # 袖仕切り: a partition at each door end, a pole at the bench's middle
            for yp, on in ((y0 + 0.02, near_door0), (y1 - 0.02, near_door1)):
                if on:
                    px0, px1 = sorted((sg * xw, sg * (xw - SEAT_D - 0.08)))
                    m.box((px0, yp - 0.02, fz + 0.08), (px1, yp + 0.02, fz + 1.75), "partition")
                    m.cyl("z", (sg * (xw - SEAT_D - 0.10), yp, (fz + CEIL_Z) / 2), 0.018, CEIL_Z - fz,
                          "pole_priority" if prio else "pole")
            if n >= 5:
                m.cyl("z", (sg * (xw - SEAT_D - 0.05), (s0 + s1) / 2, (fz + CEIL_Z) / 2), 0.016, CEIL_Z - fz,
                      "pole_priority" if prio else "pole")
            # 網棚: the luggage rack over the bench
            rx0, rx1 = sorted((sg * (xw - 0.02), sg * (xw - 0.30)))
            m.box((rx0, s0, fz + 1.72), (rx1, s1, fz + 1.75), "rack")
    # the grab rails, their ceiling hangers and the straps (吊り革), yellow over the priority seats
    r0 = -half + 0.4
    r1 = (half - CAB_D - 0.3) if cab else (half - 0.4)
    prio_y1 = bays(cab)[0][1]
    for sx in (-1.0, 1.0):
        m.cyl("y", (sx * RAIL_X, (r0 + r1) / 2, RAIL_Z), 0.014, r1 - r0, "pole")
        y = r0 + 0.1
        while y < r1:
            m.box((sx * RAIL_X - 0.01, y - 0.01, RAIL_Z), (sx * RAIL_X + 0.01, y + 0.01, CEIL_Z - 0.02), "pole")
            y += 1.8
        y = r0 + 0.2
        while y < r1 - 0.1:
            pr = y < prio_y1
            m.box((sx * RAIL_X - 0.004, y - 0.013, STRAP_LOW + 0.06), (sx * RAIL_X + 0.004, y + 0.013, RAIL_Z - 0.01),
                  "strap_priority" if pr else "strap")
            m.ring_yz(y, STRAP_LOW, sx * RAIL_X, 0.062, 0.009, "strap_priority" if pr else "strap")
            y += STRAP_PITCH
    # two LED light lines, the air-conditioning diffuser between them
    for sx in (-1.0, 1.0):
        m.box((sx * 0.48 - 0.06, r0, CEIL_Z - 0.035), (sx * 0.48 + 0.06, r1, CEIL_Z - 0.02), "light")
    m.box((-0.18, r0, CEIL_Z - 0.03), (0.18, r1, CEIL_Z - 0.02), "vent")
    # a door-top screen (ドア上LCD) over every door, and a yellow line on the floor at every doorway
    for sg in (-1.0, 1.0):
        xs = sg * (x_out(3.1) - WALL_T - 0.03)
        for y in DOOR_Y:
            a0, a1 = sorted((xs, xs - sg * 0.05))
            m.box((a0, y - 0.32, 3.02), (a1, y + 0.32, 3.24), "screen")
            w0, w1 = sorted((sg * (x_out(fz) - WALL_T - 0.08), sg * (x_out(fz) - WALL_T - 0.03)))
            m.box((w0, y - DOOR_W / 2, fz), (w1, y + DOOR_W / 2, fz + 0.004), "warning")
    if cab:
        cy = half - CAB_D
        # the cab partition: a wall with a window, and the cab door (shut) on the right
        m.box((-1.42, cy - 0.04, fz), (1.42, cy, 2.0), "lining")
        m.box((-1.42, cy - 0.04, 2.70), (1.42, cy, CEIL_Z), "lining")
        m.box((-1.42, cy - 0.04, 2.0), (-0.9, cy, 2.70), "lining")
        m.box((-0.9, cy - 0.03, 2.0), (0.35, cy - 0.01, 2.70), "glass")
        m.box((0.35, cy - 0.04, 2.0), (1.42, cy, 2.70), "lining")
        m.box((0.45, cy - 0.05, fz), (1.10, cy - 0.04, fz + 1.90), "door")
        # the driving desk across the front, the one-handle controller and the driver's seat (on the left)
        m.box((-1.35, half - 0.70, fz), (1.35, half - 0.10, fz + 0.95), "cab")
        m.box((-0.75, half - 0.75, fz + 0.95), (-0.35, half - 0.55, fz + 1.10), "rubber")
        m.box((-0.85, cy + 0.35, fz), (-0.35, cy + 0.85, fz + 0.50), "cab")
        m.box((-0.85, cy + 0.30, fz + 0.50), (-0.35, cy + 0.38, fz + 1.10), "cab")
    return m


def underframe(pantograph):
    m = Mesh("Underframe")
    half = BODY_L / 2.0
    # under-floor equipment between the bogies, the couplers
    m.box((-1.20, -BOGIE_C + 2.0, 0.40), (1.20, BOGIE_C - 2.0, 0.95), "under")
    for end in (-1.0, 1.0):
        y = end * half
        m.box((-0.18, min(y, y + end * 0.25), 0.72), (0.18, max(y, y + end * 0.25), 0.95), "under")
    # roof: two air-conditioning units, and on a motor car a folded pantograph
    for yc in (-4.8, 4.8):
        m.box((-0.95, yc - 1.3, 3.60), (0.95, yc + 1.3, 3.98), "roof")
    if pantograph:
        m.box((-0.8, -0.8, 3.62), (0.8, 0.8, 3.72), "under")
        m.box((-0.05, -0.9, 3.72), (0.05, 0.9, 3.95), "under")
        m.box((-0.85, -0.12, 3.97), (0.85, 0.12, 4.05), "under")
    return m


def bogies():
    m = Mesh("Bogies")
    for yc in (-BOGIE_C, BOGIE_C):
        m.box((-1.15, yc - 1.6, 0.30), (1.15, yc + 1.6, 0.85), "under")
        for dy in (-WHEELBASE / 2, WHEELBASE / 2):
            for sx in (-1.0, 1.0):
                m.cyl_x(sx * (GAUGE / 2 + 0.035), yc + dy, WHEEL_R, WHEEL_R, 0.13, "under")
            m.box((-GAUGE / 2, yc + dy - 0.07, WHEEL_R - 0.07), (GAUGE / 2, yc + dy + 0.07, WHEEL_R + 0.07), "under")
    return m


def collider_boxes(cab):
    """The car's collision as boxes (name, lo, hi), Blender frame -- a SHELL a character can walk inside: the floor,
    the roof, the walls with the doorways open, the end walls with the gangway open, the benches and partitions.
    Each doorway has its own `DOORCOL_<side><i>` box, which the game switches off while that door stands open."""
    half = BODY_L / 2.0
    out = [("COL_floor", (-1.42, -half, 0.30), (1.42, half, FLOOR_Z)),
           ("COL_roof", (-1.45, -half, CEIL_Z), (1.45, half, 3.62))]
    for sg, sd in ((1.0, "P"), (-1.0, "N")):
        x0, x1 = sorted((sg * 1.40, sg * 1.50))
        k = 0
        for y0, y1, kind in side_spans(half):
            if kind == "door":
                out.append(("COL_lintel_%s%d" % (sd, k), (x0, y0, DOOR_TOP), (x1, y1, CEIL_Z)))
                out.append(("DOORCOL_%s%d" % (sd, k), (x0, y0, FLOOR_Z), (x1, y1, DOOR_TOP)))
                k += 1
            else:
                out.append(("COL_wall_%s_%.2f" % (sd, y0), (x0, y0, FLOOR_Z), (x1, y1, CEIL_Z)))
    for end in (-1.0, 1.0):
        y = end * half
        ya, yb = sorted((y, y - end * 0.08))
        tag = "f" if end > 0 else "r"
        if cab and end > 0:
            out.append(("COL_front", (-1.45, ya, FLOOR_Z), (1.45, yb, CEIL_Z)))
            cy = half - CAB_D
            out.append(("COL_cab", (-1.45, cy - 0.06, FLOOR_Z), (1.45, cy, CEIL_Z)))
        else:
            for sx, sn in ((-1.0, "n"), (1.0, "p")):
                out.append(("COL_end_%s%s" % (tag, sn), (min(sx * GANG_W, sx * 1.45), ya, FLOOR_Z),
                            (max(sx * GANG_W, sx * 1.45), yb, CEIL_Z)))
                b0, b1 = sorted((y, y + end * 0.25))
                out.append(("COL_bellows_%s%s" % (tag, sn), (min(sx * GANG_W, sx * (GANG_W + 0.1)), b0, FLOOR_Z),
                            (max(sx * GANG_W, sx * (GANG_W + 0.1)), b1, GANG_TOP)))
            out.append(("COL_end_%st" % tag, (-GANG_W, ya, GANG_TOP), (GANG_W, yb, CEIL_Z)))
            b0, b1 = sorted((y, y + end * 0.25))
            out.append(("COL_foot_%s" % tag, (-GANG_W, b0, FLOOR_Z - 0.05), (GANG_W, b1, FLOOR_Z)))
    xw = x_out(FLOOR_Z + 0.4) - WALL_T
    for i, (y0, y1, prio, wc) in enumerate(bays(cab)):
        for sg, sd in ((1.0, "P"), (-1.0, "N")):
            if wc == sg:
                continue
            x0, x1 = sorted((sg * xw, sg * (xw - SEAT_D)))
            out.append(("COL_bench_%s%d" % (sd, i), (x0, y0 + 0.02, FLOOR_Z), (x1, y1 - 0.02, FLOOR_Z + SEAT_H)))
    return out


def add_markers(coll, cab):
    """COL_ / DOORCOL_ boxes (empty cubes, scale = half size) and LIGHT_ points (where the game hangs a light) --
    in the .blend so an artist sees and moves them; the export reads them back."""
    for name, lo, hi in collider_boxes(cab):
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "CUBE"
        e.location = tuple((a + b) / 2 for a, b in zip(lo, hi))
        e.scale = tuple(max(0.005, (b - a) / 2) for a, b in zip(lo, hi))
        coll.objects.link(e)
    half = BODY_L / 2.0
    for k, y in enumerate((-half * 0.5, half * 0.5 - (CAB_D / 2 if cab else 0.0))):
        e = bpy.data.objects.new("LIGHT_%d" % k, None)
        e.empty_display_type = "SPHERE"
        e.empty_display_size = 0.2
        e.location = (0.0, y, CEIL_Z - 0.15)
        coll.objects.link(e)


def build_car(name, cab, pantograph):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    obs = [body(cab).done(coll), interior(cab).done(coll), underframe(pantograph).done(coll), bogies().done(coll)]
    obs += door_leaves(coll)
    add_markers(coll, cab)
    # object names are global in a .blend: every car's objects carry its own prefix (`Tc_Door_P0a`, `M_COL_floor`)
    pre = name.split("_", 1)[1] + "_"
    for ob in list(coll.objects):
        ob.name = pre + ob.name.split(".")[0]
        if ob.data is not None:
            ob.data.name = ob.name
    return coll, obs


def godot_box(ob):
    """A COL_ empty -> [cx, cy, cz, sx, sy, sz] in the GODOT car frame ((x, y, z) -> (x, z, -y))."""
    c, h = ob.location, ob.scale
    return [round(c.x, 4), round(c.z, 4), round(-c.y, 4), round(2 * h.x, 4), round(2 * h.z, 4), round(2 * h.y, 4)]


def car_facts(coll):
    """What the game reads per car: colliders, doors (their leaves and how each slides), light points. Names are read
    without the car's prefix; a leaf's `node` is its full name (the glTF node the game looks up)."""
    cols, doors, lights = [], {}, []

    def base(ob):
        return ob.name.split("_", 1)[1] if "_" in ob.name else ob.name
    for ob in coll.objects:
        n = base(ob)
        if ob.type == "EMPTY" and n.startswith("COL_"):
            cols.append(godot_box(ob))
        elif ob.type == "EMPTY" and n.startswith("DOORCOL_"):
            key = n[len("DOORCOL_"):]
            doors.setdefault(key, {})["box"] = godot_box(ob)
        elif ob.type == "EMPTY" and n.startswith("LIGHT_"):
            lights.append([round(ob.location.x, 3), round(ob.location.z, 3), round(-ob.location.y, 3)])
    for ob in coll.objects:
        n = base(ob)
        if ob.type == "MESH" and n.startswith("Door_"):
            key, leaf = n[len("Door_"):-1], n[-1]
            # leaf a opens toward Blender -Y = Godot +Z, leaf b the other way
            dz = DOOR_OPEN if leaf == "a" else -DOOR_OPEN
            doors.setdefault(key, {}).setdefault("leaves", []).append({"node": ob.name, "slide": [0.0, 0.0, dz]})
    out = []
    for key in sorted(doors):
        d = doors[key]
        if "box" not in d:
            continue
        d["name"] = key
        d["side"] = 1 if key.startswith("P") else -1
        d.setdefault("leaves", []).sort(key=lambda l: l["node"])
        out.append(d)
    cols.sort()
    return {"colliders": cols, "doors": out, "lights": lights}


def measure(obs):
    """Every number the gauge / platform checks need, off the built vertices (not the constants above)."""
    xs, ys, zs = [], [], []
    for ob in obs:
        for v in ob.data.vertices:
            xs.append(v.co.x)
            ys.append(v.co.y)
            zs.append(v.co.z)
    body_ob = obs[0]
    bx = [abs(v.co.x) for v in body_ob.data.vertices]
    return {"half_width": round(max(abs(x) for x in xs), 4), "body_half_width": round(max(bx), 4),
            "length": round(max(ys) - min(ys), 3), "height": round(max(zs), 3), "bottom": round(min(zs), 3)}


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(BLEND) and not force:
        # the .blend is the owner once it exists: export what is there, never rebuild it over an artist's edit
        bpy.ops.wm.open_mainfile(filepath=BLEND)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_car("EMU1_Tc", cab=True, pantograph=False)
        build_car("EMU1_M", cab=False, pantograph=True)
        bpy.data.collections["EMU1_M"].hide_render = False
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    facts = {"id": "EMU1", "gauge_m": GAUGE, "body_length_m": BODY_L, "coupled_length_m": COUPLED_L,
             "bogie_centres_m": 2 * BOGIE_C, "wheelbase_m": WHEELBASE, "floor_m": FLOOR_Z,
             "profile": [[x, z] for x, z in PROFILE], "door_y_m": list(DOOR_Y), "door_w_m": DOOR_W,
             "door_h_m": DOOR_H, "door_open_m": DOOR_OPEN, "ceiling_m": CEIL_Z, "cars": {}}
    for cname in ("EMU1_Tc", "EMU1_M"):
        coll = bpy.data.collections[cname]
        obs = sorted((o for o in coll.objects if o.type == "MESH"), key=lambda o: (not o.name.endswith("_Body"), o.name))
        facts["cars"][cname] = measure([o for o in obs if "_Door_" not in o.name and not o.name.endswith("_Interior")])
        facts["cars"][cname].update(car_facts(coll))
        for o in bpy.context.scene.objects:
            o.select_set(False)
        for o in obs:
            o.select_set(True)
        path = os.path.join(OUT, cname + ".glb")
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                                  export_apply=True)
        print("[make_train] %s -> %s %s" % (cname, os.path.relpath(path, ROOT), facts["cars"][cname]))
    # the whole envelope the checks use: the widest point of any car, over the rail head
    facts["half_width_m"] = max(c["half_width"] for c in facts["cars"].values())
    facts["height_m"] = max(c["height"] for c in facts["cars"].values())
    with open(os.path.join(OUT, "EMU1.train.json"), "w") as fh:
        json.dump(facts, fh, indent=1)
        fh.write("\n")
    print("[make_train] EMU1: half width %.3f m, height %.3f m" % (facts["half_width_m"], facts["height_m"]))


main()
