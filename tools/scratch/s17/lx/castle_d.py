import json, math, sys
from PIL import Image, ImageDraw, ImageFont
R = "/data/danilko/git/third-person-shooter/"
OUT = sys.argv[1]
roads = json.load(open(R + "assets/world_source/pieces/IslandRoads.roads.json"))
P = {p["uid"]: p["pos"] for p in roads["points"]}
res = json.load(open(R + "assets/world_source/buildings/IslandRailReserve.json"))
blds = json.load(open(R + "assets/world_source/buildings/IslandBuildings.json"))
blds = blds["buildings"] if isinstance(blds, dict) else blds
FONT = "/usr/share/fonts/google-noto-sans-mono-cjk-vf-fonts/NotoSansMonoCJK-VF.ttc"
f = lambda s: ImageFont.truetype(FONT, s)
X0, X1, Y0, Y1 = -800.0, -400.0, -330.0, 40.0
S = 2.1
PW, PH = int((X1 - X0) * S), int((Y1 - Y0) * S)
TOP = 70
img = Image.new("RGB", (PW * 2 + 30, PH + TOP + 110), (255, 255, 255))
D = ImageDraw.Draw(img)

def rail(cx, rad, n=90):
    pts = [(-380.0, -160.0), (cx + rad, -160.0)]
    ox, oy = cx + rad, -160.0 - rad
    for i in range(n + 1):
        a = math.pi / 2 + (math.pi / 2) * i / n
        pts.append((ox + rad * math.cos(a), oy + rad * math.sin(a)))
    pts.append((cx, -430.0))
    return pts, cx + rad

def castle_rect(cx, cy, tilt):
    t = math.radians(tilt); ax = (-math.sin(t), math.cos(t)); px = (ax[1], -ax[0])
    return [(cx + px[0] * u + ax[0] * v, cy + px[1] * u + ax[1] * v) for u, v in ((-79, -64), (79, -64), (79, 64), (-79, 64))], ax, px

def panel(k, rad, castle, sando, title, lines):
    OX = 10 + k * (PW + 10)
    im = Image.new("RGB", (PW, PH), (244, 241, 234)); d = ImageDraw.Draw(im)
    T = lambda x, y: ((x - X0) * S, (Y1 - y) * S)
    for g in range(-800, -400, 50):
        d.line([T(g, Y0), T(g, Y1)], fill=(228, 224, 214))
        d.text((T(g, Y0)[0] + 2, PH - 16), str(g), fill=(140, 140, 140), font=f(11))
    for b in blds:
        x, y = b["pos"][0], -b["pos"][2]
        if X0 < x < X1 and Y0 < y < Y1 and not b["type"].startswith("ShuriCastle"):
            d.rectangle([T(x - 5, y + 5), T(x + 5, y - 5)], fill=(214, 204, 188))
    # the castle footprint + its gate axis
    rect, ax, px = castle_rect(*castle)
    d.polygon([T(*p) for p in rect], fill=(236, 214, 200), outline=(150, 60, 40), width=2)
    d.text(T(castle[0] - 40, castle[1] + 10), "Shuri Castle", fill=(150, 60, 40), font=f(15))
    d.text(T(castle[0] - 40, castle[1] - 4), "yaw %.1f" % (90 + castle[2]), fill=(150, 60, 40), font=f(12))
    for r in roads["roads"]:
        if r["name"].startswith("jokamachi_sando"):
            continue
        pts = [P[u] for u in r["points"] if u in P]
        if len(pts) < 2 or not any(X0 - 80 < p[0] < X1 + 80 and Y0 - 80 < p[1] < Y1 + 80 for p in pts):
            continue
        lanes = r["base"].get("lanes_fwd", 1) + r["base"].get("lanes_bwd", 1)
        d.line([T(p[0], p[1]) for p in pts], fill=(90, 90, 90) if lanes >= 4 else (150, 150, 150),
               width=max(3, int(3.2 * lanes * S / 2)), joint="curve")
    d.line([T(*p) for p in sando], fill=(192, 57, 43), width=int(7 * S), joint="curve")
    for b in res["boxes"]:
        if b["id"] in ("station:Castle Town", "parking:Castle Town"):
            x, y, ux, uy = b["x"], b["y"], b.get("ux", 1.0), b.get("uy", 0.0)
            nx, ny = -uy, ux
            c = [T(x + ux * sa * b["h_along"] + nx * sc * b["h_across"], y + uy * sa * b["h_along"] + ny * sc * b["h_across"])
                 for sa, sc in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
            st = b["id"].startswith("station")
            d.polygon(c, fill=(150, 180, 225) if st else (190, 190, 190), outline=(29, 63, 117) if st else (90, 90, 90))
            if st:
                d.text(T(x - 50, y - 18), "Castle Town station", fill=(29, 63, 117), font=f(14))
    pts, tx = rail(-750.0, rad)
    d.line([T(*p) for p in pts], fill=(60, 75, 95), width=int(11 * S), joint="curve")
    d.line([T(*p) for p in pts], fill=(250, 250, 250), width=2, joint="curve")
    a, b_ = T(tx, -160)
    d.polygon([(a - 9, b_ - 30), (a + 9, b_ - 30), (a, b_ - 12)], fill=(39, 174, 96))
    d.text((a - 75, b_ - 52), "curve starts x %.0f" % tx, fill=(39, 174, 96), font=f(14))
    # the crossing angle of the sando at the track (y -160 or on the curve)
    d.text(T(-605, -190), "踏切", fill=(192, 57, 43), font=f(14))
    d.text(T(-596, -240), "nishi_dori", fill=(70, 70, 70), font=f(12))
    im_d = d
    img.paste(im, (OX, TOP))
    D.text((OX + 4, 10), title, fill=(0, 0, 0), font=f(19))
    for i, ln in enumerate(lines):
        D.text((OX + 4, TOP + PH + 10 + 22 * i), ln, fill=(30, 30, 30), font=f(15))

sando_now = [tuple(P[u][:2]) for r in roads["roads"] if r["name"] == "jokamachi_sando" for u in r["points"]]
sando_now = [(-610.0, -224.0)] + sando_now
panel(0, 140.0, (-600.0, -40.0, 14.43), sando_now,
      "C. REBUILDING NOW: corner R 140, castle as it is",
      ["the 踏切 at the curve's start, the sando kinks 14° at the track (\">\")",
       "to reach the castle's tilted gate axis (yaw 104.4)"])
panel(1, 100.0, (-569.9, -40.0, 0.0), [(-610.0, -224.0), (-610.0, -128.0)],
      "D. PROPOSAL: corner R 100, castle squared + 30 m east",
      ["rail straight to x -650: the 踏切 40 m along the straight, 90 deg;",
       "the sando ONE straight line x -610 from nishi_dori to the gate;",
       "the castle turned 14.4 deg (yaw 90) and 30 m east, its gate axis on x -610"])
D.text((10, TOP - 26), "Castle Town, the sando and the castle -- plan, north up, 50 m grid (record x labelled)",
       fill=(90, 90, 90), font=f(13))
img.save(OUT); print(OUT, img.size)
