#!/usr/bin/env python3
"""
road_network.py — cell-grid road solver (PURE PYTHON, no bpy).

A TownGrid tags 7 m cells as ROAD / LOT / RESERVED; the classifier turns every
ROAD cell into the right auto-tiler tile + rotation from its 4-neighbour mask, so
ANY street map (side streets, T-junctions, crossings) tiles correctly with no
gaps. This is what fixes the three reported bugs by construction:

  (a) no ground on side streets -> every NON-road cell emits Road_Ground_7.
  (b) pole in the middle of the road -> props are placed only on sidewalk edges,
      which are emitted only on road/non-road boundaries (never on asphalt).
  (c) shrine inside a building -> shrine/konbini cells are RESERVED up front and
      the building-lot list excludes them.

Coordinates: cell (cx,cy) centre = (cx*CELL, cy*CELL). +Y=N, +X=E.
Run `python3 lib/road_network.py` for an ASCII self-test of the classifier.
"""
import math

CELL = 7.0
H = CELL / 2.0
LANE_OFF = 1.75               # lane centre offset for VehicleRoute markers

# directions, CCW ring (a +90deg CCW rotation shifts forward in this ring)
RING = ['N', 'W', 'S', 'E']
DVEC = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}

# base tile open-side sets (at rot_z = 0), matching tools/build_roads.py
BASE = {
    'Road_End_7':      frozenset(['N']),
    'Road_Straight_7': frozenset(['N', 'S']),
    'Road_Corner_7':   frozenset(['N', 'E']),
    'Road_Tee_7':      frozenset(['N', 'S', 'E']),
    'Road_Cross_7':    frozenset(['N', 'E', 'S', 'W']),
}


def _rot_dir(d, steps):
    return RING[(RING.index(d) + steps) % 4]


def _rot_set(s, steps):
    return frozenset(_rot_dir(d, steps) for d in s)


def tile_for(openset):
    """openset: which of N/E/S/W have a road neighbour. -> (tile_name, rot_deg)."""
    n = len(openset)
    if n == 0:
        return 'Road_End_7', 0
    if n == 1:
        base = 'Road_End_7'
    elif n == 2:
        a, b = sorted(openset)
        opposite = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
        base = 'Road_Straight_7' if opposite[a] == b else 'Road_Corner_7'
    elif n == 3:
        base = 'Road_Tee_7'
    else:
        return 'Road_Cross_7', 0
    bs = BASE[base]
    for steps in range(4):
        if _rot_set(bs, steps) == openset:
            return base, steps * 90
    return base, 0          # fallback (shouldn't happen)


# ---- JP intersection library --------------------------------------------------------------
# A junction's PIECE depends on its open-side topology AND its road class. Local junctions stay
# 1-cell; an ARTERIAL junction stamps a multi-cell piece (2 through + dedicated left/right turn
# lanes, channelizing islands, crosswalks); a one-way cell gets a feeder. intersection_for()
# returns the piece NAME + rotation + integer-cell FOOTPRINT (centred on the cell) so the solver
# can stamp it like a tile (assemble.lay_intersections), making real intersections easy to map
# onto the grid. Plain straight/corner runs still go through tile_for.
ARTERIAL_FOOT = (3, 3)           # an arterial intersection occupies a 3x3 cell block (21 m)
_TOPO = {                        # topology key -> open-set at rot 0 (mirrors BASE)
    'cross':    frozenset(['N', 'E', 'S', 'W']),
    'tee':      frozenset(['N', 'S', 'E']),
    'corner':   frozenset(['N', 'E']),
    'straight': frozenset(['N', 'S']),
    'end':      frozenset(['N']),
}
_INT_LOCAL    = {'cross': 'Int_Cross_1', 'tee': 'Int_Tee_1'}
_INT_ARTERIAL = {'cross': 'Int_Cross_Arterial', 'tee': 'Int_Tee_Arterial',
                 'corner': 'Int_Corner_Arterial'}


def _topo_and_rot(openset):
    """Open-side set -> (topology key, rotation deg). Same rotation logic as tile_for."""
    n = len(openset)
    if n == 0:
        return 'end', 0
    if n == 4:
        return 'cross', 0
    if n == 1:
        base = 'end'
    elif n == 2:
        a, b = sorted(openset)
        opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
        base = 'straight' if opp[a] == b else 'corner'
    else:
        base = 'tee'
    bs = _TOPO[base]
    for steps in range(4):
        if _rot_set(bs, steps) == openset:
            return base, steps * 90
    return base, 0


def _lane_config_cross(arms):
    """A 4-way cross keyed by per-arm lane count -> (piece, extra_rot_deg) or (None, 0).
    Symmetric 2-lane -> Int_Cross_2; asymmetric 2-lane major x 1-lane minor -> Int_Cross_Major2_Minor1
    (authored major on E/W; rotate 90 deg when the major axis runs N/S). All-1-lane -> None (the
    caller falls back to the 1-cell Int_Cross_1)."""
    ew = (arms.get('E', 0), arms.get('W', 0))
    ns = (arms.get('N', 0), arms.get('S', 0))
    if min(ew) < 1 or min(ns) < 1:                # not a full 4-way with lanes on every arm
        return (None, 0)
    ewmax, nsmax = max(ew), max(ns)
    if ewmax >= 2 and nsmax >= 2:
        return ('Int_Cross_2', 0)
    if ewmax >= 2 and nsmax == 1:
        return ('Int_Cross_Major2_Minor1', 0)     # major axis = E/W (as authored)
    if nsmax >= 2 and ewmax == 1:
        return ('Int_Cross_Major2_Minor1', 90)    # major axis = N/S -> rotate the piece
    return (None, 0)


def intersection_for(openset, cls='local', arms=None):
    """The JP intersection PIECE for a junction cell -> (name, rot_deg, (fw, fh)) cell footprint,
    or None to fall back to tile_for (plain straight/corner runs). `cls` = the cell's road class;
    `arms`={dir: lanes-per-direction} (from grid.arm_config) selects a LANE-CONFIG piece first — an
    asymmetric 2-lane x 1-lane crossing resolves to its dedicated 3x3 piece before class fallback."""
    topo, rot = _topo_and_rot(openset)
    if arms and topo == 'cross':                  # lane-config crossings win when a config matches
        piece, extra = _lane_config_cross(arms)
        if piece:
            return (piece, (rot + extra) % 360, (3, 3))
    if cls == 'arterial':
        name = _INT_ARTERIAL.get(topo)
        return (name, rot, ARTERIAL_FOOT) if name else None
    if cls == 'oneway' and topo in ('cross', 'tee'):
        return ('Int_Oneway_Feed', rot, (1, 1))
    if topo in ('cross', 'tee'):
        return (_INT_LOCAL[topo], rot, (1, 1))
    return None


ZONE_CELLS = 8                # 56 m / 7 m  -> streaming chunk = 8x8 cells
REGION_CELLS = 24             # 168 m -> region = 3x3 zones (tier above zones)


def zone_index(c):
    return c // ZONE_CELLS        # floor division (handles negatives)


def region_index(c):
    return c // REGION_CELLS


# road classes, ranked low->high so an arterial cell is never downgraded by a
# crossing street (the intersection keeps the wider/heavier treatment). 'alley' (roji)
# is the lowest — a narrow lane with no raised walk, used to subdivide dense blocks.
CLASS_RANK = {'alley': -1, 'local': 0, 'oneway': 1, 'arterial': 2}


