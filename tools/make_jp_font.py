#!/usr/bin/env python3
"""make_jp_font.py -- the sign fonts, ONE PER SIGN LANGUAGE (user, 2026-10-12: Japanese stays the default, Traditional
Chinese is a setting): `NotoSansJP-Signs.otf` from the JP face and the `ja` strings, `NotoSansTC-Signs.otf` from the TC
face and the `zh` strings (the JP face lacks 驛 區 灣 狀 鐵 會 ... and draws shared code points in Japanese shapes).
world.StreetNames.font() picks by world.SignLanguage. Each is a SUBSET of Noto Sans CJK (SIL OFL 1.1,
credited in CREDITS.md), holding only the characters the game actually shows, so it is kilobytes, not 32 MB.

    python3 tools/make_jp_font.py [--src <NotoSansCJK .ttc/.otf>] [--check]

Input characters: `IslandStreetNames.json`'s `chars` (every street name, written by tools/island_street_names.py) +
ASCII + the kana + `UI_WORDS` (what the HUD prints). Output: `src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf`, a STATIC Bold instance
(the variable font pinned at wght 700: a road sign is bold). Re-run after the street names change; `--check` exits 1
when a character the names need is missing from the committed subset. Needs `fonttools` (pip install fonttools).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
NAMES = os.path.join(ROOT, "src/main/resources/com/openworld/world/IslandStreetNames.json")
# the stations' names and the board / in-car screen words (world.TrainSystem)
STATIONS = os.path.join(ROOT, "src/main/resources/com/openworld/world/StationNames.json")
OUT = os.path.join(ROOT, "src/main/resources/com/openworld/ui/fonts/NotoSansJP-Signs.otf")
SRC = "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc"
# words the HUD itself prints (game.RespawnSystem's cards: hospitalized / arrested / abducted, the ransom line, ¥)
UI_WORDS = "入院逮捕拉致身代金運休¥"
# the gangs' names (gangs.json name_ja), printed on the abduction prompt
GANGS = os.path.join(ROOT, "src/main/resources/com/openworld/game/gangs.json")
KANA = "".join(chr(c) for c in range(0x3041, 0x3097)) + "".join(chr(c) for c in range(0x30A1, 0x30FB)) + "ー・、。「」"


sys.path.insert(0, HERE)
import sign_lang          # noqa: E402

OUT_ZH = OUT.replace("NotoSansJP-Signs", "NotoSansTC-Signs")


TABLE = os.path.join(ROOT, "src/main/resources/com/openworld/i18n/signs.csv")


def wanted(lang="ja"):
    """Every character the `lang` column of the string table draws (tools/build_sign_table.py: THE owner of what
    the signs say), plus ASCII, the digits a clock prints and, for Japanese, the kana."""
    import csv
    with open(TABLE, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    chars = set()
    for r in rows:
        chars |= set(r.get(lang) or r.get("ja") or "")
    chars -= set("{}")
    ascii_ = set(chr(c) for c in range(0x20, 0x7F)) | set("¥→←↑↓")
    if lang == "ja":
        return chars | ascii_ | set(KANA)
    return chars | ascii_ | set("、。「」・")


FACES = (("ja", "JP", OUT), ("zh_TW", "TC", OUT_ZH))


def main(argv):
    from fontTools.ttLib import TTFont, TTCollection
    src = argv[argv.index("--src") + 1] if "--src" in argv else SRC
    bad = 0
    for lang, face, out in FACES:
        need = wanted(lang)
        if "--check" in argv:
            if not os.path.exists(out):
                print("make_jp_font: MISSING %s" % out)
                bad = 1
                continue
            cmap = TTFont(out).getBestCmap()
            missing = sorted(c for c in need if ord(c) not in cmap and not c.isspace())
            print("make_jp_font: %s %s" % (lang, "up to date" if not missing else "MISSING %s" % "".join(missing)))
            bad |= 1 if missing else 0
            continue
        from fontTools import subset
        from fontTools.varLib import instancer
        if src.endswith(".ttc"):
            coll = TTCollection(src)
            font = next(f for f in coll.fonts if face in f["name"].getDebugName(1))
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
        os.makedirs(os.path.dirname(out), exist_ok=True)
        font.save(out)
        cmap = TTFont(out).getBestCmap()
        missing = sorted(c for c in need if ord(c) not in cmap and not c.isspace())
        print("make_jp_font: %s %d characters -> %s (%d KB)%s" % (
            lang, len(need), os.path.relpath(out, ROOT), os.path.getsize(out) // 1024,
            "  NOT IN THE FACE: " + "".join(missing) if missing else ""))
        bad |= 1 if missing else 0
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
