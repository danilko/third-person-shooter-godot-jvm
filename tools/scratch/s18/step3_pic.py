"""S18 step 3 review picture: chuo_dori__3 and ring_kita__5, BEFORE (HEAD) | AFTER (dry), plan + the Main line profile.
    python3 tools/scratch/s18/step3_pic.py <dry dir> <out.png>"""
import json, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")) + "/"
sys.path.insert(0, R + "tools")
import island_layout as IL
DRY, OUT = sys.argv[1], sys.argv[2]
FONT = "/usr/share/fonts/google-noto-sans-mono-cjk-vf-fonts/NotoSansMonoCJK-VF.ttc"
f = lambda s: ImageFont.truetype(FONT, s)
RD = "assets/world_source/pieces/IslandRoads.roads.json"; RL = "assets/world_source/pieces/IslandRail.roads.json"


def head(path):
    return json.loads(subprocess.run(["git", "show", "HEAD:" + path], cwd=R, capture_output=True, text=True).stdout)


def lines(doc):
    P = {p["uid"]: p["pos"] for p in doc["points"]}
    return {r["name"]: ([P[u] for u in r["points"] if u in P], r.get("base", {})) for r in doc["roads"]}


tmp = os.path.join(DRY, "_head"); os.makedirs(tmp, exist_ok=True)
for p in (RD, RL):
    json.dump(head(p), open(os.path.join(tmp, os.path.basename(p)), "w"))
import shutil
for d_ in (tmp, DRY):
    shutil.copy(R + "assets/world_source/pieces/IslandRoads.network.json", os.path.join(d_, "IslandRoads.network.json"))
SETS = {"before": (lines(head(RD)), lines(head(RL)), IL.level_crossings(os.path.join(tmp, "IslandRoads.roads.json"),
                                                                        os.path.join(tmp, "IslandRail.roads.json"), IL.arterial_names())),
        "after": (lines(json.load(open(os.path.join(DRY, "IslandRoads.roads.json")))),
                  lines(json.load(open(os.path.join(DRY, "IslandRail.roads.json")))),
                  IL.level_crossings(os.path.join(DRY, "IslandRoads.roads.json"), os.path.join(DRY, "IslandRail.roads.json"),
                                     IL.arterial_names()))}


