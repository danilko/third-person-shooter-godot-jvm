"""S17: a crop picture -- land (Godot Y) shaded with height bands, roads as polylines, optional overlays. PIL only.
python3 tools/scratch/s17/cape_pic.py <out.png> [--land f32] [--box x0,y0,x1,y1] [--k px_per_m]
   [--line name:colour:width:file.json(stations)] ... [--rec record.json] [--poly colour:x,y;x,y;...] [--title t]"""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "blender/addons/road_kit_authoring"), os.path.join(ROOT, "blender/lib")]
sys.dont_write_bytecode = True
import island_reshape as RS

def args(k):
    return [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == k]
def arg(k, d):
    v = args(k)
    return v[0] if v else d
out = sys.argv[1]
H = RS.load(arg("--land", RS.LAND))
x0, y0, x1, y1 = [float(v) for v in arg("--box", "-800,1650,450,2250").split(",")]
K = float(arg("--k", "1.2"))
W, Hh = int((x1 - x0) * K), int((y1 - y0) * K)
TOP = 30
img = Image.new("RGB", (W, Hh + TOP), "white")
px = img.load()
BANDS = [(-1e9, -10, (110, 150, 200)), (-10, -3, (150, 185, 225)), (-3, 0.35, (190, 215, 240)), (0.35, 1.5, (240, 230, 190)),
         (1.5, 3.2, (225, 232, 210)), (3.2, 6, (205, 222, 190)), (6, 12, (185, 210, 170)), (12, 25, (165, 195, 150)),
         (25, 50, (150, 180, 135)), (50, 100, (140, 165, 120)), (100, 200, (150, 150, 120)), (200, 1e9, (170, 160, 140))]
for v in range(Hh):
    y = y1 - v / K
    j = int(round((-y - RS.Z0) / RS.STEP))
    for u in range(W):
        x = x0 + u / K
        i = int(round((x - RS.X0) / RS.STEP))
        h = float(H[j, i]) if (0 <= i < RS.N and 0 <= j < RS.N) else -30
        c = next(b[2] for b in BANDS if b[0] <= h < b[1])
        px[u, v + TOP] = c
d = ImageDraw.Draw(img)
def P(x, y):
    return ((x - x0) * K, (y1 - y) * K + TOP)
for g in range(int(x0 // 50) * 50, int(x1) + 1, 50):
    d.line([P(g, y0), P(g, y1)], fill=(200, 200, 200) if g % 250 else (150, 150, 150), width=1)
for g in range(int(y0 // 50) * 50, int(y1) + 1, 50):
    d.line([P(x0, g), P(x1, g)], fill=(200, 200, 200) if g % 250 else (150, 150, 150), width=1)
for g in range(int(x0 // 250) * 250, int(x1) + 1, 250):
    d.text(P(g + 2, y1 - 2), str(g), fill=(80, 80, 80))
for g in range(int(y0 // 250) * 250, int(y1) + 1, 250):
    d.text(P(x0 + 2, g), str(g), fill=(80, 80, 80))
COL = {"red": (220, 30, 30), "orange": (240, 140, 0), "magenta": (200, 0, 200), "blue": (20, 60, 220), "black": (0, 0, 0),
       "grey": (110, 110, 110), "green": (0, 140, 0), "cyan": (0, 170, 190)}
if arg("--rec", None):
    import point_model as pm, point_solve as ps
    net = pm.load_network(arg("--rec", None))
    for name, solves in ps.solve_network(net).items():
        for s in solves:
            pts = [P(sm.pos[0], sm.pos[1]) for sm in s.samples]
            w = max(1, int(2 * (s.values[0]["rka_halfw"]) * K))
            col = (90, 90, 90) if "touge" not in name else (240, 140, 0)
            if name.startswith("kaigan"):
                col = (220, 30, 30)
            d.line(pts, fill=col, width=w)
for spec in args("--line"):
    name, col, w, f = spec.split(":", 3)
    st = json.load(open(f))["stations"]
    d.line([P(p[0], p[1]) for p in st], fill=COL[col], width=int(w))
for spec in args("--poly"):
    col, pts = spec.split(":", 1)
    q = [P(*map(float, a.split(","))) for a in pts.split(";")]
    d.line(q + [q[0]], fill=COL[col], width=2)
for spec in args("--path"):
    col, pts = spec.split(":", 1)
    q = [P(*map(float, a.split(","))) for a in pts.split(";")]
    d.line(q, fill=COL[col], width=3)
d.text((6, 8), arg("--title", "north cape -- record frame, 50 m grid; bands: Godot Y"), fill=(0, 0, 0))
img.save(out)
print("wrote", out, img.size)
