#!/usr/bin/env python3
"""Render the compression design as a single self-contained HTML sheet.

Generated FROM layout.json, so the page can never drift from the data the Blender
tools consume.

    python3 tokyo6km_page.py --in build/tokyo6km --out build/tokyo6km/design.html
"""

from __future__ import annotations

import argparse
import base64
import json
import os

THEME_COL = {
    "city": "#4b2f63", "resid": "#3a3f49", "industry": "#5c4a2f",
    "harbor": "#173352", "rural": "#22452c", "mtn": "#5b5540",
    "snow": "#8d949c", "void": "#0d1219",
}
TENT_CELL = {}

CSS = """
:root{
  --paper:#e9ecef; --sheet:#f5f7f8; --ink:#111820; --ink-2:#48545f; --ink-3:#78848f;
  --rule:#c2cbd2; --rule-2:#dde3e8;
  --hwy:#cf4a33; --rail:#2f8a5c; --touge:#c07d16; --water:#2a5f96;
  --shadow:0 1px 0 rgba(17,24,32,.06), 0 8px 28px -18px rgba(17,24,32,.5);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#0c1116; --sheet:#131a21; --ink:#e6ecf1; --ink-2:#9aa8b4; --ink-3:#6b7883;
    --rule:#2a343d; --rule-2:#1d262e;
    --hwy:#f0705a; --rail:#4fc98a; --touge:#e0a63c; --water:#4a8ac9;
    --shadow:0 1px 0 rgba(0,0,0,.4), 0 10px 30px -18px #000;
  }
}
:root[data-theme="dark"]{
  --paper:#0c1116; --sheet:#131a21; --ink:#e6ecf1; --ink-2:#9aa8b4; --ink-3:#6b7883;
  --rule:#2a343d; --rule-2:#1d262e;
  --hwy:#f0705a; --rail:#4fc98a; --touge:#e0a63c; --water:#4a8ac9;
  --shadow:0 1px 0 rgba(0,0,0,.4), 0 10px 30px -18px #000;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.mono{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:1180px; margin:0 auto; padding:0 24px 96px}

/* ---- title block: an engineering drawing's, not a hero ---- */
header{border-bottom:2px solid var(--ink); margin-bottom:34px}
.tb{display:grid; grid-template-columns:1fr auto; gap:28px; align-items:end;
    padding:40px 0 18px}
h1{margin:0; font-size:clamp(30px,4.6vw,52px); line-height:1.02; font-weight:800;
   letter-spacing:-.028em; text-wrap:balance; max-width:16ch}
h1 em{font-style:normal; color:var(--hwy)}
.sub{margin:14px 0 0; color:var(--ink-2); max-width:62ch; font-size:16px}
.meta{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:2px 26px;
      font-size:12px; text-align:right}
.meta dt{color:var(--ink-3); text-transform:uppercase; letter-spacing:.09em;
         font-size:10px; margin-top:8px}
.meta dd{margin:0; font-variant-numeric:tabular-nums}

/* ---- sections keyed by the vocabulary the map actually uses ---- */
section{margin-top:54px}
.eyebrow{display:flex; align-items:baseline; gap:12px; border-bottom:1px solid var(--rule);
         padding-bottom:8px; margin-bottom:20px}
.tag{font-size:10.5px; letter-spacing:.14em; text-transform:uppercase; font-weight:700;
     color:var(--paper); background:var(--ink); padding:3px 7px; border-radius:2px}
.tag.a{background:var(--hwy)} .tag.b{background:var(--touge); color:#1a1206}
h2{margin:0; font-size:21px; font-weight:700; letter-spacing:-.014em}
.eyebrow p{margin:0 0 0 auto; color:var(--ink-3); font-size:12.5px}
p{max-width:72ch}
.lede{font-size:17px; color:var(--ink-2)}
strong{font-weight:670}
code{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.88em;
     background:var(--sheet); border:1px solid var(--rule-2); border-radius:3px;
     padding:1px 5px}

figure{margin:0}
.map{border:1px solid var(--rule); background:var(--sheet); box-shadow:var(--shadow);
     border-radius:3px; overflow:hidden}
.map img{display:block; width:100%; height:auto}
figcaption{margin-top:10px; color:var(--ink-3); font-size:12.5px}
.key{display:flex; flex-wrap:wrap; gap:6px 18px; margin:14px 0 0; padding:0; list-style:none;
     font-size:12.5px; color:var(--ink-2)}
.key li{display:flex; align-items:center; gap:7px}
.sw{width:16px; height:3px; border-radius:2px; flex:none}

.scroll{overflow-x:auto; border:1px solid var(--rule-2); border-radius:3px;
        background:var(--sheet)}
table{border-collapse:collapse; width:100%; font-size:13.5px}
th,td{padding:7px 12px; text-align:left; border-bottom:1px solid var(--rule-2);
      white-space:nowrap}
thead th{font-size:10.5px; letter-spacing:.09em; text-transform:uppercase;
         color:var(--ink-3); font-weight:700; background:var(--paper);
         position:sticky; top:0; border-bottom:1px solid var(--rule)}
tbody tr:last-child td{border-bottom:0}
.num{text-align:right; font-variant-numeric:tabular-nums;
     font-family:ui-monospace,Menlo,Consolas,monospace}
.wide{white-space:normal; min-width:22ch; color:var(--ink-2)}
tr.hot td{background:color-mix(in srgb, var(--hwy) 9%, transparent)}
tr.keep td{background:color-mix(in srgb, var(--rail) 10%, transparent)}

/* scale bar — the deletion is the point, so draw it */
.bar{position:relative; width:120px; height:9px; background:var(--rule-2);
     border-radius:2px; overflow:hidden; display:inline-block; vertical-align:middle}
.bar i{position:absolute; inset:0 auto 0 0; background:var(--hwy); display:block}
.bar.k i{background:var(--rail)}

/* district matrix */
.grid{display:grid; grid-template-columns:auto repeat(12,minmax(0,1fr)); gap:2px;
      font-size:10px}
.grid .hd{color:var(--ink-3); font-size:9.5px; letter-spacing:.06em; text-align:center;
          padding:2px 0}
.grid .rl{color:var(--ink-3); font-size:9.5px; padding-right:6px; text-align:right;
          align-self:center}
.cell{aspect-ratio:1; border-radius:2px; display:flex; align-items:center;
      justify-content:center; color:#fff; font-weight:700; font-size:9px;
      letter-spacing:.02em; opacity:.92}
.cell.t{outline:2px solid var(--touge); outline-offset:-2px; opacity:1}
.legend{display:flex; flex-wrap:wrap; gap:6px 16px; margin-top:14px; padding:0;
        list-style:none; font-size:12px; color:var(--ink-2)}
.legend li{display:flex; align-items:center; gap:7px}
.chip{width:12px; height:12px; border-radius:2px; flex:none}

.cols{display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:22px}
.card{border:1px solid var(--rule-2); border-left:2px solid var(--hwy);
      background:var(--sheet); border-radius:3px; padding:16px 18px}
.card h3{margin:0 0 6px; font-size:14px; font-weight:700; letter-spacing:-.008em}
.card p{margin:0; font-size:13.5px; color:var(--ink-2); max-width:none}
.card .n{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11.5px;
         color:var(--ink-3); display:block; margin-top:8px}
.card.b{border-left-color:var(--touge)}
.card.c{border-left-color:var(--rail)}

.rule{margin:0; border:0; border-top:1px solid var(--rule); }
footer{margin-top:64px; padding-top:18px; border-top:1px solid var(--rule);
       color:var(--ink-3); font-size:12.5px; display:flex; flex-wrap:wrap; gap:6px 22px}
@media (max-width:700px){
  .tb{grid-template-columns:1fr} .meta{text-align:left}
  th,td{padding:6px 9px; font-size:12.5px}
}
"""


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def bar(scale, keep=False):
    w = max(2.0, min(100.0, scale * 100.0))
    cls = "bar k" if keep else "bar"
    return f'<span class="{cls}"><i style="width:{w:.0f}%"></i></span>'


