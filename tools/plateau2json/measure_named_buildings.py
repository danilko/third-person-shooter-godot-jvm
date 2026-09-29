#!/usr/bin/env python3
"""measure_named_buildings.py -- sizes of NAMED Japanese public buildings, measured from raw PLATEAU CityGML.

    python3 tools/plateau2json/measure_named_buildings.py <citygml dir or .zip> [...] [--json out.json]

A PLATEAU building of public interest carries its name (`gml:name`: 麹町警察署, 虎の門病院, 麹町警察署九段下交番,
...), so a class here is a NAME pattern (plus a use code for the defence buildings, which are rarely named), and
the output is percentiles of plan size (minimum-area rectangle: short side, long side), footprint area, height,
storeys and height per storey. PLATEAU (CC BY 4.0) is a MEASUREMENT reference only: nothing but rounded statistics
from this output enters the repo (CLAUDE.md, the map-data licence rule; credited in CREDITS.md "Real-world data").
"""
import json
import re
import sys

import measure_building_types as mb

TAG_NAME = re.compile(r"<gml:name[^>]*>([^<]+)</gml:name>")

# class: (description, name regex or None, usage codes or None, extra predicate(storeys, area) or None)
CLASSES = {
    "police_station": ("警察署 (the station itself, not its boxes)", r"警察署$", None, None),
    "koban":          ("交番 / 駐在所 (police box)", r"(交番|駐在所)$", None, None),
    "fire_station":   ("消防署 (a main station)", r"消防署$", None, None),
    "fire_branch":    ("消防出張所 / 分署", r"消防.*(出張所|分署)$", None, None),
    "hospital":       ("病院 (a hospital: 20+ beds; the large ones)", r"病院$", None, lambda s, a: a >= 800),
    "clinic":         ("診療所 / クリニック / 医院 (stand-alone)", r"(診療所|クリニック|医院)$", None, None),
    "elementary":     ("小学校", r"小学校$", None, None),
    "junior_high":    ("中学校", r"中学校$", None, None),
    "post_office":    ("郵便局", r"郵便局$", None, None),
    "ward_office":    ("区役所 / 市役所 / 庁舎", r"(区役所|市役所|庁舎)$", None, None),
    "hotel":          ("ホテル (named, 6+ storeys)", r"ホテル", None, lambda s, a: s >= 6),
    "shrine":         ("神社 (the hall)", r"神社$", None, None),
    "temple":         ("寺 / 院 (the hall)", r"(寺|院)$", None, lambda s, a: s <= 3),
    "market":         ("市場 (a wholesale / fish market hall)", r"市場", None, lambda s, a: a >= 2000),
    "defence":        ("防衛施設 (use 454, any name)", None, {"454"}, None),
    "hangar":         ("格納庫 (hangar)", r"格納庫", None, None),
    "gym":            ("体育館 (a gym)", r"体育館$", None, None),
}


def main(argv):
    out_json = None
    if "--json" in argv:
        i = argv.index("--json")
        out_json = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        raise SystemExit(__doc__)
    rows = {k: [] for k in CLASSES}
    total = 0
    for src in argv:
        for b in mb.buildings(src):
            total += 1
            nm = TAG_NAME.search(b)
            name = nm.group(1).strip() if nm else ""
            u = (mb.TAG_USAGE.search(b) or [None, ""])[1]
            sm, hm = mb.TAG_STOREYS.search(b), mb.TAG_HEIGHT.search(b)
            if not hm:
                continue
            s, h = (int(sm.group(1)) if sm else 0), float(hm.group(1))
            ring = mb.LOD0.search(b) or mb.LOD1.search(b)
            if not ring:
                continue
            poly = mb.ring_xy(ring.group(1))
            if len(poly) < 3:
                continue
            a = mb.area(poly)
            for k, (_, rx, uses, pred) in CLASSES.items():
                if rx is not None and not (name and re.search(rx, name)):
                    continue
                if uses is not None and u not in uses:
                    continue
                if pred is not None and not pred(s, a):
                    continue
                r = mb.min_rect(poly)
                if r:
                    rows[k].append({"short": r[0], "long": r[1], "area": a, "height": h, "storeys": s})
    report = {"sources": [src.rstrip("/").split("/")[-1] for src in argv], "buildings_read": total, "classes": {}}
    print("%d buildings read" % total)
    for k, (desc, *_r) in CLASSES.items():
        rs = rows[k]
        entry = {"description": desc, "count": len(rs)}
        line = "%-15s n=%-4d" % (k, len(rs))
        for f in ("short", "long", "area", "height", "storeys"):
            vals = [r[f] for r in rs if not (f == "storeys" and not r[f])]
            entry[f] = [round(mb.pct(vals, q), 1) if vals else None for q in (0.25, 0.5, 0.75)]
            line += " %s %s" % (f, entry[f])
        sh = [r["height"] / r["storeys"] for r in rs if r["storeys"]]
        entry["height_per_storey"] = [round(mb.pct(sh, q), 2) if sh else None for q in (0.25, 0.5, 0.75)]
        print(line + " h/st %s" % entry["height_per_storey"])
        report["classes"][k] = entry
    if out_json:
        json.dump(report, open(out_json, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
