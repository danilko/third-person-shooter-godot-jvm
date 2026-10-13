#!/usr/bin/env python3
"""build_paint_glyphs.py -- the characters the road kit PAINTS on a carriageway, as flat triangles
(`assets/world_source/kits/road_kit/paint_glyphs.json`).

    python3 tools/build_paint_glyphs.py [--src <NotoSansCJK .ttc/.otf>] [--chars 止まれ0123456789] [--check]

A legend on the road (止まれ before a stop line, the limit's numerals in a lane) is geometry in the road's own
mark material, like the stop line and the zebra: no texture, no extra draw. The road build is plain Python with no
font library, so the outlines are triangulated HERE, once, and the kit reads the result:

    {"font": ..., "glyphs": {"止": {"w": 0.93, "h": 0.89, "tris": [[x, y], [x, y], [x, y], ...]}, ...}}

x to the reader's right and y up the character, in em, the ORIGIN AT THE CENTRE OF THE INK; `w` / `h` are the ink's
size. `point_furniture._legend` scales a whole legend by the largest `w` and `h` of its characters, so they keep
their proportions (a 1 stays narrower than a 0).

The face is the signs' own (tools/make_jp_font.py: Noto Sans CJK JP at weight 700, OFL). `--chars` adds characters
(a legend in another language is `stop_text` in furniture.json plus its characters here). `--check` exits 1 when a
character furniture.json asks for is not in the file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "assets/world_source/kits/road_kit/paint_glyphs.json")
RULES = os.path.join(ROOT, "assets/world_source/kits/road_kit/furniture.json")
SRC = "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc"
DIGITS = "0123456789"
#: a curve segment is cut into this many chords: paint seen from a car, not a title screen
CURVE_STEPS = 4
#: outline points nearer the simplified outline than this (em) are dropped
SIMPLIFY = 0.004


def wanted():
    with open(RULES, encoding="utf-8") as fh:
        rules = json.load(fh).get("rules", {})
    return "".join(dict.fromkeys(str(rules.get("stop_text", "")) + DIGITS))


def contours(font, ch):
    """The glyph's closed outlines as lists of (x, y) in font units, curves flattened."""
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    gs = font.getGlyphSet()
    name = font.getBestCmap().get(ord(ch))
    if name is None:
        return None
    pen = DecomposingRecordingPen(gs)
    gs[name].draw(pen)
    out, cur = [], []
    for op, a in pen.value:
        if op == "moveTo":
            cur = [a[0]]
        elif op == "lineTo":
            cur.append(a[0])
        elif op in ("curveTo", "qCurveTo"):
            p0 = cur[-1]
            if op == "curveTo" and len(a) == 3:
                c1, c2, p3 = a
                for k in range(1, CURVE_STEPS + 1):
                    t = k / CURVE_STEPS
                    u = 1.0 - t
                    cur.append(tuple(u ** 3 * p0[i] + 3 * u * u * t * c1[i] + 3 * u * t * t * c2[i] + t ** 3 * p3[i]
                                     for i in range(2)))
            else:                                   # TrueType: a run of quadratics with implied on-curve points
                pts = [p for p in a if p is not None]
                for n in range(len(pts) - 1):
                    c = pts[n]
                    e = pts[n + 1] if n == len(pts) - 2 else tuple(0.5 * (pts[n][i] + pts[n + 1][i]) for i in range(2))
                    s = cur[-1]
                    for k in range(1, CURVE_STEPS + 1):
                        t = k / CURVE_STEPS
                        u = 1.0 - t
                        cur.append(tuple(u * u * s[i] + 2 * u * t * c[i] + t * t * e[i] for i in range(2)))
        elif op in ("closePath", "endPath"):
            if len(cur) >= 3:
                out.append(cur)
            cur = []
    return out


def triangles(cs, em):
    """Non-zero fill of the outlines, as triangles in em about the ink's centre: (w, h, [(x, y) x 3n])."""
    import shapely
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    def signed(c):
        return 0.5 * sum(c[i][0] * c[(i + 1) % len(c)][1] - c[(i + 1) % len(c)][0] * c[i][1] for i in range(len(c)))
    pos = [Polygon(c).buffer(0) for c in cs if signed(c) > 0]
    neg = [Polygon(c).buffer(0) for c in cs if signed(c) < 0]
    # whichever winding carries more area is the ink, the other the counters cut out of it
    if sum(p.area for p in neg) > sum(p.area for p in pos):
        pos, neg = neg, pos
    ink = unary_union(pos).difference(unary_union(neg)) if neg else unary_union(pos)
    ink = ink.simplify(SIMPLIFY * em, preserve_topology=True)
    x0, y0, x1, y1 = ink.bounds
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    tris = []
    parts = list(ink.geoms) if hasattr(ink, "geoms") else [ink]
    for part in parts:
        for t in shapely.constrained_delaunay_triangles(part).geoms:
            ring = list(t.exterior.coords)[:3]
            if signed(ring) < 0:
                ring.reverse()
            tris.extend((round((x - cx) / em, 4), round((y - cy) / em, 4)) for x, y in ring)
    return round((x1 - x0) / em, 4), round((y1 - y0) / em, 4), tris, ink.area / (em * em)


def main(argv):
    chars = wanted()
    if "--chars" in argv:
        chars = "".join(dict.fromkeys(chars + argv[argv.index("--chars") + 1]))
    if "--check" in argv:
        have = json.load(open(OUT, encoding="utf-8"))["glyphs"] if os.path.exists(OUT) else {}
        missing = [c for c in chars if c not in have]
        print("build_paint_glyphs: %s" % ("up to date" if not missing else "MISSING " + "".join(missing)))
        return 1 if missing else 0
    from fontTools.ttLib import TTFont, TTCollection
    from fontTools.varLib import instancer
    src = argv[argv.index("--src") + 1] if "--src" in argv else SRC
    if src.endswith(".ttc"):
        font = next(f for f in TTCollection(src).fonts if "JP" in f["name"].getDebugName(1))
    else:
        font = TTFont(src)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": 700})
    em = float(font["head"].unitsPerEm)
    glyphs, bad = {}, 0
    for ch in chars:
        cs = contours(font, ch)
        if not cs:
            print("build_paint_glyphs: NOT IN THE FACE: %s" % ch)
            bad = 1
            continue
        w, h, tris, area = triangles(cs, em)
        # the triangles must cover the ink and nothing else
        got = sum(abs(0.5 * ((tris[i + 1][0] - tris[i][0]) * (tris[i + 2][1] - tris[i][1])
                             - (tris[i + 2][0] - tris[i][0]) * (tris[i + 1][1] - tris[i][1])))
                  for i in range(0, len(tris), 3))
        assert abs(got - area) < 0.01 * area, (ch, got, area)
        glyphs[ch] = {"w": w, "h": h, "tris": [list(p) for p in tris]}
    doc = {"font": "Noto Sans CJK JP, weight 700 (SIL Open Font License 1.1)", "glyphs": glyphs}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print("build_paint_glyphs: %d characters, %d triangles -> %s (%d KB)" % (
        len(glyphs), sum(len(g["tris"]) // 3 for g in glyphs.values()), os.path.relpath(OUT, ROOT),
        os.path.getsize(OUT) // 1024))
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