def warp_rows(segs, labels):
    out = []
    for s, lab in zip(segs, labels):
        keep = s["scale"] >= 0.85
        hot = s["scale"] <= 0.16
        cls = "keep" if keep else ("hot" if hot else "")
        out.append(
            f'<tr class="{cls}"><td>{esc(lab[0])}</td>'
            f'<td class="num">{s["real_len_m"]:,.0f}</td>'
            f'<td class="num">{s["game_len_m"]:,.0f}</td>'
            f'<td class="num">{s["scale"]:.2f} {bar(s["scale"], keep)}</td>'
            f'<td class="num">{s["deleted_m"]/1000:,.1f} km</td>'
            f'<td class="wide">{esc(lab[1])}</td></tr>')
    return "\n".join(out)


def matrix_html(doc):
    tents = {tuple(t["district"]): t["id"] for t in doc["tentpoles"]}
    cells = {(d["gx"], d["gy"]): d["theme"] for d in doc["districts"]}
    h = ['<div class="grid">', '<div></div>']
    for gx in range(12):
        h.append(f'<div class="hd">{gx}</div>')
    for gy in range(11, -1, -1):
        h.append(f'<div class="rl">gy{gy}</div>')
        for gx in range(12):
            th = cells[(gx, gy)]
            t = tents.get((gx, gy))
            cls = "cell t" if t else "cell"
            lab = th[:4] if th != "industry" else "ind"
            title = f"gx{gx} gy{gy} — {th}" + (f" — {t}" if t else "")
            h.append(f'<div class="{cls}" style="background:{THEME_COL[th]}" '
                     f'title="{esc(title)}">{esc(lab)}</div>')
    h.append("</div>")
    keys = ["city", "resid", "industry", "harbor", "rural", "mtn", "snow", "void"]
    leg = "".join(f'<li><span class="chip" style="background:{THEME_COL[k]}"></span>'
                  f'{k}</li>' for k in keys)
    h.append(f'<ul class="legend">{leg}'
             '<li><span class="chip" style="background:transparent;'
             'outline:2px solid var(--touge);outline-offset:-2px"></span>'
             'tentpole cell</li></ul>')
    return "\n".join(h)


