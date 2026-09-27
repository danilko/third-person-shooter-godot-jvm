#!/usr/bin/env python3
"""make_jp_font.py -- the Japanese font the game draws street names with: a SUBSET of Noto Sans CJK JP (SIL OFL 1.1,
credited in CREDITS.md), holding only the characters the game actually shows, so it is kilobytes, not 32 MB.

    python3 tools/make_jp_font.py [--src <NotoSansCJK .ttc/.otf>] [--check]

Input characters: `IslandStreetNames.json`'s `chars` (every street name, written by tools/island_street_names.py) +
ASCII + the kana. Output: `src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf`, a STATIC Bold instance
(the variable font pinned at wght 700: a road sign is bold). Re-run after the street names change; `--check` exits 1
when a character the names need is missing from the committed subset. Needs `fonttools` (pip install fonttools).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
NAMES = os.path.join(ROOT, "src/main/resources/com/openworld/world/IslandStreetNames.json")
OUT = os.path.join(ROOT, "src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf")
SRC = "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc"
KANA = "".join(chr(c) for c in range(0x3041, 0x3097)) + "".join(chr(c) for c in range(0x30A1, 0x30FB)) + "ー・、。「」"


def wanted():
    doc = json.load(open(NAMES))
    return set(doc["chars"]) | set(chr(c) for c in range(0x20, 0x7F)) | set(KANA)


def main(argv):
    from fontTools.ttLib import TTFont, TTCollection
    need = wanted()
    if "--check" in argv:
        if not os.path.exists(OUT):
            print("make_jp_font: MISSING %s" % OUT)
            return 1
        cmap = TTFont(OUT).getBestCmap()
        missing = sorted(c for c in need if ord(c) not in cmap and not c.isspace())
        print("make_jp_font: %s" % ("up to date" if not missing else "MISSING %s" % "".join(missing)))
        return 1 if missing else 0
    src = argv[argv.index("--src") + 1] if "--src" in argv else SRC
    from fontTools import subset
    from fontTools.varLib import instancer
    if src.endswith(".ttc"):
        coll = TTCollection(src)
        font = next(f for f in coll.fonts if "JP" in f["name"].getDebugName(1))
    else:
        font = TTFont(src)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": 700})
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(need)))
    sub.subset(font)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    font.save(OUT)
    print("make_jp_font: %d characters -> %s (%d KB)" % (len(need), os.path.relpath(OUT, ROOT),
                                                       os.path.getsize(OUT) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
