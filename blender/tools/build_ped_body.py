"""Build the LIGHT-PED body: one skinned mesh, one material, one atlas, two clips.

    blender -b --factory-startup --python blender/tools/build_ped_body.py -- --body shino
        [--cell 256] [--gutter 16] [--decimate 0.0] [--keep-face]

reads   assets/characters/<body>/<body>.glb        (the SHIPPED export -- see below)
writes  assets/characters/<body>/<body>_ped.glb

To LOOK at the atlas, import the project (`godot --headless --path . --import`): this project's glTF
import setting is `gltf/embedded_image_handling=1` (Extract Textures), so Godot writes the embedded
atlas out beside the .glb as `<body>_ped_<body>_ped_atlas.png` -- the same convention that produced
the 34 `shino_F00_*.png` beside the body's own export. That extracted file IS the texture the game
samples, so this tool deliberately does not write a second copy of it.

WHY IT READS THE .glb AND NOT THE .blend.  The game plays the exported `.glb`, so the ped LOD is
derived from the same artefact the full body is -- it can never disagree with what is on screen,
and it needs to know nothing about the authoring file (Auto-Rig Pro, the control rig, the linked
weapon libraries, the 173 authored actions).  One tool serves every body for the same reason
`export_character.py` derives its output from the file it was handed.

WHAT IT IS FOR.  `world.PedCrowd`'s far tier draws a script-free body between `promoteDistance`
(80 m) and `drawDistance` (180 m).  At 80 m a 1.65 m body is ~14 px tall on a 1080p screen, so
what costs anything there is DRAW CALLS, not detail: the shipped body is 3 MeshInstance3D but
**17 surfaces with 17 materials**, i.e. ~17 draws per light ped, and ~100 of them are in range in
downtown.  This collapses that to ONE.

WHAT IT DROPS, AND THE MEASUREMENT THAT ALLOWS IT.  The eight sub-pixel face surfaces (iris, white,
highlight, extra, eyelash, eyeline, brow, mouth -- 1 808 tris and 8 of the 17 textures) cannot be
resolved at the nearest distance this body is ever drawn: a HEAD is ~2 px there.  A client, which
may not promote, HIDES its light peds inside `promoteDistance` rather than drawing them close, so
there is no path that puts this body in front of a camera at conversational range.  What is kept is
every surface that carries the SILHOUETTE and its colour: skin, face skin, the four clothing
surfaces, and all three hair surfaces (hair is 53 % of the triangles and is alpha cut-out, so
dropping its alpha would turn it into a block).

THE ATLAS AND ITS ONE KNOWN LIMIT.  Each kept material's base colour is scaled into one cell of a
square grid and the faces using it have their UVs mapped into that cell.  Every cell is grown by a
gutter of its own EDGE pixels (`--gutter`, 16 px), so the first four mip levels cannot sample a
neighbouring cell; past that -- i.e. once the whole ped is a few tens of pixels -- cells do average
into each other, which is a slight colour shift on a body that is already a smudge.  That is the
trade this file makes deliberately: a per-cell mip chain cannot cross glTF, and the alternative
(no atlas) is the 17 draws this exists to remove.

`--decimate` IS A LEVER THAT IS OFF, AND THE ARITHMETIC IS WHY.  The LOD body is 29 403 triangles,
so ~100 light peds in range are ~2.9 M of the ~5.4 M the busiest station cell draws -- a real share,
and a Decimate COLLAPSE keeps vertex groups, so it would work.  It is not applied because the thing
it would buy is already bought: with the atlas alone the station walk measures p95 15.72 ms against
a 16.7 budget.  Turn it on when a measurement asks for it, not before -- and re-run
`probe_ped_body.gd` plus a picture, because a decimate is the one step here that can visibly break
a skinned silhouette.

`--keep-face` keeps the eight sub-pixel surfaces (a 5x5 atlas), for a body that is drawn closer than
this tier ever is.

Everything is measured and printed, and the exporter REFUSES rather than writing a body that has
lost its rig: the bone set, the vertex-group set and the two clips are asserted against the source.
"""
import bpy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # blender/
REPO = os.path.dirname(ROOT)

# The two clips PedCrowd plays (world/PedCrowd.java: WALK_CLIP, RUN_CLIP). A third would be a
# change there first; this list is asserted against the source export, so a rename fails loudly.
# Named the way the GAME names them: the exported action carries the `-loop` suffix Godot's
# importer strips (that suffix is what sets loop mode -- CLAUDE.md "Animation"), so the suffix is
# resolved against the source and KEPT on the way out, or a walk cycle would play once and stop.
CLIPS = ["upright_walk_forward", "upright_sprint_forward"]

