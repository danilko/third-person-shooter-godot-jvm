#!/usr/bin/env python3
"""island_street_names.py -- every road of the island gets a REAL Japanese street name (user, 2026-09-26: "update
street with real street name"), shown on the signal name plates (the kit's "E 12 St" plate is gone) and on the
minimap.

    python3 tools/island_street_names.py [<record>] [--check]

Writes `src/main/resources/com/openworld/world/IslandStreetNames.json`:
    {"roads": {<base road name>: {"ja": "中央通り", "en": "Chuo-dori", "kind": "arterial"}}, "chars": "..."}
A road's BASE name is its record name without the zone/joint suffixes (`chuo_dori__3__x1` -> `chuo_dori`): every
piece of one street carries one name. `chars` is every character the game must draw (the font subset's input:
`tools/make_jp_font.py`).

Where a name comes from, and nothing is typed per generated street:
* the ARTERIALS, the expressway and the authored streets are named by `NAMED` below -- their romaji already IS a
  Japanese name (`chuo_dori` 中央通り), so this is a transliteration table, one row per street;
* every GENERATED street (`island_streets`: `machi_342`, `nishi_cho_561`, `hata_yoko_920`, ...) is drawn from a pool
  of the names Japanese towns really give their streets (桜通り, 本町通り, 昭和通り, 銀杏並木, 八幡通り ...) chosen by a
  hash of its base name, so an unchanged record keeps its names; the pool is per DISTRICT KIND (a farm road is a 農道,
  an industry street a 産業道路 / 工場通り), and a name is used once on the island (the next free one is taken on a
  collision, in sorted base-name order, so the answer is deterministic).
Run by `island_world.sh`'s layout stage after `island_layout.py`. `--check` exits 1 if the file would change.
"""
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
RECORD = os.path.join(ROOT, "assets/world_source/pieces/IslandRoads.roads.json")
#: DebugWorld's roads are named too (its signals carry plates): its four roads, by hand
DEBUG_RECORD = os.path.join(ROOT, "assets/world_source/pieces/DebugRoads.roads.json")
OUT = os.path.join(ROOT, "src/main/resources/com/openworld/world/IslandStreetNames.json")

