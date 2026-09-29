"""The small building DSL behind blender/tools/interior_plans.py (user, 2026-09-28: detailed mission buildings -- an
office, police, fire, hospital, a resort hotel, a warehouse yard -- authored in Blender, one .blend per building).

Frame (every library / kit piece's): Blender metres, Z up, the building's origin on the ground at its PLOT centre, the
STREET toward -Y. What it makes, per building, is ONE piece collection holding:

* mesh objects by group (`Structure` slabs and columns, `Walls_F<n>` per floor, `Facade`, `Glazing`, `Stairs`,
  `Roof`, `Site` paving) -- plain boxes in the library palette (`MI_*`), a PLACEHOLDER an artist remodels;
* furniture: copies of library pieces (shared meshes; `Make Single User` to change one);
* Empties the game reads (export_building_kit.py): `DOOR_` interior doors, `EXIT_` outer doors, `LIFT_` lifts
  (world.Elevator: every stop, its door face), `MARK_` mission markers (a weapon spot, a spawn point).

Rules taken from Japanese practice, stated where used: a stair riser <= 0.19 m and tread 0.27 m (建築基準法 public
buildings: riser <= 0.20, tread >= 0.24), a flight 1.25 m wide (>= 1.2 for an evacuation stair); a door 0.9 x 2.1 m
(a hospital room 1.2 m, for a bed); a floor-to-floor of 3.8-4.5 m for public buildings (PLATEAU h/storey p50 3.7-4.0).
"""
import math
import os

import bpy
import mathutils

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "assets", "world_source", "kits", "library", "library.blend")

RISER_MAX = 0.19
TREAD = 0.27
STAIR_NEAR = 1.4          # the landing at each floor, in front of the first step
DOOR_W, DOOR_H = 0.9, 2.1
SLAB_T = 0.2
DOOR_CLEAR = 1.1          # nothing may stand this deep in front of / behind a doorway (the capsule is 0.7 m)


class Opening:
    def __init__(self, u0, u1, z0, z1, glass=None, frame=None):
        self.u0, self.u1, self.z0, self.z1, self.glass, self.frame = u0, u1, z0, z1, glass, frame


