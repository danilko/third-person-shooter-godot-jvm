"""Namespace-agnostic streaming reader for PLATEAU CityGML tiles.

Everything here matches on the *local* XML tag name (the part after `}`), never on a
namespace URI.  PLATEAU tiles drift between CityGML 2.0 + i-UR 1.5 (the 2020/2022
datasets), i-UR 3.0 (2023) and the v5 spec (2025); the URIs change, the local names do
not.  See README.md for the dataset survey this was written against.

Coordinates in PLATEAU posLists are EPSG:6697 (JGD2011 geographic 3D) and arrive as
`lat lon height` triplets — *not* lon/lat.  Nothing here reorders them silently; the
swap happens once, in `Projector`, which is also the only place metres are produced.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# tag helpers
# ---------------------------------------------------------------------------


def local(tag: str) -> str:
    """`{http://…/transportation/2.0}Road` -> `Road`."""
    return tag.rpartition("}")[2]


LOD_RE = re.compile(r"^lod(\d)")

# Geometry leaves we harvest coordinates from.
POS_TAGS = {"posList", "pos"}

# Ring-ish containers: a posList under one of these is a polygon ring.
RING_TAGS = {"LinearRing"}

# Curve-ish containers: a posList under one of these is an open polyline.
CURVE_TAGS = {"LineString", "Curve", "LineStringSegment", "GeodesicString"}

# bldg LOD2 semantic surfaces — kept so a converter can tell wall from roof.
ROLE_TAGS = {
    "WallSurface",
    "RoofSurface",
    "GroundSurface",
    "ClosureSurface",
    "OuterCeilingSurface",
    "OuterFloorSurface",
    "CeilingSurface",
    "FloorSurface",
    "InteriorWallSurface",
}

# Nested *features* we do not want swallowed into the parent's attribute sweep.
NESTED_FEATURE_TAGS = {"TrafficArea", "AuxiliaryTrafficArea"}

# Scalar tags that are geometry/plumbing, never interesting as attributes.
SKIP_SCALAR = {
    "posList",
    "pos",
    "lowerCorner",
    "upperCorner",
}


# ---------------------------------------------------------------------------
# codelists
# ---------------------------------------------------------------------------


class CodeLists:
    """Resolves `codeSpace="../../codelists/Road_function.xml"` + a value to its label.

    The dictionaries ship inside every dataset, so the extractor never hardcodes a
    Japanese label — the output carries whatever the source dataset says.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, str]] = {}

    def _load(self, path: str) -> dict[str, str]:
        table = self._cache.get(path)
        if table is not None:
            return table
        table = {}
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in re.finditer(
                r"<gml:description>(.*?)</gml:description>\s*<gml:name>(.*?)</gml:name>",
                text,
                re.S,
            ):
                table[m.group(2).strip()] = m.group(1).strip()
        except OSError:
            pass
        self._cache[path] = table
        return table

    def resolve(self, gml_path: str, code_space: str | None, value: str | None):
        """-> {"code": "5", "label": "都市高速道路"} (label omitted if unresolvable)."""
        if value is None:
            return None
        out = {"code": value}
        if code_space:
            path = os.path.normpath(os.path.join(os.path.dirname(gml_path), code_space))
            label = self._load(path).get(value)
            if label:
                out["label"] = label
                out["codelist"] = os.path.basename(path)
        return out


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------


@dataclass
class Projector:
    """EPSG:6697 lat/lon/h -> local metric XYZ (X=east, Y=north, Z=up, metres).

    Horizontal goes through EPSG:6677 (JGD2011 / Japan Plane Rectangular CS IX — the
    Tokyo zone, and the same CS this repo's earlier extractions recorded as
    `reference_epsg6677`).  We transform from the *2D* geographic CRS 6668 rather than
    the compound 6697 so pyproj never applies a vertical datum shift: PLATEAU heights
    are already T.P. elevations in metres and are carried through untouched.
    """

    origin_lon: float
    origin_lat: float
    target_epsg: str = "EPSG:6677"
    _fwd: object = field(init=False, repr=False, default=None)
    _inv: object = field(init=False, repr=False, default=None)
    origin_e: float = field(init=False, default=0.0)
    origin_n: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        from pyproj import Transformer

        self._fwd = Transformer.from_crs("EPSG:6668", self.target_epsg, always_xy=True)
        self._inv = Transformer.from_crs(self.target_epsg, "EPSG:6668", always_xy=True)
        self.origin_e, self.origin_n = self._fwd.transform(self.origin_lon, self.origin_lat)

    def to_metres(self, lon: float, lat: float, h: float) -> tuple[float, float, float]:
        e, n = self._fwd.transform(lon, lat)
        return (
            round(e - self.origin_e, 4),
            round(n - self.origin_n, 4),
            round(h, 4),
        )

    def to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        return self._inv.transform(x + self.origin_e, y + self.origin_n)


