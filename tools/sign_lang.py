#!/usr/bin/env python3
"""sign_lang.py -- the displayed names in a SECOND language (user, 2026-10-12: "keep the Japanese style name, and do a
language conversion as needed; for now keep Japanese, but also able to go Chinese Traditional (English subtitle on
both)").

The names stay Japanese-style -- 西通り, 駅前通り, 海都高速 環状線 -- and the Traditional Chinese line is the SAME name
written the way a Traditional-Chinese town with a Japanese-era street grid writes it: the kana go (通り -> 通,
日の出 -> 日之出), the shinjitai become the traditional forms (駅 -> 驛, 桜 -> 櫻, 湾 -> 灣, 環状 -> 環狀), and the one
kokuji with no Chinese form is replaced by its word (峠 -> 嶺). ONE table, here; `to_zh` refuses a name it cannot
finish (a kana left over), so a new street name cannot ship half converted. English is not converted: the romaji
subtitle is the same under both.
"""
import re

#: longest first: words before the single characters inside them
WORDS = (("日の出", "日之出"), ("道の駅", "道之驛"), ("通り", "通"), ("まもなく", "即將進站"), ("次は", "下一站"),
         ("ドアが開きます", "車門開啟"), ("当駅止まり", "本站終點"), ("先発", "本班"), ("次発", "次班"), ("運休", "停駛"),
         ("普通", "區間車"), ("拉致", "綁架"), ("身代金", "贖金"), ("入院", "送醫"), ("方面", "方向"))
CHARS = {"駅": "驛", "桜": "櫻", "浜": "濱", "辺": "邊", "灯": "燈", "稲": "稻", "緑": "綠", "寿": "壽", "弁": "辯",
         "栄": "榮", "湾": "灣", "状": "狀", "絡": "絡", "連": "聯", "鉄": "鐵", "産": "產", "学": "學", "団": "團",
         "黒": "黑", "会": "會", "参": "參", "峠": "嶺", "麦": "麥", "発": "發", "着": "到", "行": "往", "車": "車",
         "区": "區", "駐": "駐", "広": "廣", "国": "國", "県": "縣", "図": "圖", "沢": "澤", "条": "條", "竜": "龍",
         "写": "寫", "売": "賣", "楽": "樂", "薬": "藥", "医": "醫", "関": "關", "転": "轉", "横": "橫", "対": "對"}
KANA = re.compile("[぀-ヿ]")


def to_zh(ja):
    s = ja
    for a, b in WORDS:
        s = s.replace(a, b)
    s = "".join(CHARS.get(c, c) for c in s)
    if KANA.search(s):
        raise SystemExit("sign_lang: %r still carries kana after conversion (%r): add its word to WORDS" % (ja, s))
    return s


if __name__ == "__main__":
    assert to_zh("西通り") == "西通" and to_zh("駅前通り") == "驛前通" and to_zh("日の出通り") == "日之出通"
    assert to_zh("海都高速 環状線") == "海都高速 環狀線" and to_zh("神社峠") == "神社嶺" and to_zh("空港連絡線") == "空港聯絡線"
    assert to_zh("黒鉄会") == "黑鐵會" and to_zh("中央") == "中央"
    print("sign_lang self-test OK")