X_LABELS = [
    ("Nakano → Shinjuku", "Ōkubo / Yoyogi mid-rise infill"),
    ("Shinjuku → Yotsuya", "Ichigaya office plateau"),
    ("Yotsuya → Palace", "Kōjimachi ministry blocks"),
    ("Palace → Tokyo Stn", "Marunouchi outer ring"),
    ("Tokyo Stn → Akihabara", "nothing — the hero corridor survives at 93%"),
    ("Akihabara → Haneda col.", "Nihonbashi east"),
    ("Haneda col. → Toyosu", "Tsukiji / Kachidoki"),
    ("Toyosu → Shinonome", "nothing — the waterfront is 1:1"),
]
Y_LABELS = [
    ("Runway S → terminal", "southern apron taxiways"),
    ("Terminal → runway N", "apron"),
    ("Runway N → Keihinjima", "outer Keihin yards"),
    ("Keihinjima → Ōi wharf", "Ōmori–Kamata sprawl"),
    ("Ōi wharf → Odaiba", "Shinagawa–Ōmori sprawl — the biggest single cut"),
    ("Odaiba → Shinagawa", "bay channel"),
    ("Shinagawa → Rainbow Br", "Konan wharf sheds"),
    ("Rainbow Br → Tokyo Tower", "Shibaura wharf sheds"),
    ("Tokyo Tower → Shibuya", "Azabu"),
    ("Shibuya → Ginza", "Shimbashi / Toranomon"),
    ("Ginza → Tokyo Stn", "Kyōbashi"),
    ("Tokyo Stn → Shinjuku", "Ōtemachi / Jimbōchō"),
    ("Shinjuku → Akihabara", "Kanda infill"),
    ("Akihabara → Ueno", "Okachimachi — mostly kept, it's good"),
    ("North of Ueno", "Sugamo / Ikebukuro homogeneous ward"),
]


