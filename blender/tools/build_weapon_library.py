"""The weapon library ("zoo"): every weapon, the character, and each weapon's real reference, in ONE file.

    blender -b --python blender/tools/build_weapon_library.py [-- --render out.png]

Writes `assets/weapons/WeaponLibrary.blend`. Open it to size a new weapon against everything else.

WHY ONE FILE
------------
A weapon modelled alone in its own .blend has nothing to be wrong against: it can be the right
length and still have its origin in the wrong place, a stock too long for the character, or a
pistol the size of a rifle's receiver. That is exactly what happened here — every model's origin sat
wherever a centring offset left it (SG1's on the receiver, 0.48 m from the butt), and nobody could
see it because nobody ever put two weapons side by side. Studios keep a "zoo"/line-up file for this.

WHAT IS IN IT, AND WHY IT IS LINKED
-----------------------------------
* every weapon in `weapon_models.json`, LINKED from its own `assets/weapons/<id>.blend` as a
  collection instance. Linked, not appended: the weapon's .blend stays the one owner, so an edit
  there shows up here on reload, and an edit made here cannot silently fork a copy.
* laid out so the thing being compared lines up: every weapon's ORIGIN (its grip) sits on ONE
  vertical line, one row per weapon — so butts, muzzles and grips read straight across.
* under each weapon, a REFERENCE BAR: the real weapon's overall length, rear-aligned with the model,
  with a tick at the real length of pull (trigger to butt) where the table gives one. A model whose
  muzzle overshoots the bar, or whose trigger is nowhere near the tick, is out of proportion.
* the primitive-only weapons (ATL4, MW2, T1) as boxes at their table size and centre.
* the character (linked from `assets/merged_animation.blend`) and a 1.49 m height stick beside it,
  plus a metre rule with 10 cm ticks.

It is a VIEW: nothing in the game reads it, and `build_weapon.py` never exports it. Re-run this
script after adding a weapon to the table.
"""
import bpy, json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE = os.path.join(ROOT, "blender", "tools", "weapon_models.json")
WEAPONS = os.path.join(ROOT, "assets", "weapons")
OUT = os.path.join(WEAPONS, "WeaponLibrary.blend")
CHARACTER = os.path.join(ROOT, "assets", "merged_animation.blend")
CHARACTER_COLLECTION = "Collection"
CHARACTER_HEIGHT = 1.49     # GodotChan, crown of the head (measured in Godot, rest pose)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RENDER = argv[argv.index("--render") + 1] if "--render" in argv else None

ROW = 0.44                  # vertical spacing between weapon rows (label above, reference bar below)
cfg = json.load(open(TABLE))


def material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def box(name, collection, center, size, mat):
    """An axis-aligned box in BLENDER axes (x, y forward, z up)."""
    me = bpy.data.meshes.new(name)
    hx, hy, hz = (s / 2 for s in size)
    v = [(x, y, z) for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f)
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    o.location = center
    collection.objects.link(o)
    return o


def label(name, collection, text, loc, size=0.028):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = text
    cu.size = size
    o = bpy.data.objects.new(name, cu)
    o.location = loc
    o.rotation_euler = (math.radians(90), 0, math.radians(90))   # readable from the +X side view
    o.data.materials.append(material("M_Label", (0.05, 0.05, 0.05, 1)))
    collection.objects.link(o)
    return o


def godot_to_blender(v):
    x, y, z = v
    return (x, -z, y)


