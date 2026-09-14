"""point_ground.py -- the ground a road is built over, read from a height-grid sidecar (PLAN.md 3.1 B6b).

A road authored in the Godot editor is solved and meshed here with NO terrain in the Blender scene --
the terrain is Terrain3D, and it lives in Godot. Every support decision is `delta = surface_z -
ground_z` per sample (`point_solve.solve_road`), and with no terrain to raycast each sample fell back
to a LERP of its stations' `ground_z`: a 3-station road over a 150 m gap got a triangle of columns
under its middle station, standing on a ground that is not there, instead of a bridge.

The Godot plugin (`addons/road_kit/road_kit_ground.gd`) writes the ground itself:

    <stem>.ground.json  {"schema_ver": 1, "origin": [x0, y0], "step": 2.0, "nx": .., "ny": .., "bin": "<stem>.ground.bin"}
    <stem>.ground.bin   float32 little-endian, row-major; row j is y = y0 + j*step, column i is x = x0 + i*step;
                        NaN where the terrain has no data

in the NETWORK's frame and the kit's axes -- the frame the `.roads.json` record is written in -- so a
`GroundGrid` is a drop-in `ground_fn(x, y) -> z | None` for `point_build.solve_all`.

A MISS IS NOT ZERO, the same rule the raycast sampler keeps: outside the grid, or where any of the
four cells around a point is NaN, the answer is None and the solve keeps the station's own
`ground_z` there. Bilinear over the four cells, never nearest -- a 2 m staircase under a 4 m sample
would flicker a road near FILL_MAX between FILL and PIER.

Pure python3 (no bpy), so the numbers are testable anywhere: `python3 point_ground.py` self-tests.
"""

import array
import json
import math
import os
import sys

SCHEMA_VER = 1


class GroundGrid(object):
    """A height grid in the network frame. Call it: `grid(x, y) -> z or None`."""

    __slots__ = ("x0", "y0", "step", "nx", "ny", "h", "hits", "misses")

    def __init__(self, x0, y0, step, nx, ny, heights):
        if len(heights) != nx * ny:
            raise ValueError("ground grid: %d heights for a %dx%d grid" % (len(heights), nx, ny))
        if step <= 0.0 or nx < 2 or ny < 2:
            raise ValueError("ground grid: step %.3f and %dx%d cannot interpolate" % (step, nx, ny))
        self.x0, self.y0, self.step, self.nx, self.ny = float(x0), float(y0), float(step), int(nx), int(ny)
        self.h = heights
        #: Counters for the build report: how many queries found ground, how many did not.
        self.hits = self.misses = 0

    def __call__(self, x, y):
        fx = (float(x) - self.x0) / self.step
        fy = (float(y) - self.y0) / self.step
        i, j = int(math.floor(fx)), int(math.floor(fy))
        # The far edge is inside the grid: clamp the cell so a query exactly on it still interpolates.
        if i == self.nx - 1 and fx <= self.nx - 1 + 1e-9:
            i -= 1
        if j == self.ny - 1 and fy <= self.ny - 1 + 1e-9:
            j -= 1
        if i < 0 or j < 0 or i >= self.nx - 1 or j >= self.ny - 1:
            self.misses += 1
            return None
        tx, ty = fx - i, fy - j
        n = self.nx
        a, b = self.h[j * n + i], self.h[j * n + i + 1]
        c, d = self.h[(j + 1) * n + i], self.h[(j + 1) * n + i + 1]
        if any(v != v for v in (a, b, c, d)):          # NaN: the terrain has no data here
            self.misses += 1
            return None
        self.hits += 1
        return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def load_ground(json_path):
    """A `GroundGrid` from a `<stem>.ground.json` sidecar (and the `.bin` it names)."""
    with open(json_path) as f:
        head = json.load(f)
    ver = int(head.get("schema_ver", 0))
    if ver != SCHEMA_VER:
        raise ValueError("%s: ground schema_ver %s, this build reads %d" % (json_path, ver, SCHEMA_VER))
    nx, ny = int(head["nx"]), int(head["ny"])
    bin_path = os.path.join(os.path.dirname(os.path.abspath(json_path)), head["bin"])
    heights = array.array("f")
    with open(bin_path, "rb") as f:
        heights.frombytes(f.read())
    if sys.byteorder != "little":
        heights.byteswap()
    return GroundGrid(head["origin"][0], head["origin"][1], float(head["step"]), nx, ny, heights)


def write_ground(json_path, x0, y0, step, nx, ny, heights):
    """The inverse of `load_ground` -- used by the self-test and by tools that make a grid in python."""
    bin_path = os.path.splitext(json_path)[0] + ".bin"
    arr = array.array("f", heights)
    if sys.byteorder != "little":
        arr.byteswap()
    with open(bin_path, "wb") as f:
        f.write(arr.tobytes())
    with open(json_path, "w") as f:
        json.dump({"schema_ver": SCHEMA_VER, "origin": [x0, y0], "step": step, "nx": nx, "ny": ny,
                   "bin": os.path.basename(bin_path)}, f, indent=1)
        f.write("\n")


def _self_test():
    import tempfile
    # A plane z = 2x + 3y + 1 is reproduced EXACTLY by bilinear interpolation -- anywhere inside.
    nx, ny, step, x0, y0 = 11, 6, 2.0, -10.0, 4.0
    hs = [2 * (x0 + i * step) + 3 * (y0 + j * step) + 1 for j in range(ny) for i in range(nx)]
    d = tempfile.mkdtemp()
    p = os.path.join(d, "T.ground.json")
    write_ground(p, x0, y0, step, nx, ny, hs)
    g = load_ground(p)
    for (x, y) in ((-10.0, 4.0), (-3.3, 7.7), (10.0, 14.0), (0.0, 13.99)):
        z = g(x, y)
        assert z is not None and abs(z - (2 * x + 3 * y + 1)) < 1e-3, (x, y, z)
    print("OK: a plane is reproduced exactly, far edges included")
    assert g(-10.01, 5.0) is None and g(10.01, 5.0) is None and g(0.0, 3.99) is None and g(0.0, 14.01) is None
    print("OK: outside the grid is a MISS (None), not zero")
    hs[2 * nx + 3] = float("nan")
    write_ground(p, x0, y0, step, nx, ny, hs)
    g = load_ground(p)
    assert g(x0 + 3.5 * step, y0 + 2.5 * step) is None and g(x0 + 2.5 * step, y0 + 1.5 * step) is None
    assert g(x0 + 5.5 * step, y0 + 2.5 * step) is not None
    print("OK: a NaN cell (off the terrain) is a miss for the four cells that touch it, and only them")
    assert g.hits == 1 and g.misses == 2, (g.hits, g.misses)
    print("OK: hits/misses are counted for the build report")


if __name__ == "__main__":
    _self_test()
