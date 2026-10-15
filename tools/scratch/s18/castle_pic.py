"""S18 castle group review picture: BEFORE (HEAD's records) | AFTER (a dry run's), plan, north up.
    python3 tools/scratch/s18/castle_pic.py <dry dir> <out.png>"""
import json, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")) + "/"
sys.path.insert(0, R + "tools")
DRY, OUT = sys.argv[1], sys.argv[2]
FONT = "/usr/share/fonts/google-noto-sans-mono-cjk-vf-fonts/NotoSansMonoCJK-VF.ttc"
f = lambda s: ImageFont.truetype(FONT, s)
X0, X1, Y0, Y1 = -830.0, -420.0, -350.0, 110.0
S = 2.0
PW, PH = int((X1 - X0) * S), int((Y1 - Y0) * S)
TOP = 60


def head(path):
    return json.loads(subprocess.run(["git", "show", "HEAD:" + path], cwd=R, capture_output=True, text=True).stdout)


def lines(doc):
    P = {p["uid"]: p["pos"] for p in doc["points"]}
    return {r["name"]: ([P[u][:2] for u in r["points"] if u in P], r.get("base", {})) for r in doc["roads"]}


def castle_poly(cx, cy, yaw):
    """The piece's real outer extents (library_landmarks: x -79..72 incl. the approach, y -64..60) in the record frame."""
    a = math.radians(yaw)
    out = []
    for px, py in ((-79, -64), (72, -64), (72, 60), (-79, 60)):
        gx, gz = px, -py                                    # piece -> Godot local
        x = gx * math.cos(a) + gz * math.sin(a)
        z = -gx * math.sin(a) + gz * math.cos(a)
        out.append((cx + x, cy - z))
    return out


def clear_box(cx, cy, yaw, size, grow=25.0):
    a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
    hu, hv = size[0] / 2 + grow, size[1] / 2 + grow
    return [(cx + u * c - v * s, cy + u * s + v * c) for u, v in ((-hu, -hv), (hu, -hv), (hu, hv), (-hu, hv))]


def panel(roads, rails, site, lx, title, notes):
    im = Image.new("RGB", (PW, PH), (244, 241, 234)); d = ImageDraw.Draw(im)
    T = lambda x, y: ((x - X0) * S, (Y1 - y) * S)
    for g in range(-800, -400, 50):
        d.line([T(g, Y0), T(g, Y1)], fill=(228, 224, 214))
        d.text((T(g, Y0)[0] + 2, PH - 16), str(g), fill=(140, 140, 140), font=f(11))
    for g in range(-350, 101, 50):
        d.line([T(X0, g), T(X1, g)], fill=(228, 224, 214))
        d.text((2, T(X0, g)[1] + 1), str(g), fill=(140, 140, 140), font=f(11))
    cb = clear_box(site["x"], site["y"], site["yaw"], site["size"])
    d.polygon([T(*p) for p in cb], outline=(200, 150, 140))
    cp = castle_poly(site["x"], site["y"], site["yaw"])
    d.polygon([T(*p) for p in cp], fill=(236, 214, 200), outline=(150, 60, 40), width=2)
    d.text(T(site["x"] - 40, site["y"] + 8), "Shuri Castle", fill=(150, 60, 40), font=f(15))
    d.text(T(site["x"] - 40, site["y"] - 6), "yaw %.1f" % site["yaw"], fill=(150, 60, 40), font=f(12))
    for name, (pts, b) in roads.items():
        if len(pts) < 2 or not any(X0 - 50 < p[0] < X1 + 50 and Y0 - 50 < p[1] < Y1 + 50 for p in pts):
            continue
        n = (b.get("lanes_fwd") or 2) + (b.get("lanes_bwd") or 2)
        col = (192, 57, 43) if name.startswith("jokamachi_sando") else (196, 120, 20) if name.startswith(
            "shrine_touge") else (90, 90, 90) if n >= 4 else (150, 150, 150)
        d.line([T(*p) for p in pts], fill=col, width=max(3, int(1.6 * n * S)), joint="curve")
    for name, (pts, b) in rails.items():
        if len(pts) < 2 or not any(X0 - 50 < p[0] < X1 + 50 and Y0 - 50 < p[1] < Y1 + 50 for p in pts):
            continue
        d.line([T(*p) for p in pts], fill=(60, 75, 95), width=int(5 * S), joint="curve")
        d.line([T(*p) for p in pts], fill=(250, 250, 250), width=1, joint="curve")
    for r in lx:
        x, y = r[2]
        if not (X0 < x < X1 and Y0 < y < Y1):
            continue
        ok = not r[5]
        col = (39, 140, 80) if ok else (200, 30, 30)
        d.ellipse([T(x - 6, y + 6), T(x + 6, y - 6)], outline=col, width=3)
        d.text(T(x + 8, y - 4), "%s %.0f°%s" % (r[0], r[3], "" if ok else "\n" + "\n".join(r[5])), fill=col, font=f(12))
    return im, title, notes