# Sub-pixel face detail: see the module docstring. Matched against the MATERIAL name.
ALPHA_CUTOFF = 0.5

DROP_TOKENS = ("EyeWhite", "EyeIris", "EyeHighlight", "EyeExtra",
               "FaceEyelash", "FaceEyeline", "FaceBrow", "FaceMouth")


def argv():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"body": "shino", "cell": 256, "gutter": 16, "decimate": 0.0, "keep-face": False}
    i = 0
    while i < len(a):
        t = a[i]
        if t.startswith("--"):
            k = t[2:]
            if "=" in k:
                k, v = k.split("=", 1)
            elif k == "keep-face":
                v = "1"
            else:
                i += 1
                v = a[i]
            out[k] = v
        i += 1
    out["cell"] = int(out["cell"])
    out["gutter"] = int(out["gutter"])
    out["decimate"] = float(out["decimate"])
    out["keep-face"] = bool(out["keep-face"]) and str(out["keep-face"]) not in ("0", "false")
    return out


def die(msg):
    print(f"[build_ped_body] REFUSED: {msg}")
    sys.exit(1)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                 bpy.data.images, bpy.data.actions, bpy.data.armatures):
        for d in list(coll):
            coll.remove(d)


def tint_node(mat):
    """The MULTIPLY node that tints this material's texture, and its constant input index.

    VRoid tints a GREYSCALE texture with a constant (shino's hair is a dark blue 0.10/0.14/0.22 over
    a white mask), and that constant is the glTF `baseColorFactor`. An atlas that copied the texture
    alone would put a WHITE-HAIRED ped in the crowd -- measured, on the first build of this file.
    """
    if not mat.node_tree:
        return None, -1
    for n in mat.node_tree.nodes:
        if n.type not in ('MIX', 'MIX_RGB') or getattr(n, 'blend_type', '') != 'MULTIPLY':
            continue
        rgba = [i for i in n.inputs if i.type == 'RGBA']
        linked = [i for i in rgba if i.links]
        const = [i for i in rgba if not i.links]
        if len(linked) == 1 and len(const) == 1:
            return n, list(n.inputs).index(const[0])
    return None, -1


def base_tint(mat):
    """This material's Base Color FACTOR -- what its texture is multiplied by."""
    n, idx = tint_node(mat)
    if n is None:
        # no multiply: a Principled material carries the factor on the socket itself
        for b in (mat.node_tree.nodes if mat.node_tree else []):
            if b.type == 'BSDF_PRINCIPLED' and not b.inputs['Base Color'].links:
                return tuple(b.inputs['Base Color'].default_value[:3])
        return (1.0, 1.0, 1.0)
    return tuple(n.inputs[idx].default_value[:3])


def base_image(mat):
    """The image feeding this material's Base Color, or None."""
    if not mat.node_tree:
        return None
    for n in mat.node_tree.nodes:
        if n.type != 'BSDF_PRINCIPLED':
            continue
        link = n.inputs['Base Color'].links
        if not link:
            continue
        src = link[0].from_node
        if src.type == 'TEX_IMAGE' and src.image is not None:
            return src.image
    # a few VRoid setups route through a mix; take the first image node in the tree
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image is not None:
            return n.image
    return None


def image_rgba(img):
    """The image as a uint8 HxWx4 array, top row first (PIL order)."""
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    a = buf.reshape(h, w, 4)[::-1]            # Blender's origin is bottom-left
    return np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)


