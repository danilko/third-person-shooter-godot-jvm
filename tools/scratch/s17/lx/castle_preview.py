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
X0, X1, Y0, Y1 = -830.0, -390.0, -400.0, -70.0
S = 1.9                                    # px per metre
PW, PH = int((X1 - X0) * S), int((Y1 - Y0) * S)
TOP = 70
img = Image.new("RGB", (PW * 3 + 40, PH + TOP + 120), (255, 255, 255))
d = ImageDraw.Draw(img)

def rail(cx, rad, n=90):
    pts = [(-380.0, -160.0), (cx + rad, -160.0)]
    ox, oy = cx + rad, -160.0 - rad
    for i in range(n + 1):
        a = math.pi / 2 + (math.pi / 2) * i / n
        pts.append((ox + rad * math.cos(a), oy + rad * math.sin(a)))
    pts.append((cx, -430.0))
    return pts, cx + rad

def panel(k, cx, rad, title, lines, good):
    global d
    OX = 10 + k * (PW + 10)
    full = d
    pim = Image.new("RGB", (PW, PH), (244, 241, 234))
    d = ImageDraw.Draw(pim)
    ox, top = 0, 0
    T = lambda x, y: (ox + (x - X0) * S, top + (Y1 - y) * S)
    for g in range(-800, -380, 50):
        d.line([T(g, Y0), T(g, Y1)], fill=(228, 224, 214))
        d.text((T(g, Y0)[0] + 2, PH - 16), str(g), fill=(140, 140, 140), font=f(11))
    for b in blds:
        x, y = b["pos"][0], -b["pos"][2]
        if X0 < x < X1 and Y0 < y < Y1:
            d.rectangle([T(x - 5, y + 5), T(x + 5, y - 5)], fill=(214, 204, 188))
    for r in roads["roads"]:
        pts = [P[u] for u in r["points"] if u in P]
        if len(pts) < 2 or not any(X0 - 80 < p[0] < X1 + 80 and Y0 - 80 < p[1] < Y1 + 80 for p in pts):
            continue
        nm = r["name"]
        lanes = r["base"].get("lanes_fwd", 1) + r["base"].get("lanes_bwd", 1)
        col = (192, 57, 43) if nm.startswith("jokamachi_sando") else (90, 90, 90) if lanes >= 4 else (150, 150, 150)
        d.line([T(p[0], p[1]) for p in pts], fill=col, width=max(3, int(3.2 * lanes * S / 2)), joint="curve")
    for b in res["boxes"]:
        if b["id"] in ("station:Castle Town", "parking:Castle Town"):
            x, y, ux, uy = b["x"], b["y"], b.get("ux", 1.0), b.get("uy", 0.0)
            nx, ny = -uy, ux
            c = [T(x + ux * sa * b["h_along"] + nx * sc * b["h_across"], y + uy * sa * b["h_along"] + ny * sc * b["h_across"])
                 for sa, sc in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
            st = b["id"].startswith("station")
            d.polygon(c, fill=(150, 180, 225) if st else (190, 190, 190), outline=(29, 63, 117) if st else (90, 90, 90))
            if st:
                d.text(T(x - 60, y + 40), "Castle Town station", fill=(29, 63, 117), font=f(15))
                d.text(T(x - 60, y + 31), "box incl. ramps: x %.0f .. %.0f" % (x - b["h_along"], x + b["h_along"]),
                       fill=(29, 63, 117), font=f(12))
            else:
                d.text(T(x + 8, y - 4), "car park", fill=(80, 80, 80), font=f(11))
    pts, tx = rail(cx, rad)
    d.line([T(*p) for p in pts], fill=(60, 75, 95), width=int(11 * S), joint="curve")      # the double-track bed, 11 m
    d.line([T(*p) for p in pts], fill=(250, 250, 250), width=2, joint="curve")
    mark = (39, 174, 96) if good else (230, 126, 34)
    a, b_ = T(tx, -160)
    d.polygon([(a - 9, b_ - 30), (a + 9, b_ - 30), (a, b_ - 12)], fill=mark)
    d.text((a - 70, b_ - 52), "curve starts x %.0f" % tx, fill=mark, font=f(14))
    if not good:   # the overlap: station box x -600 .. curve start
        d.rectangle([T(-600.4, -146), T(tx, -174)], outline=(200, 30, 30), width=3)
        d.text(T(-640, -186), "CLASH: train clips station", fill=(200, 30, 30), font=f(14))
    d.text(T(-655, -92), "to the castle (守礼門 axis) ↑", fill=(192, 57, 43), font=f(13))
    d.text(T(-640, -268), "jokamachi_sando", fill=(192, 57, 43), font=f(12))
    d.text(T(-500, -258), "nishi_dori (arterial)", fill=(70, 70, 70), font=f(12))
    d.text(T(-445, -128), "踏切", fill=(70, 70, 70), font=f(12))
    d.text(T(-627, -128), "踏切", fill=(192, 57, 43), font=f(12))
    d.text(T(cx + 8, -330), "Blue line (leg x %.0f)" % cx, fill=(60, 75, 95), font=f(12))
    d = full
    img.paste(pim, (OX, TOP))
    d.text((OX + 4, 8), title, fill=(0, 0, 0), font=f(18))
    for i, ln in enumerate(lines):
        d.text((OX + 4, TOP + PH + 10 + 22 * i), ln, fill=(30, 130, 73) if good else (190, 40, 40), font=f(15))

panel(0, -800.0, 200.0, "A. BEFORE (HEAD): leg x -800, corner R 200",
      ["curve starts at x -600 = the station's west end:", "no clash, but zero margin"], True)
panel(1, -750.0, 200.0, "B. REBUILT NOW: leg x -750, corner R 200",
      ["curve starts at x -550: the station's west 50 m", "stand on the curve -> rail_track FAIL"], False)
panel(2, -750.0, 140.0, "C. THE FIX: leg x -750, corner R 140",
      ["curve starts at x -610, at the sando's 踏切:", "station on straight track; station, sando,", "rail leg and car park all unchanged"], True)
d.text((10, TOP - 26), "Castle Town and the Blue line's west corner -- plan, north up, 50 m grid (record x labelled)",
       fill=(90, 90, 90), font=f(13))
img.save(OUT)
print(OUT, img.size)