def site_of(doc):
    return next(s for s in doc["sites"] if s["id"] == "shuri_castle")


import island_layout as IL
RD = "assets/world_source/pieces/IslandRoads.roads.json"; RL = "assets/world_source/pieces/IslandRail.roads.json"
SITES = "assets/world_source/buildings/IslandSites.json"
tmp = os.path.join(DRY, "_head"); os.makedirs(tmp, exist_ok=True)
for p in (RD, RL):
    json.dump(head(p), open(os.path.join(tmp, os.path.basename(p)), "w"))
import shutil
shutil.copy(R + "assets/world_source/pieces/IslandRoads.network.json", os.path.join(tmp, "IslandRoads.network.json"))
shutil.copy(R + "assets/world_source/pieces/IslandRoads.network.json", os.path.join(DRY, "IslandRoads.network.json"))
lx_head = IL.level_crossings(os.path.join(tmp, "IslandRoads.roads.json"), os.path.join(tmp, "IslandRail.roads.json"),
                             IL.arterial_names())
lx_dry = IL.level_crossings(os.path.join(DRY, "IslandRoads.roads.json"), os.path.join(DRY, "IslandRail.roads.json"),
                            IL.arterial_names())
A = panel(lines(head(RD)), lines(head(RL)), site_of(head(SITES)), lx_head, "BEFORE (HEAD): Blue corner R 140, castle yaw 104",
          ["the sando kinks 18° at the track ('>') to reach the tilted gate axis;",
           "nishi_dori__x1 crosses on the Blue curve"])
B = panel(lines(json.load(open(os.path.join(DRY, "IslandRoads.roads.json")))),
          lines(json.load(open(os.path.join(DRY, "IslandRail.roads.json")))), site_of(json.load(open(R + SITES))),
          lx_dry, "AFTER (dry): R 100, castle yaw 90 + 30 m east, hairpin moved",
          ["the sando ONE straight line x -610 onto the gate axis; rail straight from x -650;",
           "shrine_touge's first hairpin (orange) moved (30, 15) m: 31 m clear of the castle, 9.3 % worst grade;",
           "faint box = the castle's 25 m SITE_CLEAR"])
img = Image.new("RGB", (PW * 2 + 30, PH + TOP + 90), (255, 255, 255)); D = ImageDraw.Draw(img)
for k, (im, title, notes) in enumerate((A, B)):
    OX = 10 + k * (PW + 10)
    img.paste(im, (OX, TOP))
    D.text((OX + 4, 8), title, fill=(0, 0, 0), font=f(18))
    for i, ln in enumerate(notes):
        D.text((OX + 4, TOP + PH + 8 + 20 * i), ln, fill=(30, 30, 30), font=f(14))
D.text((10, TOP - 22), "Castle Town: the castle, its sando, the Blue corner and shrine_touge's first hairpin -- plan, north up,"
       " 50 m grid (record x / y)", fill=(90, 90, 90), font=f(13))
img.save(OUT); print(OUT, img.size)