# ---------------------------------------------------------------------------
# geometry harvesting
# ---------------------------------------------------------------------------


def parse_poslist(text: str, dim: int = 3) -> list[tuple[float, float, float]]:
    """`lat lon h lat lon h …` -> [(lon, lat, h), …]  (order swapped exactly once)."""
    vals = text.split()
    out = []
    for i in range(0, len(vals) - dim + 1, dim):
        lat = float(vals[i])
        lon = float(vals[i + 1])
        h = float(vals[i + 2]) if dim >= 3 else 0.0
        out.append((lon, lat, h))
    return out


@dataclass
class Geometry:
    lod: str | None          # "lod0RoofEdge", "lod1Solid", …
    kind: str                # "ring" | "line"
    role: str | None         # "WallSurface" … (LOD2 semantics) or None
    hole: bool               # True when the ring came from a gml:interior (a hole)
    coords: list             # [(x, y, z), …] metres, or [(lon, lat, h), …] if unprojected


def harvest(elem, projector: Projector | None, stop_at_nested: bool = True):
    """Collect geometry + scalar attributes from one feature subtree.

    Returns `(geoms, scalars)` where `scalars` maps a local tag name to
    `(text, codeSpace)` for every leaf element carrying text.
    """
    geoms: list[Geometry] = []
    scalars: dict[str, tuple[str, str | None]] = {}

    # Iterative walk (document order) so deep LOD2 solids can't blow the stack and
    # ring order stays exterior-then-interior as authored.
    stack = [(elem, None, None, False)]
    while stack:
        node, lod, role, hole = stack.pop(0)
        for child in node:
            name = local(child.tag)

            if stop_at_nested and name in NESTED_FEATURE_TAGS:
                continue

            child_lod = name if LOD_RE.match(name) else lod
            child_role = name if name in ROLE_TAGS else role
            child_hole = True if name == "interior" else (False if name == "exterior" else hole)

            if name in POS_TAGS:
                if child.text:
                    dim = int(child.get("srsDimension", node.get("srsDimension", "3")))
                    pts = parse_poslist(child.text, dim)
                    if projector is not None:
                        pts = [projector.to_metres(*p) for p in pts]
                    kind = "line" if local(node.tag) in CURVE_TAGS else "ring"
                    geoms.append(Geometry(child_lod, kind, child_role, child_hole, pts))
                continue

            if len(child) == 0:
                text = (child.text or "").strip()
                if text and name not in SKIP_SCALAR and name not in scalars:
                    scalars[name] = (text, child.get("codeSpace"))
                continue

            stack.append((child, child_lod, child_role, child_hole))

    return geoms, scalars


# ---------------------------------------------------------------------------
# tile iteration
# ---------------------------------------------------------------------------


def iter_features(path: str, wanted: set[str]):
    """Yield `(local_tag, element)` for each wanted top-level city object in a tile.

    Streams with `iterparse` and drops each processed `cityObjectMember` off the root,
    so a 400 MB tile parses in bounded memory.
    """
    ctx = ET.iterparse(path, events=("start", "end"))
    _, root = next(ctx)
    for event, elem in ctx:
        if event != "end":
            continue
        if local(elem.tag) != "cityObjectMember":
            continue
        for child in elem:
            name = local(child.tag)
            if name in wanted:
                yield name, child
        elem.clear()
        root.remove(elem)   # cityObjectMember is a direct child of CityModel
    root.clear()
