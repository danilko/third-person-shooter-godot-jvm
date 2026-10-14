"""The fish market AS DERIVED: python3 tools/scratch/market_p12/built.py [record] [land grid] [out.svg]
(run from the repo root; then `magick -density 96 out.svg out.png`). Unlike p12.py (a proposal drawn from round-6
numbers), every road here is the record's own solved centreline and the land is the height grid."""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
sys.path.insert(0, ROOT + "/blender/lib")
import point_profile as pp
import island_dike as ID
rec = sys.argv[1] if len(sys.argv) > 1 else P + "IslandRoads.roads.json"
gridf = sys.argv[2] if len(sys.argv) > 2 else ROOT + "/assets/world_source/terrain/island_natural.f32"
outf = sys.argv[3] if len(sys.argv) > 3 else ROOT + "/docs/previews/market_built_plan.svg"
BX, BZ, K = (215, 885), (630, 870), 2.0
PAD, HEAD = 20, 70
W, Hh = (BX[1] - BX[0]) * K + 2 * PAD, (BZ[1] - BZ[0]) * K + HEAD + 150
def XY(x, z): return (PAD + (x - BX[0]) * K, HEAD + (z - BZ[0]) * K)
o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="DejaVu Sans, sans-serif"><rect width="100%%" height="100%%" fill="#fff"/>' % (W, Hh)]
o.append('<text x="%d" y="26" font-size="18" font-weight="bold">Fish market on its low quay, as derived: the road record and the land grid (not a sketch)</text>' % PAD)
o.append('<text x="%d" y="46" font-size="12" fill="#444">North up, 50 m grid. Roads are drawn at their own width on their solved centrelines; purple = expressway deck, pink = its ramps.</text>' % PAD)
o.append('<defs><clipPath id="frame"><rect x="%d" y="%d" width="%d" height="%d"/></clipPath></defs><g clip-path="url(#frame)">' % (PAD, HEAD, (BX[1] - BX[0]) * K, (BZ[1] - BZ[0]) * K))
g = np.fromfile(gridf, dtype="<f4").reshape(2305, 2305)
S = 4
for z in range(BZ[0], BZ[1], S):
    x = BX[0]
    while x < BX[1]:
        h = float(g[(z + 2304) // 2, (x + 2304) // 2])
        c = "#bcd9ea" if h < 0.35 else ("#e3e6dc" if h < 6.2 else ("#d9cfae" if h < 11.0 else "#c9b98a"))
        x1 = x
        while x1 < BX[1]:
            h1 = float(g[(z + 2304) // 2, (x1 + 2304) // 2])
            c1 = "#bcd9ea" if h1 < 0.35 else ("#e3e6dc" if h1 < 6.2 else ("#d9cfae" if h1 < 11.0 else "#c9b98a"))
            if c1 != c: break
            x1 += S
        a = XY(x, z)
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (a[0], a[1], (x1 - x) * K, S * K, c))
        x = x1
for x in range(250, BX[1], 50):
    a, b = XY(x, BZ[0]), XY(x, BZ[1]); o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" stroke-opacity="0.08"/><text x="%.1f" y="%.1f" font-size="9" fill="#777">x %d</text>' % (a[0], a[1], b[0], b[1], a[0] + 2, b[1] - 3, x))
for z in range(650, BZ[1], 50):
    a, b = XY(BX[0], z), XY(BX[1], z); o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" stroke-opacity="0.08"/><text x="%.1f" y="%.1f" font-size="9" fill="#777">z %d</text>' % (a[0], a[1], b[0], b[1], a[0] + 2, a[1] - 2, z))
def rect(x0, x1, z0, z1, fill, label=None, stroke="#555", fs=10, op=1.0):
    a = XY(x0, z0)
    o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" fill-opacity="%.2f"/>' % (a[0], a[1], (x1 - x0) * K, (z1 - z0) * K, fill, stroke, op))
    if label:
        for i, ln in enumerate(label.split("\n")):
            o.append('<text x="%.1f" y="%.1f" font-size="%d" text-anchor="middle" fill="#222">%s</text>' % (a[0] + (x1 - x0) * K / 2, a[1] + (z1 - z0) * K / 2 + 4 + (i - (len(label.split("\n")) - 1) / 2) * (fs + 2), fs, ln))
def text(x, z, s, fs=10, col="#111", bg=True):
    a = XY(x, z)
    if bg: o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" fill="#fff" fill-opacity="0.8"/>' % (a[0] - 2, a[1] - fs, len(s) * fs * 0.56 + 4, fs + 4))
    o.append('<text x="%.1f" y="%.1f" font-size="%d" fill="%s">%s</text>' % (a[0], a[1], fs, col, s))
# the market piece (blender/tools/library_civic.py fish_market): the low quay layout
rect(293, 338, 730, 762, "#dfe7f2", "PUBLIC\nCAR PARK", stroke="#888")
rect(345, 368.5, 746, 770, "#f3e9d2", "OFFICE\nshop\nroof deck", fs=8)
rect(374, 464, 751, 771, "#f7f7f7", "AUCTION HALL 90 x 20")
rect(374, 464, 771, 775.5, "#eeeeee", None, stroke="#bbb")
rect(470, 504, 747, 771, "#eef3f7", "COLD\n+ ICE", fs=8)
rect(506, 512, 764, 770, "#9fb4c4", None)
rect(576, 600, 760, 771, "#e6e0d0", "nets", fs=8)
rect(294, 324, 781.6, 788.1, "#b9b9b9", None); text(288, 797, "slipway", 9)
for sx in (352, 468, 598): rect(sx - 5.2, sx + 2, 781.6, 783.6, "#8e44ad", None, stroke="#8e44ad")
text(474, 792, "landing stairs (purple)", 8, "#6c3483")
for sx in (300, 350, 590): rect(sx - 1, sx + 1, 698.7, 718.5, "#8e44ad", None, stroke="#8e44ad")
text(304, 712, "stairs up the dike", 8, "#6c3483")
for bx, lab in ((325, "W"), (400, "F"), (425, "F"), (450, "F"), (495, "F"), (555, "W")): rect(bx - 6, bx + 6, 784.2, 787.8, "#3d6f8e", None, stroke="#234")
text(520, 742, "trucks' turning ground", 9, "#333", bg=False)
text(398, 746, "truck berths", 9, "#333", bg=False)
a, b = XY(610, 712), XY(610, 780); o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#555" stroke-width="2"/>' % (a[0], a[1], b[0], b[1]))
text(616, 772, "retaining wall 3.6 m; strip under the viaduct", 9, "#444")
# the roads
net = pm.load_network(rec)
def style(name, r):
    if name.startswith("shuto_"):
        ramp = str(r.road_class) == "ramp"
        return ("#d6589f" if ramp else "#5b3ea6", 0.75)
    if name.startswith("ichiba"): return ("#d35400", 0.95)
    if name.startswith("ring_kita"): return ("#3a3a3a", 0.9)
    return ("#8a8a8a", 0.8)
runs = pp.centreline_runs(net, step=2.0, with_uids=True)
order = sorted(runs, key=lambda r_: (r_[0].startswith("shuto_"), r_[0]))
for name, pts, _u in order:
    if not any(BX[0] - 30 < q[0] < BX[1] + 30 and BZ[0] - 30 < -q[1] < BZ[1] + 30 for q in pts): continue
    r = net.roads[name]; col, op = style(name, r)
    wdt = 2.0 * ID._half(r) if (r.base.lanes_fwd and r.base.lanes_bwd) else max(r.base.lanes_fwd, r.base.lanes_bwd) * r.base.lane_width + 2.0
    one = not (r.base.lanes_fwd and r.base.lanes_bwd)
    d = " ".join("%.1f,%.1f" % XY(q[0], -q[1]) for q in pts)
    o.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%.1f" stroke-opacity="%.2f" stroke-linejoin="round"/>' % (d, col, wdt * K, op))
    o.append('<polyline points="%s" fill="none" stroke="#fff" stroke-width="0.8" stroke-dasharray="6,5" stroke-opacity="0.9"/>' % d)
o.append('</g>')
labels = [(455, 664, "coast (dike) road, crest 12 m", "#111"), (236, 652, "corner: one arc R 60", "#111"), (450, 704, "truck ramp 7 %, 10 m down, from the existing signal", "#a04000"),
          (430, 842, "Wangan: R 200 right - 91 m straight - R 200 left", "#3b1f7a"),
          (640, 838, "Suburb entrance: straight - one arc R 100 - straight", "#a02070"), (600, 700, "Suburb exit: one arc R 96", "#a02070"),
          (772, 806, "ferris wheel park (north-west lawn under the ramp)", "#444")]
for x, z, s, c in labels: text(x, z, s, 10, c)
rect(760, 870, 798, 870, "#9fd09f", None, stroke="#4a8a4a", op=0.25)
y0 = HEAD + (BZ[1] - BZ[0]) * K + 22
notes = ["The market on a quay 2 m over the water (user, 2026-10-13 late), after three reviews (port planner, level designer, developer):",
         "1. Yard x 262-608 lowered from 5.6 m to 2.0 m; boats lie against the quay itself (6 moored; no pontoon). A slipway and three landing stairs are the ways out of the water.",
         "2. One truck ramp from the existing signal: 7 %, 163 m, skewed down the dike face. The crest-level car park and its second junction are gone.",
         "3. Planner's order: the public parks at the ramp's foot (west) beside the office / shop and is fenced off; trucks pass the berths to a turning ground at the east end.",
         "4. Hall 20 m deep (was 27) so trucks get 13-18 m to back in; an eave over the apron; cold store and ice tower east of the hall; three evacuation stairs up the dike.",
         "5. Expressway (unchanged from this morning): two R 200 arcs with a 91 m straight; Suburb entrance and exit each one arc. The ferris wheel park did not move."]
for i, t_ in enumerate(notes):
    o.append('<text x="%d" y="%d" font-size="%d" fill="#222"%s>%s</text>' % (PAD, y0 + i * 18, 11, ' font-weight="bold"' if i == 0 else "", t_))
o.append('</svg>')
open(outf, "w").write("\n".join(o)); print("wrote", outf)
