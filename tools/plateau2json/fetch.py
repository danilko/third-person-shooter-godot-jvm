#!/usr/bin/env python3
"""Download PLATEAU datasets for a list of wards, straight from the official catalogue.

Resource URLs are resolved live through the G-Spatial Information Center CKAN API
rather than hardcoded — the asset hashes in a PLATEAU download URL are opaque and
change between publications, so a baked-in list rots.

    python3 fetch.py --wards 13101 13102 13103 13108 13109 13111 13113 --year 2025
    python3 fetch.py --wards 13103 --list-only          # just show what's published

Downloads land in --dest (default /data/danilko/plateau_model), never in the repo —
raw CityGML zips are multi-GB.  After each extraction the script prints the dataset's
actual `udx/` module list and a feature census, so `wtr` (waterbody) / `tran:Railway`
presence is *verified* rather than assumed.

Data: Project PLATEAU (MLIT), CC BY 4.0 — credit "Data: Project PLATEAU (MLIT)".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import zipfile

CKAN = "https://www.geospatial.jp/ckan/api/3/action/package_show?id="

# ward code -> the slug PLATEAU uses in its CKAN dataset id
WARD_SLUGS = {
    "13101": "chiyoda-ku", "13102": "chuo-ku", "13103": "minato-ku",
    "13104": "shinjuku-ku", "13105": "bunkyo-ku", "13106": "taito-ku",
    "13107": "sumida-ku", "13108": "koto-ku", "13109": "shinagawa-ku",
    "13110": "meguro-ku", "13111": "ota-ku", "13112": "setagaya-ku",
    "13113": "shibuya-ku", "13114": "nakano-ku", "13115": "suginami-ku",
    "13116": "toshima-ku", "13117": "kita-ku", "13118": "arakawa-ku",
    "13119": "itabashi-ku", "13120": "nerima-ku", "13121": "adachi-ku",
    "13122": "katsushika-ku", "13123": "edogawa-ku",
}

# Modules that decide whether a download is worth it for this project.
INTERESTING = ("tran", "wtr", "dem", "luse", "bldg", "brid", "rwy", "veg", "frn")


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "plateau2json/1.0"})
    with urllib.request.urlopen(req, timeout=120) as fh:
        return json.load(fh)


def resources(ward: str, year: int) -> list[dict]:
    slug = WARD_SLUGS.get(ward)
    if not slug:
        raise SystemExit(f"unknown ward code {ward}; known: {sorted(WARD_SLUGS)}")
    pkg = f"plateau-{ward}-{slug}-{year}"
    data = fetch_json(CKAN + pkg)
    if not data.get("success"):
        raise SystemExit(f"CKAN lookup failed for {pkg}")
    return data["result"].get("resources", [])


def pick(res: list[dict], *needles: str):
    """First resource whose name or URL contains all the needles."""
    for r in res:
        hay = f"{r.get('name', '')} {r.get('url', '')}".lower()
        if all(n.lower() in hay for n in needles):
            return r
    return None


def download(url: str, dest: str) -> str:
    path = os.path.join(dest, os.path.basename(url.split("?")[0]))
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"    have  {os.path.basename(path)} ({os.path.getsize(path) / 1e9:.2f} GB)")
        return path
    tmp = path + ".part"
    print(f"    get   {os.path.basename(path)} …", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "plateau2json/1.0"})
    # Progress is carriage-returned on a terminal, but redirected to a file `\r` does
    # nothing and a per-MB line floods the log — so off a tty we emit one line per 10%.
    tty = sys.stdout.isatty()
    with urllib.request.urlopen(req, timeout=300) as src, open(tmp, "wb") as out:
        total = int(src.headers.get("Content-Length") or 0)
        done = 0
        step = 0
        while chunk := src.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if not total:
                continue
            pct = done / total * 100
            if tty:
                print(f"\r      {done / 1e9:.2f}/{total / 1e9:.2f} GB ({pct:.0f}%)",
                      end="", flush=True)
            elif pct >= step:
                print(f"      {done / 1e9:.2f}/{total / 1e9:.2f} GB ({pct:.0f}%)", flush=True)
                step += 10
    if tty:
        print()
    os.rename(tmp, path)
    return path


def report_zip(path: str) -> None:
    """Print the udx module list, and which of the interesting ones are present."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        print(f"    !! {os.path.basename(path)} is not a readable zip")
        return
    modules = sorted({m.group(1) for n in names
                      if (m := re.search(r"udx/([a-z]+)/", n))})
    print(f"    udx modules: {', '.join(modules) or '(none)'}")
    for mod in INTERESTING:
        mark = "yes" if mod in modules else "-- "
        if mod in modules:
            count = sum(1 for n in names if f"udx/{mod}/" in n and n.endswith(".gml"))
            print(f"      {mod:5s} {mark}  ({count} tiles)")
    extras = [n for n in names if n.lower().endswith(".geojson")]
    if extras:
        print(f"    geojson sidecars: {', '.join(sorted(os.path.basename(e) for e in extras))}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wards", nargs="+", required=True,
                    help="5-digit ward codes, e.g. 13103 (Minato) 13111 (Ota)")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--dest", default="/data/danilko/plateau_model")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--with-related", action="store_true", default=True,
                    help="also fetch the small 'related' zip — it carries the official "
                         "railway / station / landmark GeoJSON layers")
    ap.add_argument("--extract", action="store_true",
                    help="unzip the CityGML archive after download")
    args = ap.parse_args()

    os.makedirs(args.dest, exist_ok=True)

    for ward in args.wards:
        print(f"\n=== {ward} ({WARD_SLUGS.get(ward, '?')}) {args.year} ===")
        try:
            res = resources(ward, args.year)
        except SystemExit as exc:
            print(f"  {exc}")
            continue
        except Exception as exc:                       # network / catalogue hiccup
            print(f"  lookup failed: {type(exc).__name__}: {exc}")
            continue

        for r in res:
            print(f"  - {r.get('name')} [{r.get('format')}]")

        if args.list_only:
            continue

        citygml = pick(res, "citygml", ".zip") or pick(res, "citygml")
        if not citygml:
            print("  !! no CityGML resource published for this ward/year")
        else:
            path = download(citygml["url"], args.dest)
            report_zip(path)
            if args.extract:
                out = os.path.join(args.dest, os.path.basename(path)[:-4])
                if not os.path.isdir(out):
                    print(f"    unzip -> {out}")
                    with zipfile.ZipFile(path) as zf:
                        zf.extractall(out)

        if args.with_related:
            related = pick(res, "related", ".zip")
            if related:
                path = download(related["url"], args.dest)
                report_zip(path)

    print("\nAll data: Project PLATEAU (MLIT), CC BY 4.0 — "
          'credit "Data: Project PLATEAU (MLIT)" in any public build.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
