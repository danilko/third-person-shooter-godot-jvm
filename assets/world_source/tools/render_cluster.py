#!/usr/bin/env python3
"""
render_cluster.py — top-down composite render of N REAL, already-baked district .blend
pieces together, so you can actually see whether their edges/roads/blocks line up —
not the abstract world_master.blend blockout (theme plates + arterial lines only), the
real per-district geometry each piece's own build_district.py produced.

Each district .blend is authored at ORIGIN (spans [-half,+half], see build_district.py's
recenter()) — this script appends each one's STREET collection into one working scene and
translates it to its world position (lib/world_grid.district_center(gx,gy)), the same
placement WorldZoneManager applies at runtime, then renders one ortho top-down shot
spanning the combined bounding box.

Usage:
  blender --background --python tools/render_cluster.py -- <out_prefix> \\
      <blend1>:<gx1>:<gy1> <blend2>:<gx2>:<gy2> ...

Example (the Shibuya / city_2_1 / resid_1_2 cluster):
  blender --background --python tools/render_cluster.py -- _preview_cluster \\
      districts/District_city_1_1.blend:1:1 \\
      districts/District_city_2_1.blend:2:1 \\
      districts/District_resid_1_2.blend:1:2
"""
import bpy, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import world_grid as wg

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) < 2:
    print(__doc__)
    sys.exit(2)
prefix = argv[0]
specs = []
for tok in argv[1:]:
    path, gx, gy = tok.rsplit(":", 2)
    specs.append((path, int(gx), int(gy)))

sc = bpy.context.scene
dest = bpy.data.collections.new("CLUSTER")
sc.collection.children.link(dest)

bounds = []
for path, gx, gy in specs:
    abspath = path if os.path.isabs(path) else os.path.join(ROOT, path)
    with bpy.data.libraries.load(abspath, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == "STREET"]
    st = dst.collections[0]
    if st is None:
        print(f"WARNING: {abspath} has no STREET collection — skipped")
        continue
    cx, cy = wg.district_center(gx, gy)
    # ONE Collection-Instance empty carries the whole piece's world offset — O(1) regardless of
    # how many objects are inside. Do NOT iterate/reposition individual objects here: each piece
    # can hold thousands of markers (kit_common._emit_markers' one-bpy-object-per-instance-point
    # pattern), and touching them one at a time hits the same superlinear Blender per-object
    # overhead that made a dense cells=72 district bake take 10+ minutes (see AUTHORING_GUIDE.md /
    # CONFIG's comment in build_district.py) — this render tool doesn't need to repeat that mistake.
    inst = bpy.data.objects.new(f"Piece_{gx}_{gy}", None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = st
    inst.location = (cx, cy, 0.0)
    dest.objects.link(inst)
    bounds.append((cx, cy))
    print(f"placed {os.path.basename(path)} at district ({gx},{gy}) -> world ({cx:.0f},{cy:.0f})")

if not bounds:
    print("ERROR: nothing placed — check the blend:gx:gy args")
    sys.exit(1)

xs = [b[0] for b in bounds]; ys = [b[1] for b in bounds]
ccx = (min(xs) + max(xs)) / 2.0
ccy = (min(ys) + max(ys)) / 2.0
# span = cluster extent + one district's worth of margin on each side so edge content isn't clipped.
span = max(max(xs) - min(xs), max(ys) - min(ys)) + wg.DISTRICT * 1.5

for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'):
    try:
        sc.render.engine = eng
        break
    except Exception:
        continue
sc.render.resolution_x = 1600
sc.render.resolution_y = 1600
try:
    sc.view_settings.view_transform = 'Standard'
except Exception:
    pass

acam_d = bpy.data.cameras.new("ClusterCam"); acam_d.type = 'ORTHO'
acam_d.ortho_scale = span; acam_d.clip_end = 100000.0
acam = bpy.data.objects.new("ClusterCam", acam_d)
dest.objects.link(acam)
acam.location = (ccx, ccy, 400)
acam.rotation_euler = (0, 0, 0)
sc.camera = acam

sc.render.filepath = os.path.join(ROOT, f"{prefix}_aerial.png")
bpy.ops.render.render(write_still=True)
print(f"rendered {prefix}_aerial.png — {len(bounds)} pieces, span={span:.0f} m, "
      f"centre=({ccx:.0f},{ccy:.0f})")