class TownGrid:
    def __init__(self):
        self.roads = set()           # {(cx,cy)}
        self.reserved = {}           # {(cx,cy): name}
        self.lots = set()            # {(cx,cy)}
        self.manual = set()          # {(cx,cy)} hand-authoring slots (no auto building)
        self.infra = set()           # {(cx,cy)} elevated-corridor band (no auto building)
        self.shoulder = set()        # {(cx,cy)} arterial flanking band (no auto building)
        self.road_class = {}         # {(cx,cy): 'local'|'oneway'|'arterial'}
        self.lanes = {}              # {(cx,cy): lanes-per-direction} (default 1) — per-lane composition
        self.ramp_links = []         # lane split/merge records (ramp <-> street lane graph)

    # ---- authoring ----
    def _set_class(self, cell, cls):
        cur = self.road_class.get(cell)
        if cur is None or CLASS_RANK[cls] > CLASS_RANK[cur]:
            self.road_class[cell] = cls

    def _set_lanes(self, cell, lanes):
        """Store lanes-per-direction, keeping the WIDER count if a crossing road already set it."""
        if lanes != 1 or cell in self.lanes:
            self.lanes[cell] = max(self.lanes.get(cell, 1), lanes)

    def road_h(self, y, x0, x1, cls='local', lanes=1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            self.roads.add((x, y)); self._set_class((x, y), cls); self._set_lanes((x, y), lanes)

    def road_v(self, x, y0, y1, cls='local', lanes=1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            self.roads.add((x, y)); self._set_class((x, y), cls); self._set_lanes((x, y), lanes)

    def arterial_h(self, cy, x0, x1, width=3):
        """A wide divided arterial along row cy: centreline cells become 'arterial'
        road; the ±(width//2) flanking cells are reserved as `shoulder` (kept clear of
        auto buildings, like infra) so the wide carriageway + median + gantries have
        room and buildings set back. Returns the centreline cells."""
        half = width // 2
        for x in range(min(x0, x1), max(x0, x1) + 1):
            self.roads.add((x, cy)); self._set_class((x, cy), 'arterial')
            for w in range(-half, half + 1):
                if w:
                    self.shoulder.add((x, cy + w)); self.lots.discard((x, cy + w))
        return [(x, cy) for x in range(min(x0, x1), max(x0, x1) + 1)]

    def arterial_v(self, cx, y0, y1, width=3):
        """A wide divided arterial along column cx (see arterial_h)."""
        half = width // 2
        for y in range(min(y0, y1), max(y0, y1) + 1):
            self.roads.add((cx, y)); self._set_class((cx, y), 'arterial')
            for w in range(-half, half + 1):
                if w:
                    self.shoulder.add((cx + w, y)); self.lots.discard((cx + w, y))
        return [(cx, y) for y in range(min(y0, y1), max(y0, y1) + 1)]

    def class_of(self, cell):
        return self.road_class.get(cell, 'local')

    def lanes_of(self, cell):
        """Lanes-per-direction of a road cell (default 1). A full carriageway = 2*lanes_of."""
        return self.lanes.get(cell, 1)

    def arm_config(self, cx, cy):
        """-> {dir: lanes-per-direction} for each OPEN side of a junction cell, read from the
        neighbour road's lane count (falls back to this cell's own). Drives lane-config
        intersection selection (an asymmetric 2-lane x 1-lane crossing picks the right piece)."""
        out = {}
        for d, (dx, dy) in DVEC.items():
            nb = (cx + dx, cy + dy)
            if nb in self.roads:
                out[d] = self.lanes.get(nb, 1)     # a 1-lane road is unstored -> default 1
        return out

    def reserve(self, x0, y0, x1, y1, name):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.reserved[(x, y)] = name

    def reserve_manual(self, x0, y0, x1, y1):
        """Cells left OPEN for hand-placed content: excluded from auto building fill,
        but emitted as drop-in anchor slots (see assemble.place_manual_slots)."""
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                if (x, y) not in self.roads:
                    self.manual.add((x, y)); self.lots.discard((x, y))

    def reserve_corridor_h(self, cy, x0, x1, width=1):
        """Reserve a `width`-cell band centred on row cy (an elevated-line corridor):
        excluded from auto building, kept clear so piers land in the band. Returns the
        centreline cells [(cx,cy), ...] for building a Corridor/OverlayLine."""
        half = (width - 1) // 2
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for w in range(-half, width - half):
                self.infra.add((x, cy + w)); self.lots.discard((x, cy + w))
        return [(x, cy) for x in range(min(x0, x1), max(x0, x1) + 1)]

    def reserve_corridor_v(self, cx, y0, y1, width=1):
        """Reserve a `width`-cell band centred on column cx (an elevated-line corridor)."""
        half = (width - 1) // 2
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for w in range(-half, width - half):
                self.infra.add((cx + w, y)); self.lots.discard((cx + w, y))
        return [(cx, y) for y in range(min(y0, y1), max(y0, y1) + 1)]

    def infra_cells(self):
        return sorted(self.infra)

    # ---- lane split / merge graph (ramp <-> street lane connections) ----
    def lane_split(self, cell, side, route):
        """Record that the street lane at (cell, side) SPLITS off into ramp `route` (a
        diverge — an off/on connection branches from a through lane). Emitted as a baker
        link marker by assemble.add_ramp_links and used by the connectivity test."""
        self.ramp_links.append(('split', cell, side, route))
        return ramp_socket(cell, side)

    def lane_merge(self, route, cell, side):
        """Record that ramp `route` MERGES back into the street lane at (cell, side)."""
        self.ramp_links.append(('merge', route, cell, side))
        return ramp_socket(cell, side)

    def ramp_links_world(self):
        """-> [(kind, route, x, y, heading)] for the split/merge nodes (baker + markers)."""
        out = []
        for rec in self.ramp_links:
            if rec[0] == 'split':
                _, cell, side, route = rec
            else:
                _, route, cell, side = rec
            x, y, hd = ramp_socket(cell, side)
            out.append((rec[0], route, x, y, hd))
        return out

    def add_lots(self, x0, y0, x1, y1):
        """Mark a rectangle of cells as candidate building lots (road/reserved skipped)."""
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                if (x, y) not in self.roads and (x, y) not in self.reserved \
                        and (x, y) not in self.manual and (x, y) not in self.infra \
                        and (x, y) not in self.shoulder:
                    self.lots.add((x, y))

    def auto_lots(self):
        """Every cell touching a road (4-neighbour) not road/reserved/manual/infra/
        shoulder -> lot."""
        for (cx, cy) in list(self.roads):
            for d, (dx, dy) in DVEC.items():
                c = (cx + dx, cy + dy)
                if c not in self.roads and c not in self.reserved \
                        and c not in self.manual and c not in self.infra \
                        and c not in self.shoulder:
                    self.lots.add(c)

    # ---- queries ----
    def bounds(self):
        cells = self.roads | set(self.reserved) | self.lots | self.manual | self.infra | self.shoulder
        xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
        return min(xs), min(ys), max(xs), max(ys)

    # ---- zones / streaming seam (BLENDER_CONVENTIONS zone model) ----
    def zone_chunks(self):
        """-> {zone_id: (centre_wx, centre_wy)} one per 56 m chunk covering the map.
        Chunk zx spans cells [zx*8 .. zx*8+7]; neighbours abut on a cell grid line."""
        cells = self.roads | set(self.reserved) | self.lots | self.manual | self.infra | self.shoulder
        out = {}
        for zid in set((zone_index(cx), zone_index(cy)) for cx, cy in cells):
            zx, zy = zid
            cxc = (zx * ZONE_CELLS + (ZONE_CELLS - 1) / 2.0)
            cyc = (zy * ZONE_CELLS + (ZONE_CELLS - 1) / 2.0)
            out[f"{zx}_{zy}"] = (cxc * CELL, cyc * CELL)
        return out

    def seam_sockets(self):
        """Enter/exit connection points: every road cell whose +E or +N neighbour is a
        road in a DIFFERENT zone -> a socket on the shared grid line (the lane crosses
        unbroken). -> [(wx, wy, zoneA, zoneB, axis)] axis 'EW'|'NS'."""
        out = []
        for (cx, cy) in self.roads:
            for d, axis in (('E', 'EW'), ('N', 'NS')):
                dx, dy = DVEC[d]
                n = (cx + dx, cy + dy)
                if n in self.roads:
                    za = (zone_index(cx), zone_index(cy))
                    zb = (zone_index(n[0]), zone_index(n[1]))
                    if za != zb:
                        out.append(((cx + dx*0.5) * CELL, (cy + dy*0.5) * CELL,
                                    f"{za[0]}_{za[1]}", f"{zb[0]}_{zb[1]}", axis))
        return out

    def manual_slots(self):
        """-> [(cx, cy, wx, wy, road_dir)] for hand-authoring cells; road_dir faces the
        nearest road (or 'S' if none) so a dropped building auto-aligns to the street."""
        out = []
        for (cx, cy) in sorted(self.manual):
            rdir = 'S'
            for d, (dx, dy) in DVEC.items():
                if (cx + dx, cy + dy) in self.roads:
                    rdir = d; break
            out.append((cx, cy, cx * CELL, cy * CELL, rdir))
        return out

    def open_sides(self, cx, cy):
        return frozenset(d for d, (dx, dy) in DVEC.items()
                         if (cx + dx, cy + dy) in self.roads)

    def lane_transitions(self):
        """Straight LOCAL/oneway road cells whose along-travel-axis neighbour carries FEWER lanes —
        a wide carriageway that must taper DOWN before it reaches the narrower road/junction, or its
        outer lanes overrun the narrow cell (the reported '2-lane -> 1-lane intersection' error).
        Returns [(cx, cy, axis, hi, lo, sign)]: `axis` 'EW'/'NS', `hi`/`lo` = lanes-per-direction of
        this cell / the narrower neighbour, `sign` = +1/-1 direction along the axis toward it. The
        returned cell is the WIDE one — the taper is paved over it, funnelling hi->lo lanes."""
        out = []
        for (cx, cy) in self.roads:
            if self.class_of((cx, cy)) not in ('local', 'oneway'):
                continue
            opens = self.open_sides(cx, cy)
            ew, ns = bool({'E', 'W'} & opens), bool({'N', 'S'} & opens)
            if ew == ns:                      # only a clean straight run tapers (skip corner/cross/tee)
                continue
            axis = 'EW' if ew else 'NS'
            hi = self.lanes_of((cx, cy))
            for sign, d in ((1, 'E' if ew else 'N'), (-1, 'W' if ew else 'S')):
                dx, dy = DVEC[d]
                nb = (cx + dx, cy + dy)
                if nb in self.roads and self.lanes_of(nb) < hi:
                    out.append((cx, cy, axis, hi, self.lanes_of(nb), sign))
        return out

    def road_tiles(self):
        """-> [(tile_name, wx, wy, rot_deg)] for the classifier."""
        out = []
        for (cx, cy) in sorted(self.roads):
            tile, rot = tile_for(self.open_sides(cx, cy))
            out.append((tile, cx * CELL, cy * CELL, rot))
        return out

    def ground_tiles(self, pad=1):
        """Road_Ground_7 under every NON-road cell in the padded bounds -> no void."""
        x0, y0, x1, y1 = self.bounds()
        out = []
        for x in range(x0 - pad, x1 + pad + 1):
            for y in range(y0 - pad, y1 + pad + 1):
                if (x, y) not in self.roads:
                    out.append((x * CELL, y * CELL))
        return out

    def sidewalk_edges(self):
        """Sidewalk strips on each road/non-road boundary.
        -> [(wx, wy, rot_deg)] for the 2 m strip (piece runs along Y -> rot 0=E/W edge,
        rot 90=N/S edge). Placed 1 m onto the non-road side."""
        out = []
        for (cx, cy) in self.roads:
            if self.class_of((cx, cy)) == 'alley':   # alleys (roji) have no raised walk
                continue
            for d, (dx, dy) in DVEC.items():
                if (cx + dx, cy + dy) in self.roads:
                    continue
                wx = cx * CELL + dx * (H + 1.0)
                wy = cy * CELL + dy * (H + 1.0)
                rot = 90 if d in ('N', 'S') else 0
                out.append((wx, wy, rot))
        return out

    def building_lots(self):
        """-> [(wx, wy, road_dir)] one per lot cell; road_dir is the side ('N'/'E'/
        'S'/'W') where the adjacent road is, so the assembler can face the front at it."""
        out = []
        for (cx, cy) in sorted(self.lots):
            for d, (dx, dy) in DVEC.items():
                if (cx + dx, cy + dy) in self.roads:
                    out.append((cx * CELL, cy * CELL, d))
                    break
        return out

    def reserved_cells(self):
        groups = {}
        for c, name in self.reserved.items():
            groups.setdefault(name, []).append(c)
        return groups

    # ---- road hierarchy queries ----
    def arterial_cells(self):
        return sorted(c for c, cls in self.road_class.items() if cls == 'arterial')

    def oneway_cells(self):
        return sorted(c for c, cls in self.road_class.items() if cls == 'oneway')

    def shoulder_cells(self):
        return sorted(self.shoulder)

    def arterial_runs(self):
        """Maximal straight runs of arterial centreline cells -> [(axis, [(cx,cy)...])]
        ordered, axis 'EW' (constant cy) or 'NS' (constant cx). Drives lay_arterials."""
        arts = set(self.arterial_cells())
        runs = []
        rows = {}
        for (cx, cy) in arts:
            rows.setdefault(cy, []).append(cx)
        for cy, xs in rows.items():
            for (a, b) in _runs(sorted(xs)):
                runs.append(('EW', [(x, cy) for x in range(a, b + 1)]))
        cols = {}
        for (cx, cy) in arts:
            cols.setdefault(cx, []).append(cy)
        for cx, ys in cols.items():
            for (a, b) in _runs(sorted(ys)):
                runs.append(('NS', [(cx, y) for y in range(a, b + 1)]))
        return runs

    def arterial_intersections(self):
        """Major junctions: road cells on an arterial where roads actually cross (both
        an EW and an NS neighbour). -> [(cx, cy, open_sides)]. Local x local stays off."""
        arts = set(self.arterial_cells())
        out = []
        for (cx, cy) in sorted(self.roads):
            opens = self.open_sides(cx, cy)
            if not (({'E', 'W'} & opens) and ({'N', 'S'} & opens)):
                continue
            on_art = (cx, cy) in arts or any(
                (cx + DVEC[d][0], cy + DVEC[d][1]) in arts for d in opens)
            if on_art:
                out.append((cx, cy, opens))
        return out

    def intersection_pieces(self):
        """JP intersection PIECES to stamp on the grid + the cells they CLAIM (so road/arterial
        laying can skip them, no double-pave). -> ([(cx, cy, piece, rot, (fw, fh)), ...], {cells}).
        Arterial junctions get a multi-cell turn-lane piece (claims a fw x fh block); local /
        one-way junctions a 1-cell piece. Plain straight/corner runs are NOT claimed (tile_for
        handles them). Consumed by assemble.lay_intersections."""
        placements, claimed = [], set()
        for (cx, cy, opens) in self.arterial_intersections():          # arterials first (big block)
            got = intersection_for(opens, 'arterial')
            if not got:
                continue
            name, rot, (fw, fh) = got
            placements.append((cx, cy, name, rot, (fw, fh)))
            for dx in range(-(fw // 2), fw // 2 + 1):
                for dy in range(-(fh // 2), fh // 2 + 1):
                    claimed.add((cx + dx, cy + dy))
        for (cx, cy) in sorted(self.roads):                            # local / one-way junctions
            if (cx, cy) in claimed:
                continue
            cls = self.class_of((cx, cy))
            if cls == 'arterial':
                continue
            got = intersection_for(self.open_sides(cx, cy), cls, arms=self.arm_config(cx, cy))
            if not got:
                continue
            name, rot, (fw, fh) = got                                  # a lane-config cross claims 3x3
            placements.append((cx, cy, name, rot, (fw, fh)))
            for dx in range(-(fw // 2), fw // 2 + 1):
                for dy in range(-(fh // 2), fh // 2 + 1):
                    claimed.add((cx + dx, cy + dy))
        return placements, claimed

    def sidewalk_cells_world(self):
        """Cell centres that are non-road & adjacent to a road -> safe prop spots."""
        spots = set()
        for (cx, cy) in self.roads:
            for d, (dx, dy) in DVEC.items():
                c = (cx + dx, cy + dy)
                if c not in self.roads:
                    spots.add(c)
        return [(x * CELL, y * CELL) for (x, y) in sorted(spots)]

    def lane_routes(self):
        """Maximal straight runs -> two VehicleRoute polylines each (keep-left, +-1.75).
        -> {route_name: [(wx,wy), ...]} ordered in travel direction."""
        routes = {}
        # vertical runs (constant cx)
        cols = {}
        for (cx, cy) in self.roads:
            cols.setdefault(cx, []).append(cy)
        for cx, ys in cols.items():
            for (a, b) in _runs(sorted(ys)):
                base = cx * CELL
                nb = [(base - LANE_OFF, y * CELL) for y in range(a, b + 1)]   # northbound, west lane
                sb = [(base + LANE_OFF, y * CELL) for y in range(b, a - 1, -1)]  # southbound, east lane
                routes[f"v{cx}_{a}_N"] = nb
                routes[f"v{cx}_{a}_S"] = sb
        # horizontal runs (constant cy)
        rows = {}
        for (cx, cy) in self.roads:
            rows.setdefault(cy, []).append(cx)
        for cy, xs in rows.items():
            for (a, b) in _runs(sorted(xs)):
                base = cy * CELL
                eb = [(x * CELL, base + LANE_OFF) for x in range(a, b + 1)]   # eastbound, north lane
                wb = [(x * CELL, base - LANE_OFF) for x in range(b, a - 1, -1)]  # westbound, south lane
                routes[f"h{cy}_{a}_E"] = eb
                routes[f"h{cy}_{a}_W"] = wb
        return routes

    # ---- regions (tier above zones) + inter-region road portals ----
    def region_chunks(self):
        """-> {region_id: (centre_wx, centre_wy)} one per REGION_CELLS chunk (a region
        spans 3x3 zones). Separate region .blends abut on these boundaries."""
        cells = self.roads | set(self.reserved) | self.lots | self.manual | self.infra | self.shoulder
        out = {}
        for rid in set((region_index(cx), region_index(cy)) for cx, cy in cells):
            rx, ry = rid
            cxc = rx * REGION_CELLS + (REGION_CELLS - 1) / 2.0
            cyc = ry * REGION_CELLS + (REGION_CELLS - 1) / 2.0
            out[f"{rx}_{ry}"] = (cxc * CELL, cyc * CELL)
        return out

    def region_road_portals(self):
        """Road cells whose +E/+N neighbour road is in a different REGION -> an
        inter-region connection point. -> [(wx, wy, regionA, regionB, axis)]."""
        out = []
        for (cx, cy) in self.roads:
            for d, axis in (('E', 'EW'), ('N', 'NS')):
                dx, dy = DVEC[d]
                n = (cx + dx, cy + dy)
                if n in self.roads:
                    ra = (region_index(cx), region_index(cy))
                    rb = (region_index(n[0]), region_index(n[1]))
                    if ra != rb:
                        out.append(((cx + dx*0.5) * CELL, (cy + dy*0.5) * CELL,
                                    f"{ra[0]}_{ra[1]}", f"{rb[0]}_{rb[1]}", axis))
        return out


# ===================================================================== Z-LAYERS
# Locked vertical convention (deck-top heights, m) so layers never clash and a
# neighbouring region lines up. Piers are authored 0..<layer> in the elevated kit.
LAYER_STREET = 0.0
LAYER_PED    = 5.0
LAYER_RAIL   = 8.0     # elevated rail viaduct deck top
LAYER_EXPS   = 11.0    # elevated expressway deck top (clears the rail)


class OverlayLine:
    """An elevated run (rail viaduct or expressway) laid ABOVE the street grid.
    cells = ordered [(cx,cy), ...]; z = deck-top height; deck/pier = piece names;
    pier_every = drop a column every N cells; route = lane/rail marker prefix or None.
    offset = lateral metres from the centreline (parallel up/down lines); reverse =
    travel the opposite way (route order + consist flipped); track = optional rail/lane
    piece laid on the deck. Consumed by assemble.lay_overlay()."""
    def __init__(self, cells, z, deck, pier, pier_every=2, route=None,
                 offset=0.0, reverse=False, track=None):
        self.cells = list(cells)
        self.z = z
        self.deck = deck
        self.pier = pier
        self.pier_every = pier_every
        self.route = route
        self.offset = offset
        self.reverse = reverse
        self.track = track

    @property
    def axis(self):
        if len(self.cells) < 2:
            return 'NS'
        (x0, _), (x1, _) = self.cells[0], self.cells[1]
        return 'EW' if x1 != x0 else 'NS'


class Corridor:
    """A multi-track elevated CORRIDOR: one (wide) deck run along a centreline carrying
    N parallel lines at lateral offsets, each with its own direction. cells = ordered
    centreline [(cx,cy), ...]; z = deck-top height; deck = wide deck piece; pier = column;
    lines = [(offset_m, route, reverse, track_piece), ...] one per parallel track/lane.
    Piers drop once along the centreline (road-aware skip). Consumed by
    assemble.lay_corridor().

    The carriageway surface is swept as ONE curve->road (corridor_curve + lay_corridor
    swept=True), so on/off ramps (RampCurves from ramp_between) merge into it as one continuous
    surface; piers/barriers/signs stay instanced along the centreline cells."""
    def __init__(self, cells, z, deck, pier, lines, pier_every=2):
        self.cells = list(cells)
        self.z = z
        self.deck = deck
        self.pier = pier
        self.lines = list(lines)
        self.pier_every = pier_every

    @property
    def axis(self):
        if len(self.cells) < 2:
            return 'NS'
        (x0, _), (x1, _) = self.cells[0], self.cells[1]
        return 'EW' if x1 != x0 else 'NS'

    def lane_offsets(self):
        return [off for (off, *_ ) in self.lines]

    def lane_polyline(self, off, reverse=False):
        """Ordered [(x,y,z), ...] for the lane at lateral `off`, in travel order (reverse =
        opposite). Used to verify ramp waypoints connect into the mainline lane graph."""
        seq = list(reversed(self.cells)) if reverse else list(self.cells)
        ew = self.axis == 'EW'
        return [((cx*CELL, cy*CELL + off, self.z) if ew else (cx*CELL + off, cy*CELL, self.z))
                for (cx, cy) in seq]

    def outer_lane(self, side):
        """Lateral offset (m) of the OUTERMOST lane on a side ('L' = -, 'R' = +) — where a
        ramp merges in. Returns 0.0 if there are no lines."""
        offs = self.lane_offsets() or [0.0]
        return min(offs) if side == 'L' else max(offs)

    def overlay_lines(self):
        """Expand to one OverlayLine per parallel line (sharing the centreline cells)."""
        return [OverlayLine(self.cells, self.z, self.deck, self.pier, self.pier_every,
                            route=r, offset=off, reverse=rev, track=trk)
                for (off, r, rev, trk) in self.lines]


def overlay_h(cy, x0, x1, z, deck, pier, pier_every=2, route=None, offset=0.0,
              reverse=False, track=None):
    return OverlayLine([(x, cy) for x in range(min(x0, x1), max(x0, x1)+1)],
                       z, deck, pier, pier_every, route, offset, reverse, track)


def overlay_v(cx, y0, y1, z, deck, pier, pier_every=2, route=None, offset=0.0,
              reverse=False, track=None):
    return OverlayLine([(cx, y) for y in range(min(y0, y1), max(y0, y1)+1)],
                       z, deck, pier, pier_every, route, offset, reverse, track)


def corridor_h(cy, x0, x1, z, deck, pier, lines, pier_every=2):
    return Corridor([(x, cy) for x in range(min(x0, x1), max(x0, x1)+1)],
                    z, deck, pier, lines, pier_every)


def corridor_v(cx, y0, y1, z, deck, pier, lines, pier_every=2):
    return Corridor([(cx, y) for y in range(min(y0, y1), max(y0, y1)+1)],
                    z, deck, pier, lines, pier_every)


# ================================================== UNIFIED SPLINE-ROAD MODEL
# A highway is just a ROAD at a higher elevation (godot-road-generator model): the SAME
# swept curve->road surface carries the mainline carriageway, the on/off ramps, AND the
# merge. RampCurve is the one road-spline type (pts carry z, bank and HALF-WIDTH). The grid
# supplies the snap ANCHORS (ramp_socket on a street lane; road_lane_anchor on a road's edge
# lane); between anchors the spline curves freely. A ramp is ONE line built by ramp_between()
# that ends EXACTLY on the target road's lane, tangent to its travel direction — a real merge,
# not a bolted-on stub. The mainline (corridor_curve) bulges +1 lane over each merge span (a
# real acceleration/deceleration lane) and can drop a lane (3->2). assemble.lay_curve_road()
# sweeps any RampCurve; assemble.lay_corridor(swept=True) sweeps the mainline.
LANE = CELL / 2.0                # 3.5 m single lane (matches kit_common.LANE)
RAMP_BANK = 0.06                 # gentle default super-elevation (rad) — "lower" ramp feel

# ---- TRAVELABILITY BUDGET (a normal car is 4.3-4.9 m long, ~1.8 m wide) ---------------------
# Every drivable piece is sized against these so nothing reads as "untravelable": walls never
# sit in a lane (SHY), ramp landings/lead-ins are >= a car (VEH_LEN), grades stay drivable
# (MAX_GRADE), curves stay above the car's turning circle (MIN_RAMP_R), overpasses clear the
# road below (CLEAR_V). Used by ramp_between(), barrier_offset(), overpass_cells() + self-test.
VEH_LEN     = 4.9    # design vehicle length (m) — min length of any straight drivable segment
SHY         = 0.6    # lateral clearance (JP sokuho-yoyuu) from the outer LANE edge to a wall
SHOULDER_W  = 0.75   # elevated-deck shoulder strip width (carries the SHY gap on the deck)
MIN_SEG     = 5.0    # min straight segment length on a ramp (> VEH_LEN), e.g. the merge landing
MAX_GRADE   = 0.08   # JP urban ramp ceiling (8 %); ramp_between() raises if a climb exceeds it
MIN_RAMP_R  = 30.0   # min ramp centreline radius (m) — compact JP urban loop (Shuto-style) min;
                     # motorway cloverleaf loops run 40-50 m, tight urban directional ramps ~25-30 m.
                     # Well above a car's ~6 m turning circle, so a 4-5 m car tracks the loop
                     # comfortably; the smoothness fix is the swept mesh, this just widens the arc
                     # past the old 15 m value that forced the tight-facet look.
ACCEL_LEN   = 20.0   # straight parallel MERGE landing (m) at a ramp's end — long enough to read as
                     # an acceleration lane running alongside the host deck, not a stub jabbing in.
CLEAR_V     = 4.5    # vertical clearance over a road below (JP kenchiku-genkai)
DECK_T      = 0.6    # deck thickness — overpass soffit clear height = deck_top - DECK_T
SEG_LEN     = CELL   # 7 m — arc-length at which a ramp spine is RESAMPLED into discrete pieces
                     # (piers / lane-graph nodes / collision boxes). Aligns to the road module and
                     # existing pier_step; well above VEH_LEN so a 4-5 m car fits every segment. The
                     # swept road/wall SURFACE stays smooth regardless (it sweeps the smooth spine);
                     # this only sets discrete-placement granularity, so raise it (8-12 m) only for
                     # wide gentle freeway ramps where fewer nodes are wanted. Single source of truth:
                     # RampCurve.densify(SEG_LEN) feeds road + both walls + piers + collision + nodes.


def barrier_offset(lanes):
    """Lateral offset (m) from a deck centreline to its edge BARRIER/wall, so the wall stands
    just OUTSIDE the outermost lane plus a shoulder + shy gap (never in the travel lane). This
    is the fix for the old `half=6.9` that sat 0.1 m INSIDE a 4-lane (7.0 m half) deck edge."""
    return lanes * LANE / 2.0 + SHOULDER_W + SHY


def overpass_cells(rise, grade=MAX_GRADE):
    """Number of 7 m grade TILES needed to climb `rise` m at <= `grade` (each tile climbs
    CELL*grade). Used by assemble.place_overpass to size the straight raised approach."""
    per_tile = CELL * grade
    return max(1, math.ceil(rise / per_tile))


class RampCurve:
    """A curvilinear ramp/connector spine (pure data, no bpy).
    pts = [(x, y, z, bank, half_w), ...] world-metre control points: z climbs slowly,
    bank = tilt (rad), half_w = carriageway half-width there (so the same curve can taper
    lanes). route = lane-marker prefix; grip = surface material key; walls = author edge
    barriers (opened near a merge). tag names the built objects."""
    def __init__(self, pts, route=None, grip="red", walls=True, tag="RAMP", seg_len=SEG_LEN):
        self.pts = list(pts)
        self.route = route
        self.grip = grip
        self.walls = walls
        self.tag = tag
        self.seg_len = seg_len          # resample granularity carried to lay_curve_road/densify

    def lane_polyline(self):
        """Centre-line polyline [(x,y,z), ...] for lane markers / the connectivity graph."""
        return [(x, y, z) for (x, y, z, _, _) in self.pts]

    @property
    def end(self):
        return self.pts[-1]

    @property
    def start(self):
        return self.pts[0]

    def end_heading(self):
        """Travel heading (rad) at the tangent end, from the last two control points."""
        (x0, y0, *_), (x1, y1, *_) = self.pts[-2], self.pts[-1]
        return math.atan2(y1 - y0, x1 - x0)

    def densify(self, seg_len=None):
        """THE single source of truth for the ramp geometry: resample the spine at ~`seg_len`
        arc-length along a SMOOTH (centripetal Catmull-Rom) interpolation of `self.pts`, carrying
        interpolated bank + half_w. Returns [(x, y, z, bank, half_w), ...] — the ONE curve that
        drives the swept road, both edge walls, piers, lane nodes AND collision, so none of them
        diverge (the old bug: road swept a smooth NURBS while walls/piers chorded the sparse
        control points -> gap/facet). Endpoints are preserved exactly (merge stays gap-0). Pure
        Python, no bpy. `seg_len` only sets DISCRETE granularity — the swept surface is smooth
        regardless (it re-fits a spline through these denser points)."""
        seg_len = self.seg_len if seg_len is None else seg_len
        p = self.pts
        n = len(p)
        if n < 2:
            return list(p)
        # centripetal Catmull-Rom: smooth, no self-intersection/overshoot on tight loops
        def cr(p0, p1, p2, p3, t):
            def comp(i):
                a0, a1, a2, a3 = p0[i], p1[i], p2[i], p3[i]
                return (0.5 * ((2*a1) + (-a0 + a2) * t
                               + (2*a0 - 5*a1 + 4*a2 - a3) * t * t
                               + (-a0 + 3*a1 - 3*a2 + a3) * t * t * t))
            return tuple(comp(i) for i in range(5))
        # 1) evaluate a dense smooth polyline (fixed sub-steps per control segment)
        dense = []
        for i in range(n - 1):
            p0 = p[i - 1] if i > 0 else p[i]
            p1, p2 = p[i], p[i + 1]
            p3 = p[i + 2] if i + 2 < n else p[i + 1]
            sub = 8
            for k in range(sub):
                pt = cr(p0, p1, p2, p3, k / sub)
                if not dense or (pt[0], pt[1]) != (dense[-1][0], dense[-1][1]):
                    dense.append(pt)
        dense.append(tuple(p[-1]))
        # 2) resample the dense polyline at `seg_len` by cumulative XY arc-length
        cum = [0.0]
        for a, b in zip(dense, dense[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total = cum[-1]
        if total < 1e-6:
            return [tuple(p[0]), tuple(p[-1])]
        n_out = max(1, int(math.ceil(total / seg_len)))   # ceil -> every segment <= seg_len
        out, j = [], 0
        for s in range(n_out + 1):
            d = total * s / n_out
            while j < len(cum) - 2 and cum[j + 1] < d:
                j += 1
            span = cum[j + 1] - cum[j] or 1.0
            t = (d - cum[j]) / span
            a, b = dense[j], dense[j + 1]
            out.append(tuple(a[i] + (b[i] - a[i]) * t for i in range(5)))
        out[0], out[-1] = tuple(p[0]), tuple(p[-1])   # preserve endpoints exactly (gap-0 merge)
        return out


def _norm_angle(a):
    """Wrap an angle to (-pi, pi]."""
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


def _span_factor(c, c0, c1, ease=2.0):
    """0..1 trapezoid factor for column `c` over the cell range [c0, c1] with a linear `ease`
    of `ease` cells at each end (so a deck widening/lane drop ramps in and out smoothly)."""
    if c < c0 - ease or c > c1 + ease:
        return 0.0
    if c < c0:
        return max(0.0, (c - (c0 - ease)) / ease)
    if c > c1:
        return max(0.0, ((c1 + ease) - c) / ease)
    return 1.0


def corridor_curve(corridor, base_lanes=4, widenings=None, drops=None):
    """The CORRIDOR carriageway as ONE swept road-spline (replaces the tiled deck): a straight
    centreline along corridor.cells at corridor.z, half_w = base_lanes*LANE/2. `widenings` =
    [(side, c0, c1)] add a +1-lane ACCEL/DECEL lane on `side` ('L' = -lateral, 'R' = +lateral,
    matching _lateral / place_corridor_barriers) over the cell-column range [c0, c1]: the centre
    shifts LANE/2 and half_w grows LANE/2 (eased), so ONLY that edge bulges out one lane — the
    other edge holds. `drops` = [(c0, c1)] taper half_w down one lane (a 4->3 / 3->2 lane drop).
    Returns [(x, y, z, bank, half_w), ...] for road_from_curve (and road_lane_anchor)."""
    ew = corridor.axis == 'EW'
    base_hw = base_lanes * LANE / 2.0
    widenings = widenings or []
    drops = drops or []
    pts = []
    for (cx, cy) in corridor.cells:
        c = cx if ew else cy
        hw = base_hw
        shift = 0.0
        for (side, c0, c1) in widenings:
            f = _span_factor(c, c0, c1)
            hw += f * LANE / 2.0
            shift += (-1.0 if side == 'L' else 1.0) * f * LANE / 2.0
        for (c0, c1) in drops:
            hw -= _span_factor(c, c0, c1) * LANE / 2.0
        if ew:
            pts.append((cx * CELL, cy * CELL + shift, corridor.z, 0.0, hw))
        else:
            pts.append((cx * CELL + shift, cy * CELL, corridor.z, 0.0, hw))
    return pts


def _road_edge_point(road_pts, i, side, lane_in=1):
    """World (x, y) of the OUTER edge-lane centre on `side` ('L' = -lateral, 'R' = +lateral) at
    index i of a road-spline: centreline shifted by (half_w - lane_in*LANE/2) along the local
    left-normal, signed by side. Matches the _lateral / corridor_curve convention."""
    n = len(road_pts)
    a = road_pts[max(0, i - 1)]; b = road_pts[min(n - 1, i + 1)]
    tx, ty = b[0] - a[0], b[1] - a[1]
    L = math.hypot(tx, ty) or 1.0
    lnx, lny = -ty / L, tx / L                       # left normal of the tangent
    sgn = -1.0 if side == 'L' else 1.0               # 'L' = -lateral (matches _lateral)
    off = road_pts[i][4] - lane_in * LANE / 2.0
    return (road_pts[i][0] + sgn * off * lnx, road_pts[i][1] + sgn * off * lny)


def road_edge_polyline(road_pts, side, lane_in=1):
    """Outer edge-lane polyline [(x, y, z), ...] on `side` ('L'/'R') of a road-spline — the lane
    a ramp merges onto/peels from. Used by the connectivity test to confirm a ramp end lands on
    the carriageway edge (not just near the centre)."""
    return [(*_road_edge_point(road_pts, i, side, lane_in), road_pts[i][2])
            for i in range(len(road_pts))]


def road_lane_anchor(road_pts, side, travel=1, frac=0.5, near=None, lane_in=1):
    """A road MERGE ANCHOR: the world point + TRAVEL heading of a road's OUTER edge lane, so a
    ramp can end (on-ramp) or start (off-ramp) coincident with it and in the SAME direction.
    `side` 'L'/'R' picks the edge (matches corridor_curve); `travel` +1 = along the spline
    tangent, -1 = against it (pick the carriageway whose direction the ramp joins). Locate by
    `near`=(x,y) (nearest edge point — used to snap onto wherever the loop exits) or else by
    `frac` (0..1 along the spline). Returns (x, y, z, heading_rad)."""
    n = len(road_pts)
    if near is not None:
        i = min(range(n),
                key=lambda j: (lambda p: (p[0] - near[0])**2 + (p[1] - near[1])**2)
                (_road_edge_point(road_pts, j, side, lane_in)))
    else:
        i = max(0, min(n - 1, round(frac * (n - 1))))
    ax, ay = _road_edge_point(road_pts, i, side, lane_in)
    a = road_pts[max(0, i - 1)]; b = road_pts[min(n - 1, i + 1)]
    tang = math.atan2(b[1] - a[1], b[0] - a[0])
    hd = tang if travel >= 0 else _norm_angle(tang + math.pi)
    return (ax, ay, road_pts[i][2], hd)


def deck_lane_anchor(corridor, cell, side, travel=1, base_lanes=4, lane_in=1):
    """Merge anchor on a TILED corridor deck's OUTER lane edge — the grid-tiled-highway analogue
    of road_lane_anchor (which works on a swept spline). A straight elevated mainline is laid as
    grid lane tiles (lay_corridor swept=False); a ramp spline joins it here. `cell`=(cx,cy) on
    corridor.cells; `side` 'L'=-lateral / 'R'=+lateral; `travel` +1 along the cell order, -1
    against. Returns (x, y, z, heading) like road_lane_anchor."""
    ew = corridor.axis == 'EW'
    edge = base_lanes * LANE / 2.0 - lane_in * LANE / 2.0     # centre of the outermost lane
    sgn = -1.0 if side == 'L' else 1.0
    cx, cy = cell
    if ew:
        x, y, tang = cx * CELL, cy * CELL + sgn * edge, 0.0
    else:
        x, y, tang = cx * CELL + sgn * edge, cy * CELL, math.pi / 2
    hd = tang if travel >= 0 else _norm_angle(tang + math.pi)
    return (x, y, corridor.z, hd)


def _bezier_blend(p0, h0, p1, h1, z, half_w, n=10, handle=None):
    """Cubic Bezier from p0 heading h0 to p1 heading h1 (flat at z, constant half_w). Lands
    EXACTLY on p1 tangent to h1 — the merge feeder that eases the ramp onto the lane. Returns
    [(x, y, z, 0, half_w), ...] (n+1 pts)."""
    dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    d = (dist / 3.0) if handle is None else handle
    b1 = (p0[0] + d * math.cos(h0), p0[1] + d * math.sin(h0))
    b2 = (p1[0] - d * math.cos(h1), p1[1] - d * math.sin(h1))
    out = []
    for i in range(n + 1):
        t = i / n; u = 1.0 - t
        x = u*u*u*p0[0] + 3*u*u*t*b1[0] + 3*u*t*t*b2[0] + t*t*t*p1[0]
        y = u*u*u*p0[1] + 3*u*u*t*b1[1] + 3*u*t*t*b2[1] + t*t*t*p1[1]
        out.append((x, y, z, 0.0, half_w))
    return out


def ramp_between(start, end, z0, z1, radius=25.0, side='L', turns=1.0, lanes=1,
                 bank=RAMP_BANK, grip="asphalt", route=None, tag="RAMP", lead=None,
                 step_deg=8, blend_n=10, land=None, seg_len=SEG_LEN):
    """ONE continuous road-spline reaching FROM `start` TO `end`, merging in the SAME direction
    at each end (the godot-style 'single line from a road into another road'). `start`/`end` =
    (x, y, heading[, ...]) anchors — a street ramp_socket OR a road road_lane_anchor. z0/z1 =
    the elevation at start/end (on-ramp climbs z0<z1; off-ramp descends z0>z1). Builds, as ONE
    pts list / ONE swept mesh:
      (1) a tangent LEAD-IN off `start` (so it branches smoothly, no kink),
      (2) a gentle climbing/descending LOOP turning `side` ('L' CCW / 'R' CW) whose exit heading
          AUTO-ALIGNS to `end`'s heading, +`turns` extra full turns to gain/lose height in a
          small footprint (the Shuto loop),
      (3) a Bezier BLEND that lands EXACTLY on `end`, tangent to its heading — so the ramp
          arrives parallel and coincident = a real merge, NOT a bolted-on diagonal stub.
    half_w is held at `lanes` lane(s); the host road widens to absorb it (corridor_curve). The
    returned RampCurve's .end == `end` (gap 0 by construction)."""
    if radius < MIN_RAMP_R:
        raise ValueError("ramp_between: radius %.1f < MIN_RAMP_R %.1f (tighter than a car can take)"
                         % (radius, MIN_RAMP_R))
    lead = max(MIN_SEG, VEH_LEN) if lead is None else lead   # straight branch >= one car length
    land = ACCEL_LEN if land is None else land               # straight parallel MERGE landing (accel lane)
    sx, sy, h0 = start[0], start[1], start[-1]
    ex, ey, h1 = end[0], end[1], end[-1]
    half_w = lanes * LANE / 2.0
    turn = 1.0 if side == 'L' else -1.0
    # (1) tangent lead-in off the start anchor; (x, y, tilt) — z is assigned by arc-length below
    qx, qy = sx + lead * math.cos(h0), sy + lead * math.sin(h0)
    raw = [(sx, sy, 0.0), (qx, qy, 0.0)]
    # (2) gentle loop: centre perpendicular to the lane heading; sweep AUTO-ALIGNS exit -> h1
    # (+`turns` extra FULL turns, which preserve heading, to gain/lose height in a small print)
    dtheta = _norm_angle((h1 - h0) * turn)          # alignment delta in the turn sense
    if dtheta < 0:
        dtheta += 2 * math.pi                        # keep a positive sweep magnitude
    sweep = (dtheta + turns * 2 * math.pi) * turn
    tilt = bank * turn
    if abs(sweep) > 1e-4:
        cx = qx + radius * math.cos(h0 + turn * math.pi / 2)
        cy = qy + radius * math.sin(h0 + turn * math.pi / 2)
        a0 = math.atan2(qy - cy, qx - cx)
        n = max(6, int(abs(math.degrees(sweep)) / step_deg))
        for i in range(1, n + 1):
            a = a0 + sweep * (i / n)
            raw.append((cx + radius * math.cos(a), cy + radius * math.sin(a), tilt))
    # (3) Bezier blend from the loop exit to the START of a straight LANDING, then a dead-straight
    # run of `land` m colinear with h1 ENDING exactly on end — so the last car-length runs parallel
    # to the host lane (a real merge a car can sit on), not a short diagonal stub.
    lx, ly = ex - land * math.cos(h1), ey - land * math.sin(h1)
    px, py = raw[-1][0], raw[-1][1]
    for (bx, by, *_) in _bezier_blend((px, py), h1, (lx, ly), h1, 0.0, half_w, n=blend_n)[1:]:
        raw.append((bx, by, 0.0))
    raw.append((ex, ey, 0.0))                                # straight landing end == the anchor
    # assign z = z0->z1 by cumulative HORIZONTAL distance, so the grade is spread evenly over the
    # WHOLE spline (lead-in + loop + blend + landing) — smooth even when turns=0 (no loop)
    cum = [0.0]
    for a, b in zip(raw, raw[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = cum[-1] or 1.0
    grade = abs(z1 - z0) / total
    if grade > MAX_GRADE + 1e-6:
        raise ValueError("ramp_between: grade %.1f%% over %.0f m exceeds MAX_GRADE %.0f%% — raise "
                         "`radius`/`turns` for length or split the climb"
                         % (grade * 100, total, MAX_GRADE * 100))
    pts = [(x, y, z0 + (z1 - z0) * (cum[i] / total), tl, half_w)
           for i, (x, y, tl) in enumerate(raw)]
    rc = RampCurve(pts, route=route, grip=grip, tag=tag, seg_len=seg_len)
    rc.grade = grade
    return rc


def ramp_socket(cell, side):
    """A RAMP SOCKET: the world point + travel heading of a STREET LANE at `cell`, so a ramp
    can branch off it TANGENTIALLY (derived from the street line, not bolted on at an angle).
    `side` selects the lane (matches lane_routes / DVEC conventions):
      'N'/'S' = vertical street (x=cx), lane offset ∓LANE_OFF in X, travels +Y / -Y;
      'E'/'W' = horizontal street (y=cy), lane offset ±LANE_OFF in Y, travels +X / -X.
    Returns (x, y, heading_rad)."""
    cx, cy = cell
    if side in ('N', 'S'):
        x = cx * CELL + (-LANE_OFF if side == 'N' else LANE_OFF)
        return (x, cy * CELL, math.pi / 2 if side == 'N' else -math.pi / 2)
    y = cy * CELL + (LANE_OFF if side == 'E' else -LANE_OFF)
    return (cx * CELL + (0.0), y, 0.0 if side == 'E' else math.pi)


def lanes_connected(ramp_polyline, mainline_polyline, tol=1.0):
    """Merge-graph check (self-test): True if the ramp's final lane point coincides with
    SOME point on the mainline lane polyline within `tol` m — i.e. routes connect."""
    ex, ey = ramp_polyline[-1][0], ramp_polyline[-1][1]
    return any(math.hypot(p[0] - ex, p[1] - ey) <= tol for p in mainline_polyline)


def _runs(sorted_vals):
    """Contiguous integer runs -> list of (start,end). Only runs length>=2."""
    if not sorted_vals:
        return []
    out = []
    a = p = sorted_vals[0]
    for v in sorted_vals[1:]:
        if v == p + 1:
            p = v
        else:
            if p > a:
                out.append((a, p))
            a = p = v
    if p > a:
        out.append((a, p))
    return out


# --------------------------------------------------------------- self-test
def _demo_grid():
    g = TownGrid()
    g.road_v(0, 0, 8)            # main N-S avenue
    g.road_v(6, 2, 8)            # second avenue
    g.road_h(2, 0, 6)            # cross street
    g.road_h(5, 0, 6)            # cross street
    g.road_h(8, 0, 6)            # top street
    g.reserve(2, 6, 3, 7, "shrine")
    g.auto_lots()
    return g


if __name__ == "__main__":
    g = _demo_grid()
    x0, y0, x1, y1 = g.bounds()
    sym = {'Road_Straight_7': '|', 'Road_Corner_7': 'L', 'Road_Tee_7': 'T',
           'Road_Cross_7': '+', 'Road_End_7': '.'}
    tiles = {(round(wx/CELL), round(wy/CELL)): (t, r) for (t, wx, wy, r) in g.road_tiles()}
    print("classifier map (top=N):")
    for y in range(y1, y0 - 1, -1):
        row = []
        for x in range(x0, x1 + 1):
            if (x, y) in tiles:
                t, r = tiles[(x, y)]
                s = sym[t]
                if t == 'Road_Straight_7' and r % 180 == 90:
                    s = '-'
                row.append(s)
            elif (x, y) in g.reserved:
                row.append('S')
            elif (x, y) in g.lots:
                row.append('o')
            else:
                row.append(' ')
        print('  ' + ''.join(row))
    print("road tiles:", len(g.road_tiles()), " lots:", len(g.lots),
          " ground:", len(g.ground_tiles()), " sidewalk edges:", len(g.sidewalk_edges()),
          " lane routes:", len(g.lane_routes()))

    # --- overlay + region assertions (multi-level foundation) ---
    assert LAYER_STREET < LAYER_PED < LAYER_RAIL < LAYER_EXPS, "layer heights must increase"
    ol = overlay_h(3, 0, 6, LAYER_RAIL, "SM_Rail_Viaduct_Deck", "SM_Rail_Pier", route="rail_t")
    assert ol.axis == 'EW' and len(ol.cells) == 7 and ol.z == LAYER_RAIL
    assert overlay_v(2, 0, 4, LAYER_EXPS, "d", "p").axis == 'NS'
    assert region_index(0) == 0 and region_index(REGION_CELLS) == 1
    big = TownGrid()
    for x in range(0, REGION_CELLS * 2 + 1, 4):
        big.road_v(x, 0, REGION_CELLS * 2)
    big.road_h(REGION_CELLS, 0, REGION_CELLS * 2)
    rp = big.region_road_portals()
    assert all(ra != rb for (_, _, ra, rb, _) in rp), "region portals must straddle an edge"

    # --- corridor + infra-exclusion + reverse assertions ---
    cg = TownGrid()
    cg.road_h(0, 0, 10)
    centre = cg.reserve_corridor_h(5, 0, 10, width=3)   # 3-cell band, centreline row 5
    assert len(centre) == 11 and all(cy == 5 for _, cy in centre)
    assert (5, 4) in cg.infra and (5, 6) in cg.infra and (5, 5) in cg.infra
    cg.auto_lots()
    assert not (cg.lots & cg.infra), "auto_lots must skip the infra corridor band"
    cor = corridor_h(5, 0, 10, LAYER_RAIL, "SM_Rail_Viaduct_Deck_2T", "SM_Rail_Pier",
                     lines=[(-2.0, "rail_dn", True, "SM_Track_Std"),
                            (2.0, "rail_up", False, "SM_Track_Std")])
    lns = cor.overlay_lines()
    assert len(lns) == 2 and lns[0].reverse and not lns[1].reverse
    assert lns[0].offset == -2.0 and lns[1].offset == 2.0 and cor.axis == 'EW'
    # --- road-hierarchy assertions (classes, arterial shoulder, run/junction detect) ---
    hg = TownGrid()
    hg.arterial_h(4, 0, 10, width=3)          # wide EW avenue, rows 3-5 reserved
    hg.road_v(5, 0, 8, cls='oneway')          # a one-way cross street
    hg.road_v(2, 0, 8)                         # a plain local cross street
    assert hg.class_of((2, 0)) == 'local'
    # a lone local cell emits 4 sidewalk edges; the same cell as an alley emits none
    lc = TownGrid(); lc.road_h(0, 0, 0)
    al = TownGrid(); al.road_h(0, 0, 0, cls='alley')
    assert len(lc.sidewalk_edges()) == 4 and len(al.sidewalk_edges()) == 0, \
        "alley cells emit no raised sidewalk"
    assert hg.class_of((3, 4)) == 'arterial'
    assert hg.class_of((5, 4)) == 'arterial', "arterial must not be downgraded at a crossing"
    assert hg.class_of((5, 0)) == 'oneway' and hg.class_of((2, 0)) == 'local'
    # lane-count transition: a 2-lane road funnelling to a 1-lane road must be detected (so a taper
    # is paved and the wide outer lanes don't overrun the narrow cell)
    tg = TownGrid(); tg.road_h(0, 0, 4, lanes=2); tg.road_h(0, 5, 8, lanes=1)
    trans = tg.lane_transitions()
    assert any(t[2] == 'EW' and t[3] == 2 and t[4] == 1 and t[5] == 1 and (t[0], t[1]) == (4, 0)
               for t in trans), "2->1 lane drop detected on the wide cell, toward +X"
    assert not any(t[4] >= t[3] for t in trans), "a transition is always hi->lo (a real drop)"
    assert (5, 3) in hg.shoulder and (5, 5) in hg.shoulder, "arterial flanks -> shoulder"
    hg.auto_lots()
    assert not (hg.lots & hg.shoulder), "auto_lots must skip the arterial shoulder band"
    runs = hg.arterial_runs()
    assert len(runs) == 1 and runs[0][0] == 'EW' and len(runs[0][1]) == 11
    junc = hg.arterial_intersections()
    jc = {(x, y) for x, y, _ in junc}
    assert (5, 4) in jc and (2, 4) in jc, "arterial x road junctions detected"
    assert (5, 0) not in jc, "a non-crossing one-way cell is not a junction"
    # --- unified spline-road assertions (swept highway + single-spline ramp + merge graph) ---
    deck_z = LAYER_EXPS
    exps = corridor_h(18, 4, 28, deck_z, "SM_Exps_Deck_4L", "SM_Exps_Pillar",
                      lines=[(-3.5, "w", True, None), (3.5, "e", False, None)])
    # the carriageway as ONE swept spline: 4 lanes, with a +1-lane accel lane on the south ('L')
    # edge over cols 22..26 and a 4->3 lane drop over cols 8..12
    base_hw = 4 * LANE / 2.0
    cpts = corridor_curve(exps, base_lanes=4, widenings=[('L', 22, 26)], drops=[(8, 12)])
    midw = next(p for p in cpts if round(p[0] / CELL) == 24)     # inside the widening
    assert abs(midw[4] - (base_hw + LANE / 2.0)) < 1e-9, "deck bulges +1 lane over the merge span"
    assert midw[1] < 18 * CELL, "the 'L' (south) edge is the one that shifts out"
    midd = next(p for p in cpts if round(p[0] / CELL) == 10)     # inside the lane drop
    assert abs(midd[4] - (base_hw - LANE / 2.0)) < 1e-9, "deck drops one lane (4->3)"
    plain = next(p for p in cpts if round(p[0] / CELL) == 18)    # neither span
    assert abs(plain[4] - base_hw) < 1e-9 and abs(plain[1] - 18 * CELL) < 1e-9, "plain run = base width, centred"
    # a road MERGE ANCHOR on the south ('L') edge, joined by a WEST-bound (travel -1) ramp
    anc = road_lane_anchor(cpts, 'L', travel=-1, frac=0.83)
    assert abs(_norm_angle(anc[3] - math.pi)) < 1e-9, "south edge, west-bound -> heading pi"
    assert anc[1] < 18 * CELL and abs(anc[2] - deck_z) < 1e-6, "anchor on the south edge at deck z"
    # ramp SOCKET: a ramp branches tangentially off a street lane (heading = lane travel dir)
    sk = ramp_socket((25, 13), 'N')                  # x=25 street, northbound lane
    assert abs(sk[0] - (25 * CELL - LANE_OFF)) < 1e-9 and abs(sk[2] - math.pi/2) < 1e-9, "socket on lane, heads +Y"
    # ONE-SPLINE on-ramp: socket -> climbing loop -> merge, ending EXACTLY on the anchor
    ramp = ramp_between(sk, anc, z0=0.4, z1=deck_z, radius=MIN_RAMP_R, side='L', turns=1.0, route="on")
    assert abs(ramp.pts[0][0] - sk[0]) < 1e-9 and ramp.pts[0][2] == 0.4, "ramp starts AT the socket, at grade"
    assert math.dist(ramp.end[:3], (anc[0], anc[1], anc[2])) < 1e-6, "ramp ends EXACTLY on the road anchor (gap 0)"
    assert abs(_norm_angle(ramp.end_heading() - anc[3])) < 0.2, "ramp arrives tangent to the lane (real merge)"
    assert abs(max(p[2] for p in ramp.pts) - deck_z) < 1e-6, "ramp climbs to deck height"
    assert lanes_connected(ramp.lane_polyline(), [(anc[0], anc[1], anc[2])]), "merge connects the lane graph"
    # densify(): the SINGLE resampled spine driving road+walls+piers+collision — every segment fits
    # a vehicle (<= seg_len), endpoints are preserved (gap-0 merge), and it tracks the design curve.
    dp = ramp.densify(SEG_LEN)
    assert len(dp) >= 2, "densify returns a polyline"
    gaps = [math.dist(a[:2], b[:2]) for a, b in zip(dp, dp[1:])]
    assert max(gaps) <= SEG_LEN + 1e-6, "every densified segment is <= seg_len (a car fits each piece)"
    assert math.dist(dp[0][:3], ramp.pts[0][:3]) < 1e-6, "densify keeps the exact start point"
    assert math.dist(dp[-1][:3], ramp.end[:3]) < 1e-6, "densify keeps the exact end point (gap-0 merge)"
    assert all(len(q) == 5 for q in dp), "densify carries (x,y,z,bank,half_w)"
    dp8 = ramp.densify(8.0)
    assert max(math.dist(a[:2], b[:2]) for a, b in zip(dp8, dp8[1:])) <= 8.0 + 1e-6, "seg_len is honoured (8 m truck)"
    co = exps
    assert co.outer_lane('R') == 3.5 and co.outer_lane('L') == -3.5, "outer-lane offsets"
    gg = TownGrid(); gg.road_v(25, 0, 28)
    gg.lane_split((25, 13), 'N', "on"); gg.lane_merge("off", (20, 22), 'E')
    assert len(gg.ramp_links_world()) == 2 and gg.ramp_links_world()[0][0] == 'split', "lane split/merge recorded"
    # --- travelability budget + JP intersection library + tiled-deck anchor + overpass sizing ---
    assert barrier_offset(4) > base_hw + SHY and barrier_offset(4) > 7.0, \
        "edge wall stands OUTSIDE the outer lane + shy (the old half=6.9 sat 0.1 m INSIDE)"
    assert ramp.grade <= MAX_GRADE + 1e-9, "ramp grade within the drivable ceiling"
    assert math.dist(ramp.pts[-1][:2], ramp.pts[-2][:2]) >= VEH_LEN - 1e-6, \
        "ramp ends with a straight LANDING >= one car length (a real merge, not a stub)"
    try:
        ramp_between(sk, anc, z0=0.0, z1=deck_z * 8, radius=MIN_RAMP_R, turns=0.0)  # too tall to climb
        raise AssertionError("expected a grade overflow to raise ValueError")
    except ValueError:
        pass
    try:
        ramp_between(sk, anc, z0=0.0, z1=deck_z, radius=MIN_RAMP_R - 1.0)  # tighter than a car can take
        raise AssertionError("expected a sub-MIN_RAMP_R radius to raise ValueError")
    except ValueError:
        pass
    assert intersection_for(frozenset('NESW'), 'arterial') == ('Int_Cross_Arterial', 0, (3, 3))
    assert intersection_for(frozenset('NESW'), 'local') == ('Int_Cross_1', 0, (1, 1))
    assert intersection_for(frozenset(['N', 'S']), 'local') is None, "a straight run is not an intersection"
    assert intersection_for(frozenset(['N', 'S', 'E']), 'oneway')[0] == 'Int_Oneway_Feed'
    # lane-config crossings: symmetric 2-lane, asymmetric 2-major x 1-minor (rotated when N/S is major)
    full = frozenset('NESW')
    assert intersection_for(full, 'local', arms={'N': 2, 'E': 2, 'S': 2, 'W': 2}) == ('Int_Cross_2', 0, (3, 3))
    assert intersection_for(full, 'local', arms={'E': 2, 'W': 2, 'N': 1, 'S': 1}) == \
        ('Int_Cross_Major2_Minor1', 0, (3, 3)), "2-lane E/W major, 1-lane N/S minor -> rot 0"
    assert intersection_for(full, 'local', arms={'N': 2, 'S': 2, 'E': 1, 'W': 1}) == \
        ('Int_Cross_Major2_Minor1', 90, (3, 3)), "2-lane N/S major -> piece rotated 90"
    assert intersection_for(full, 'local', arms={'N': 1, 'E': 1, 'S': 1, 'W': 1}) == \
        ('Int_Cross_1', 0, (1, 1)), "all-1-lane falls back to the 1-cell cross"
    lg = TownGrid()                                  # a real 2-lane x 1-lane crossing on the grid
    lg.road_h(4, 0, 8, lanes=2); lg.road_v(4, 0, 8, lanes=1)
    assert lg.arm_config(4, 4) == {'N': 1, 'E': 2, 'S': 1, 'W': 2}, "arm_config reads neighbour lane counts"
    lgp = {(cx, cy): (n, r, f) for (cx, cy, n, r, f) in lg.intersection_pieces()[0]}
    assert lgp[(4, 4)] == ('Int_Cross_Major2_Minor1', 0, (3, 3)), "grid stamps the asymmetric cross"
    da = deck_lane_anchor(exps, (24, 18), 'L', travel=-1, base_lanes=4)
    assert abs(da[1] - (18 * CELL - (base_hw - LANE / 2.0))) < 1e-9 and abs(da[2] - deck_z) < 1e-6, \
        "tiled-deck anchor sits on the outer lane edge at deck z"
    assert abs(_norm_angle(da[3] - math.pi)) < 1e-9, "west-bound tiled-deck anchor -> heading pi"
    assert overpass_cells(CLEAR_V + DECK_T) * CELL * MAX_GRADE >= CLEAR_V + DECK_T - 1e-9, \
        "overpass grade tiles clear the road below at <= MAX_GRADE"

    print("overlay/region/corridor self-test OK: layers ordered, %d region portals, "
          "corridor=%d lines, infra band kept clear; road-hierarchy OK: classes ranked, "
          "%d shoulder cells excluded, %d arterial junctions; UNIFIED ROAD OK: deck bulges to "
          "%.1f m half-width over the merge / drops to %.1f m, single-spline ramp ends ON the "
          "anchor (gap 0) tangent to the lane, climbs %.1f->%.1f m"
          % (len(rp), len(lns), len(hg.shoulder), len(junc), midw[4], midd[4],
             ramp.pts[0][2], max(p[2] for p in ramp.pts)))
    print("TRAVELABILITY OK: edge wall at %.2f m (outside the %.1f m lane edge + shy), ramp grade "
          "%.1f%% <= %.0f%%, straight landing %.1f m >= car %.1f m; JP intersections: arterial->3x3 "
          "turn-lane piece, local->1x1, one-way->feeder; overpass needs %d grade tiles to clear %.1f m"
          % (barrier_offset(4), base_hw, ramp.grade * 100, MAX_GRADE * 100,
             math.dist(ramp.pts[-1][:2], ramp.pts[-2][:2]), VEH_LEN,
             overpass_cells(CLEAR_V + DECK_T), CLEAR_V + DECK_T))
