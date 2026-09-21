#!/usr/bin/env python3
"""Take the yellow cast out of the downtown kit and make the inner walls white (PLAN.md 3.18e, user-reported:
"the building texture seems all yellowish, but Japanese buildings are black/red; inner walls always more white").

MEASURED first, which is what made the fix specific. The mean of each base-colour texture, sampled over the PNG:

    T_Trim_BaseColor        146.4 135.1 102.0   R-B +44.4   <- the tile facade: every `tile_*` row, and the sides
    T_MarbleFloor           181.0 162.1 132.1   R-B +48.9      of nearly every type
    T_RedBrick              109.5  81.4  65.9   R-B +43.6   (correct: brick IS red)
    T_Ornaments             146.5 140.7 119.3   R-B +27.2
    T_MetalConcrete          99.7  95.2  90.7   R-B  +9.0
    T_Concrete              127.2 124.4 121.9   R-B  +5.3   (neutral)

and two defects the measurement named that no screenshot would have separated:

  * `MI_Trim`, `MI_Trim_Dark` and `MI_Trim_Green` are the SAME texture with NO tint on any of them, so the kit's
    three trim variants render identically -- a "dark" shopfront frame is the same tan as the wall behind it;
  * `MI_InteriorWall` is on `T_RedBrick_BaseColor`, so every interior wall in the game is brick brown. A Japanese
    interior wall is flat white plaster, so it is moved onto the neutral concrete texture and tinted white rather
    than having a brick pattern bleached.

The tint is the multiplier that puts a texture's channel means on ONE neutral target: `albedo_color = target /
mean`, per channel. So each row below is read "this surface should read as a <target> grey", which is a decision
to argue with, rather than a colour picked by eye. `albedo_color` multiplies the texture, so a value over 1
brightens and clips the brightest texels -- kept in view by printing the resulting mean beside the target.

Run: python3 tools/building_kit/retone_downtown_kit.py [--check]
"""
import json, os, re, sys

KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                   "assets/world_source/kits/quaternius_downtown_city")
MATS = os.path.normpath(os.path.join(KIT, "materials"))
TEX = "res://assets/world_source/kits/quaternius_downtown_city/textures"

# measured mean of each base-colour texture (sRGB bytes), by texture stem
MEAN = {
    "T_Trim": (146.4, 135.1, 102.0),
    "T_MarbleFloor": (181.0, 162.1, 132.1),
    "T_RedBrick": (109.5, 81.4, 65.9),
    "T_Ornaments": (146.5, 140.7, 119.3),
    "T_MetalConcrete": (99.7, 95.2, 90.7),
    "T_Concrete": (127.2, 124.4, 121.9),
    "T_Concrete_Asphalt": (58.8, 57.6, 56.4),
    "T_RoofSlate": (73.2, 73.2, 73.2),
    "T_Dirt": (90.0, 78.8, 70.3),
}

