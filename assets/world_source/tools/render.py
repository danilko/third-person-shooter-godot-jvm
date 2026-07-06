#!/usr/bin/env python3
"""
render.py — render a town .blend to aerial (top ortho) + iso preview PNGs.

Usage: blender --background <town>.blend --python tools/render.py -- <out_prefix> [cx cy span]
"""
import bpy, sys, math, os

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
prefix = argv[0] if argv else "_preview_town"
cx = float(argv[1]) if len(argv) > 1 else 28.0
cy = float(argv[2]) if len(argv) > 2 else 42.0
span = float(argv[3]) if len(argv) > 3 else 120.0
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)

sc = bpy.context.scene
for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'):
    try:
        sc.render.engine = eng
        break
    except Exception:
        continue
sc.render.resolution_x = 1400
sc.render.resolution_y = 1000
sc.render.film_transparent = False
try:
    sc.view_settings.view_transform = 'Standard'
except Exception:
    pass

# `.library is None` guards against a FOREIGN "STREET" collection true-linked in from a district
# piece (e.g. tools/link_landmark_preview.py against world_master.blend) — a linked collection is
# read-only, so linking a throwaway camera/sun into it crashes; fall back to the scene collection.
_street = bpy.data.collections.get("STREET")
st = _street if (_street is not None and _street.library is None) else sc.collection

# --- aerial: top orthographic ---
acam_d = bpy.data.cameras.new("ACam"); acam_d.type = 'ORTHO'
acam_d.ortho_scale = span
acam = bpy.data.objects.new("ACam", acam_d); st.objects.link(acam)
acam.location = (cx, cy, 200); acam.rotation_euler = (0, 0, 0)
sc.camera = acam
sc.render.filepath = os.path.join(OUT, f"{prefix}_aerial.png")
bpy.ops.render.render(write_still=True)

# --- iso: use the scene's tracked camera if present ---
cam = bpy.data.objects.get("Cam")
if cam:
    sc.camera = cam
    sc.render.filepath = os.path.join(OUT, f"{prefix}_iso.png")
    bpy.ops.render.render(write_still=True)

# --- street-up: optional eye-level camera (e.g. looking up under the viaduct) ---
camup = bpy.data.objects.get("CamUp")
if camup:
    sc.camera = camup
    sc.render.filepath = os.path.join(OUT, f"{prefix}_streetup.png")
    bpy.ops.render.render(write_still=True)

# --- ramp: optional camera framing the expressway ramp / corkscrew interchange ---
camrp = bpy.data.objects.get("CamRamp")
if camrp:
    sc.camera = camrp
    sc.render.filepath = os.path.join(OUT, f"{prefix}_ramp.png")
    bpy.ops.render.render(write_still=True)

# --- off-ramp: optional camera framing the trumpet off-ramp peel + street merge ---
camoff = bpy.data.objects.get("CamOff")
if camoff:
    sc.camera = camoff
    sc.render.filepath = os.path.join(OUT, f"{prefix}_offramp.png")
    bpy.ops.render.render(write_still=True)

# --- intersection: optional camera framing a JP arterial crossing (turn lanes + islands) ---
camint = bpy.data.objects.get("CamInt")
if camint:
    sc.camera = camint
    sc.render.filepath = os.path.join(OUT, f"{prefix}_intersection.png")
    bpy.ops.render.render(write_still=True)

# --- region: optional camera framing the region seam (expressway continuation + roundabout) ---
camreg = bpy.data.objects.get("CamRegion")
if camreg:
    sc.camera = camreg
    sc.render.filepath = os.path.join(OUT, f"{prefix}_region.png")
    bpy.ops.render.render(write_still=True)

# --- str-ramp: optional camera framing the simple straight walled ramp (v1) ---
camstr = bpy.data.objects.get("CamStr")
if camstr:
    sc.camera = camstr
    sc.render.filepath = os.path.join(OUT, f"{prefix}_strramp.png")
    bpy.ops.render.render(write_still=True)

# --- lane-config: optional camera framing the asymmetric 2-lane x 1-lane JP crossing ---
camlc = bpy.data.objects.get("CamLaneCfg")
if camlc:
    sc.camera = camlc
    sc.render.filepath = os.path.join(OUT, f"{prefix}_lanecfg.png")
    bpy.ops.render.render(write_still=True)
print("rendered", prefix)