def main():
    opt = argv()
    body = opt["body"]
    src = os.path.join(REPO, "assets", "characters", body, f"{body}.glb")
    out = os.path.join(REPO, "assets", "characters", body, f"{body}_ped.glb")
    if not os.path.exists(src):
        die(f"no source export {src} -- run export_character.py first")

    drop = () if opt["keep-face"] else DROP_TOKENS
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=src)

    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(arms) != 1:
        die(f"expected one armature in {src}, found {[a.name for a in arms]}")
    arm = arms[0]
    # Only what the armature DEFORMS may enter the ped -- `export_character.deform_armature`'s rule
    # from the other side. Blender's glTF IMPORTER builds a 42-vertex `Icosphere` as the display
    # shape for all 158 bones and leaves it in the scene (in a `glTF_not_exported` collection), so a
    # filter on `type == 'MESH'` silently joins a bone widget into the body.
    meshes = [o for o in bpy.data.objects if o.type == 'MESH'
              and any(m.type == 'ARMATURE' and m.object is arm for m in o.modifiers)]
    if not meshes:
        die("no meshes skinned to the armature in the source export")

    src_bones = {b.name for b in arm.data.bones}
    src_groups = set()
    for m in meshes:
        src_groups |= {g.name for g in m.vertex_groups}
    src_tris = sum(len(m.data.loop_triangles) if m.data.loop_triangles else
                   sum(len(p.vertices) - 2 for p in m.data.polygons) for m in meshes)
    src_mats = []
    for m in meshes:
        for s in m.data.materials:
            if s and s.name not in [x.name for x in src_mats]:
                src_mats.append(s)
    print(f"[build_ped_body] source meshes: {[m.name for m in meshes]}")
    print(f"[build_ped_body] source: {len(meshes)} meshes, {len(src_mats)} materials, "
          f"{src_tris} tris, {len(src_bones)} bones, {len(bpy.data.actions)} actions")

    actions, missing = [], []
    for c in CLIPS:
        name = c if c in bpy.data.actions else (f"{c}-loop" if f"{c}-loop" in bpy.data.actions else None)
        (actions.append(name) if name else missing.append(c))
    if missing:
        die(f"the source export has no clip(s) {missing} -- PedCrowd plays them")

    # ---------------------------------------------------------------- 1. drop the sub-pixel detail
    dropped = []
    for m in meshes:
        keep_idx = []
        for i, s in enumerate(m.data.materials):
            if s is not None and any(t in s.name for t in drop):
                dropped.append(s.name)
            else:
                keep_idx.append(i)
        if len(keep_idx) == len(m.data.materials):
            continue
        keep = set(keep_idx)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = m
        m.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for p in m.data.polygons:
            p.select = p.material_index not in keep
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.delete(type='FACE')
        bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[build_ped_body] dropped {len(dropped)} sub-pixel surface(s): {sorted(dropped)}")

    # ---------------------------------------------------------------- 2. the atlas
    used = []                                   # material -> cell, in a stable order
    for m in meshes:
        for p in m.data.polygons:
            s = m.data.materials[p.material_index] if p.material_index < len(m.data.materials) else None
            if s is not None and s not in used:
                used.append(s)
    if not used:
        die("every surface was dropped")
    cols = int(math.ceil(math.sqrt(len(used))))
    rows = int(math.ceil(len(used) / cols))
    cell, gut = opt["cell"], opt["gutter"]
    inner = cell - 2 * gut
    if inner < 16:
        die(f"--cell {cell} leaves {inner} px inside a {gut} px gutter")
    atlas = np.zeros((rows * cell, cols * cell, 4), dtype=np.uint8)
    slot = {}
    for i, mat in enumerate(used):
        img = base_image(mat)
        c, r = i % cols, i // cols
        slot[mat.name] = (c, r)
        if img is None:
            print(f"[build_ped_body]   {mat.name}: no base-colour image, cell left black")
            continue
        from PIL import Image
        pil = Image.fromarray(image_rgba(img), "RGBA").resize((inner, inner), Image.LANCZOS)
        a = np.asarray(pil).astype(np.float32)
        tint = base_tint(mat)
        if max(abs(t - 1.0) for t in tint) > 1e-3:
            # sRGB texel x linear factor, the way a renderer multiplies them
            lin = np.power(a[:, :, :3] / 255.0, 2.2) * np.asarray(tint, dtype=np.float32)
            a[:, :, :3] = np.power(np.clip(lin, 0.0, 1.0), 1.0 / 2.2) * 255.0
            print(f"[build_ped_body]   {mat.name}: base-colour factor "
                  f"({tint[0]:.3f}, {tint[1]:.3f}, {tint[2]:.3f}) baked in")
        a = np.clip(a + 0.5, 0, 255).astype(np.uint8)
        y0, x0 = r * cell + gut, c * cell + gut
        atlas[y0:y0 + inner, x0:x0 + inner] = a
        # the gutter is this cell's own EDGE pixels, so mips 1-4 cannot reach a neighbour
        atlas[r * cell:y0, x0:x0 + inner] = a[0:1, :, :]
        atlas[y0 + inner:(r + 1) * cell, x0:x0 + inner] = a[-1:, :, :]
        blk = atlas[r * cell:(r + 1) * cell, x0:x0 + inner]
        atlas[r * cell:(r + 1) * cell, c * cell:x0] = blk[:, 0:1, :]
        atlas[r * cell:(r + 1) * cell, x0 + inner:(c + 1) * cell] = blk[:, -1:, :]
        print(f"[build_ped_body]   cell ({c},{r}) <- {mat.name} [{img.size[0]}x{img.size[1]}]")

    print("[build_ped_body] atlas %dx%d cells of %d px (%dx%d)"
          % (cols, rows, cell, cols * cell, rows * cell))

    # ---------------------------------------------------------------- 3. remap the UVs
    for m in meshes:
        uv = m.data.uv_layers.active
        if uv is None:
            die(f"{m.name} has no UV layer")
        for p in m.data.polygons:
            s = m.data.materials[p.material_index] if p.material_index < len(m.data.materials) else None
            if s is None or s.name not in slot:
                continue
            c, r = slot[s.name]
            for li in p.loop_indices:
                u, v = uv.data[li].uv
                # VRoid UVs are inside 0..1; clamp so a stray one cannot cross into a neighbour
                u = min(max(u, 0.0), 1.0)
                v = min(max(v, 0.0), 1.0)
                # the atlas image's row 0 is the TOP; Blender V runs up, so flip the row
                uv.data[li].uv = ((c * cell + gut + u * inner) / (cols * cell),
                                  1.0 - ((r * cell + gut + (1.0 - v) * inner) / (rows * cell)))

    # ---------------------------------------------------------------- 4. one material
    aimg = bpy.data.images.new(f"{body}_ped_atlas", cols * cell, rows * cell, alpha=True)
    aimg.colorspace_settings.name = 'sRGB'
    flat = (atlas[::-1].astype(np.float32) / 255.0).reshape(-1)
    aimg.pixels.foreach_set(flat)
    aimg.pack()

    # THE PED'S MATERIAL IS THE BODY'S MATERIAL WITH THE ATLAS IN IT, never a fresh Principled one.
    # Every shino surface is `KHR_materials_unlit` (a VRoid/VRM import artefact that survives the
    # export, so the shipped body is shadeless), and a LIT ped beside an UNLIT player would change
    # brightness at the moment it promotes, 80 m from the camera. Cloning the graph the body already
    # uses makes the ped match whatever that body is, with nothing here to keep in step.
    donor = max(used, key=lambda m: sum(1 for x in meshes for p in x.data.polygons
                                        if x.data.materials[p.material_index] is m))
    mat = donor.copy()
    mat.name = f"{body}_ped"
    nt = mat.node_tree
    texes = [n for n in nt.nodes if n.type == 'TEX_IMAGE']
    if len(texes) != 1:
        die(f"donor material {donor.name!r} has {len(texes)} image nodes, expected 1")
    tex = texes[0]
    tex.image = aimg
    tex.interpolation = 'Linear'
    tn, ti = tint_node(mat)
    if tn is not None:
        tn.inputs[ti].default_value = (1.0, 1.0, 1.0, 1.0)   # every tint is already in the atlas

    # A CUT-OUT, never a blend: the hair is alpha cards, and one blended surface repeated across a
    # crowd would sort against itself. **Since Blender 4.2 the glTF exporter derives `alphaMode`
    # from the NODE TREE, not from `blend_method`** (`search_node_tree.gather_alpha_info` /
    # `detect_alpha_clip`), so setting `blend_method = 'CLIP'` exports as BLEND and says nothing --
    # measured on the first build of this file. The shape it looks for is a compare on the alpha:
    alpha_out = next((o for o in tex.outputs if o.name == 'Alpha'), None)
    if alpha_out is None:
        die(f"donor material {donor.name!r} has no alpha output on its image node")
    # A MASK donor already carries a clip chain on its alpha (`Alpha -> Math.001 -> Math -> Factor`,
    # the shape `detect_alpha_clip` reads) and a BLEND one wires the alpha straight through. Both
    # must end up as ONE cutoff, so the chain is cut back to the image and re-made here.
    def consumers(node, sock_name):
        # Blender hands back a FRESH Python wrapper for an RNA socket on every access, so `is` on
        # two of them is False even for one socket. Match the node and the socket NAME instead.
        return [l.to_socket for l in list(nt.links)
                if l.from_node == node and l.from_socket.name == sock_name]

    targets, chain, frontier = [], [], consumers(tex, 'Alpha')
    while frontier:
        nxt = []
        for sock in frontier:
            if sock.node.type == 'MATH':          # part of the donor's own clip chain
                if sock.node not in chain:
                    chain.append(sock.node)
                for o in sock.node.outputs:
                    nxt.extend(consumers(sock.node, o.name))
            else:
                targets.append(sock)
        frontier = nxt
    for node in chain:
        nt.nodes.remove(node)
    if not targets:
        die(f"donor material {donor.name!r} does not route the texture's alpha anywhere")
    clip = nt.nodes.new('ShaderNodeMath')
    clip.operation = 'GREATER_THAN'
    clip.inputs[1].default_value = ALPHA_CUTOFF
    nt.links.new(clip.inputs[0], alpha_out)
    for t in targets:
        nt.links.new(t, clip.outputs['Value'])
    mat.use_backface_culling = False          # -> glTF doubleSided: the hair is single-sided cards
    if hasattr(mat, "blend_method"):
        mat.blend_method = 'CLIP'             # the Blender viewport only; the export ignores it
    if hasattr(mat, "alpha_threshold"):
        mat.alpha_threshold = ALPHA_CUTOFF

    for m in meshes:
        m.data.materials.clear()
        m.data.materials.append(mat)
        for p in m.data.polygons:
            p.material_index = 0

    # ---------------------------------------------------------------- 5. one mesh
    bpy.ops.object.select_all(action='DESELECT')
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = f"{body}_ped"
    joined.data.name = f"{body}_ped"

    if opt["decimate"] > 0.0:
        d = joined.modifiers.new("PedDecimate", 'DECIMATE')
        d.decimate_type = 'COLLAPSE'
        d.ratio = opt["decimate"]
        d.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=d.name)

    joined.data.calc_loop_triangles()
    tris = len(joined.data.loop_triangles)
    groups = {g.name for g in joined.vertex_groups}

    # ---------------------------------------------------------------- 6. two clips, on NLA tracks
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    for t in list(ad.nla_tracks):
        ad.nla_tracks.remove(t)
    for name in actions:
        act = bpy.data.actions[name]
        trk = ad.nla_tracks.new()
        trk.name = name
        trk.strips.new(name, int(act.frame_range[0]), act)
    for act in list(bpy.data.actions):
        if act.name not in actions:
            act.use_fake_user = False
            bpy.data.actions.remove(act)

    # ---------------------------------------------------------------- 7. refuse a broken body
    lost = src_groups - groups
    if lost:
        die(f"the join lost {len(lost)} vertex group(s): {sorted(lost)[:8]}")
    if {b.name for b in arm.data.bones} != src_bones:
        die("the bone set changed")
    if tris <= 0:
        die("the joined mesh has no triangles")

    bpy.ops.object.select_all(action='DESELECT')
    for o in (joined, arm):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=out, export_format='GLB', use_selection=True,
        export_apply=False, export_yup=True,
        export_animations=True, export_animation_mode='NLA_TRACKS',
        export_def_bones=True, export_all_influences=False,
        export_skins=True, export_morph=False, export_cameras=False, export_lights=False,
        export_materials='EXPORT', export_image_format='AUTO',
    )
    with open(out, "rb") as fh:
        fh.read(12)
        clen = int.from_bytes(fh.read(4), "little")
        fh.read(4)
        gj = json.loads(fh.read(clen))
    if len(gj["meshes"]) != 1 or len(gj["meshes"][0]["primitives"]) != 1:
        die(f"the export is not ONE surface: {[len(m['primitives']) for m in gj['meshes']]}")
    gm = gj["materials"]
    if len(gm) != 1 or gm[0].get("alphaMode") != "MASK":
        die(f"expected one MASK material, got {[(m.get('name'), m.get('alphaMode')) for m in gm]}")
    got = sorted(a.get("name") for a in gj.get("animations", []))
    if got != sorted(actions):
        die(f"expected clips {sorted(actions)}, got {got}")
    size = os.path.getsize(out)
    print(f"[build_ped_body] {os.path.relpath(out, REPO)}: 1 mesh, 1 material, "
          f"{tris} tris (source {src_tris}, {100.0 * tris / src_tris:.0f} %), "
          f"{len(src_bones)} bones, clips {actions}, {size / 1e6:.1f} MB "
          f"(source {os.path.getsize(src) / 1e6:.1f} MB)")


main()