def new_collection(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def link_collection(path, name):
    with bpy.data.libraries.load(path, link=True, relative=True) as (src, dst):
        if name not in src.collections:
            raise SystemExit(f"[weapon_library] {path} has no collection {name!r}")
        dst.collections = [name]
    return dst.collections[0]


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.ops.wm.save_as_mainfile(filepath=OUT)          # save first, so linked paths are made relative
scene = bpy.context.scene
top = scene.collection
c_weapons = new_collection("Weapons", top)
c_refs = new_collection("References", top)
c_rule = new_collection("Rule", top)
m_ref = material("M_Reference", (0.85, 0.25, 0.2, 1))
m_pull = material("M_LengthOfPull", (0.15, 0.35, 0.9, 1))
m_prim = material("M_Primitive", (0.55, 0.55, 0.5, 1))
m_rule = material("M_Rule", (0.2, 0.2, 0.2, 1))

row = 0
for w in cfg["weapons"]:
    z = -row * ROW
    col = link_collection(os.path.join(WEAPONS, w["id"] + ".blend"), w["id"])
    inst = bpy.data.objects.new(w["id"], None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = col
    inst.location = (0, 0, z)
    c_weapons.objects.link(inst)
    ref = w["reference"]
    rear = -w["grip_to_rear_m"]
    bar_z = z - 0.16
    box(w["id"] + "_ref", c_refs, (0, rear + ref["overall_m"] / 2, bar_z), (0.01, ref["overall_m"], 0.008), m_ref)
    if "length_of_pull_m" in ref:
        box(w["id"] + "_pull", c_refs, (0, rear + ref["length_of_pull_m"], bar_z), (0.012, 0.006, 0.04), m_pull)
    label(w["id"] + "_label", c_refs,
          f"{w['id']}  model {w['length_m']:.3f} m, grip->rear {w['grip_to_rear_m']:.3f} m   |   "
          f"ref {ref['based_on']}: {ref['overall_m']:.3f} m"
          + (f", pull {ref['length_of_pull_m']:.3f} m" if "length_of_pull_m" in ref else ""),
          (0.02, -0.75, z + 0.16))
    row += 1

for wid, p in cfg["primitives"].items():
    if not isinstance(p, dict):
        continue
    z = -row * ROW
    sx, sy, sz = p["size"]
    cx, cy, cz = godot_to_blender(p["center"])
    box(wid, c_weapons, (cx, cy, z + cz), (sx, sz, sy), m_prim)      # Godot (x, y, z) size -> Blender (x, z, y)
    ref = p["reference"]
    label(wid + "_label", c_refs, f"{wid}  primitive (.tscn)   |   ref {ref['based_on']}: {ref['overall_m']:.3f} m",
          (0.02, -0.75, z + 0.16))
    row += 1

# The grip line every weapon's origin sits on, and a metre rule under the whole line-up.
bottom = -row * ROW
box("GripLine", c_rule, (0, 0, bottom / 2 + 0.1), (0.004, 0.004, -bottom + 0.3), m_rule)
for i in range(-10, 11):
    tall = 0.05 if i % 5 == 0 else 0.02
    box(f"Tick_{i:+d}", c_rule, (0, i * 0.1, bottom), (0.004, 0.004, tall), m_rule)
box("Rule", c_rule, (0, 0, bottom - tall / 2), (0.004, 2.0, 0.004), m_rule)

# The character, standing behind the line-up, with a height stick.
c_char = new_collection("Character", top)
char_col = link_collection(CHARACTER, CHARACTER_COLLECTION)
ch = bpy.data.objects.new("Character", None)
ch.instance_type = 'COLLECTION'
ch.instance_collection = char_col
ch.location = (0, -1.95, bottom)
c_char.objects.link(ch)
box("HeightStick_1.49m", c_char, (0, -1.5, bottom + CHARACTER_HEIGHT / 2), (0.01, 0.01, CHARACTER_HEIGHT), m_rule)
label("HeightStick_label", c_char, f"{CHARACTER_HEIGHT:.2f} m", (0.02, -1.49, bottom + CHARACTER_HEIGHT + 0.02))

# A side camera, so the file opens (and renders) on the view the line-up is built for.
cam = bpy.data.objects.new("SideCamera", bpy.data.cameras.new("SideCamera"))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 3.95
cam.location = (4.0, -0.83, bottom / 2 + 0.2)
cam.rotation_euler = (math.radians(90), 0, math.radians(90))
top.objects.link(cam)
scene.camera = cam
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.color_type = 'MATERIAL'
scene.render.resolution_x, scene.render.resolution_y = 1500, 1850

bpy.ops.wm.save_as_mainfile(filepath=OUT, relative_remap=True)
print(f"[weapon_library] wrote {OUT}: {len(cfg['weapons'])} linked weapons, "
      f"{sum(1 for p in cfg['primitives'].values() if isinstance(p, dict))} primitives, character")
if RENDER:
    scene.render.filepath = RENDER
    bpy.ops.render.render(write_still=True)
    print(f"[weapon_library] rendered {RENDER}")
