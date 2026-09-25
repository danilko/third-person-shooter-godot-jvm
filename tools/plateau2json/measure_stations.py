#!/usr/bin/env python3
"""measure_stations.py -- how big a Japanese railway station is, measured from raw PLATEAU CityGML.

    python3 tools/plateau2json/measure_stations.py <ward citygml dir> <ward *_related.zip> [<dir> <zip> ...]
                                                  [--radius 260] [--only 東京駅,品川駅] [--json out.json]

PLATEAU is a MEASUREMENT source (CC BY 4.0, credited in CREDITS.md "Real-world data"), never shipped data: this
reads the raw download outside the repo and prints numbers only. Rounded numbers from its output are what go into
the building table (PLAN.md 3.36, C0/B4 -- the user's ask: "use Tokyo Station and other stations from PLATEAU for
data/sizing; an artist rebuilds the models later").

A station has no footprint of its own in PLATEAU. What it has:
* a POINT per station and line, with its name, in the ward's `*_station.geojson` (inside `*_related.zip`);
* the rail LINES as centrelines, one per route, in `*_railway.geojson` (Z = 0; no track or platform count);
* the BUILDINGS, whose use code says transport (`bldg:usage` 431 / `uro:detailedUsage` 1431): the station
  building, and at the big stations the platform roofs and concourse blocks too.
So a station here is measured as: every transport-use building whose footprint centroid is within `--radius` of
the station's point, reported one by one (the largest is the station building) and as their union's extent along
and across the rail; plus how many distinct routes pass within 120 m of the point, and how wide that bundle is
across its own direction -- which, for a through station, IS the width of the track-and-platform band.
"""
import json
import math
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure_building_types import (BUILDING, LOD0, LOD1, TAG_DET, TAG_HEIGHT, TAG_STOREYS, TAG_USAGE,  # noqa: E402
                                    area, min_rect)

TRANSPORT = {"431"}
TRANSPORT_D = {"1431", "431"}
NAME = re.compile(r"<gml:name>(.*?)</gml:name>")
K_LAT = 110574.0


def k_lon(lat):
    return 111320.0 * math.cos(math.radians(lat))


def ring_ll(poslist):
    v = [float(x) for x in poslist.split()]
    return [(v[i], v[i + 1]) for i in range(0, len(v) - 2, 3)]      # (lat, lon)


def related(zpath):
    zf = zipfile.ZipFile(zpath)
    st, rw = [], []
    for n in zf.namelist():
        if n.endswith("_station.geojson"):
            st = json.loads(zf.read(n))["features"]
        elif n.endswith("_railway.geojson"):
            rw = json.loads(zf.read(n))["features"]
    return st, rw


def stations(features):
    """{station name: (lat, lon, [routes])} -- one entry per NAME (a hub has a point per line; they are averaged)."""
    acc = {}
    for f in features:
        p = f["properties"]
        name = p.get("駅名")
        g = f.get("geometry") or {}
        if not name or g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        a = acc.setdefault(name, [0.0, 0.0, 0, set()])
        a[0] += lat
        a[1] += lon
        a[2] += 1
        a[3].add(p.get("路線名", ""))
    return {n: (a[0] / a[2], a[1] / a[2], sorted(a[3])) for n, a in acc.items()}


def line_parts(rw):
    """[(route name, [(lat, lon)])] for every LineString part of the railway layer."""
    out = []
    for f in rw:
        g = f.get("geometry") or {}
        name = f["properties"].get("路線名", "")
        parts = [g["coordinates"]] if g.get("type") == "LineString" else g.get("coordinates", []) \
            if g.get("type") == "MultiLineString" else []
        for part in parts:
            out.append((name, [(c[1], c[0]) for c in part]))
    return out


def rail_bundle(parts, lat, lon, reach=120.0):
    """Routes passing within `reach` m of the point, the bundle's direction, and its width ACROSS that direction
    (the spread of the routes' nearest points)."""
    kx = k_lon(lat)
    near = {}
    for name, pts in parts:
        best = None
        for (a_lat, a_lon), (b_lat, b_lon) in zip(pts, pts[1:]):
            ax, ay = (a_lon - lon) * kx, (a_lat - lat) * K_LAT
            bx, by = (b_lon - lon) * kx, (b_lat - lat) * K_LAT
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
            px, py = ax + dx * t, ay + dy * t
            d = math.hypot(px, py)
            if best is None or d < best[0]:
                best = (d, (px, py), (dx, dy))
        if best and best[0] <= reach:
            if name not in near or best[0] < near[name][0]:
                near[name] = best
    if not near:
        return [], None, 0.0
    # the bundle's direction: the length-weighted mean of the segment directions (sign-folded)
    sx = sy = 0.0
    for _d, _p, (dx, dy) in near.values():
        a = math.atan2(dy, dx) * 2.0
        L = math.hypot(dx, dy)
        sx += math.cos(a) * L
        sy += math.sin(a) * L
    th = math.atan2(sy, sx) / 2.0
    nx, ny = -math.sin(th), math.cos(th)
    across = [p[0] * nx + p[1] * ny for _d, p, _s in near.values()]
    return sorted(near), math.degrees(th), max(across) - min(across)


