#!/usr/bin/env python3
"""build_sign_table.py -- THE STRING TABLE of everything the world writes in a native script
(`src/main/resources/com/openworld/i18n/signs.csv`), keyed by id, one column per language.

    python3 tools/build_sign_table.py [--check]

User, 2026-10-12: "keep these names with id, and names can be more easily translated, without need to recompile";
"for now keep Japanese, but also able to go Chinese Traditional (English subtitle on both)".

    key,ja,zh_TW,en
    street.nishi_dori,西通り,西通,Nishi-dori
    station.Central,中央,中央,Central
    word.exit,出口,出口,EXIT

* The game reads the CSV at start (world.SignText, which also registers every column with Godot's TranslationServer)
  and `user://signs.csv` on top of it, so a translation is an edit and a restart: no compile, no import (the file's
  `.import` says "keep", or Godot would turn it into .translation resources and the raw file would not ship).
* THE CSV IS THE OWNER. This script only ADDS what is missing and never rewrites a cell that is filled:
    - a `street.<id>` row for every road of the island and DebugWorld (its default `ja` / `en` from
      tools/island_street_names.py), and it DROPS the street rows of roads that no longer exist;
    - the `station.*`, `gang.*` and `word.*` rows the game asks for (SEED below), once;
    - an empty cell of a language column this script knows how to derive: `zh_TW` from `ja` by tools/sign_lang.py.
  Any other column (a language somebody added) is carried through untouched; its empty cells stay empty and the game
  falls back to `ja`.
* `--check` exits 1 when the file would change (a road was added or removed and this was not re-run).
Then `python3 tools/make_jp_font.py`: the sign fonts are subsets of exactly the characters in this table.
"""
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import sign_lang          # noqa: E402

OUT = os.path.join(ROOT, "src/main/resources/com/openworld/i18n/signs.csv")
STREETS = os.path.join(ROOT, "src/main/resources/com/openworld/world/IslandStreetNames.json")
STATIONS = os.path.join(ROOT, "src/main/resources/com/openworld/world/StationNames.json")
GANGS = os.path.join(ROOT, "src/main/resources/com/openworld/game/gangs.json")
BASE = ("key", "ja", "zh_TW", "en")
#: the words the game prints beside a name: key -> (ja, en). `{0}` is a name, `{1}` a time.
SEED = {
    "word.exit": ("出口", "EXIT"), "word.entrance": ("入口", "ENTRANCE"), "word.junction": ("JCT", "JCT"),
    "word.train_first": ("先発", "Next"), "word.train_second": ("次発", "Then"),
    "word.train_soon": ("まもなく", "Arriving"), "word.train_departs": ("{1} 発", "dep. {1}"),
    "word.train_local": ("普通", "Local"), "word.train_bound": ("{0} 行", "For {0}"),
    "word.train_none": ("運休", "Not in service"), "word.train_next_stop": ("次は", "Next"),
    "word.train_arrives": ("{1} 着", "arr. {1}"),
    "word.arrested": ("逮捕", "ARRESTED"), "word.abducted": ("拉致", "ABDUCTED"),
    "word.hospitalized": ("入院", "HOSPITALIZED"), "word.ransom": ("身代金", "ransom"),
}
#: the cells a mechanical conversion would get wrong
ZH_FIX = {"station.Light Industry": "工業團地", "word.train_departs": "{1} 開", "word.train_arrives": "{1} 到",
          "word.train_bound": "往 {0}", "word.train_none": "停駛", "word.train_local": "區間車"}


def load():
    if not os.path.exists(OUT):
        return list(BASE), {}
    with open(OUT, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    cols = rows[0]
    return cols, {r[0]: dict(zip(cols, r + [""] * (len(cols) - len(r)))) for r in rows[1:] if r and r[0]}


def main(argv):
    cols, table = load()
    for c in BASE:
        if c not in cols:
            cols.append(c)
    want = {}
    for b, v in json.load(open(STREETS))["roads"].items():
        want["street." + b] = (v["ja"], v["en"])
    if os.path.exists(STATIONS):
        for k, v in json.load(open(STATIONS))["stations"].items():
            want["station." + k] = (v["ja"], v["en"])
    for k, g in json.load(open(GANGS)).get("gangs", {}).items():
        if g.get("name_ja"):
            want["gang." + k] = (g["name_ja"], g.get("name", k))
    want.update(SEED)
    added = dropped = filled = 0
    for key in [k for k in table if k.startswith("street.") and k not in want]:
        del table[key]
        dropped += 1
    for key, (ja, en) in want.items():
        row = table.get(key)
        if row is None:
            row = table[key] = {c: "" for c in cols}
            row.update({"key": key, "ja": ja, "en": en})
            added += 1
        for c in cols:
            row.setdefault(c, "")
        if not row["zh_TW"] and row["ja"]:
            row["zh_TW"] = ZH_FIX.get(key) or sign_lang.to_zh(row["ja"])
            filled += 1
    order = {"street": 0, "station": 1, "gang": 2, "word": 3}
    keys = sorted(table, key=lambda k: (order.get(k.split(".")[0], 9), k))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for k in keys:
        w.writerow([table[k].get(c, "") for c in cols])
    text = buf.getvalue()
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if "--check" in argv:
        print("build_sign_table: %s" % ("up to date" if old == text else "STALE (re-run tools/build_sign_table.py)"))
        return 0 if old == text else 1
    if old != text:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        open(OUT, "w", encoding="utf-8").write(text)
    keep = OUT + ".import"
    if not os.path.exists(keep):
        open(keep, "w").write('[remap]\n\nimporter="keep"\n')
    print("build_sign_table: %d rows x %s; +%d rows, -%d street rows, %d cells derived -> %s" % (
        len(keys), cols[1:], added, dropped, filled, os.path.relpath(OUT, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
