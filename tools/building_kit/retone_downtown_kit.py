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
import os, re, sys

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

# material -> (texture stem to wear, neutral target mean, why)
PLAN = {
    "MI_Trim":              ("T_Trim", 178.0, "the 磁器タイル facade: light off-white tile, the commonest wall in a Japanese street"),
    "MI_Trim_Dark":         ("T_Trim", 52.0, "dark panel and sash: the near-black the kit's name always claimed"),
    "MI_Trim_Green":        ("T_Trim", 140.0, "balcony guard: grey aluminium, not green"),
    "MI_Trim_MetalConcrete":("T_MetalConcrete", 168.0, "exposed concrete / ALC panel"),
    "MI_Ornaments":         ("T_Ornaments", 150.0, "cornices and mouldings, neutral"),
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


def tint(stem, target):
    r, g, b = MEAN[stem]
    return (target / r, target / g, target / b)


def patch(text, stem, colour):
    """Set `albedo_color` in the [resource] block, and point the three maps at `stem`'s set."""
    for kind, suffix in (("albedo_texture", "_BaseColor"), ("metallic_texture", "_ORM"),
                         ("roughness_texture", "_ORM"), ("normal_texture", "_Normal")):
        pass
    # re-point every ext_resource that is one of this kit's textures at `stem`'s own set
    def repoint(m):
        path = m.group(1)
        base = os.path.basename(path)
        for tail in ("_BaseColor.png", "_ORM.png", "_Normal.png"):
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


def main(argv):
    check = "--check" in argv
    changed = []
    print("%-24s %-18s %-7s  tint                 -> mean" % ("material", "texture", "target"))
    for name, (stem, target, why) in sorted(PLAN.items()):
        path = os.path.join(MATS, name + ".tres")
        if not os.path.exists(path):
            print("  MISSING %s" % path)
            return 2
        col = tint(stem, target)
        got = tuple(min(255.0, c * m) for c, m in zip(col, MEAN[stem]))
        print("%-24s %-18s %7.0f  (%.3f %.3f %.3f) -> %5.1f %5.1f %5.1f   %s"
              % (name, stem, target, col[0], col[1], col[2], got[0], got[1], got[2], why))
        body = patch(open(path).read(), stem, col)
        if body != open(path).read():
            changed.append(name)
            if not check:
                open(path, "w").write(body)
    for name, why in sorted(KEEP.items()):
        print("  kept %-22s %s" % (name, why))
    print("retone: %s" % ("%d material(s) change" % len(changed) if changed else "up to date"))
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