def main(argv):
    out_json, radius, only = None, 260.0, None
    for flag in ("--json", "--radius", "--only"):
        if flag in argv:
            i = argv.index(flag)
            v = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
            if flag == "--json":
                out_json = v
            elif flag == "--radius":
                radius = float(v)
            else:
                only = set(v.split(","))
    if len(argv) < 2 or len(argv) % 2:
        raise SystemExit(__doc__)
    report = {}
    for gml_dir, zpath in zip(argv[0::2], argv[1::2]):
        st_f, rw_f = related(zpath)
        sts = stations(st_f)
        if only:
            sts = {n: v for n, v in sts.items() if n in only}
        parts = line_parts(rw_f)
        if not sts:
            continue
        found = {n: [] for n in sts}
        bdir = os.path.join(gml_dir, "udx", "bldg")
        for fn in sorted(os.listdir(bdir)):
            if not fn.endswith(".gml"):
                continue
            text = open(os.path.join(bdir, fn), encoding="utf-8", errors="replace").read()
            for m in BUILDING.finditer(text):
                b = m.group(1)
                u = (TAG_USAGE.search(b) or [None, ""])[1]
                d = (TAG_DET.search(b) or [None, ""])[1]
                if u not in TRANSPORT and d not in TRANSPORT_D:
                    continue
                ring = LOD0.search(b) or LOD1.search(b)
                if not ring:
                    continue
                ll = ring_ll(ring.group(1))
                if len(ll) < 3:
                    continue
                clat = sum(p[0] for p in ll) / len(ll)
                clon = sum(p[1] for p in ll) / len(ll)
                for n, (slat, slon, _r) in sts.items():
                    kx = k_lon(slat)
                    if math.hypot((clon - slon) * kx, (clat - slat) * K_LAT) > radius:
                        continue
                    xy = [((p[1] - slon) * kx, (p[0] - slat) * K_LAT) for p in ll]
                    hm, sm = TAG_HEIGHT.search(b), TAG_STOREYS.search(b)
                    nm = NAME.search(b)
                    found[n].append(dict(xy=xy, area=area(xy), rect=min_rect(xy),
                                         h=float(hm.group(1)) if hm else None,
                                         s=int(sm.group(1)) if sm else None, name=nm.group(1) if nm else ""))
        for n, (slat, slon, routes) in sorted(sts.items()):
            routes_near, th, width = rail_bundle(parts, slat, slon)
            bs = sorted(found[n], key=lambda r: -r["area"])
            row = dict(ward=os.path.basename(gml_dir.rstrip("/")), routes=routes, rail_routes_120m=routes_near,
                       rail_dir_deg=None if th is None else round(th, 1), rail_bundle_width_m=round(width, 1),
                       transport_buildings=len(bs), transport_area_m2=round(sum(r["area"] for r in bs)))
            if bs and th is not None:
                # the union's extent ALONG and ACROSS the rail
                ux, uy = math.cos(math.radians(th)), math.sin(math.radians(th))
                us = [p[0] * ux + p[1] * uy for r in bs for p in r["xy"]]
                vs = [-p[0] * uy + p[1] * ux for r in bs for p in r["xy"]]
                row["extent_along_m"] = round(max(us) - min(us), 1)
                row["extent_across_m"] = round(max(vs) - min(vs), 1)
            row["largest"] = [dict(area_m2=round(r["area"]), short_m=round(r["rect"][0], 1) if r["rect"] else None,
                                   long_m=round(r["rect"][1], 1) if r["rect"] else None, height_m=r["h"],
                                   storeys=r["s"], name=r["name"]) for r in bs[:5]]
            report[n] = row
            lg = row["largest"][0] if row["largest"] else {}
            print("%-14s routes %-2d near %-2d bundle %6.1f m | %3d bldgs %7d m2 | along %6s across %6s | "
                  "largest %s x %s m h %s s %s %s" % (
                      n, len(routes), len(routes_near), width, len(bs), row["transport_area_m2"],
                      row.get("extent_along_m", "-"), row.get("extent_across_m", "-"),
                      lg.get("short_m"), lg.get("long_m"), lg.get("height_m"), lg.get("storeys"), lg.get("name", "")))
    if out_json:
        with open(out_json, "w") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