# WHAT A JAPANESE FACADE ACTUALLY MEASURES (studied 2026-09-20 at the user's ask, from two sources they named):
#
#   /data/danilko/concept_arts/japan_city.blend -- PLATEAU, textured, 3048 real Tokyo facade materials.
#       RE-MEASURED 2026-09-21 by `blender/tools/measure_plateau_facades.py`, which states its method:
#       luminance p10 100.0, MEDIAN 135.6, p90 160.6, mean 132.6, R-B +0.9. (The numbers this comment carried
#       before -- p10 113 / median 146 / p90 168 -- were about ten levels brighter and had no way to be
#       re-derived. Rows below whose target was set against the old median are marked.)
#   /data/danilko/references/japan/20240317_133825.jpg -- the user's own street photograph:
#       built mean R-B -13.8, every cluster cool, sunlit facades 195/201/202.
#
# The two disagree, and the disagreement IS the finding: the photograph is LIT BY A BLUE SKY, so its cool cast is
# lighting, which our own sky light applies again at run time -- tinting the albedo cool as well would count it
# twice. PLATEAU's photogrammetry is averaged over a whole city and largely de-lit, so it is the ALBEDO source.
# What it says is that Tokyo is NEUTRAL (R-B +1.7, and a +-7 spread over 3048 materials) and MID-LIGHT (146), not
# bright -- so the targets below sit at ~150, not at the 178 this table first carried. Dark accents keep their
# own number: PLATEAU's p10 of 113 is a limit of aerial photogrammetry, not evidence that Tokyo has no black
# panel, and the user asked for black.
#
# material -> (texture stem to wear, neutral target mean, why)
PLAN = {
    "MI_Trim":              ("T_Trim", 136.0, "the 磁器タイル facade -- tone 0 (see TONE_LEVELS)"),
    "MI_Trim_Dark":         ("T_Trim", 52.0, "dark panel and sash: the near-black the kit's name always claimed"),
    "MI_Trim_Green":        ("T_Trim", 140.0, "balcony guard: grey aluminium, not green"),
    "MI_Trim_MetalConcrete":("T_MetalConcrete", 136.0, "the panel facade -- tone 0 (see TONE_LEVELS)"),
    "MI_Ornaments":         ("T_Ornaments", 150.0, "cornices and mouldings, neutral (set against the OLD median; not re-tuned here)"),
    "MI_InteriorWall":      ("T_Concrete", 214.0, "white plaster (moved OFF the red-brick texture)"),
    "MI_InteriorRoof":      ("T_Concrete", 226.0, "white ceiling"),
    "MI_InteriorFloor":     ("T_MarbleFloor", 212.0, "white tile floor (user: a Japanese shop floor is white square tile)"),
}
# left alone on purpose, and why
KEEP = {"MI_RedBrick": "brick is red, and the user asked for red",
        "MI_RedBrick_Pale": "ditto, pale",
        "MI_Concrete": "already neutral (R-B +5.3)",
        "MI_Asphalt": "already neutral (R-B +2.4)",
        "MI_Glass": "a tint, not a texture",
        "MI_Dirt": "ground, warm is correct",
        "MI_StreetDecals": "paint",
        "MI_FakeInterior": "a lit-window fake, its own look"}


# --- the texture itself, not just its mean (PLAN.md 3.18e, user: "the grey in the game still has a reddish cast,
# unlike the photo or PLATEAU's clean grey/white -- can the material be changed?").
#
# They are right, and it is a limit of the tint above: `albedo_color` MULTIPLIES, so it can move a texture's mean
# onto a neutral target while every rust-streaked texel stays rust. The kit's `T_Trim` and `T_Ornaments` carry
# painted-on weathering, and no per-material colour removes a per-TEXEL hue.
#
# So the chroma is taken out of the texture and only the LUMINANCE detail is kept: `<stem>_Neutral.png` is the
# same image with each texel replaced by its own Rec.709 luminance. The panel joints, the grain and the wear all
# survive -- they are luminance -- and the colour cast does not. The kit's own colour is then entirely the
# material's `albedo_color`, which is the project's rule for this kit anyway (3.6b step 2, option (a): the .tres
# owns the look). Derived from the kit's CC0 textures and written beside them, like any other generated asset.
#
# T_RedBrick is NOT in this list: brick is red, and the user asked for red.
NEUTRALISE = ("T_Trim", "T_Ornaments", "T_MetalConcrete", "T_Concrete", "T_MarbleFloor")
NEUTRAL_SUFFIX = "_Neutral"

# ... and the RUST STAINS go with the hue (user, 2026-09-20: "remove the rust in the textures, keep the normal").
# Taking the luminance removes the orange but leaves the stain's own darkness as grey blotching. The two are
# separable by SCALE, which is what makes this a filter and not a judgement: a rust run is hundreds of texels
# across, a tile joint or a panel edge is a few. So the neutral copy keeps only what survives a high pass --
# `detail = lum - blur(lum, FLATTEN_RADIUS)` -- laid back on a flat field. The joints, the panel lines and the
# grain stay crisp (they are high frequency); the blotches go. The NORMAL and ORM maps are untouched, so the
# surface keeps all of its relief and its roughness variation.
FLATTEN_RADIUS = 48        # texels, on the kit's 2048 px maps: well above a joint, well below a stain
FLATTEN_GAIN = 1.0         # 1.0 keeps the detail at its original contrast