#: base road name -> (kanji, romaji, kind). kind: expressway / arterial / street / farm / access
#: FICTIONAL on purpose (user, 2026-09-30, for legal reasons): no displayed name may be a real expressway brand or
#: route (the expressway is 海都高速 "Kaito Expwy", not 首都高 / Shuto) or a famous real Tokyo road (山手通り, 明治通り,
#: 昭和通り, 春日通り, 白山通り, 公園通り, 湾岸通り, 臨海通り, 海岸通り and Tokyo's 中央通り were renamed). Generic Japanese
#: street words (駅前通り, 本町通り, 桜通り) stay: every town has them. Internal road ids (`shuto_*`) are never shown.
NAMED = {
    # DebugWorld (tools/debug_world_layout.py)
    "w_ring": ("西環状通り", "Nishi-kanjo-dori", "arterial"),
    "e_ring": ("東環状通り", "Higashi-kanjo-dori", "arterial"),
    "w_ns": ("南北通り", "Nanboku-dori", "street"),
    "w_ew": ("東西通り", "Tozai-dori", "street"),
    "link": ("連絡橋通り", "Renraku-kyo-dori", "arterial"),
    "chuo_dori": ("中央大路", "Chuo-oji", "arterial"),
    "nishi_dori": ("西通り", "Nishi-dori", "arterial"),
    "rinkai_dori": ("浜風通り", "Hamakaze-dori", "arterial"),
    "ring_kita": ("外周環状通り", "Gaishu-kanjo-dori", "arterial"),
    "kaigan_dori": ("磯辺通り", "Isobe-dori", "arterial"),
    "kaigan_machi": ("磯辺町通り", "Isobe-machi-dori", "arterial"),
    "wangan_dori": ("入江通り", "Irie-dori", "arterial"),
    "eki_minami_dori": ("駅南通り", "Eki-minami-dori", "arterial"),
    "ekimae_dori": ("駅前通り", "Ekimae-dori", "arterial"),
    "yamate_dori": ("丘手通り", "Okate-dori", "arterial"),
    "yamate_dori_w": ("丘手西通り", "Okate-nishi-dori", "arterial"),
    "nishi_hondori": ("西本通り", "Nishi-hondori", "arterial"),
    "naka_hondori": ("中本通り", "Naka-hondori", "arterial"),
    "higashi_hondori": ("東本通り", "Higashi-hondori", "arterial"),
    "kichi_dori": ("基地通り", "Kichi-dori", "street"),
    "kichi_mon_michi": ("基地正門通り", "Kichi-seimon-dori", "access"),
    "jokamachi_dori": ("城下町通り", "Jokamachi-dori", "street"),
    "jokamachi_sando": ("城参道", "Shiro-sando", "access"),
    "kogai_michi": ("郊外通り", "Kogai-dori", "street"),
    "kogai_loop": ("浜辺通り", "Hamabe-dori", "street"),
    "butsuryu_michi": ("物流通り", "Butsuryu-dori", "street"),
    "todai_michi": ("灯台通り", "Todai-dori", "access"),
    "michinoeki_michi": ("道の駅通り", "Michi-no-eki-dori", "access"),
    "airport_dori": ("空港通り", "Kuko-dori", "arterial"),
    "airport_dori_loop": ("空港通り", "Kuko-dori", "arterial"),
    "shrine_touge": ("神社峠", "Jinja-toge", "arterial"),
    "c1_ura_nishi": ("裏西通り", "Ura-nishi-dori", "street"),
    "c1_ura_higashi": ("裏東通り", "Ura-higashi-dori", "street"),
    "nodo_waku": ("田園通り", "Den-en-dori", "farm"),
    "kojo_waku": ("工場通り", "Kojo-dori", "street"),
    "teibo_sokudo": ("堤防側道", "Teibo-sokudo", "street"),
    "shuto_c1": ("海都高速 環状線", "Kaito Expwy Loop", "expressway"),
    "shuto_wangan": ("海都高速 潮風線", "Kaito Expwy Shiokaze", "expressway"),
    "shuto_spur": ("海都高速 空港連絡線", "Kaito Expwy Airport Link", "expressway"),
}
#: a generated street's pool by the region its STEM names (`island_plan.STREET_NAMES`)
POOLS = {
    "street": [("桜通り", "Sakura-dori"), ("本町通り", "Honcho-dori"), ("陽光通り", "Yoko-dori"),
               ("鈴蘭通り", "Suzuran-dori"), ("星見通り", "Hoshimi-dori"), ("平和通り", "Heiwa-dori"),
               ("若葉通り", "Wakaba-dori"), ("緑町通り", "Midoricho-dori"), ("旭通り", "Asahi-dori"),
               ("錦通り", "Nishiki-dori"), ("寿通り", "Kotobuki-dori"), ("八幡通り", "Hachiman-dori"),
               ("稲荷通り", "Inari-dori"), ("弁天通り", "Benten-dori"), ("日の出通り", "Hinode-dori"),
               ("朝日通り", "Asahi-dori"), ("富士見通り", "Fujimi-dori"), ("汐見通り", "Shiomi-dori"),
               ("仲通り", "Naka-dori"), ("栄通り", "Sakae-dori"), ("銀杏通り", "Icho-dori"),
               ("松原通り", "Matsubara-dori"), ("柳通り", "Yanagi-dori"), ("宮前通り", "Miyamae-dori"),
               ("新町通り", "Shinmachi-dori"), ("元町通り", "Motomachi-dori"), ("東町通り", "Higashimachi-dori"),
               ("南町通り", "Minamimachi-dori"), ("北町通り", "Kitamachi-dori"), ("風見通り", "Kazami-dori"),
               ("月見通り", "Tsukimi-dori"), ("天神通り", "Tenjin-dori"), ("大和通り", "Yamato-dori"),
               ("青葉通り", "Aoba-dori"), ("紅葉通り", "Momiji-dori"), ("梅通り", "Ume-dori"),
               ("藤通り", "Fuji-dori"), ("菊通り", "Kiku-dori"), ("中町通り", "Nakamachi-dori"),
               ("市場通り", "Ichiba-dori"), ("学園通り", "Gakuen-dori"), ("桔梗通り", "Kikyo-dori"),
               ("文化通り", "Bunka-dori"), ("商店街通り", "Shotengai-dori"), ("大通り", "O-dori")],
    "industry": [("産業道路", "Sangyo-doro"), ("工業通り", "Kogyo-dori"), ("鉄工通り", "Tekko-dori"),
                 ("運河通り", "Unga-dori"), ("倉庫通り", "Soko-dori"), ("埠頭通り", "Futo-dori"),
                 ("製作所通り", "Seisakusho-dori"), ("新開地通り", "Shinkaichi-dori"), ("港南通り", "Konan-dori"),
                 ("浜町通り", "Hamacho-dori")],
    "farm": [("北田農道", "Kitada-nodo"), ("南田農道", "Minamida-nodo"), ("池田農道", "Ikeda-nodo"),
             ("上田農道", "Ueda-nodo"), ("下田農道", "Shimoda-nodo"), ("稲田農道", "Inada-nodo"),
             ("麦田農道", "Mugita-nodo"), ("水田農道", "Suiden-nodo"), ("新田農道", "Shinden-nodo"),
             ("中田農道", "Nakada-nodo")],
}
POOL_OF_STEM = {"hata": "farm", "kojo": "industry", "koba": "industry", "butsuryu": "industry"}


