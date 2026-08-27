#!/usr/bin/env python3
"""
ramp_merge_testbed.py -> blender/_ramp_merge_test.blend

THE SMALLEST SCENE THAT CONTAINS THE PROBLEM: one straight expressway with a wall along its
edges, and one ramp merging into it. Nothing else -- no terrain, no other roads, no interchange.
The island is where these defects are FOUND (it has every awkward case), and the worst possible
place to work them out: a rebuild is minutes, a junction is one of fifty, and every measurement
has to be teased out of a 1,600-edge graph.

It prints the three numbers that say whether a merge is built correctly, so a change can be
judged without opening Blender at all:

  1. IS THE ROAD CONTINUOUS?   the swept ribbon's own gaps, measured along the trunk.
  2. DOES THE RAMP REACH IT?   distance from the ramp's ribbon to the widened carriageway edge.
  3. DOES THE WALL OPEN?       where wall geometry stops and restarts on the merge side, and
                               whether the far side keeps its wall throughout.

RUN:
  blender --background --python blender/tools/ramp_merge_testbed.py
  blender --background --python blender/tools/ramp_merge_testbed.py -- --keep   (leave the .blend)
"""
import bpy, bmesh, os, sys, math
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "addons"))
sys.path.insert(0, os.path.join(ROOT, "lib"))

import road_kit_authoring as rka                            # noqa: E402
from road_kit_authoring import graph_attrs as ga            # noqa: E402
from road_kit_authoring import graph_build as gb            # noqa: E402
from road_kit_authoring import graph_solve as gs            # noqa: E402
from road_kit_authoring import graph_export as gx           # noqa: E402

#: The GENERATED scene. Deliberately a different file from the one you edit by hand: this script
#: rewrites it on every run, and it has already eaten one hand-authored pad that was saved into
#: the path it writes. Copy it to `_ramp_merge_test.blend` (or any name) before editing.
OUT = os.path.join(ROOT, "_ramp_merge_test_gen.blend")