def plan(box, S, which, hl):
    X0, X1, Y0, Y1 = box
    roads, rails, lx = SETS[which]
    PW, PH = int((X1 - X0) * S), int((Y1 - Y0) * S)
    im = Image.new("RGB", (PW, PH), (244, 241, 234)); d = ImageDraw.Draw(im)
    T = lambda x, y: ((x - X0) * S, (Y1 - y) * S)
    for g in range(int(X0 // 50 * 50), int(X1), 50):
        d.line([T(g, Y0), T(g, Y1)], fill=(228, 224, 214)); d.text((T(g, Y0)[0] + 2, PH - 14), str(g), fill=(140, 140, 140), font=f(10))
    for g in range(int(Y0 // 50 * 50), int(Y1), 50):
        d.line([T(X0, g), T(X1, g)], fill=(228, 224, 214)); d.text((2, T(X0, g)[1] + 1), str(g), fill=(140, 140, 140), font=f(10))
    inside = lambda pts: any(X0 - 60 < p[0] < X1 + 60 and Y0 - 60 < p[1] < Y1 + 60 for p in pts)
    for name, (pts, b) in roads.items():
        if len(pts) < 2 or not inside(pts):
            continue
        n = (b.get("lanes_fwd") or 2) + (b.get("lanes_bwd") or 2)
        col = (192, 57, 43) if name.startswith(hl) else (120, 150, 200) if name.startswith("shuto_") else (90, 90, 90) if n >= 4 else (150, 150, 150)
        d.line([T(p[0], p[1]) for p in pts], fill=col, width=max(2, int(1.4 * n * S)), joint="curve")
        if name.startswith(hl):
            for p in pts:
                if X0 < p[0] < X1 and Y0 < p[1] < Y1:
                    d.ellipse([T(p[0] - 1.6 / S * 3, p[1] + 1.6 / S * 3), T(p[0] + 1.6 / S * 3, p[1] - 1.6 / S * 3)], fill=(0, 0, 0))
    for name, (pts, b) in rails.items():
        if len(pts) < 2 or not inside(pts):
            continue
        d.line([T(p[0], p[1]) for p in pts], fill=(60, 75, 95), width=int(4 * S), joint="curve")
        d.line([T(p[0], p[1]) for p in pts], fill=(250, 250, 250), width=1, joint="curve")
    for r in lx:
        x, y = r[2]
        if X0 < x < X1 and Y0 < y < Y1:
            col = (39, 140, 80) if not r[5] else (200, 30, 30)
            d.ellipse([T(x - 6, y + 6), T(x + 6, y - 6)], outline=col, width=3)
            d.text(T(x + 8, y - 4), "%s %.0f°%s" % (r[0], r[3], "" if not r[5] else "\n" + "\n".join(r[5])), fill=col, font=f(11))
    return im


def profile(which):
    """The Main line's rail head from the EW leg to the bridge, with the roads it meets."""
    roads, rails, _ = SETS[which]
    box = lambda p: p[1] > -720 and p[0] > 900 and p[1] < -370
    pts = max((v[0] for k, v in rails.items() if k.startswith("rail_main")), key=lambda ps: sum(1 for p in ps if box(p)))
    seg = [p for p in pts if box(p)]
    s = [0.0]
    for a, b in zip(seg, seg[1:]):
        s.append(s[-1] + math.dist(a[:2], b[:2]))
    W, H = 760, 260
    im = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(im)
    Z0, Z1 = 0.0, 26.0
    T = lambda ss, z: (40 + ss / s[-1] * (W - 60), H - 24 - (z - Z0) / (Z1 - Z0) * (H - 40))
    for z in range(0, 27, 4):
        d.line([T(0, z), T(s[-1], z)], fill=(235, 235, 235)); d.text((4, T(0, z)[1] - 7), "%d" % z, fill=(140, 140, 140), font=f(10))
    d.line([T(si, p[2]) for si, p in zip(s, seg)], fill=(60, 75, 95), width=3)
    # the roads that cross it: their deck at the crossing
    import island_rail_layout as RLY
    for name, (rp, b) in roads.items():
        if not (name.startswith("ring_kita__5") or name.startswith("shuto_t4") or name.startswith("shuto_spur__2")):
            continue
        for a, b2 in zip(rp, rp[1:]):
            for i in range(len(seg) - 1):
                h = RLY.seg_x(seg[i], seg[i + 1], a, b2)
                if h:
                    t, u = h
                    ss = s[i] + (s[i + 1] - s[i]) * t
                    rz = a[2] + (b2[2] - a[2]) * u
                    d.line([T(ss - 6, rz), T(ss + 6, rz)], fill=(192, 57, 43) if name.startswith("ring") else (120, 150, 200), width=4)
                    d.text((T(ss, rz)[0] + 6, T(ss, rz)[1] - 14), "%s %.1f" % (name.split("__")[0], rz), fill=(60, 60, 60), font=f(10))
                    railz = seg[i][2] + (seg[i + 1][2] - seg[i][2]) * t
                    d.text((T(ss, railz)[0] + 4, T(ss, railz)[1] + 2), "rail %.1f" % railz, fill=(60, 75, 95), font=f(10))
    d.text((44, 4), "Main line rail head, x 900 -> the bridge (m)", fill=(30, 30, 30), font=f(12))
    return im


CHUO = (-150.0, 30.0, -280.0, -60.0); RING = (1050.0, 1300.0, -620.0, -340.0)
cols = []
for which in ("before", "after"):
    a = plan(CHUO, 3.0, which, "chuo_dori"); b = plan(RING, 2.2, which, "ring_kita"); c = profile(which)
    cols.append((a, b, c))
W = max(a.width + b.width for a, b, c in cols) + 20
img = Image.new("RGB", (W * 2 + 20, 60 + max(max(a.height, b.height) for a, b, c in cols) + 280 + 120), (255, 255, 255))
D = ImageDraw.Draw(img)
titles = ("BEFORE (HEAD)", "AFTER (dry)")
notes = (["chuo_dori__3 bends 5.8° 8 m south of the track ('>' at the 踏切);",
          "ring_kita__5, the dike road, meets the Main line viaduct at grade on its curve, 48°"],
         ["chuo_dori__3: the bend moved 22 m south of the track (island_local_fixes lx_straight),",
          "  the road is straight across; the rail's own curve starts 2 m east of it (3.5°, R 160 = R_MIN)",
          "ring_kita__5: no 踏切 -- the Main line climbs over the dike road (rail 4.8 m clear over it,",
          "  T4 6.15 m over the rail: both just inside the rules) and on to the bridge deck"])
for k, (a, b, c) in enumerate(cols):
    OX = 10 + k * (W + 10)
    D.text((OX, 8), titles[k], fill=(0, 0, 0), font=f(18))
    D.text((OX, 34), "chuo_dori x Blue line (left), ring_kita x Main line (right) -- plan, north up, 50 m grid", fill=(90, 90, 90), font=f(12))
    img.paste(a, (OX, 56)); img.paste(b, (OX + a.width + 10, 56))
    y = 56 + max(a.height, b.height) + 10
    img.paste(c, (OX, y))
    for i, ln in enumerate(notes[k]):
        D.text((OX, y + c.height + 8 + 18 * i), ln, fill=(30, 30, 30), font=f(13))
img.save(OUT); print(OUT, img.size)