def neutralise(check):
    """Write `<stem>_Neutral.png` for every texture in NEUTRALISE: its own luminance, so the detail stays and the
    hue goes. Returns the list that changed."""
    from PIL import Image
    import numpy as np
    tex = os.path.normpath(os.path.join(KIT, "textures"))
    changed = []
    for stem in NEUTRALISE:
        src = os.path.join(tex, stem + "_BaseColor.png")
        dst = os.path.join(tex, stem + NEUTRAL_SUFFIX + ".png")
        if not os.path.exists(src):
            print("  MISSING %s" % src)
            continue
        from PIL import ImageFilter
        im = Image.open(src).convert("RGBA")
        a = np.asarray(im, dtype=np.float32)
        lum = a[:, :, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        radius = FLATTEN_RADIUS * im.size[0] / 2048.0        # the same real scale on a 1024 px map
        blur = np.asarray(Image.fromarray(lum.astype("uint8"), "L")
                          .filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
        flat = float(lum.mean()) + (lum - blur) * FLATTEN_GAIN
        out = np.stack([flat, flat, flat, a[:, :, 3]], axis=2).clip(0, 255).astype("uint8")
        body = Image.fromarray(out, "RGBA")
        before = None
        if os.path.exists(dst):
            before = np.asarray(Image.open(dst).convert("RGBA"), dtype=np.uint8)
        if before is None or before.shape != out.shape or not (before == out).all():
            changed.append(stem)
            if not check:
                body.save(dst)
        r, g, b = (float(a[:, :, i].mean()) for i in range(3))
        blotch_before = float(np.std(blur))
        blotch_after = float(np.std(np.asarray(Image.fromarray(flat.clip(0, 255).astype("uint8"), "L")
                                               .filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)))
        print("  %-18s %5.1f %5.1f %5.1f  R-B %+5.1f  ->  grey %5.1f, R-B +0.0; blotching %.1f -> %.1f, "
              "detail sd %.1f kept" % (stem, r, g, b, r - b, float(flat.mean()), blotch_before, blotch_after,
                                       float(np.std(lum - blur))))
    return changed


def tint(stem, target):
    r, g, b = MEAN[stem]
    if stem in NEUTRALISE:
        # the neutral copy IS its own luminance, so one factor serves all three channels
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return (target / lum, target / lum, target / lum)
    return (target / r, target / g, target / b)


def texture_stem(stem):
    return stem + NEUTRAL_SUFFIX if stem in NEUTRALISE else stem


def patch(text, stem, colour):
    """Set `albedo_color` in the [resource] block, and point the three maps at `stem`'s set."""
    for kind, suffix in (("albedo_texture", "_BaseColor"), ("metallic_texture", "_ORM"),
                         ("roughness_texture", "_ORM"), ("normal_texture", "_Normal")):
        pass
    # re-point every ext_resource that is one of this kit's textures at `stem`'s own set
    def repoint(m):
        path = m.group(1)
        base = os.path.basename(path)
        if base.endswith("_BaseColor.png") or base.endswith(NEUTRAL_SUFFIX + ".png"):
            return m.group(0).replace(path, "%s/%s.png" % (TEX, texture_stem(stem)
                                                           if stem in NEUTRALISE else stem + "_BaseColor"))
        for tail in ("_ORM.png", "_Normal.png"):
            if base.endswith(tail):
                return m.group(0).replace(path, "%s/%s%s" % (TEX, stem, tail))
        return m.group(0)
    text = re.sub(r'\[ext_resource type="Texture2D" path="([^"]+)"[^\]]*\]', repoint, text)
    line = "albedo_color = Color(%.4f, %.4f, %.4f, 1)" % colour
    if re.search(r"^albedo_color = .*$", text, re.M):
        text = re.sub(r"^albedo_color = .*$", line, text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(\[resource\]\n)", r"\1" + line + "\n", text, count=1, flags=re.M)
    return text


# --- ONE TONE PER BUILDING, NOT ONE TONE PER CITY (PLAN.md 3.18p, user 2026-09-21: "every facade is the same
# grey; Tokyo is a MIXTURE").
#
# The table above gives `MI_Trim` ONE target, and the merged mesh is per TYPE and shared, so every building of a
# type wears it -- which trades "all yellow" for "all grey". What a street looks like is a SPREAD.
#
# RE-MEASURED 2026-09-21, and the re-measurement is itself a finding. The percentiles this file carried (p10
# 113 / median 146 / p90 168) had no way to be re-derived, so `blender/tools/measure_plateau_facades.py` now
# exists and states its method -- and over the SAME 3048 materials it reads about ten luminance levels DARKER:
#
#       p5 88.5   p10 100.0   p25 116.2   p35 125.0   MEDIAN 135.6   p75 150.9   p90 160.6   p95 165.9
#       mean 132.6, R-B +0.9
#
# Two things follow. Tokyo is GREY (R-B +0.9 over 3048 materials), so every tone below is a LUMINANCE on the
# same neutral texture and never a hue. And the shipped single target of 150 sat at this distribution's p75 --
# the whole city was lit a quarter brighter than its reference -- so `MI_Trim` moves onto the measured MEDIAN.
#
# Three of the four tones are measured percentiles outright. The fourth is a stated extension: PLATEAU is aerial
# photogrammetry, averaged and largely de-lit, which compresses both tails -- the same reason this file already
# says its dark end "is a limit of aerial photogrammetry, not evidence that Tokyo has no black panel" -- and a
# white porcelain-tile facade is ordinary in Tokyo and the user asked for white.
#
#       Slate 100 (p10)   Trim 136 (median)   Light 161 (p90)   Pale 185 (past p95: white tile)
#
# The base material is one of the four, so a building with no override still wears one of the city's tones.
#
# A FACADE IS TWO MATERIALS HERE, NOT ONE, and naming only the tile one would have left the mixture out of
# exactly the places that look most uniform. The kit's walls come in two families: `Trim_*` pieces wear
# `MI_Trim` (the 磁器タイル tile of a mansion, a shop-house, a pencil building) and `Metal_*` pieces wear
# `MI_Trim_MetalConcrete` (the panel of an office, a warehouse, a konbini -- and the SIDES of nearly every other
# type). Measured after the first pass: 4 of 19 types had a tile surface at all, so downtown's offices and the
# harbour's warehouses would have kept one grey between them. Both families get the same four levels.
#
# The variants are written FROM their own base `.tres`, so a change to a facade's textures, roughness or normal
# map reaches its four with no second recipe to keep in step. `facade_tones.json` beside them is the one record
# of which materials are facades and which tones exist -- read by `build_building_scenes.gd` (to write down
# WHICH merged surface each is, which only the merge knows) and by `tools/island_buildings.py` (to choose one
# tone per building and override every facade surface it has).
FACADES = ("MI_Trim", "MI_Trim_MetalConcrete")
# suffix, target, why -- the levels, shared by every facade family. Index 0 IS the base material.
TONE_LEVELS = (
    ("",       136.0, "mid grey: the measured PLATEAU median"),
    ("_Pale",  185.0, "white, past p95 (photogrammetry compresses the light tail)"),
    ("_Light", 161.0, "light grey: the measured p90"),
    ("_Slate", 100.0, "dark grey: the measured p10"),
)
TONES_JSON = "facade_tones.json"


def write_tones(check):
    """Write each tone variant of every facade material from its own base `.tres`, and the record naming them."""
    changed, doc = [], {}
    for facade in FACADES:
        base = os.path.join(MATS, facade + ".tres")
        if not os.path.exists(base):
            print("  MISSING %s" % base)
            return None
        src, stem = open(base).read(), PLAN[facade][0]
        names = []
        for suffix, target, _why in TONE_LEVELS:
            name = facade + suffix
            names.append(name)
            if suffix == "":
                continue                  # the base IS tone 0; `main` has already written it
            path = os.path.join(MATS, name + ".tres")
            body = patch(src, stem, tint(stem, target))
            body = re.sub(r'^resource_name = .*$', 'resource_name = "%s"' % name, body, count=1, flags=re.M)
            if not os.path.exists(path) or open(path).read() != body:
                changed.append(name)
                if not check:
                    open(path, "w").write(body)
        doc[facade] = names
        print("facade tones (%s): %s" % (facade, ", ".join(
            "%s %.0f" % (n, t) for n, (_s, t, _w) in zip(names, TONE_LEVELS))))
    record = {"_comment": "PLAN.md 3.18p. Written by tools/building_kit/retone_downtown_kit.py -- do not hand-edit.",
              "levels": [{"suffix": s_, "target": t, "why": w} for s_, t, w in TONE_LEVELS],
              "facades": doc}
    jpath = os.path.join(MATS, TONES_JSON)
    text = json.dumps(record, indent=2) + "\n"
    if not os.path.exists(jpath) or open(jpath).read() != text:
        changed.append(TONES_JSON)
        if not check:
            open(jpath, "w").write(text)
    return changed



# --- THE SHOP WINDOW'S 目隠しシート (PLAN.md 3.18o follow-up, user 2026-09-21: "in Japan the store window glass
# CAN see internal folks -- just in the middle of the glass there is a strip along the whole window, white gloss
# with the store's colour stripes; top and bottom stay transparent").
#
# So a konbini's glass is not frosted and never was: what hides the customers' faces is an opaque privacy strip
# applied across the middle of every panel at about eye height. The strip is white with the store's livery
# stripes through it, which is what makes one chain read as a different chain without naming either -- these are
# brand-neutral liveries, not any real chain's mark.
#
# These are FLAT materials with no texture (a strip is painted vinyl), so they are written whole rather than
# derived from one of the kit's maps.
SHOP_BAND = {
    "MI_ShopBand":         (0.93, 0.93, 0.92, "the white gloss strip the stripes run through"),
    "MI_ShopStripe_Blue":  (0.10, 0.36, 0.66, "livery A"),
    "MI_ShopStripe_Green": (0.11, 0.46, 0.27, "livery B"),
    "MI_ShopStripe_Red":   (0.72, 0.16, 0.16, "livery C"),
    "MI_ShopStripe_Amber": (0.88, 0.52, 0.09, "livery D"),
}


# A SHOPFRONT'S GLASS IS CLEARER THAN A TOWER'S, which is the follow-up `MI_Glass` itself records: its own
# comment says the ground storey wants its own clearer material and that "the row table knows which rows are
# shopfronts, the MERGED mesh no longer does". It does now -- the layout records each piece's row -- so a
# shopfront panel on a building with a real interior wears this instead. A Tokyo tower's upper glazing stays
# reflective; a konbini's window is nearly clear, because you are meant to see the shop.
SHOP_GLASS = ("MI_GlassShopfront", (0.66, 0.74, 0.78, 0.14), 0.05)


def write_shop_glass(check):
    name, c, rough = SHOP_GLASS
    text = ('[gd_resource type="StandardMaterial3D" format=3]\n\n[resource]\n'
            'resource_name = "%s"\ntransparency = 4\ncull_mode = 2\n'
            'albedo_color = Color(%.4f, %.4f, %.4f, %.4f)\nroughness = %.2f\n' % ((name,) + c + (rough,)))
    path = os.path.join(MATS, name + ".tres")
    print("  %-22s alpha %.2f -- a shop window, not a tower's glazing" % (name, c[3]))
    if os.path.exists(path) and open(path).read() == text:
        return []
    if not check:
        open(path, "w").write(text)
    return [name]


def write_shop_band(check):
    changed = write_shop_glass(check)
    for name, (r, g, b, why) in sorted(SHOP_BAND.items()):
        text = ('[gd_resource type="StandardMaterial3D" format=3]\n\n[resource]\n'
                'resource_name = "%s"\nalbedo_color = Color(%.4f, %.4f, %.4f, 1)\n'
                'roughness = 0.35\nmetallic = 0.0\n' % (name, r, g, b))
        path = os.path.join(MATS, name + ".tres")
        if not os.path.exists(path) or open(path).read() != text:
            changed.append(name)
            if not check:
                open(path, "w").write(text)
        print("  %-22s (%.2f %.2f %.2f)  %s" % (name, r, g, b, why))
    return changed


def main(argv):
    check = "--check" in argv
    print("neutralising the kit's base-colour textures (the tint cannot reach a per-texel hue):")
    changed = list(neutralise(check))
    print()
    print("%-24s %-18s %-7s  tint                 -> mean" % ("material", "texture", "target"))
    for name, (stem, target, why) in sorted(PLAN.items()):
        path = os.path.join(MATS, name + ".tres")
        if not os.path.exists(path):
            print("  MISSING %s" % path)
            return 2
        col = tint(stem, target)
        src = MEAN[stem]
        if stem in NEUTRALISE:      # the neutral copy is one luminance value in all three channels
            src = (0.2126 * src[0] + 0.7152 * src[1] + 0.0722 * src[2],) * 3
        got = tuple(min(255.0, c * m) for c, m in zip(col, src))
        print("%-24s %-18s %7.0f  (%.3f %.3f %.3f) -> %5.1f %5.1f %5.1f   %s"
              % (name, stem, target, col[0], col[1], col[2], got[0], got[1], got[2], why))
        body = patch(open(path).read(), stem, col)
        if body != open(path).read():
            changed.append(name)
            if not check:
                open(path, "w").write(body)
    print()
    print("the shop window's privacy strip:")
    changed += write_shop_band(check)
    print()
    tones = write_tones(check)
    if tones is None:
        return 2
    changed += tones
    print()
    for name, why in sorted(KEEP.items()):
        print("  kept %-22s %s" % (name, why))
    print("retone: %s" % ("%d material(s) change" % len(changed) if changed else "up to date"))
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