WALL = 1.0          # barrier height along the expressway edge
LANE = 3.5
TAPER = 90.0


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    if not hasattr(bpy.types.Scene, "rka_graph"):
        rka.register()
    # `--outline` builds the kerb/wall from the road surface's boundary instead of by lateral
    # offset from each chain's centreline. Both paths are kept runnable while they are compared:
    # the whole point of the gates below is to say which one puts a wall in a lane.
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    bpy.context.scene.rka_graph.stage_edge_furniture = "--outline" in argv

    # Trunk: straight, west -> east, 2+2 lanes with a median. The ramp merges from the NORTH,
    # which is the kerb side of the eastbound (forward) carriageway under keep-left.
    verts = [(x, 0.0, 0.0) for x in (-600, -400, -200, 0, 200, 400, 600)]
    ramp = [(-520, 150, 0.0), (-380, 96, 0.0), (-240, 52, 0.0), (-110, 22, 0.0)]
    n0 = len(verts)
    verts += ramp
    edges = [(i, i + 1) for i in range(n0 - 1)]
    edges += [(n0 + i, n0 + i + 1) for i in range(len(ramp) - 1)]
    edges.append((n0 + len(ramp) - 1, 3))          # ramp meets the trunk at x = 0

    me = bpy.data.meshes.new("RampTest")
    me.from_pydata(verts, edges, [])
    me.update()
    obj = bpy.data.objects.new("RampTest", me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    ga.ensure_mesh_attributes(me)

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    el = ga.ensure_edge_layers(bm)
    vl = ga.ensure_vert_layers(bm)
    for e in bm.edges:
        is_ramp = e.index >= n0 - 1
        e[el["lane_width"]] = 4.5 if is_ramp else LANE
        e[el["lanes_fwd"]] = 1 if is_ramp else 2
        e[el["lanes_bwd"]] = 0 if is_ramp else 2
        e[el["median_width"]] = 0.0 if is_ramp else 1.2
        e[el["sidewalk_left_width"]] = 0.0
        e[el["sidewalk_right_width"]] = 0.0
        e[el["curb_left_on"]] = 1
        e[el["curb_right_on"]] = 1
        e[el["curb_height"]] = WALL          # the barrier, both sides, trunk and ramp
        e[el["aux_taper_length"]] = TAPER
    for v in bm.verts:                        # a motorway: no crossing anywhere
        v[vl["allow_cross"]] = 0
    bm.to_mesh(me)
    bm.free()
    me.update()

    pre = gs.solve_object(obj)
    bm = bmesh.new()
    bm.from_mesh(me)
    n_aux, wrong = gs.auto_aux_lanes(bm, pre, count=1, taper=TAPER)
    bm.to_mesh(me)
    bm.free()
    me.update()
    print("[testbed] aux chains stamped: %d, offside: %d" % (n_aux, len(wrong)))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    el = ga.ensure_edge_layers(bm, fill_defaults=False)
    print("[testbed] trunk aux (L/R) per edge: %s"
          % [(e.index, int(e[el["aux_lanes_left"]]), int(e[el["aux_lanes_right"]]))
             for e in bm.edges if e.index < 6])
    bm.free()
    result, carrier = gb.build_object(obj)
    # what the carrier actually carries at the merge end of the trunk
    hw = carrier.data.attributes["rka_halfw"]
    hl = carrier.data.attributes["rka_curb_hl"]
    hr = carrier.data.attributes["rka_curb_hr"]
    row = sorted((v.co.x, round(hw.data[i].value, 2), round(hl.data[i].value, 2),
                  round(hr.data[i].value, 2))
                 for i, v in enumerate(carrier.data.vertices) if abs(v.co.y) < 12.0)
    print("[testbed] trunk carrier  x: halfw / wallL / wallR")
    for r in row:
        print("     %7.1f  %5.2f  %4.2f  %4.2f" % r)
    return obj, carrier, result


def report(obj, carrier, result):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = carrier.evaluated_get(dg).to_mesh()
    # WHERE THE FENCE LIVES DEPENDS ON THE BUILD PATH, so the gates must not assume. With the
    # centreline path the barrier is a band on the carrier; with the outline path it is swept on
    # `<graph>_Edges` instead. Every wall measurement below reads the union of the two, so the
    # SAME gate scores both paths and the comparison is like for like.
    edges_obj = bpy.data.objects.get(carrier.name.replace("_Carrier", "_Edges"))
    ev_edges = (edges_obj.evaluated_get(dg).to_mesh()
                if edges_obj is not None and len(edges_obj.data.vertices) else None)
    wall_meshes = [ev] + ([ev_edges] if ev_edges is not None else [])
    road = [v.co for v in ev.vertices if v.co.z < 0.2]        # the carriageway surface
    wall = [v.co for m in wall_meshes for v in m.vertices if v.co.z > WALL * 0.5]

    # 1. the carriageway's northern edge along the trunk, sampled every 20 m
    print("[testbed] carriageway north edge (the merge side), x -> y:")
    row = []
    for x in range(-400, 401, 50):
        near = [v for v in road if abs(v.x - x) < 6.0 and v.y > -40.0]
        row.append((x, max((v.y for v in near), default=float("nan"))))
    print("   " + "  ".join("%d:%.1f" % r for r in row))

    # 2a. the ramp's own carrier points, with the band its profile sweeps around them
    hw = carrier.data.attributes["rka_halfw"]
    sh = carrier.data.attributes["rka_shift"]
    ramp_row = sorted((v.co.x, round(v.co.y, 2), round(hw.data[i].value, 2),
                       round(sh.data[i].value, 2))
                      for i, v in enumerate(carrier.data.vertices)
                      if hw.data[i].value < 4.0)
    print("[testbed] ramp carrier   x, y, halfw, shift  (band = y+shift +/- halfw)")
    for r in ramp_row[-4:]:
        print("     %7.1f  %6.2f  %5.2f  %5.2f   -> band y %.2f .. %.2f"
              % (r[0], r[1], r[2], r[3], r[1] + r[3] - r[2], r[1] + r[3] + r[2]))
    trunk_at_gore = [(v.co.x, round(hw.data[i].value, 2), round(sh.data[i].value, 2))
                     for i, v in enumerate(carrier.data.vertices)
                     if abs(v.co.x) < 1.0 and abs(v.co.y) < 12.0]
    for x, h, sft in trunk_at_gore:
        print("     trunk at gore: halfw %.2f shift %.2f -> band y %.2f .. %.2f"
              % (h, sft, sft - h, sft + h))

    # 2. DOES THE RAMP LAND ON THE LANE? Bands, not vertices: two surfaces meet when their
    # cross-sections overlap, and comparing vertex positions across a sparse polyline reports a
    # gap wherever the two happen not to have a vertex at the same station.
    ramp_end = ramp_row[-1] if ramp_row else None
    trunk_wide = max(trunk_at_gore, key=lambda t: t[1]) if trunk_at_gore else None
    if ramp_end and trunk_wide:
        rlo, rhi = ramp_end[1] + ramp_end[3] - ramp_end[2], ramp_end[1] + ramp_end[3] + ramp_end[2]
        tlo, thi = trunk_wide[2] - trunk_wide[1], trunk_wide[2] + trunk_wide[1]
        overlap = min(rhi, thi) - max(rlo, tlo)
        lane = 3.5
        print("[testbed] ramp band %.2f..%.2f vs carriageway %.2f..%.2f -> overlap %.2f m (%s)"
              % (rlo, rhi, tlo, thi, overlap,
                 "CONNECTED" if overlap >= lane * 0.75 else "GAP -- the ramp does not land on it"))

    # 2b. IS THE PAVED SURFACE CONTINUOUS THROUGH THE MERGE? The only question that matters for
    # "the road connects": sample the merge region and ask whether ANY face covers each point --
    # carriageway, ramp or junction pad, it makes no difference which.
    tris = []
    pads = bpy.data.objects.get(carrier.name.replace("_Carrier", "_Nodes"))
    for src, m in ((carrier, ev), (pads, pads.data if pads else None)):
        if m is None:
            continue
        for poly in m.polygons:
            vs = [m.vertices[i].co for i in poly.vertices]
            if max(v.z for v in vs) > 0.2:          # walls, not road surface
                continue
            for k in range(1, len(vs) - 1):
                a, b, c = vs[0], vs[k], vs[k + 1]
                # DEGENERATE FACES COVER NOTHING, and must not be allowed to claim they do. The
                # barrier collapses to zero height where it opens for the ramp, which leaves
                # zero-area faces lying in the road plane; a same-sign point-in-triangle test
                # reports every point as inside one of those, so the whole check came back clean
                # while there was a visible hole in the pavement.
                area = abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) * 0.5
                if area < 1e-4:
                    continue
                tris.append(((a.x, a.y), (b.x, b.y), (c.x, c.y)))

    def _covered(px, py):
        for a, b, c in tris:
            d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1])
            d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (py - c[1])
            d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (py - a[1])
            neg = d1 < -1e-9 or d2 < -1e-9 or d3 < -1e-9
            pos = d1 > 1e-9 or d2 > 1e-9 or d3 > 1e-9
            if not (neg and pos):
                return True
        return False

    # THE SEAMS, not an area. Whether two swept surfaces MEET is decided along the line where
    # they are supposed to touch: sample it densely and check the pavement is there a few
    # centimetres to either side. Sampling an area instead keeps counting the open ground beyond
    # the gore's outer angle -- which is bare on purpose -- as a hole.
    pad = bpy.data.objects.get(carrier.name.replace("_Carrier", "_Nodes"))
    if pad and len(pad.data.vertices) >= 4:
        ring = [(v.co.x, v.co.y) for v in pad.data.vertices]
        seams = []
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            if math.dist(a, b) > 0.5:
                seams.append((a, b))
        bad = 0, None
        holes = []
        for a, b in seams:
            L = math.dist(a, b)
            steps = max(int(L / 0.1), 2)
            nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L      # unit normal to the seam
            for k in range(steps + 1):
                t = k / steps
                px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if not (_covered(px + nx * 0.05, py + ny * 0.05)
                        and _covered(px - nx * 0.05, py - ny * 0.05)):
                    holes.append((px, py))
        # NOTE the corner noise: where the pad, the upstream road and the downstream road all
        # meet at one point, a sample 5 cm off the seam can fall a millimetre outside all three.
        # Points reported at the pad's own corners are that, not a hole.
        print("[testbed] pad seams: %d of %d sampled points have pavement on both sides%s"
              % (sum(int(math.dist(a, b) / 0.1) + 1 for a, b in seams) - len(holes),
                 sum(int(math.dist(a, b) / 0.1) + 1 for a, b in seams),
                 "" if not holes else "  -- open at " +
                 ", ".join("(%.2f,%.2f)" % h for h in holes[:4])))

    # 3. where the wall opens -- measured as FACE COVERAGE, not vertices. A swept band has
    # vertices only at the polyline's own points (200 m apart on this trunk), so "gaps between
    # wall vertices" says nothing about whether the wall is continuous.
    # A WALL PANEL IS A SEGMENT, NOT A POINT. The ramp's polyline is sparse, so one panel can span
    # a hundred metres of x while its y moves ten -- taking the panel's AVERAGE y and comparing it
    # to the pavement edge at one station then reads as "the wall is 8 m away" everywhere except
    # the panel's middle. Keep both ends and interpolate.
    polys = []
    for m in wall_meshes:
        for poly in m.polygons:
            vs = [m.vertices[i].co for i in poly.vertices]
            if max(v.z for v in vs) > WALL * 0.5:
                lo = min(vs, key=lambda v: v.x)
                hi = max(vs, key=lambda v: v.x)
                polys.append((lo.x, hi.x, sum(v.y for v in vs) / len(vs), lo.y, hi.y))

    def _wall_y(p, x):
        span = p[1] - p[0]
        return p[3] if span < 1e-6 else p[3] + (p[4] - p[3]) * (x - p[0]) / span
    # 3a. DOES A WALL FOLLOW THE OUTSIDE EDGE OF THE PAVEMENT, EVERYWHERE? The band test below
    # cannot answer this: the merge side carries TWO wall lines (the through road's, and the one
    # riding the auxiliary lane once it opens), so a run of one masks a hole in the other. So ask
    # the question directly -- at each station find the outermost paved y from the surface itself,
    # then require a wall within `NEAR` of it. That is "the wall wraps around the ramp" stated as
    # a measurement, and it fails loudly when the wall dives back inboard at the merge.
    NEAR = 2.5
    def _edge_y(px, up):
        y, step, last = (30.0 if up else -30.0), (-0.25 if up else 0.25), None
        for _ in range(240):
            if _covered(px, y):
                last = y
                break
            y += step
        if last is None:
            return None
        while _covered(px, last + (0.05 if up else -0.05)):
            last += (0.05 if up else -0.05)
        return last

    for label, up in (("north (merge side)", True), ("south (far side)", False)):
        miss, checked, worst = [], 0, 0.0
        for x in range(-560, 560, 10):
            ey = _edge_y(float(x), up)
            if ey is None:
                continue
            checked += 1
            near = [p for p in polys
                    if p[0] <= x <= p[1] and abs(_wall_y(p, float(x)) - ey) <= NEAR]
            if near:
                worst = max(worst, min(abs(_wall_y(p, float(x)) - ey) for p in near))
            else:
                miss.append((x, ey))
        print("[testbed] wall follows %-18s %d/%d stations (worst offset %.2f m)%s"
              % (label, checked - len(miss), checked, worst,
                 "" if not miss else "  -- MISSING at " +
                 ", ".join("x=%d (edge y=%.1f)" % m for m in miss[:8])))

    # ATTRIBUTED BY BAND, not by sign: the ramp's own wall shares the merge side's x range, and
    # counting it there masks exactly the hole this is looking for.
    for label, keep in (("north (merge side)", lambda y: 0.0 < y < 11.6),
                        ("south (far side)", lambda y: y < 0.0),
                        ("ramp, both sides", lambda y: y > 11.6)):
        side = [p for p in polys if keep(p[2])]  # p[2] = the panel's average y
        covered, holes, run = 0, [], None
        for x in range(-600, 600, 10):
            hit = any(p[0] <= x + 5 <= p[1] for p in side)
            covered += 1 if hit else 0
            if hit and run is not None:
                holes.append((run, x))
                run = None
            elif not hit and run is None:
                run = x
        if run is not None:
            holes.append((run, 600))
        # A HOLE ON THE MERGE SIDE IS EXPECTED, and is the point of the exercise: the approach
        # carriageway's barrier stops where the corridor between it and the ramp narrows to one
        # lane, so this band is open from there to the nose. What must NOT happen is the wall
        # standing inside that corridor -- gate 3c below is what tests for that.
        print("[testbed] wall %-18s covers %3d%% of the 1200 m, %d hole(s): %s"
              % (label, covered * 100 // 120, len(holes),
                 ", ".join("%d..%d" % h for h in holes[:5])))

    # 3c. NO BARRIER MAY STAND ON SOMEONE ELSE'S ROAD. The direct statement of "an extra wall
    # blocks the ramp entrance", and the guarantee the corridor setback exists to provide.
    #
    # Measured from the CARRIER's own numbers, not from the swept mesh: a kerb box is extruded
    # DOWN to the road surface, so its bottom face is a flat polygon at z=0 and every mesh-face
    # test reports each wall as standing on pavement -- its own. The carrier says exactly where
    # each ribbon's asphalt and each of its barriers are, and the question is whether one chain's
    # barrier lies inside ANOTHER chain's asphalt. A barrier straddling its OWN road edge by half
    # its thickness is a kerb, which is what it is supposed to be.
    # With the outline path the carrier still CARRIES `rka_curb_ol/or` but no longer builds from
    # them, so deriving the barrier from those numbers would score a wall that is not there. Ask
    # the object that actually holds the fence: `_Edges`' vertices ARE the barrier line.
    chains = _carrier_chains(carrier.data)
    offenders = []
    if edges_obj is not None and len(edges_obj.data.vertices):
        samples = [(v.co.x, v.co.y) for v in edges_obj.data.vertices]
        for px, py in samples:
            for cj, other in enumerate(chains):
                if _in_band(other, px, py):
                    offenders.append((-1, cj, px, py))
                    break
    else:
        for ci, ch in enumerate(chains):
            for side in ('L', 'R'):
                for px, py in _kerb_samples(ch, side):
                    for cj, other in enumerate(chains):
                        if cj == ci:
                            continue
                        if _in_band(other, px, py):
                            offenders.append((ci, cj, px, py))
                            break
    print("[testbed] barriers standing on another road's asphalt: %d%s"
          % (len(offenders),
             "" if not offenders else "  -- chain %d's wall inside chain %d at %s"
             % (offenders[0][0], offenders[0][1],
                ", ".join("(%.0f,%.1f)" % (o[2], o[3]) for o in offenders[:6]))))