def base(name):
    return name.split("__")[0]


def generated_kind(b):
    stem = b.split("_")[0]
    return POOL_OF_STEM.get(stem, "street")


def names_for(bases):
    out, used = {}, set()
    for b in sorted(bases):
        # longest matching key first: `shuto_spur_out_w` is the airport line, `teibo_sokudo_3` a dike side road
        hit = NAMED.get(b) or next((NAMED[k] for k in sorted(NAMED, key=len, reverse=True) if b.startswith(k + "_")),
                                   None)
        if hit is None and b.startswith("shuto_"):
            hit = ("海都高速", "Kaito Expwy", "expressway")
        if hit is not None:
            out[b] = {"ja": hit[0], "en": hit[1], "kind": hit[2]}
            continue
    used = {v["ja"] for v in out.values()}
    for b in sorted(bases):
        if b in out:
            continue
        pk = generated_kind(b)
        pool = POOLS[pk]
        i = zlib.crc32(b.encode()) % len(pool)
        for k in range(len(pool)):
            ja, en = pool[(i + k) % len(pool)]
            if ja not in used:
                break
        else:                                   # the pool ran out: number the street within its name (二丁目 style)
            n = sum(1 for v in out.values() if v["ja"].startswith(ja)) + 1
            ja, en = ja + "%d" % n, en + " %d" % n
        used.add(ja)
        out[b] = {"ja": ja, "en": en, "kind": "farm" if pk == "farm" else "street"}
    return out


def main(argv):
    rec = next((a for a in argv if not a.startswith("--")), RECORD)
    roads = json.load(open(rec))["roads"]
    if os.path.exists(DEBUG_RECORD):
        roads = roads + json.load(open(DEBUG_RECORD))["roads"]
    names = names_for({base(r["name"]) for r in roads})
    chars = sorted({c for v in names.values() for c in v["ja"] + v["en"]}
                   | set("0123456789-丁目交差点前駅入口出方面料金所終点先")          # + the green expressway signs
                   | set("EXITENTRANCEJCTkm→←↑↓"))
    doc = {"notes": "Written by tools/island_street_names.py from %s: each road's BASE name (no __ suffix) -> its "
                    "Japanese street name. Read by world.StreetNames." % os.path.relpath(rec, ROOT),
           "roads": names, "chars": "".join(chars)}
    text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    old = open(OUT).read() if os.path.exists(OUT) else ""
    if "--check" in argv:
        print("island_street_names: %s" % ("up to date" if old == text else "STALE"))
        return 0 if old == text else 1
    if old != text:
        open(OUT, "w").write(text)
    kinds = {}
    for v in names.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print("island_street_names: %d streets named %s, %d glyphs -> %s" % (len(names), kinds, len(chars),
                                                                         os.path.relpath(OUT, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
