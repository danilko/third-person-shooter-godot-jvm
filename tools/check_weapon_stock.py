#!/usr/bin/env python3
"""Every weapon in the catalog can be GOT somewhere on the island (PLAN.md 3.2 H4).

    python3 tools/check_weapon_stock.py [--control]

Reads what a player can actually reach, never a list kept beside it:
  * weapon/weapon_catalog.json   -- every weapon id (Fist excepted: everybody has one);
  * world/places/World.places.json -- the buildings PLACED on the island, by kind;
  * world/buildings/<Kind>.tscn  -- each placed kind's BAKED shop counters (`"stock": "..."` in a MARK_shop_counter's
    props, which is what ShopCounter sells). A kit's pieces.json or a shop .blend is not enough: a counter only sells
    once its building is re-baked, and a kind with no place on the island sells to nobody.
Prints, per weapon, where it is sold (kind x how many placed), then every weapon sold NOWHERE. Exit 1 if any.
Also printed, for information only: which AI tables arm a body with it (character/loadouts.json, game/crimes.json,
game/gangs.json) -- a weapon a downed body DROPS can be picked up, but the gate is that it can be BOUGHT.

--control drops the KonbiniL / KonbiniS counters, which must then fail on the guns only they sell.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "src/main/resources/com/openworld")
CATALOG = os.path.join(RES, "weapon/weapon_catalog.json")
PLACES = os.path.join(RES, "world/places/World.places.json")
BUILDINGS = os.path.join(RES, "world/buildings")
STOCK = re.compile(r'"stock":\s*"([^"]*)"')
ARMED_BY = {"character/loadouts.json": "loadouts", "game/crimes.json": "police dispatch", "game/gangs.json": "gangs"}
ARM_KEYS = ("weapons", "extra", "weapons_by_stars", "police_weapons")


def armed_by(ids):
    """{id: [table, ...]} for every catalog id named under an ARM_KEYS key in the AI tables."""
    out = {i: set() for i in ids}

    def walk(o, label, armed):
        if isinstance(o, dict):
            for k, v in o.items():
                if armed and k in ids:                 # {"PIS1": 3.0}: a weighted pick
                    out[k].add(label)
                walk(v, label, armed or k in ARM_KEYS)
        elif isinstance(o, list):
            for v in o:
                walk(v, label, armed)
        elif armed and isinstance(o, str) and o in ids:
            out[o].add(label)

    for rel, label in ARMED_BY.items():
        walk(json.load(open(os.path.join(RES, rel))), label, False)
    return out


def main():
    control = "--control" in sys.argv
    ids = [r["id"] for r in json.load(open(CATALOG))["weapons"] if r["id"] != "Fist"]
    placed = {}
    for p in json.load(open(PLACES))["places"]:
        placed[p["kind"]] = placed.get(p["kind"], 0) + 1
    sold = {i: [] for i in ids}
    for kind, n in sorted(placed.items()):
        if control and kind in ("KonbiniL", "KonbiniS"):
            continue
        path = os.path.join(BUILDINGS, kind + ".tscn")
        if not os.path.exists(path):
            continue
        stock = set()
        for m in STOCK.finditer(open(path, encoding="utf-8").read()):
            stock.update(s.strip() for s in m.group(1).split(",") if s.strip())
        for i in ids:
            if i in stock:
                sold[i].append(f"{kind} x{n}")
    missing = [i for i in ids if not sold[i]]
    armed = armed_by(set(ids))
    for i in ids:
        drop = f"   (dropped by: {', '.join(sorted(armed[i]))})" if armed[i] else ""
        print(f"{'PASS' if sold[i] else 'FAIL'}  {i:5s} {', '.join(sold[i]) if sold[i] else 'sold nowhere'}{drop}")
    print(f"\n{'FAIL' if missing else 'PASS'}: {len(ids) - len(missing)} of {len(ids)} catalog weapons can be bought"
          + (f"; sold nowhere: {', '.join(missing)}" if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