def _carrier_chains(me):
    """`[[(co, values dict), ...], ...]` -- the carrier's polylines, one list per chain, with each
    point's attributes alongside. The carrier is a plain edge mesh, so the chains are recovered by
    walking adjacency from the degree-1 ends."""
    adj = {}
    for e in me.edges:
        a, b = e.vertices
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    names = [a.name for a in me.attributes if a.name.startswith("rka_")]
    seen, out = set(), []
    for start in [i for i in range(len(me.vertices)) if len(adj.get(i, [])) == 1]:
        if start in seen:
            continue
        seen.add(start)
        run, cur = [start], start
        while True:
            nxt = [n for n in adj[cur] if n not in seen]
            if not nxt:
                break
            cur = nxt[0]
            seen.add(cur)
            run.append(cur)
        out.append([(me.vertices[i].co.copy(),
                     {n: me.attributes[n].data[i].value for n in names}) for i in run])
    return out


def _frame(ch, k):
    """(point, left-normal) at index `k` of a carrier chain."""
    co = ch[k][0]
    nb = ch[k + 1][0] if k + 1 < len(ch) else ch[k - 1][0]
    t = (nb - co) if k + 1 < len(ch) else (co - nb)
    t.z = 0.0
    if t.length < 1e-9:
        return co, Vector((0.0, 1.0, 0.0))
    t.normalize()
    return co, Vector((-t.y, t.x, 0.0))


