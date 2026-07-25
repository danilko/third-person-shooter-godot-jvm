#!/usr/bin/env python3
"""
build_debug_preview.py — like render_cluster.py (composites N REAL, already-baked district
.blend pieces at their true world positions) but SAVES the assembled scene as an openable .blend
instead of only rendering a flat top-down PNG, so you can fly the Blender viewport around and
actually inspect edges/connectors/seams/landmarks in 3D, at any angle, not just from directly above.

Same O(1)-per-piece placement as render_cluster.py (one Collection-Instance empty per district, NOT
iterating/flattening individual objects -- a piece can hold thousands of markers, see that script's
comment) -- this is the same mechanism, just persisted instead of thrown away after one render.

USES TRUE LIBRARY LINKING (`link=True`), not append. This matters a lot in practice, not just in
principle: a procedural filler district can hold 20,000+ tiny marker objects (one bpy object per
kit-instance point, see kit_common._emit_markers), and APPENDING (`link=False`, copies + remaps
every datablock into the local file) took over 60 SECONDS and didn't even finish for a single one
such district -- measured directly, not assumed. True linking loaded the exact same file in 1.4
SECONDS. Real PLATEAU precincts are much lighter regardless (Shibuya: 875 objects total), so this
matters most for procedural fillers, but true linking is faster across the board and is also what
makes this tool genuinely useful for iterative hand-refinement: since linked data is a live
reference (not a copy), re-opening a saved preview after editing a SOURCE district/landmark .blend
directly shows the edit -- no rebuild step. (Linked data is read-only in the outer file unless you
explicitly "Make Local" it in the Blender UI -- a feature here, not a limitation: it stops you
accidentally editing the source out from under yourself while just inspecting.)

Usage:
  blender --background --python tools/build_debug_preview.py -- <out_name> \\
      <blend1>:<gx1>:<gy1> [<blend2>:<gx2>:<gy2> ...] [--harbor] [--ring]

  --harbor  also links in the harbor content (Haneda/Rainbow Bridge) from world_master.blend
  --ring    also links in the C1 Loop ring content from world_master.blend

Examples:
  # the resid_0_1 <-> Shibuya edge (the connector-stub obstacle investigation):
  blender --background --python tools/build_debug_preview.py -- _debug_edge \\
      districts/District_city_1_1.blend:1:1 districts/District_resid_0_1.blend:0:1

  # the harbor:
  blender --background --python tools/build_debug_preview.py -- _debug_harbor --harbor

  # the WHOLE 36-district world (fast now -- seconds, not the 5+ minutes append needed):
  # generate the arg list with lib/world_grid.py's theme_at()/district_center() per (gx,gy),
  # or see this session's scratch space for the exact one-liner used to build it.

Output: assets/world_source/<out_name>.blend -- open directly in Blender (not a bake-tool host
scene, just a plain inspection copy of LINKED references; the real per-district source files are
untouched unless you deliberately "Make Local" something).
"""
import bpy, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # assets/world_source
sys.path.insert(0, os.path.join(ROOT, "lib"))
import world_grid as wg
import kit_common as kc

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) < 1:
    print(__doc__)
    sys.exit(2)
out_name = argv[0]
want_harbor = "--harbor" in argv
want_ring = "--ring" in argv
specs = []
for tok in argv[1:]:
    if tok.startswith("--"):
        continue
    path, gx, gy = tok.rsplit(":", 2)
    specs.append((path, int(gx), int(gy)))

kc.setup_units()
sc = bpy.context.scene
dest = kc.get_coll("DEBUG_PREVIEW")

bounds = []
for path, gx, gy in specs:
    abspath = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(abspath):
        print(f"WARNING: {abspath} does not exist -- skipped")
        continue
    with bpy.data.libraries.load(abspath, link=True) as (src, dst):
        dst.collections = [c for c in src.collections if c == "STREET"]
    st = dst.collections[0] if dst.collections else None
    if st is None:
        print(f"WARNING: {abspath} has no STREET collection -- skipped")
        continue
    cx, cy = wg.district_center(gx, gy)
    inst = bpy.data.objects.new(f"Piece_{gx}_{gy}", None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = st
    inst.location = (cx, cy, 0.0)
    dest.objects.link(inst)
    bounds.append((cx, cy))
    print(f"placed {os.path.basename(path)} at district ({gx},{gy}) -> world ({cx:.0f},{cy:.0f})", flush=True)

if want_harbor or want_ring:
    master_path = os.path.join(ROOT, "world_master.blend")
    if os.path.exists(master_path):
        want = []
        if want_harbor:
            want.append("HARBOR")
        if want_ring:
            want.append("RING")
        with bpy.data.libraries.load(master_path, link=True) as (src, dst):
            dst.collections = [c for c in src.collections if c in want]
        for st in dst.collections:
            if st is None:
                continue
            inst = bpy.data.objects.new(f"Master_{st.name}", None)
            inst.instance_type = 'COLLECTION'
            inst.instance_collection = st
            inst.location = (0.0, 0.0, 0.0)  # world_master's own content is already world-placed
            dest.objects.link(inst)
            bounds.append((0.0, 0.0))
            print(f"linked master collection {st.name}", flush=True)
    else:
        print(f"WARNING: {master_path} not found -- --harbor/--ring skipped")

if not bounds:
    print("ERROR: nothing placed")
    sys.exit(1)

# a simple sun + ortho top-down camera framing the assembled content, purely as a starting
# viewport aid -- the point of saving a .blend is to fly the viewport around freely afterward.
xs = [b[0] for b in bounds]; ys = [b[1] for b in bounds]
ccx, ccy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
span = max(max(xs) - min(xs), max(ys) - min(ys)) + wg.DISTRICT * 1.5

sun_data = bpy.data.lights.new("DebugSun", type='SUN')
sun_data.energy = 3.0
sun = bpy.data.objects.new("DebugSun", sun_data)
sun.location = (ccx + 100, ccy - 100, 300)
sun.rotation_euler = (0.9599, 0, 0.6109)
dest.objects.link(sun)

cam_data = bpy.data.cameras.new("DebugCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = span
cam_data.clip_end = kc.VIEW_CLIP_END
cam = bpy.data.objects.new("DebugCam", cam_data)
cam.location = (ccx, ccy, 400)
dest.objects.link(cam)
sc.camera = cam

out_path = os.path.join(ROOT, out_name + ".blend")
bpy.ops.wm.save_as_mainfile(filepath=out_path)
print(f"saved {out_path} -- {len(bounds)} pieces, span={span:.0f} m, centre=({ccx:.0f},{ccy:.0f})")
print("Open directly in Blender to inspect (fly the viewport -- this is a plain scene copy, "
      "not a bake-tool host; editing it does not affect the real per-district source .blend files).")
