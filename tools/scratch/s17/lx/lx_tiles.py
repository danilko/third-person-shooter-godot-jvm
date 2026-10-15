import json, sys
from PIL import Image, ImageDraw, ImageFont
R = "/data/danilko/git/third-person-shooter/"
FONT = "/usr/share/fonts/google-noto-sans-mono-cjk-vf-fonts/NotoSansMonoCJK-VF.ttc"
f = lambda s: ImageFont.truetype(FONT, s)
def load(p):
    d = json.load(open(p)); P = {q["uid"]: q["pos"] for q in d["points"]}
    return [(r["name"], [P[u][:2] for u in r["points"] if u in P], r["base"].get("lanes_fwd", 1) + r["base"].get("lanes_bwd", 1)) for r in d["roads"]]
roads = load(R + "assets/world_source/pieces/IslandRoads.roads.json")
rails = load(R + "assets/world_source/pieces/IslandRail.roads.json")
CASES = [("jokamachi_sando", (-610.5, -160.0), "castle sando: road kinks 18°, rail on the curve"),
         ("nishi_dori__x1", (-724.6, -220.1), "nishi_dori x1: ON the Blue line's curve (24°), 66°"),
         ("nishi_dori__3", (-430.0, -160.0), "nishi_dori 3: the road bends 10° at the track, 63°"),
         ("chuo_dori__3", (-62.4, -160.0), "chuo_dori (City West): both bend, 74°"),
         ("ring_kita__5", (1195.6, -460.4), "ring_kita 5: on a Main line curve, 48°"),
         ("rinkai_dori__2", (-750.0, -321.4), "rinkai_dori 2: rail curve ends 21 m away (4°)")]
H, S = 110.0, 2.6
TW = int(2 * H * S)
img = Image.new("RGB", (TW * 3 + 40, (TW + 40) * 2 + 50), (255, 255, 255)); D = ImageDraw.Draw(img)
D.text((10, 8), "The 6 踏切 where the road or the track bends within 30 m (plan, north up, 220 m tiles; red = the crossing road)", fill=(0, 0, 0), font=f(17))
for k, (road, (cx, cy), cap) in enumerate(CASES):
    im = Image.new("RGB", (TW, TW), (244, 241, 234)); d = ImageDraw.Draw(im)
    T = lambda x, y: ((x - cx + H) * S, (cy + H - y) * S)
    for g in range(-100, 101, 25):
        d.line([T(cx + g, cy - H), T(cx + g, cy + H)], fill=(230, 226, 216)); d.line([T(cx - H, cy + g), T(cx + H, cy + g)], fill=(230, 226, 216))
    d.ellipse([T(cx - 30, cy + 30), T(cx + 30, cy - 30)], outline=(200, 200, 200), width=1)
    for nm, pts, lanes in roads:
        if len(pts) < 2 or not any(abs(p[0] - cx) < H + 60 and abs(p[1] - cy) < H + 60 for p in pts): continue
        col = (192, 57, 43) if nm == road else (120, 120, 120)
        d.line([T(*p) for p in pts], fill=col, width=max(3, int(3.2 * lanes * S / 2)), joint="curve")
    for nm, pts, _l in rails:
        if len(pts) < 2: continue
        d.line([T(*p) for p in pts], fill=(60, 75, 95), width=int(11 * S), joint="curve")
        d.line([T(*p) for p in pts], fill=(250, 250, 250), width=2, joint="curve")
    ox, oy = 10 + (k % 3) * (TW + 10), 50 + (k // 3) * (TW + 40)
    img.paste(im, (ox, oy)); D.text((ox + 2, oy + TW + 4), "%d. %s" % (k + 1, cap), fill=(30, 30, 30), font=f(14))
img.save(sys.argv[1]); print(sys.argv[1], img.size)