def _kerb_samples(ch, side, step=2.0):
    """Points along one chain's kerb line, only where that barrier is actually built."""
    ho, oo = ("rka_curb_hl", "rka_curb_ol") if side == 'L' else ("rka_curb_hr", "rka_curb_or")
    out = []
    for k in range(len(ch) - 1):
        if ch[k][1][ho] < 0.5 or ch[k + 1][1][ho] < 0.5:
            continue                       # the barrier ends here -- nothing to test
        (a, na), (b, nb) = _frame(ch, k), _frame(ch, k + 1)
        pa = a + na * ch[k][1][oo]
        pb = b + nb * ch[k + 1][1][oo]
        n = max(int((pb - pa).length / step), 1)
        for i in range(n + 1):
            p = pa.lerp(pb, i / n)
            out.append((p.x, p.y))
    return out


#: How far inside another road's edge a barrier has to be before it counts as standing ON it.
#: Two things legitimately sit right on an edge: a kerb straddles its own road's boundary by half
#: its thickness, and two chains that overlap by `JOIN_OVERSHOOT` share the same wall LINE for
#: those couple of metres. Neither is in anybody's way. A wall that has walked a metre and a half
#: into a live lane is, and clears this comfortably.
BAND_MARGIN = 0.55


def _in_band(ch, px, py, margin=BAND_MARGIN):
    """Is (px, py) inside this chain's swept asphalt, by more than `margin`? Segment by segment."""
    for k in range(len(ch) - 1):
        (a, na), (b, nb) = _frame(ch, k), _frame(ch, k + 1)
        sa = ch[k][1]["rka_shift"]
        sb = ch[k + 1][1]["rka_shift"]
        ha = max(ch[k][1]["rka_halfw"] - margin, 0.0)
        hb = max(ch[k + 1][1]["rka_halfw"] - margin, 0.0)
        quad = [a + na * (sa + ha), b + nb * (sb + hb),
                b + nb * (sb - hb), a + na * (sa - ha)]
        neg = pos = False
        for i in range(4):
            p, q = quad[i], quad[(i + 1) % 4]
            d = (px - p.x) * (q.y - p.y) - (py - p.y) * (q.x - p.x)
            neg |= d < -1e-6
            pos |= d > 1e-6
        if not (neg and pos):
            return True
    return False


def main():
    obj, carrier, result = build()
    report(obj, carrier, result)
    lanes, stats = gx.collect(obj)
    print("[testbed] lanes %d, connectors %d" % (stats["lanes"], stats["connectors"]))
    for line in gx.audit_movements(obj):
        print("   AUDIT: %s" % line)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("[testbed] wrote %s  (regenerated every run -- copy it before hand-editing)" % OUT)


if __name__ == "__main__":
    main()
