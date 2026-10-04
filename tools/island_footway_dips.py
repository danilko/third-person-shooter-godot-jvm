#!/usr/bin/env python3
"""The footway-edge dip scan (2026-10-04): at every at-grade footway back edge with block ground behind it, how far
the surface a player walks on (terrain, or an edge apron where one lies) dips under the block ground's level.

    python3 tools/island_footway_dips.py <heights.f32>    (dump_height_grid.gd -- <out> -2304 -2304 2305 2305 2)
"""
import sys, math, json
import numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import island_ground as G
ib = G.load_record()[0]
H = np.fromfile(sys.argv[1], dtype='<f4').reshape(G.N, G.N)
def h(x, z):
    fi, fj = (x + G.HALF) / G.STEP, (z + G.HALF) / G.STEP
    i, j = int(math.floor(fi)), int(math.floor(fj))
    if not (0 <= i < G.N - 1 and 0 <= j < G.N - 1): return float('nan')
    u, v = fi - i, fj - j
    return float(H[j, i]*(1-u)*(1-v) + H[j, i+1]*u*(1-v) + H[j+1, i]*(1-u)*v + H[j+1, i+1]*u*v)
aprons = json.load(open(G.APRONS))['aprons']
bk = {}
for k, (x, top, z, yaw, L, W) in enumerate(aprons):
    bk.setdefault((int(x // 20), int(z // 20)), []).append(k)
def apron_top(x, z):
    best = -1e9
    for gx in (-1, 0, 1):
        for gz in (-1, 0, 1):
            for k in bk.get((int(x // 20) + gx, int(z // 20) + gz), ()):
                ax, top, az, yaw, L, W = aprons[k]
                a = math.radians(yaw); ux, uz = math.cos(a), -math.sin(a)
                dx, dz = x - ax, z - az
                if abs(dx*ux + dz*uz) <= L/2 and abs(-dx*uz + dz*ux) <= W/2: best = max(best, top)
    return best
net, grid, cors = ib.solve_bands()
ny = G.network_y(open(ib.SCENE).read())
dips = []
for line, _h, owner in cors:
    owner = str(owner)
    if owner.startswith(("JCT:", "GORE:", "shuto_")): continue
    walk, _l = ib.road_walk(net, owner)
    if walk <= 0: continue
    for a, b in zip(line, line[1:]):
        if ib.elevated(a[2], grid(a[0], a[1])) or ib.elevated(b[2], grid(b[0], b[1])): continue
        dx, dy = b[0]-a[0], b[1]-a[1]; L = math.hypot(dx, dy)
        if L < 1e-6: continue
        nx, nyy = -dy/L, dx/L
        k = 1.0
        while k < L:
            t = k/L; x, y, z = a[0]+dx*t, a[1]+dy*t, a[2]+(b[2]-a[2])*t
            half = a[3]+(b[3]-a[3])*t
            top = z + ny + ib.KERB_H; lot = top + ib.LOT_RAISE
            for s in (1.0, -1.0):
                at = lambda d: (x + s*nx*d, -(y + s*nyy*d))
                edge = half + walk
                if abs(h(*at(edge+3.0)) - lot) > 0.03: continue
                surf = min(max(h(*at(edge+d)), apron_top(*at(edge+d))) for d in (0.2, 0.7, 1.2, 1.7))
                dips.append(lot - surf)
            k += 2.0
d = np.array(dips)
print("edges %d; dip > 10 cm %.2f %%, > 5 cm %.2f %%; 1%% worst %.3f m; worst %.3f m; poke (surface above lot by >2 cm) %.2f %%"
      % (len(d), 100*np.mean(d > 0.10), 100*np.mean(d > 0.05), np.quantile(d, 0.99), d.max(), 100*np.mean(d < -0.02)))
