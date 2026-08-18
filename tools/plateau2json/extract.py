#!/usr/bin/env python3
"""PLATEAU CityGML -> per-layer 3D JSON.

Pulls roads (with per-lane TrafficArea surfaces), railways (incl. per-direction track
centrelines), buildings, terrain, land use, water and bridges out of Project PLATEAU
CityGML tiles into a plain JSON intermediate that a downstream Blender generator can
consume without knowing anything about CityGML.

    python3 extract.py --input /data/danilko/plateau_model/13111_ota-ku_city_2023_citygml_1_op \
                       --out   build/plateau_json \
                       --layers road,rail,building,terrain,landuse,water,bridge \
                       --bbox 139.69 35.540 139.81 35.700

Data: Project PLATEAU (MLIT), CC BY 4.0.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citygml import CodeLists, Projector, harvest, iter_features, local  # noqa: E402

ATTRIBUTION = "Data: Project PLATEAU (MLIT), CC BY 4.0"

# layer -> (udx module dir, {feature local tag names})
#
# Geometry harvesting is LOD-agnostic: `citygml.harvest` records whatever `lodN…`
# element it walks into, so LOD3/LOD4 solids and interiors come through with no code
# change the moment a dataset authors them — each shape carries its own `lod` string.
LAYERS = {
    "road":       ("tran", {"Road", "Square"}),
    "rail":       ("tran", {"Railway", "Track"}),
    "building":   ("bldg", {"Building"}),
    "terrain":    ("dem",  {"ReliefFeature"}),
    "landuse":    ("luse", {"LandUse"}),
    "water":      ("wtr",  {"WaterBody", "WaterSurface", "WaterGroundSurface"}),
    "bridge":     ("brid", {"Bridge"}),
    "tunnel":     ("tun",  {"Tunnel"}),
    "furniture":  ("frn",  {"CityFurniture"}),
    "vegetation": ("veg",  {"SolitaryVegetationObject", "PlantCover"}),
    "underground": ("ubld", {"UndergroundBuilding", "Building"}),
    "area":       ("area", {"Zone", "GenericCityObject", "CityObjectGroup"}),
    "cityplan":   ("urf",  {"UseDistrict", "HeightControlDistrict",
                            "FirePreventionDistrict", "DistrictsAndZones"}),
}

# Every layer worth pulling for a full city rebuild, in one flag.
ALL_LAYERS = ",".join(LAYERS)

# Road_function codes -> lanes per direction, used only as a hint for LOD1-only tiles
# where no TrafficArea (code 1010 = 車線) geometry exists.  Real lanes always win.
LANES_BY_FUNCTION = {
    "1": 4,    # 高速自動車国道   national expressway
    "5": 4,    # 都市高速道路     urban expressway (Shuto)
    "2": 3,    # 一般国道
    "3": 3,    # 都道府県道
    "4": 2,    # 市町村道
}
LANES_BY_WIDTH = {
    "1": 3,    # >= 15 m
    "2": 2,    # 6-15 m
    "3": 1,    # 4-6 m
    "4": 1,    # < 4 m
}

# TrafficArea function codes that mean "this is rail, not road".
RAIL_TRAFFIC_CODES = {"1040", "1050", "8000", "8100", "8110", "8111", "8112", "8120"}

SHINKANSEN_HINTS = ("新幹線",)

# PLATEAU's per-ward "related dataset" zip ships official GeoJSON sidecars.  The
# railway one is where the *rail network actually lives* for the Tokyo wards: the
# CityGML `tran` module here authors roads only (0 `tran:Railway` features across all
# 751 local tran tiles), while `*_railway.geojson` carries every line as a WGS84
# LineString tagged 路線名 / 運営会社 / 鉄道区分 — including 東海道新幹線, the bullet train.
# Same dataset, same MLIT CC BY 4.0 licence.  Geometry is 2D, so Z comes out 0 and the
# track needs draping onto the terrain layer downstream.
GEOJSON_SIDECARS = {
    "railway": "rail",
    "station": "station",
    "landmark": "landmark",
}

JP_PROPS = {
    "路線名": "route_name",
    "運営会社": "operator",
    "鉄道区分": "railway_class",
    "事業者種別": "operator_type",
    "行政区域": "admin_area",
    "名称": "name",
}


# ---------------------------------------------------------------------------


def discover_tiles(inputs: list[str], module: str) -> list[str]:
    """Find the .gml tiles for one udx module across the given dataset roots."""
    found: list[str] = []
    for item in inputs:
        if os.path.isfile(item):
            if f"_{module}_" in os.path.basename(item):
                found.append(item)
            continue
        # dataset root (…/udx/<module>/*.gml), or a bare directory of tiles
        patterns = [
            os.path.join(item, "udx", module, "*.gml"),
            os.path.join(item, "udm", module, "*.gml"),   # alternate layout
            os.path.join(item, module, "*.gml"),
            os.path.join(item, "*.gml"),
        ]
        for pat in patterns:
            hits = sorted(glob.glob(pat))
            if pat.endswith(os.path.join("*.gml")) and pat.count(module) == 0:
                hits = [h for h in hits if f"_{module}_" in os.path.basename(h)]
            if hits:
                found.extend(hits)
                break
    return sorted(set(found))


# Set by --lods: keep only geometry whose `lod` contains one of these substrings.
# A full-city pull with every LOD2/3 solid is tens of GB of JSON.
#
# The filter is *per layer* (`--lods road=lod1,lod2 building=lod0RoofEdge`) because one
# global list cannot serve both: `lod2MultiSurface` means "the traffic-area surface I
# want" on a road and "every wall panel of every building" on a building — a single
# shared filter pulls ~4 M wall polygons across seven wards and never finishes.
# `--lods lod0RoofEdge,lod1` (no `=`) still works and applies to every layer.
LOD_FILTER: dict[str, list[str]] = {}
_ACTIVE_LOD_FILTER: list[str] = []


def parse_lod_filter(spec: str) -> dict[str, list[str]]:
    """`road=lod1,lod2MultiSurface building=lod0RoofEdge` or a bare shared list."""
    out: dict[str, list[str]] = {}
    for token in spec.split():
        if "=" in token:
            layer, _, lods = token.partition("=")
            out[layer.strip()] = [x.strip() for x in lods.split(",") if x.strip()]
        else:
            out.setdefault("*", []).extend(x.strip() for x in token.split(",") if x.strip())
    return out


def geoms_to_json(geoms) -> list[dict]:
    out = []
    for g in geoms:
        if len(g.coords) < 2:
            continue
        if _ACTIVE_LOD_FILTER and not any(f in (g.lod or "") for f in _ACTIVE_LOD_FILTER):
            continue
        rec = {"lod": g.lod, "kind": g.kind, "points": [list(p) for p in g.coords]}
        if g.role:
            rec["role"] = g.role
        if g.hole:
            rec["hole"] = True
        out.append(rec)
    return out


def scalar(scalars, name):
    hit = scalars.get(name)
    return hit[0] if hit else None


def coded(codelists, path, scalars, name):
    hit = scalars.get(name)
    if not hit:
        return None
    return codelists.resolve(path, hit[1], hit[0])


def first_lonlat(elem):
    """First (lon, lat) of a feature, read straight off the raw XML.

    Used for the --bbox test, which must run on geographic coordinates *before*
    projection — and cheaply, since most features in a large tile get rejected.
    """
    for node in elem.iter():
        if local(node.tag) in ("posList", "pos") and node.text:
            parts = node.text.split()
            if len(parts) >= 2:
                return float(parts[1]), float(parts[0])   # lat lon -> lon lat
    return None


def in_bbox(lonlat, bbox) -> bool:
    if lonlat is None:
        return False
    lon, lat = lonlat
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


# ---------------------------------------------------------------------------
# per-layer record builders
# ---------------------------------------------------------------------------


def build_road(elem, scalars, geoms, codelists, path, projector):
    function = coded(codelists, path, scalars, "function")
    width = coded(codelists, path, scalars, "widthType")
    section = coded(codelists, path, scalars, "sectionType")

    lanes = LANES_BY_FUNCTION.get(function["code"] if function else None)
    if lanes is None:
        lanes = LANES_BY_WIDTH.get(width["code"] if width else None, 2)

    rec = {
        "id": elem.get("{http://www.opengis.net/gml}id") or elem.get("id"),
        "type": local(elem.tag),
        "function": function,
        "usage": coded(codelists, path, scalars, "usage"),
        "road_class": coded(codelists, path, scalars, "class"),
        "width_type": width,
        "section_type": section,
        "lanes_per_direction_hint": lanes,
        "geometry": geoms_to_json(geoms),
        "traffic_areas": [],
    }

    # nested TrafficArea / AuxiliaryTrafficArea — these carry the real lane surfaces
    for child in elem.iter():
        name = local(child.tag)
        if name not in ("TrafficArea", "AuxiliaryTrafficArea"):
            continue
        ta_geoms, ta_scalars = harvest(child, projector, stop_at_nested=False)
        ta_fn = coded(codelists, path, ta_scalars, "function")
        rec["traffic_areas"].append({
            "id": child.get("{http://www.opengis.net/gml}id"),
            "type": name,
            "function": ta_fn,
            "surface_material": coded(codelists, path, ta_scalars, "surfaceMaterial"),
            "is_rail": bool(ta_fn and ta_fn["code"] in RAIL_TRAFFIC_CODES),
            "is_lane": bool(ta_fn and ta_fn["code"] == "1010"),
            "geometry": geoms_to_json(ta_geoms),
        })
    return rec


def build_rail(elem, scalars, geoms, codelists, path, projector):
    route = scalar(scalars, "routeName") or scalar(scalars, "name")
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "type": local(elem.tag),
        "function": coded(codelists, path, scalars, "function"),
        "route_name": route,
        "operator": coded(codelists, path, scalars, "operatorType"),
        "railway_type": coded(codelists, path, scalars, "railwayType"),
        "track_type": coded(codelists, path, scalars, "trackType"),
        "direction_type": coded(codelists, path, scalars, "directionType"),
        "alignment_type": coded(codelists, path, scalars, "alignmentType"),
        "is_shinkansen": bool(route and any(h in route for h in SHINKANSEN_HINTS)),
        "geometry": geoms_to_json(geoms),
    }


def build_building(elem, scalars, geoms, codelists, path, projector):
    height = scalar(scalars, "measuredHeight")
    storeys = scalar(scalars, "storeysAboveGround")
    below = scalar(scalars, "storeysBelowGround")
    geometry = geoms_to_json(geoms)
    # Which LODs this building actually carries — the fastest way to see whether a
    # dataset gave you LOD1 boxes or real LOD2/3 (and LOD4 interiors, if ever authored).
    lods = sorted({g["lod"] for g in geometry if g.get("lod")})
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "building_id": scalar(scalars, "buildingID"),
        "name": scalar(scalars, "name"),
        "measured_height": float(height) if height else None,
        "storeys_above_ground": int(storeys) if storeys and storeys.isdigit() else None,
        "storeys_below_ground": int(below) if below and below.isdigit() else None,
        "year_of_construction": scalar(scalars, "yearOfConstruction"),
        "usage": coded(codelists, path, scalars, "usage"),
        "building_class": coded(codelists, path, scalars, "class"),
        "roof_type": coded(codelists, path, scalars, "roofType"),
        "address": scalar(scalars, "LocalityName"),
        "lods": lods,
        "geometry": geometry,
    }


def build_generic(elem, scalars, geoms, codelists, path, projector):
    """Fallback record for the smaller modules (furniture, vegetation, tunnels, …).

    Keeps the same shape as every other layer so downstream tools need no special case;
    anything module-specific stays available under `attributes`.
    """
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "type": local(elem.tag),
        "name": scalar(scalars, "name"),
        "function": coded(codelists, path, scalars, "function"),
        "usage": coded(codelists, path, scalars, "usage"),
        "object_class": coded(codelists, path, scalars, "class"),
        "attributes": {k: v[0] for k, v in scalars.items()},
        "geometry": geoms_to_json(geoms),
    }


def build_terrain(elem, scalars, geoms, codelists, path, projector):
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "name": scalar(scalars, "name"),
        "lod": scalar(scalars, "lod"),
        "triangles": [[list(p) for p in g.coords] for g in geoms if len(g.coords) >= 3],
    }


def build_landuse(elem, scalars, geoms, codelists, path, projector):
    cls = coded(codelists, path, scalars, "class")
    org = coded(codelists, path, scalars, "orgLandUse")
    code = (cls or {}).get("code")
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "land_use_type": cls,
        "org_land_use": org,
        "is_water": code in ("204", "205"),
        "city": scalar(scalars, "city"),
        "geometry": geoms_to_json(geoms),
    }


def build_water(elem, scalars, geoms, codelists, path, projector):
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "type": local(elem.tag),
        "function": coded(codelists, path, scalars, "function"),
        "water_class": coded(codelists, path, scalars, "class"),
        "geometry": geoms_to_json(geoms),
    }


def build_bridge(elem, scalars, geoms, codelists, path, projector):
    return {
        "id": elem.get("{http://www.opengis.net/gml}id"),
        "function": coded(codelists, path, scalars, "function"),
        "bridge_class": coded(codelists, path, scalars, "class"),
        "geometry": geoms_to_json(geoms),
    }


def read_geojson_sidecars(paths: list[str], projector, bbox):
    """Read PLATEAU `related` GeoJSON sidecars into the same record shape as CityGML.

    Accepts .geojson files, directories of them, or the `*_related.zip` straight from
    fetch.py — no unzipping step needed.
    """
    import zipfile

    blobs: list[tuple[str, dict]] = []
    for item in paths:
        if os.path.isdir(item):
            for p in sorted(glob.glob(os.path.join(item, "*.geojson"))):
                with open(p, encoding="utf-8") as fh:
                    blobs.append((os.path.basename(p), json.load(fh)))
        elif item.endswith(".zip"):
            with zipfile.ZipFile(item) as zf:
                for n in zf.namelist():
                    if n.lower().endswith(".geojson"):
                        blobs.append((os.path.basename(n), json.loads(zf.read(n))))
        elif item.endswith(".geojson"):
            with open(item, encoding="utf-8") as fh:
                blobs.append((os.path.basename(item), json.load(fh)))

    out: dict[str, list[dict]] = {}
    for fname, blob in blobs:
        layer = next((v for k, v in GEOJSON_SIDECARS.items() if k in fname.lower()), None)
        if layer is None:
            continue
        for feat in blob.get("features", []):
            geom = feat.get("geometry") or {}
            gtype = geom.get("type")
            coords = geom.get("coords") or geom.get("coordinates") or []
            lines = ([coords] if gtype == "LineString" else
                     coords if gtype == "MultiLineString" else
                     [[coords]] if gtype == "Point" else [])
            if gtype == "Point":
                lines = [[coords]]
            if not lines:
                continue
            if bbox and not (bbox[0] <= lines[0][0][0] <= bbox[2]
                             and bbox[1] <= lines[0][0][1] <= bbox[3]):
                continue
            props = {JP_PROPS.get(k, k): v for k, v in (feat.get("properties") or {}).items()}
            route = props.get("route_name") or props.get("name")
            rec = {
                "id": feat.get("id") or f"{layer}_{len(out.get(layer, []))}",
                "type": layer,
                "source": f"plateau_related/{fname}",
                "route_name": route,
                "operator": props.get("operator"),
                "railway_class": props.get("railway_class"),
                "is_shinkansen": bool(route and any(h in route for h in SHINKANSEN_HINTS)),
                "properties": props,
                "geometry": [{
                    "lod": "geojson", "kind": "line",
                    "points": [list(projector.to_metres(c[0], c[1],
                                                        c[2] if len(c) > 2 else 0.0))
                               for c in line],
                } for line in lines if len(line) >= 1],
            }
            out.setdefault(layer, []).append(rec)
    return out


BUILDERS = {
    "road": build_road,
    "rail": build_rail,
    "building": build_building,
    "underground": build_building,
    "terrain": build_terrain,
    "landuse": build_landuse,
    "water": build_water,
    "bridge": build_bridge,
}


def builder_for(layer):
    return BUILDERS.get(layer, build_generic)


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", nargs="+", required=True,
                    help="dataset root(s) containing udx/, a tile directory, or .gml files")
    ap.add_argument("--out", default="build/plateau_json")
    ap.add_argument("--layers", default="road,rail,building,terrain,landuse,water,bridge",
                    help="comma list, or 'all' for every module this dataset ships")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("LON0", "LAT0", "LON1", "LAT1"),
                    help="WGS84 crop; features whose first vertex falls outside are skipped")
    ap.add_argument("--origin", nargs=2, type=float, metavar=("LON", "LAT"),
                    help="local metric origin (default: bbox centre, else 139.77/35.62)")
    ap.add_argument("--format", choices=("json", "jsonl"), default="json")
    ap.add_argument("--census-only", action="store_true",
                    help="parse and report counts/histograms without writing geometry")
    ap.add_argument("--limit-tiles", type=int, default=0, help="debug: stop after N tiles per layer")
    ap.add_argument("--lods", default="",
                    help="LOD substrings to keep, dropped at write time so a whole-city "
                         "pull stays a sane size. Per layer: "
                         "'road=lod1,lod2 building=lod0RoofEdge', or a bare shared list.")
    ap.add_argument("--related", nargs="*", default=[],
                    help="PLATEAU 'related dataset' zips/dirs/.geojson files — this is "
                         "where the railway network (incl. 東海道新幹線) actually lives")
    args = ap.parse_args()

    global LOD_FILTER
    LOD_FILTER = parse_lod_filter(args.lods)

    layers = (list(LAYERS) if args.layers.strip() == "all"
              else [l.strip() for l in args.layers.split(",") if l.strip()])
    unknown = [l for l in layers if l not in LAYERS]
    if unknown:
        print(f"unknown layer(s): {unknown}; known: {sorted(LAYERS)}", file=sys.stderr)
        return 2

    if args.origin:
        origin_lon, origin_lat = args.origin
    elif args.bbox:
        origin_lon = (args.bbox[0] + args.bbox[2]) / 2.0
        origin_lat = (args.bbox[1] + args.bbox[3]) / 2.0
    else:
        origin_lon, origin_lat = 139.77, 35.62

    projector = None if args.census_only else Projector(origin_lon, origin_lat)
    codelists = CodeLists()

    os.makedirs(args.out, exist_ok=True)
    manifest = {
        "attribution": ATTRIBUTION,
        "source_inputs": [os.path.abspath(p) for p in args.input],
        "crs": {
            "source": "EPSG:6697 (JGD2011 geographic 3D, posLists are lat lon height)",
            "target": "EPSG:6677 (JGD2011 / Japan Plane Rectangular CS IX), metres",
            "axes": "X=east, Y=north, Z=up (real elevation, never scaled)",
            "origin_wgs84": [origin_lon, origin_lat],
        },
        "bbox_wgs84": args.bbox,
        "compressed": False,
        "layers": {},
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    grand_census: dict[str, Counter] = defaultdict(Counter)

    for layer in layers:
        module, wanted = LAYERS[layer]
        tiles = discover_tiles(args.input, module)
        if args.limit_tiles:
            tiles = tiles[: args.limit_tiles]
        if not tiles:
            print(f"[{layer:8s}] no '{module}' tiles found — skipping")
            manifest["layers"][layer] = {"module": module, "tiles": 0, "features": 0}
            continue

        builder = builder_for(layer)
        global _ACTIVE_LOD_FILTER
        _ACTIVE_LOD_FILTER = LOD_FILTER.get(layer, LOD_FILTER.get("*", []))
        if _ACTIVE_LOD_FILTER:
            print(f"[{layer:8s}] keeping LODs matching {_ACTIVE_LOD_FILTER}")
        census: Counter = Counter()
        code_hist: dict[str, Counter] = defaultdict(Counter)
        records: list[dict] = []
        skipped_bbox = 0
        t0 = time.time()

        bad_tiles: list[tuple[str, str]] = []
        for n, path in enumerate(tiles, 1):
            # A single corrupt tile must not lose the whole run. 13100_tokyo23-ku_2022's
            # 53394520_tran_6668_op.gml carries a run of NUL bytes mid-attribute, and an
            # aborting ParseError there threw away 300 already-parsed tiles. Skip it,
            # keep whatever it yielded before the fault, and report at the end.
            # Stays a GENERATOR (never list()) so a 400 MB tile still streams in bounded
            # memory — the whole reason citygml.py uses iterparse.
            it = iter_features(path, wanted)
            while True:
                try:
                    tag, elem = next(it)
                except StopIteration:
                    break
                except ET.ParseError as exc:
                    bad_tiles.append((os.path.basename(path), str(exc)))
                    print(f"[{layer:8s}] SKIP malformed tile "
                          f"{os.path.basename(path)}: {exc}")
                    break
                if args.bbox and not in_bbox(first_lonlat(elem), args.bbox):
                    skipped_bbox += 1
                    elem.clear()
                    continue

                census[tag] += 1
                geoms, scalars = harvest(elem, projector)
                rec = builder(elem, scalars, geoms, codelists, path, projector)

                for key in ("function", "width_type", "section_type", "usage",
                            "land_use_type", "org_land_use", "direction_type",
                            "track_type", "railway_type"):
                    val = rec.get(key)
                    if isinstance(val, dict):
                        code_hist[key][f"{val['code']}={val.get('label', '?')}"] += 1
                for ta in rec.get("traffic_areas", []):
                    census["TrafficAreaNested"] += 1
                    if isinstance(ta.get("function"), dict):
                        fn = ta["function"]
                        code_hist["traffic_area_function"][
                            f"{fn['code']}={fn.get('label', '?')}"] += 1

                if not args.census_only:
                    records.append(rec)
                elem.clear()

            if n % 25 == 0 or n == len(tiles):
                print(f"[{layer:8s}] {n}/{len(tiles)} tiles, "
                      f"{sum(census.values())} features, {time.time() - t0:.1f}s", flush=True)

        print(f"[{layer:8s}] census: {dict(census)}")
        for key, hist in sorted(code_hist.items()):
            print(f"[{layer:8s}]   {key}: {dict(hist.most_common(12))}")
        if skipped_bbox:
            print(f"[{layer:8s}] skipped {skipped_bbox} features outside bbox")
        if bad_tiles:
            print(f"[{layer:8s}] {len(bad_tiles)} MALFORMED tile(s) skipped: "
                  + ", ".join(b[0] for b in bad_tiles))
            manifest["layers"].setdefault(layer, {})["malformed_tiles"] = \
                [{"tile": b[0], "error": b[1]} for b in bad_tiles]

        for key, hist in code_hist.items():
            grand_census[key].update(hist)

        info = {
            "module": module,
            "tiles": len(tiles),
            "features": sum(census.values()),
            "by_type": dict(census),
            "code_histograms": {k: dict(v) for k, v in code_hist.items()},
        }
        manifest["layers"][layer] = info

        if not args.census_only:
            ext = "jsonl" if args.format == "jsonl" else "json"
            out_path = os.path.join(args.out, f"{layer}.{ext}")
            with open(out_path, "w", encoding="utf-8") as fh:
                if args.format == "jsonl":
                    for rec in records:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                else:
                    json.dump({"header": manifest["crs"] | {"layer": layer,
                                                            "attribution": ATTRIBUTION},
                               "features": records}, fh, ensure_ascii=False)
            info["file"] = os.path.basename(out_path)
            info["bytes"] = os.path.getsize(out_path)
            print(f"[{layer:8s}] wrote {out_path} ({info['bytes'] / 1e6:.1f} MB)")

    # --- GeoJSON sidecars (railway / station / landmark) -----------------------
    if args.related and not args.census_only:
        side = read_geojson_sidecars(args.related, projector, args.bbox)
        for layer, records in side.items():
            shink = sum(1 for r in records if r.get("is_shinkansen"))
            routes = sorted({r["route_name"] for r in records if r.get("route_name")})
            print(f"[{layer:8s}] {len(records)} features from related GeoJSON"
                  + (f", {shink} shinkansen" if shink else ""))
            if routes:
                print(f"[{layer:8s}]   routes: {', '.join(routes[:20])}")
            out_path = os.path.join(args.out, f"{layer}.json")
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump({"header": manifest["crs"] | {"layer": layer,
                                                        "source": "plateau related geojson",
                                                        "note": "2D source: Z is 0, drape "
                                                                "onto the terrain layer",
                                                        "attribution": ATTRIBUTION},
                           "features": records}, fh, ensure_ascii=False)
            manifest["layers"][layer] = {"module": "related-geojson",
                                         "features": len(records),
                                         "shinkansen": shink,
                                         "routes": routes,
                                         "file": os.path.basename(out_path)}
            print(f"[{layer:8s}] wrote {out_path}")

    if not args.census_only:
        with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        print(f"wrote {os.path.join(args.out, 'manifest.json')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