def build_html(doc, png_b64, real_b64):
    se, g = doc["source_extent"], doc["grid"]
    tb = doc["warp"]["tier_b"]

    tents = "\n".join(
        f'<tr><td class="mono">{esc(t["id"])}</td><td>{esc(t["label"])}</td>'
        f'<td class="num">{t["game_xy"][0]:,.0f}, {t["game_xy"][1]:,.0f}</td>'
        f'<td class="mono">gx{t["district"][0]} gy{t["district"][1]}</td>'
        f'<td class="num">{t["footprint_districts"][0]}×{t["footprint_districts"][1]}</td>'
        f'<td class="wide">{esc(t["note"])}</td></tr>' for t in doc["tentpoles"])

    hw = "\n".join(
        f'<tr><td class="mono">{esc(h["id"])}</td><td>{esc(h["label"])}</td>'
        f'<td class="num">{h["length_m"]/1000:,.2f} km</td>'
        f'<td class="num">{h.get("lanes_per_dir","-")}</td>'
        f'<td class="wide">{esc(h["role"])}</td></tr>'
        for h in doc["roads"]["highways"])

    rl = "\n".join(
        f'<tr><td class="mono">{esc(r["id"])}</td><td>{esc(r["label"])}</td>'
        f'<td class="num">{r["length_m"]/1000:,.2f} km</td>'
        f'<td class="num">+{r["deck_z"]:.0f} m</td>'
        f'<td class="wide">{esc(r["role"])}</td></tr>' for r in doc["rail"])

    bufs = "\n".join(
        f'<div class="card{" b" if b["deleted_real_m"]>5000 else ""}">'
        f'<h3>{esc(b["id"])}</h3><p>{esc(b["role"])}</p>'
        f'<span class="n">{b["length_m"]:,.0f} m of map · deletes '
        f'{b["deleted_real_m"]/1000:,.1f} km · {esc(b["device"])}</span></div>'
        for b in doc["buffers"])

    order = ["city", "resid", "industry", "harbor", "rural", "mtn", "snow"]

    def sr_row(k):
        r = doc["street_rules"][k]
        def m(v):
            return f"{v:,.0f} m" if v else "&mdash;"
        chip = (f'<span class="chip" style="display:inline-block;width:10px;height:10px;'
                f'border-radius:2px;background:{THEME_COL[k]};margin-right:7px;'
                f'vertical-align:-1px"></span>')
        return (f'<tr><td>{chip}{k}</td>'
                f'<td class="num">{m(r["local_spacing_m"])}</td>'
                f'<td class="num">{m(r["alley_spacing_m"])}</td>'
                f'<td class="num">{r["block_retention"]:.2f} '
                f'{bar(r["block_retention"], True)}</td>'
                f'<td class="num">{r["max_sightline_m"]:,.0f} m</td>'
                f'<td class="num">{r["storeys"][0]}&ndash;{r["storeys"][1]}</td>'
                f'<td class="wide">{esc(r["notes"])}</td></tr>')

    sr = "\n".join(sr_row(k) for k in order)

    rw = doc["runway"]
    oc = doc["roads"]["outer_circuit"]

    return f"""<title>Tokyo 23-ku → 6 km — Spatial Compression</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <div class="tb">
    <div>
      <h1>Tokyo 23-ku, compressed to <em>6 km square</em></h1>
      <p class="sub">A spatial compression design for an open-world driving map built
      from Project PLATEAU 1:1 survey data. Four city tentpoles, a harbour, an
      industrial belt, an airport and an annexed mountain pass — inside
      {g["world_m"]:,.0f} × {g["world_m"]:,.0f} m.</p>
    </div>
    <dl class="meta">
      <div><dt>Source CRS</dt><dd class="mono">{esc(se["crs"])}</dd></div>
      <div><dt>Real extent</dt><dd class="mono">{se["real_size_km"][0]} × {se["real_size_km"][1]} km</dd></div>
      <div><dt>Linear ratio</dt><dd class="mono">{se["linear_ratio"][0]} : 1 &nbsp;/&nbsp; {se["linear_ratio"][1]} : 1</dd></div>
      <div><dt>Area ratio</dt><dd class="mono">{se["area_ratio"]} : 1</dd></div>
      <div><dt>Grid</dt><dd class="mono">{g["grid_n"]}×{g["grid_n"]} × {g["district_m"]:.0f} m</dd></div>
      <div><dt>Cell</dt><dd class="mono">{g["cell_m"]:.0f} m</dd></div>
    </dl>
  </div>
</header>

<p class="lede"><strong>The one rule:</strong> compress the distance <em>between</em>
things, never the things themselves. A 3.25 m lane stays 3.25 m; a 30 m block stays
30 m. What changes is how many of them exist between Shinjuku and Tokyo Station. Where
even a fully-collapsed gap will not fit, whole blocks are <strong>deleted</strong> —
never scaled.</p>

<section>
  <div class="eyebrow"><span class="tag">Plan</span><h2>The compressed map</h2>
    <p>2.52 m / px · centre-origin · X east, Y north</p></div>
  <figure>
    <div class="map"><img src="data:image/png;base64,{real_b64}"
      alt="Top-down plan of the compressed Tokyo map rendered from real PLATEAU survey
      geometry: organic coastline and Tokyo Bay, the Sumida and the canals, and the real
      street network warped into game space, with the district grid as a thin overlay."></div>
    <ul class="key">
      <li><span class="sw" style="background:#96d6ad"></span>land (luse chōme union)</li>
      <li><span class="sw" style="background:#273a4a"></span>water (complement + rivers)</li>
      <li><span class="sw" style="background:#fff;outline:1px solid var(--rule)"></span>roads (real footprints)</li>
      <li><span class="sw" style="background:var(--hwy)"></span>tentpole</li>
    </ul>
    <figcaption><strong>Real survey geometry, not a sketch.</strong> 376,617 land-use
    polygons give the coast; 244,352 road footprints go in and 29,604 survive the
    decimation. The district grid is the thin overlay — it is a streaming container,
    not the shape of the land.</figcaption>
  </figure>
  <figure style="margin-top:34px">
    <div class="map"><img src="data:image/png;base64,{png_b64}"
      alt="Top-down plan of the compressed Tokyo map showing district themes, the
      elevated expressway network, the rail network and the annexed mountain block."></div>
    <ul class="key">
      <li><span class="sw" style="background:var(--hwy)"></span>T1 elevated expressway</li>
      <li><span class="sw" style="background:var(--touge)"></span>touge pass road</li>
      <li><span class="sw" style="background:var(--rail)"></span>rail viaduct</li>
      <li><span class="sw" style="background:var(--ink-3)"></span>T2 arterial backbone (district seams)</li>
      <li><span class="sw" style="background:var(--water)"></span>water</li>
    </ul>
    <figcaption><strong>The schematic</strong>, same coordinate space: district themes,
    the two expressway circuits, the touge and the rail network. Every polyline that
    traces a real road is a real PLATEAU anchor pushed through the same warp, so the
    Shuto bends where the Shuto bends.</figcaption>
  </figure>
</section>

<section>
  <div class="eyebrow"><span class="tag a">Tier A</span><h2>The warp — where the deletions are</h2>
    <p>monotonic, piecewise-linear, per axis</p></div>
  <p>Control points are authored, not solved: the tentpoles are nailed to their district
  centres and the gaps absorb every metre of error. Red rows are the hard collapses;
  green rows are what the whole exercise exists to protect.</p>
  <div class="scroll"><table>
    <thead><tr><th>Segment (west → east)</th><th class="num">Real</th><th class="num">Game</th>
    <th class="num">Scale</th><th class="num">Deleted</th><th>What goes</th></tr></thead>
    <tbody>{warp_rows(doc["warp"]["tier_a"]["x"]["segments"], X_LABELS)}</tbody>
  </table></div>
  <div class="scroll" style="margin-top:18px"><table>
    <thead><tr><th>Segment (south → north)</th><th class="num">Real</th><th class="num">Game</th>
    <th class="num">Scale</th><th class="num">Deleted</th><th>What goes</th></tr></thead>
    <tbody>{warp_rows(doc["warp"]["tier_a"]["y"]["segments"], Y_LABELS)}</tbody>
  </table></div>
  <p style="margin-top:18px">Read together, the design states itself: the densest 544 m
  in Tokyo — <strong>Tokyo Station to Akihabara</strong> — survives at 93%, while the
  9.5 km of homogeneous low-rise between the bay and the airport is cut by 88%.
  <strong>That asymmetry is the map.</strong></p>
</section>

<section>
  <div class="eyebrow"><span class="tag b">Tier B</span><h2>The annex — 55 km cannot be warped</h2>
    <p>rigid translation, scale exactly 1.0</p></div>
  <p>Okutama sits 55 km west of Shinjuku. No warp survives that, so a 2,016 m window is
  <strong>cut out of the real mountain and translated whole</strong> into the north-west
  corner. Slope, relief and hairpin radii stay real — a touge that has been scaled is not
  a touge.</p>
  <div class="cols">
    <div class="card b"><h3>The transform</h3>
      <p>Source window centred on the Tama gorge floor, 1 km south of Okutama station —
      valley and ridge inside one window.</p>
      <span class="n">dx {tb["dx"]:+,.1f} · dy {tb["dy"]:+,.1f} · dz {tb["dz"]:+,.1f} · scale {tb["scale"]}</span></div>
    <div class="card b"><h3>dz is a subtraction, not a scale</h3>
      <p>Drops the valley floor from 340 m T.P. to 60 m so it meets the city's elevation
      band. Every gradient in the block is untouched.</p></div>
    <div class="card b"><h3>The pass, specified</h3>
      <p>2,978 m of road for a 240 m climb — an 8.1% ruling grade, 4 hairpin pairs, 11 m
      minimum radius. It stops at the pass; the 620 m summit above is scenery. Driving to
      the summit would force an 18% wall.</p></div>
  </div>
</section>

<section>
  <div class="eyebrow"><span class="tag">Stitch</span><h2>Transitional buffer zones</h2>
    <p>a deletion is only as good as its seam</p></div>
  <p>Three devices do all the work: <strong>a wall you cannot see past</strong> (elevated
  deck, container stack, Shinkansen viaduct), <strong>a void you cannot cross</strong>
  (water, a rail cutting), and <strong>a tunnel</strong> — the only honest way to hide a
  true discontinuity.</p>
  <div class="cols">{bufs}</div>
</section>

<section>
  <div class="eyebrow"><span class="tag">Correction</span><h2>Land and water are data, not districts</h2>
    <p>the easiest mistake here, and the first draft made it</p></div>
  <p>The first version drew the coastline as hand-authored polygons and coloured whole
  504 m districts &ldquo;harbor&rdquo;. That was wrong. <strong>A district is a streaming
  container — it is not the shape of the land and it is not the road network.</strong></p>
  <div class="cols">
    <div class="card c"><h3>The open bay is not in PLATEAU</h3>
      <p>Every ward dataset stops at its own shoreline; the <code>wtr</code> module&rsquo;s
      five 海 features are 40 m harbour curves. So land = the union of the
      <code>luse</code> chōme polygons, and water = the complement, with rivers cut
      back in. The coast falls out of the survey.</p>
      <span class="n">376,617 land-use polygons · 2,244 water bodies</span></div>
    <div class="card c"><h3>Absence ≠ water</h3>
      <p>&ldquo;No polygon here&rdquo; only means water <em>inside the extract window</em>.
      Outside it, absence means no data — painting that as sea invented an ocean across
      the whole north of the map on the first pass.</p></div>
    <div class="card"><h3>Registration beats rigidity</h3>
      <p>Roads were translated rigidly while land warped point-wise. <strong>Three
      different transforms cannot register</strong> — streets drifted off their own blocks
      and read as horizontally squeezed against the land. Everything now takes the same
      point-wise warp, and the width that costs is given back as a stroke, never narrower
      than 6 m.</p>
      <span class="n">the Palace moat and its ring road now line up to the metre</span></div>
    <div class="card"><h3>It is essentiality, not de-duplication</h3>
      <p>There is no literal duplication: all 244,452 footprints are distinct. What reads
      as duplicated is fragmentation plus redundant parallel streets — so fragments under
      100 m² go, and the rest is ranked by <em>width</em> inside each 56 m bucket with only
      the top two kept. Landmarks and majors are exempt.</p>
      <span class="n">244,452 → 22,417 kept (9.2%)</span></div>
  </div>
</section>

<section>
  <div class="eyebrow"><span class="tag">Grid</span><h2>District matrix — 12 × 12 × 504 m</h2>
    <p>north at top · hover a cell for its address</p></div>
  <p>The streaming chunk stays <strong>504 m</strong> — the size already proven in the
  engine. Only the grid count doubles. Compass relationships are all real: Shinjuku west,
  Akihabara east on the same latitude band, Tokyo Station just south and central, bay
  south-east, Haneda due south, Okutama north-west. Nothing was rotated to make the
  layout convenient.</p>
  {matrix_html(doc)}
</section>

<section>
  <div class="eyebrow"><span class="tag">Anchors</span><h2>Tentpoles</h2>
    <p>game metres, centre-origin</p></div>
  <div class="scroll"><table>
    <thead><tr><th>id</th><th>Label</th><th class="num">Game X, Y</th><th>Cell</th>
    <th class="num">Footprint</th><th>Note</th></tr></thead>
    <tbody>{tents}</tbody></table></div>
  <p style="margin-top:18px"><strong>The one deliberate violation:</strong> Haneda's
  runway. Real 16R/34L is 3,000 m — warped it becomes a 400 m stub, scaled it breaks rule
  zero. So the middle is deleted and a <strong>{rw["length_m"]:,.0f} m</strong> runway is
  authored at the true {rw["true_heading_deg"]:.0f}° heading, from
  <code>{rw["north_end"][0]:,.0f}, {rw["north_end"][1]:,.0f}</code> to
  <code>{rw["south_end"][0]:,.0f}, {rw["south_end"][1]:,.0f}</code>. The other three
  runways are deleted outright, not shrunk.</p>
</section>

<section>
  <div class="eyebrow"><span class="tag">T1–T4</span><h2>Road hierarchy</h2>
    <p>deck +12 m · arterials on every seam</p></div>
  <p><strong>T1</strong> elevated expressway (22 m deck, ramps only) ·
  <strong>T2</strong> arterial, 27 m, on <em>every district seam</em> at 504 m — which is
  the arterial backbone the world builder already generates, unchanged ·
  <strong>T3</strong> local street, 14 m, every 168 m ·
  <strong>T4</strong> alley, 4.5 m, 45–60 m by theme.</p>
  <div class="scroll"><table>
    <thead><tr><th>id</th><th>Route</th><th class="num">Length</th>
    <th class="num">Lanes/dir</th><th>Role</th></tr></thead>
    <tbody>{hw}</tbody></table></div>
  <p style="margin-top:18px"><strong>Two nested circuits.</strong> Short lap = C1 at
  4.00 km (real C1 is 14.8 km). Long lap = {esc(" + ".join(oc["legs"]))} ≈ 10.5 km,
  closing at {esc(oc["closes_at"])}.</p>
</section>

<section>
  <div class="eyebrow"><span class="tag">Rail</span><h2>Train network</h2>
    <p>decks sit below the +12 m expressway deck</p></div>
  <p>Rail is an addition — and the map's primary sightline occluder. The Yamanote and
  Chūō viaducts cut every city district in half at eye level; the izakaya under-guard
  strip goes there, so the most recognisably Tokyo space on the map is also a hard
  occlusion plane. Level crossings go on T3 streets only, never T2.</p>
  <div class="scroll"><table>
    <thead><tr><th>id</th><th>Line</th><th class="num">Length</th><th class="num">Deck</th>
    <th>Role</th></tr></thead><tbody>{rl}</tbody></table></div>
</section>

<section>
  <div class="eyebrow"><span class="tag">Budget</span><h2>Shrinking the built world</h2>
    <p>the cheapest district is the one you never build</p></div>
  <p>Streaming cost is paid <strong>per built district</strong>. Residential was the
  target — it is the taper between the city and the edge, not a destination, so it never
  needs two districts of depth. <strong>The city core is untouched;</strong> the saving
  comes entirely from land the player only drives through.</p>
  <div class="scroll"><table>
    <thead><tr><th>Theme</th><th class="num">First pass</th><th class="num">Reduced</th>
    <th class="num">Change</th><th>Why</th></tr></thead>
    <tbody>
      <tr class="hot"><td>void — nothing streams</td><td class="num">2</td><td class="num">17</td><td class="num">+15</td><td class="wide">open water and off-map</td></tr>
      <tr><td>resid</td><td class="num">60</td><td class="num">40</td><td class="num">−20</td><td class="wide">cut to a ring one district deep</td></tr>
      <tr><td>mtn + rural</td><td class="num">29</td><td class="num">38</td><td class="num">+9</td><td class="wide">cheap: no street grid at all</td></tr>
      <tr class="keep"><td>city</td><td class="num">24</td><td class="num">24</td><td class="num">0</td><td class="wide">the reason the map exists</td></tr>
      <tr><td><strong>built districts</strong></td><td class="num">142</td><td class="num"><strong>127</strong></td><td class="num">−15</td><td class="wide">of 144 cells</td></tr>
    </tbody></table></div>
</section>

<section>
  <div class="eyebrow"><span class="tag">Edge</span><h2>The map edge — why not an air wall</h2>
    <p>in descending order of quality</p></div>
  <p>An invisible wall in open, drivable ground is the one solution that always reads as
  broken: the player can see road they cannot reach, and the fiction dies at the exact
  moment they test it. What this map uses instead —</p>
  <div class="cols">
    <div class="card c"><h3>1 · Impassable terrain</h3>
      <p>Water and cliffs need no explanation and no collision trickery. This map is
      already bounded that way on <strong>all four sides</strong>: sea south and east, the
      Tama river mouth south-west, the Okutama massif north-west.</p>
      <span class="n">a second reason to annex the mountain at 1:1 — real ridges are
      unclimbable by shape, not by rule</span></div>
    <div class="card"><h3>2 · Authored terminal geometry</h3>
      <p>Where a road must stop, end it on purpose: a barrier, a construction hoarding, a
      closed tunnel gate. Costs one prop and reads as intentional rather than as a limit.</p></div>
    <div class="card"><h3>3 · Soft redirect</h3>
      <p>The outer arterial ring curves the player back inward, so the edge is rarely
      approached head-on in the first place.</p></div>
    <div class="card"><h3>4 · Non-collidable backdrop</h3>
      <p>One always-resident low-poly silhouette beyond the playable edge — no collision,
      no streaming, no AI, no nav. It is what makes a 6 km map feel like it sits inside a
      bigger city.</p></div>
  </div>
  <p style="margin-top:18px">Use an air wall only as a <strong>last-resort backstop behind
  one of those</strong>, never as the primary edge. And note that <strong>teleport-back</strong>
  and <strong>instant death at the border</strong> are both worse than an air wall — they
  punish curiosity instead of quietly redirecting it. One engine-specific caution: do not
  reintroduce a world-spanning invisible floor as an edge. That was removed for cause —
  it silently trapped characters with no recovery path, and unlike vehicles they are never
  reclaimed.</p>
</section>

<section>
  <div class="eyebrow"><span class="tag">LOD</span><h2>Density gradient &amp; asset placement</h2>
    <p>the vibe lever and the budget lever are the same lever</p></div>
  <p><strong>Block retention is the most important number here.</strong> It equals the
  local warp scale, because that is the only way the arithmetic closes: at 0.35 you keep
  one cross-street in three and delete the other two. Cull whole footprints from the
  PLATEAU extract; never rescale one.</p>
  <div class="scroll"><table>
    <thead><tr><th>Theme</th><th class="num">T3</th><th class="num">Alley</th>
    <th class="num">Block retention</th><th class="num">Max sightline</th>
    <th class="num">Storeys</th><th>Notes</th></tr></thead>
    <tbody>{sr}</tbody></table></div>
  <p style="margin-top:18px">Note the inversion: <strong>residential has the shortest
  sightline on the map</strong> (140 m), not the tower district. Two-storey low-rise with
  4 m alleys occludes harder than a tower block, so the cheapest theme to render is also
  the cheapest to cull. Harbour is allowed 900 m only because there is almost nothing in
  that cone. And <code>mtn</code> has no street grid at all — ridges are the occluder,
  which is the other reason the mountain is annexed at 1:1.</p>
</section>

<footer>
  <span>Data: Project PLATEAU (MLIT), CC BY 4.0</span>
  <span class="mono">layout.json · schema {esc(doc["schema"])}</span>
  <span class="mono">144 districts · {len(doc["roads"]["highways"])} expressways ·
  {len(doc["roads"]["arterials"])} arterials · {len(doc["rail"])} rail lines</span>
</footer>
</div>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default="build/tokyo6km")
    ap.add_argument("--out", default="build/tokyo6km/design.html")
    a = ap.parse_args()
    doc = json.load(open(os.path.join(a.src, "layout.json"), encoding="utf-8"))
    png = base64.b64encode(open(os.path.join(a.src, "preview.png"), "rb").read()).decode()
    real = base64.b64encode(open(os.path.join(a.src, "real.png"), "rb").read()).decode()
    html = build_html(doc, png, real)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {a.out}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