class Bld:
    """One building. `Builder` is library_procedural.Builder, `material` library_palette.material."""

    def __init__(self, name, Builder, material):
        self.name = name
        self.Builder = Builder
        self.material = material
        self.groups = {}
        self.objs = []          # (piece, x, y, z, rot_deg, collide_note)
        self.empties = []       # (name, kind, loc, rot_z_deg, props)
        self.doorways = []      # (x, y, z, out (dx, dy), w, label) for the clearance check
        self.counts = {}

    # ── primitives ──────────────────────────────────────────────────────────────────────────────────────────────
    def g(self, group):
        if group not in self.groups:
            self.groups[group] = self.Builder(self.name + "_" + group, self.material)
        return self.groups[group]

    def box(self, group, lo, hi, mat):
        if hi[0] - lo[0] < 1e-4 or hi[1] - lo[1] < 1e-4 or hi[2] - lo[2] < 1e-4:
            return
        self.g(group).box(lo, hi, mat)

    def _n(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return "%s%02d" % (prefix, self.counts[prefix])

    # ── slabs ───────────────────────────────────────────────────────────────────────────────────────────────────
    def slab(self, x0, y0, x1, y1, z_top, mat="MI_Terrazzo", holes=(), t=SLAB_T, group="Structure", under=None):
        """A floor slab, top at z_top, minus rectangular holes (a stair well, a lift shaft)."""
        xs = sorted({x0, x1} | {h[0] for h in holes if x0 < h[0] < x1} | {h[2] for h in holes if x0 < h[2] < x1})
        ys = sorted({y0, y1} | {h[1] for h in holes if y0 < h[1] < y1} | {h[3] for h in holes if y0 < h[3] < y1})
        for i in range(len(xs) - 1):
            run = None
            for j in range(len(ys) - 1):
                cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
                hole = any(h[0] <= cx <= h[2] and h[1] <= cy <= h[3] for h in holes)
                if not hole:
                    run = (run[0], ys[j + 1]) if run else (ys[j], ys[j + 1])
                elif run:
                    self.box(group, (xs[i], run[0], z_top - t), (xs[i + 1], run[1], z_top), mat)
                    run = None
            if run:
                self.box(group, (xs[i], run[0], z_top - t), (xs[i + 1], run[1], z_top), mat)
        if under:
            pass

    # ── walls ───────────────────────────────────────────────────────────────────────────────────────────────────
    def wall(self, axis, c, a0, a1, z0, h, t=0.15, mat="MI_Plaster", mat_out=None, out_sign=1, ops=(),
             group=None):
        """A wall along `axis` ('x': from x=a0 to a1 at y=c; 'y': from y=a0 to a1 at x=c), from z0 up h, `t` thick
        centred on c. `mat_out` = a facade material on the OUT side (out_sign +1 = the +Y / +X side). Openings
        (Opening, u along the wall, z absolute) are cut through; one with `glass` gets a pane in its middle."""
        group = group or "Walls"
        z1 = z0 + h
        us = sorted({a0, a1} | {max(a0, min(a1, o.u0)) for o in ops} | {max(a0, min(a1, o.u1)) for o in ops})
        layers = [(-t / 2, t / 2, mat)] if not mat_out else (
            [(-t / 2, 0.0, mat), (0.0, t / 2, mat_out)] if out_sign > 0 else [(-t / 2, 0.0, mat_out), (0.0, t / 2, mat)])

        def seg(u0, u1, za, zb):
            for d0, d1, m in layers:
                if axis == "x":
                    self.box(group, (u0, c + d0, za), (u1, c + d1, zb), m)
                else:
                    self.box(group, (c + d0, u0, za), (c + d1, u1, zb), m)

        for i in range(len(us) - 1):
            u0, u1 = us[i], us[i + 1]
            um = (u0 + u1) / 2
            cut = [o for o in ops if o.u0 <= um <= o.u1]
            if not cut:
                seg(u0, u1, z0, z1)
                continue
            o = cut[0]
            seg(u0, u1, z0, max(z0, o.z0))
            seg(u0, u1, min(z1, o.z1), z1)
            if o.glass:
                if axis == "x":
                    self.box("Glazing", (u0, c - 0.012, o.z0), (u1, c + 0.012, o.z1), o.glass)
                else:
                    self.box("Glazing", (c - 0.012, u0, o.z0), (c + 0.012, u1, o.z1), o.glass)
        for o in ops:
            if o.frame:                                           # a window / door frame: a thin surround
                f = 0.05
                for (lo, hi) in (((o.u0 - f, o.z0 - f), (o.u0, o.z1 + f)), ((o.u1, o.z0 - f), (o.u1 + f, o.z1 + f)),
                                 ((o.u0, o.z1), (o.u1, o.z1 + f)), ((o.u0, o.z0 - f), (o.u1, o.z0))):
                    if axis == "x":
                        self.box("Glazing", (lo[0], c - t / 2 - 0.01, lo[1]), (hi[0], c + t / 2 + 0.01, hi[1]), o.frame)
                    else:
                        self.box("Glazing", (c - t / 2 - 0.01, lo[0], lo[1]), (c + t / 2 + 0.01, hi[0], hi[1]), o.frame)

    # ── doors (the wall's opening + the Empty the game reads) ──────────────────────────────────────────────────
    def door(self, axis, c, u, z, out, w=DOOR_W, h=DOOR_H, style="swing", sdir=1.0, exit=False, label=""):
        """A doorway at u along a wall (axis/c as `wall`), floor z. `out` = +1 / -1: the arrow (the way OUT of the room,
        or out of the building for an EXIT_) points to +Y/+X or -Y/-X. Returns the Opening to pass to `wall`."""
        if axis == "x":
            loc, d = (u, c, z), (0.0, float(out))
        else:
            loc, d = (c, u, z), (float(out), 0.0)
        props = {"w": float(w), "h": float(h), "style": style, "slide_dir": float(sdir)}
        self.empties.append((self._n("EXIT_" if exit else "DOOR_"), "arrow", loc, d, props))
        self.doorways.append((loc, d, w, label or ("exit" if exit else "door")))
        return Opening(u - w / 2, u + w / 2, z, z + h, frame="MI_PaintedMetal" if exit else None)

    def window(self, u, z, w, sill=0.9, head=2.2, glass="MI_GlassClear"):
        return Opening(u - w / 2, u + w / 2, z + sill, z + head, glass=glass, frame="MI_PaintedMetal")

    def windows(self, a0, a1, z, every=3.6, w=1.8, sill=0.9, head=2.3, skip=(), glass="MI_GlassClear"):
        """Punched windows every `every` m along a wall from a0 to a1, missing any within 1.2 m of a `skip` u."""
        out = []
        n = max(1, int((a1 - a0) / every))
        for i in range(n):
            u = a0 + (a1 - a0) * (i + 0.5) / n
            if any(abs(u - s) < (w / 2 + 0.8) for s in skip):
                continue
            out.append(self.window(u, z, w, sill, head, glass))
        return out

    # ── furniture and markers ──────────────────────────────────────────────────────────────────────────────────
    def put(self, piece, x, y, rot=0.0, z=0.0, repeat=(1, 0.0, 0.0)):
        n, dx, dy = repeat
        for k in range(int(n)):
            self.objs.append((piece, x + dx * k, y + dy * k, z, float(rot)))

    def mark(self, kind, x, y, z=0.0, rot=0.0, **props):
        props = dict(props, kind=kind)
        self.empties.append((self._n("MARK_%s_" % kind), "mark", (x, y, z), rot, props))

    # ── stairs ──────────────────────────────────────────────────────────────────────────────────────────────────
    def ustair(self, x0, y0, x1, y1, z0, rise, near="s", mat="MI_ConcreteSmooth", nosing="MI_PaintedMetalDark",
               cap=False):
        """A U-return stair (折り返し階段) filling the well x0..x1 / y0..y1 from floor z0 up `rise`: a landing at the
        `near` side ('s' = -Y, 'n', 'w' = -X, 'e'), flight A up the left half away from it, a half landing at the far
        end, flight B back up the right half to the next floor's near landing. Returns the hole to cut in the slab
        above (everything but the near strip)."""
        n = int(math.ceil(rise / RISER_MAX))
        n += n % 2
        r = rise / n
        k = n // 2
        horiz = near in ("s", "n")
        W = (x1 - x0) if horiz else (y1 - y0)
        L = (y1 - y0) if horiz else (x1 - x0)
        mid = L - STAIR_NEAR - k * TREAD
        if mid < 1.15:
            raise SystemExit("%s: stair well %.2f m long is short of %.2f (%d risers)" % (
                self.name, L, STAIR_NEAR + k * TREAD + 1.15, n))

        def to_world(u0, v0, u1, v1):
            if near == "s":
                return x0 + u0, y0 + v0, x0 + u1, y0 + v1
            if near == "n":
                return x1 - u1, y1 - v1, x1 - u0, y1 - v0
            if near == "w":
                return x0 + v0, y1 - u1, x0 + v1, y1 - u0
            return x1 - v1, y0 + u0, x1 - v0, y0 + u1

        def put_box(u0, v0, u1, v1, za, zb, m):
            a, b, c, d = to_world(u0, v0, u1, v1)
            self.box("Stairs", (a, b, za), (c, d, zb), m)

        half = W / 2
        for i in range(k):                                   # flight A (left half), up away from the near side
            top = z0 + (i + 1) * r
            v0 = STAIR_NEAR + i * TREAD
            put_box(0.0, v0, half - 0.06, v0 + TREAD, max(z0, top - r - 0.25), top, mat)
            put_box(0.0, v0, half - 0.06, v0 + 0.04, top - 0.02, top + 0.005, nosing)
        zm = z0 + k * r
        put_box(0.0, STAIR_NEAR + k * TREAD, W, L, zm - SLAB_T, zm, mat)          # the half landing
        for j in range(k):                                   # flight B (right half), back toward the near side
            top = zm + (j + 1) * r
            v1 = STAIR_NEAR + k * TREAD - j * TREAD
            put_box(half + 0.06, v1 - TREAD, W, v1, top - r - 0.25, top, mat)
            put_box(half + 0.06, v1 - 0.04, W, v1, top - 0.02, top + 0.005, nosing)
        put_box(half - 0.06, STAIR_NEAR, half + 0.06, STAIR_NEAR + k * TREAD, z0, z0 + rise + 1.0, "MI_Plaster")
        if cap:           # the top floor, no flight above: a 1.1 m guard over flight A's drop at the landing's edge
            put_box(0.0, STAIR_NEAR - 0.06, half + 0.06, STAIR_NEAR + 0.06, z0 + rise, z0 + rise + 1.1, "MI_Plaster")
        return to_world(0.0, STAIR_NEAR, W, L)

    # ── lifts ───────────────────────────────────────────────────────────────────────────────────────────────────
    def lift(self, cx, cy, w, d, stops, faces=1, door_w=0.9, door_h=2.1, turned=False, t=0.15,
             mat="MI_ConcreteSmooth", head=3.2):
        """A lift shaft (inside w along the door axis, d across) whose car's floor is at each of `stops` (absolute z),
        doors on its -local-X face (faces 1), +X (2) or both (3); `turned` puts the door axis along Y (a door on -Y for
        faces 1). The walls are here (with a landing opening at each stop); the car, its doors and the landing doors
        are world.Elevator's, built at runtime from the LIFT_ Empty. Returns the hole to cut in every slab above the
        bottom stop."""
        z_lo, z_hi = stops[0] - 1.2, stops[-1] + head
        rise = stops[-1] - stops[0]
        hx, hy = (d / 2, w / 2) if turned else (w / 2, d / 2)
        for sgn in (-1, 1):
            face_bit = 1 if sgn < 0 else 2
            has_door = bool(faces & face_bit)
            ops = [Opening(-door_w / 2, door_w / 2, s, s + door_h) for s in stops] if has_door else []
            if turned:        # the door faces are the walls at y = cy +- w/2, running along X
                self.wall("x", cy + sgn * (hy + t / 2), cx - hx - t, cx + hx + t, z_lo, z_hi - z_lo, t, mat,
                          ops=[Opening(cx + o.u0, cx + o.u1, o.z0, o.z1) for o in ops], group="Shafts")
                self.wall("y", cx + sgn * (hx + t / 2), cy - hy, cy + hy, z_lo, z_hi - z_lo, t, mat, group="Shafts")
            else:
                self.wall("y", cx + sgn * (hx + t / 2), cy - hy - t, cy + hy + t, z_lo, z_hi - z_lo, t, mat,
                          ops=[Opening(cy + o.u0, cy + o.u1, o.z0, o.z1) for o in ops], group="Shafts")
                self.wall("x", cy + sgn * (hy + t / 2), cx - hx, cx + hx, z_lo, z_hi - z_lo, t, mat, group="Shafts")
        self.box("Shafts", (cx - hx, cy - hy, z_lo), (cx + hx, cy + hy, z_lo + 0.05), mat)          # the pit floor
        self.box("Shafts", (cx - hx - t, cy - hy - t, z_hi), (cx + hx + t, cy + hy + t, z_hi + 0.25), mat)
        props = {"w": float(w), "d": float(d), "rise": float(rise), "door_w": float(door_w), "door_h": float(door_h),
                 "stops": ",".join("%g" % round(s - stops[0], 4) for s in stops), "faces": int(faces)}
        self.empties.append((self._n("LIFT_"), "lift", (cx, cy, stops[0]), 90.0 if turned else 0.0, props))
        for s in stops:                                        # each landing door is a doorway for the clearance check
            for sgn in (-1, 1):
                if faces & (1 if sgn < 0 else 2):
                    if turned:
                        self.doorways.append(((cx, cy + sgn * (hy + t / 2), s), (0.0, float(sgn)), door_w, "lift"))
                    else:
                        self.doorways.append(((cx + sgn * (hx + t / 2), cy, s), (float(sgn), 0.0), door_w, "lift"))
        return (cx - hx - t, cy - hy - t, cx + hx + t, cy + hy + t)

    # ── roof ────────────────────────────────────────────────────────────────────────────────────────────────────
    def parapet(self, x0, y0, x1, y1, z, h=1.1, t=0.2, mat="MI_ConcreteSmooth"):
        self.box("Roof", (x0, y0, z), (x1, y0 + t, z + h), mat)
        self.box("Roof", (x0, y1 - t, z), (x1, y1, z + h), mat)
        self.box("Roof", (x0, y0, z), (x0 + t, y1, z + h), mat)
        self.box("Roof", (x1 - t, y0, z), (x1, y1, z + h), mat)

    # ── install ─────────────────────────────────────────────────────────────────────────────────────────────────
    def footprint(self, piece, meshes, x, y, rot):
        me = meshes[piece]
        vs = [v.co for v in me.vertices]
        if not vs:
            return None
        a = math.radians(rot)
        c, s = math.cos(a), math.sin(a)
        pts = [(x + v.x * c - v.y * s, y + v.x * s + v.y * c) for v in vs]
        zs = [v.z for v in vs]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts),
                min(zs), max(zs))

    def check_doorways(self, meshes, skip=("Hosp_Curtain",)):
        """Nothing a `put` placed stands in the 1.1 m in front of or behind any doorway (the capsule's corridor)."""
        bad = []
        for (dx, dy, dz), (ox, oy), w, label in self.doorways:
            for sgn in (1, -1):
                ax0 = dx + (ox * sgn * 0.15 if ox else -w / 2 + 0.1)
                ay0 = dy + (oy * sgn * 0.15 if oy else -w / 2 + 0.1)
                ax1 = dx + (ox * sgn * DOOR_CLEAR if ox else w / 2 - 0.1)
                ay1 = dy + (oy * sgn * DOOR_CLEAR if oy else w / 2 - 0.1)
                zx0, zx1 = min(ax0, ax1), max(ax0, ax1)
                zy0, zy1 = min(ay0, ay1), max(ay0, ay1)
                for piece, x, y, z, rot in self.objs:
                    if piece in skip:
                        continue
                    fp = self.footprint(piece, meshes, x, y, rot)
                    if fp is None or z + fp[4] > dz + 1.8 or z + fp[5] < dz + 0.1:
                        continue
                    if fp[0] < zx1 and fp[2] > zx0 and fp[1] < zy1 and fp[3] > zy0:
                        bad.append("%s %s at (%.2f, %.2f, %.2f): %s at (%.2f, %.2f) stands %s it" % (
                            self.name, label, dx, dy, dz, piece, x, y, "in front of" if sgn > 0 else "behind"))
        if bad:
            raise SystemExit("\n".join(bad))

    def install(self, col, meshes):
        for gname, b in self.groups.items():
            me = b.mesh()
            o = bpy.data.objects.new(gname, me)
            col.objects.link(o)
        for piece, x, y, z, rot in self.objs:
            o = bpy.data.objects.new(piece, meshes[piece])
            o.location = (x, y, z)
            o.rotation_euler = (0.0, 0.0, math.radians(rot))
            col.objects.link(o)
        for name, kind, loc, rot, props in self.empties:
            e = bpy.data.objects.new(name, None)
            e.location = loc
            if kind == "arrow":
                e.empty_display_type = "SINGLE_ARROW"
                e.empty_display_size = 0.8
                d = rot
                e.rotation_euler = (0.0, math.radians(90.0), math.atan2(d[1], d[0]))
            elif kind == "lift":
                e.empty_display_type = "PLAIN_AXES"
                e.empty_display_size = 1.0
                e.rotation_euler = (0.0, 0.0, math.radians(rot))
            else:
                e.empty_display_type = "CONE" if props.get("kind") == "weapon" else "SPHERE"
                e.empty_display_size = 0.3
                e.rotation_euler = (0.0, 0.0, math.radians(rot))
            for k, v in props.items():
                e[k] = v
            e.hide_render = True
            col.objects.link(e)


def library_meshes(names):
    """{piece: mesh} copied from library.blend (each piece is a collection holding one object), shared per piece."""
    import re
    have = {n: bpy.data.meshes.get("LIB_" + n) for n in names}
    want = [n for n, m in have.items() if m is None]
    if want:
        with bpy.data.libraries.load(LIB, link=False) as (src, dst):
            dst.collections = [n for n in want if n in src.collections]
        for col in dst.collections:
            if col is None:
                continue
            obj = col.objects[0]
            me = obj.data
            me.name = "LIB_" + col.name
            have[col.name] = me
            for o in list(col.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(col)
    for m in list(bpy.data.materials):
        base = re.sub(r"\.\d{3}$", "", m.name)
        if base != m.name:
            keep = bpy.data.materials.get(base)
            if keep is None:
                m.name = base
            else:
                m.user_remap(keep)
                bpy.data.materials.remove(m)
    missing = [n for n, m in have.items() if m is None]
    if missing:
        raise SystemExit("interior_kit: not in library.blend: %s" % missing)
    return have
