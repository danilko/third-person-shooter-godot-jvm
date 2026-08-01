"""piece_registry.py -- the single source of truth for what world Pieces exist, replacing
world_grid.py's MAP-driven district derivation (FREESTANDING_PIECES_PLAN.md §B). Pure Python, no
bpy, same style as world_grid.py's other JSON sidecars.

A Piece is either a migrated grid district or a freestanding hand-placed piece (an island, a
bridge, ...) -- there is no `kind` field: every piece streams the same way (WorldZoneMarker +
load/unload radius hysteresis), per the "no always-resident overlay" decision in
FREESTANDING_PIECES_PLAN.md §1. `load_radius`/`unload_radius` are OPTIONAL (null = "let
WorldBaker fall back to its size-based default formula", exactly what a plain grid district relies
on today -- only a piece that genuinely needs a bigger streamed footprint, like a bridge spanning
two landings, sets them explicitly).

assets/world_source/pieces.json is the git-tracked registry file: a flat JSON object
`{"pieces": [ {...}, {...}, ... ]}`, one entry per piece, sorted by id for a stable,
low-diff-noise file. Adding/removing a piece for real (not just a session-local unload, see
lib/session_common.py's unload_piece) goes through set_piece()/remove_piece() below, e.g. from
the addon's "Place Piece Anchor"/"Remove Piece" operators.
"""
import json
import os

WORLD_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "world_source")
_PIECES_PATH = os.path.join(WORLD_SOURCE, "pieces.json")
PIECES_DIR = os.path.join(WORLD_SOURCE, "pieces")   # every piece's own <id>.blend lives here --
                                                      # the one place that name is spelled out, so
                                                      # callers never re-derive it themselves

_REQUIRED_FIELDS = ("id", "footprint", "position")


def _load():
    """{id: piece_dict} -- empty if pieces.json doesn't exist yet (a fresh checkout before the
    one-time migration has run, or a from-scratch project)."""
    if not os.path.exists(_PIECES_PATH):
        return {}
    with open(_PIECES_PATH) as f:
        data = json.load(f)
    return {p["id"]: p for p in data.get("pieces", [])}


def _save(pieces_by_id):
    data = {"pieces": [pieces_by_id[k] for k in sorted(pieces_by_id)]}
    os.makedirs(os.path.dirname(_PIECES_PATH), exist_ok=True)
    with open(_PIECES_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def all_pieces():
    """Every registered piece (migrated grid districts + any freestanding piece), sorted by id --
    the ONE iteration source tools/build_world.py's master loop consumes (FREESTANDING_PIECES_PLAN.md
    §D), replacing `for gy in range(GRID_N): for gx in range(GRID_N):`."""
    return [_load()[k] for k in sorted(_load())]


def piece_by_id(piece_id):
    """A single piece dict, or None -- used by session tooling's resolve_item() replacement
    (FREESTANDING_PIECES_PLAN.md §E) instead of regex/file-existence probing."""
    return _load().get(piece_id)


def set_piece(piece_id, footprint, position, load_radius=None, unload_radius=None, theme=None,
              grid=None):
    """Add or overwrite one piece entry and rewrite pieces.json -- a simple read-modify-write.
    `footprint`/`position` are 3-item (x,y,z) sequences; `load_radius`/`unload_radius` stay None
    unless this piece needs an explicit override (see module docstring); `theme` is optional (a
    freestanding piece may have none). `grid` is the piece's `(gx, gy)` address (see
    world_grid.grid_cell_of) -- stored explicitly, not just derivable from `position`, so no
    caller ever needs to re-derive it (e.g. seam-adjacency, id generation); optional because a
    piece registered before this field existed, or a genuinely un-addressed one, may not have
    one."""
    pieces = _load()
    pieces[piece_id] = {
        "id": piece_id,
        "footprint": [float(v) for v in footprint],
        "position": [float(v) for v in position],
        "load_radius": float(load_radius) if load_radius is not None else None,
        "unload_radius": float(unload_radius) if unload_radius is not None else None,
        "theme": theme,
        "grid": [int(grid[0]), int(grid[1])] if grid is not None else None,
    }
    _save(pieces)
    return pieces[piece_id]


def remove_piece(piece_id):
    """Drop one piece from the registry (e.g. a district that's since been voided). No-op if
    absent."""
    pieces = _load()
    if piece_id in pieces:
        del pieces[piece_id]
        _save(pieces)
