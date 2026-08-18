#!/usr/bin/env python3
"""Build the standalone, offline review page for the Tokyo-Bay Island v3 plan.

Embeds both plates as base64 SVG data URIs (an <img>, not inline SVG — the plates carry
their own <style> with one-letter class names that would collide with the page CSS).

Self-contained: both plates are inlined as base64 SVG data URIs, so the single .html file
opens from file:// with no network, no assets folder and nothing hosted anywhere.

    python3 tools/build_island_page.py        # -> tokyo-bay-island-v3-review.html
"""

from __future__ import annotations

import argparse
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def datauri(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tokyo-Bay Island v3 — plan review</title>
<style>
/* minimal reset (the hosted renderer supplies one; a local file must carry its own) */
*,*::before,*::after {{ box-sizing:border-box; }}
html {{ -moz-text-size-adjust:none; -webkit-text-size-adjust:none; text-size-adjust:none; }}
body,h1,h2,h3,p,figure,ul {{ margin:0; }}
ul[class] {{ list-style:none; padding:0; }}
img {{ max-width:100%; display:block; }}
:root {{
  --ground:#DFE3E4; --sheet:#F5F6F5; --raised:#EAEDEC;
  --ink:#191C1D; --muted:#5E6668; --faint:#8B9294;
  --rule:#C4CBCD; --rule-soft:#D6DBDC;
  --accent:#A85F14; --accent-soft:#E8DCC9;
  --signal:#9E3113; --keep:#2F6B4F;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
}}
@media (prefers-color-scheme:dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#141719; --sheet:#1C2124; --raised:#22282B;
    --ink:#E4E7E6; --muted:#99A2A5; --faint:#6E7679;
    --rule:#2E353A; --rule-soft:#252B2E;
    --accent:#E39A50; --accent-soft:#33302A;
    --signal:#DE6A44; --keep:#6FBE96;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#141719; --sheet:#1C2124; --raised:#22282B;
  --ink:#E4E7E6; --muted:#99A2A5; --faint:#6E7679;
  --rule:#2E353A; --rule-soft:#252B2E;
  --accent:#E39A50; --accent-soft:#33302A;
  --signal:#DE6A44; --keep:#6FBE96;
}}

* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.62;
  -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:1240px; margin:0 auto; padding:0 28px 96px; }}
.col {{ max-width:70ch; }}

h1,h2,h3 {{ text-wrap:balance; margin:0; }}
h1 {{ font-size:clamp(28px,4vw,42px); font-weight:700; letter-spacing:-.022em; line-height:1.12; }}
h2 {{ font-size:22px; font-weight:700; letter-spacing:-.012em; }}
h3 {{ font-size:15px; font-weight:650; letter-spacing:-.004em; }}
p {{ margin:0; }}
a {{ color:var(--accent); }}

.eyebrow {{
  font-family:var(--mono); font-size:11px; font-weight:500;
  letter-spacing:.14em; text-transform:uppercase; color:var(--faint);
}}
.lede {{ font-size:18.5px; line-height:1.55; color:var(--muted); }}
code {{ font-family:var(--mono); font-size:.88em; color:var(--ink);
        background:var(--raised); padding:.1em .36em; border-radius:3px; }}

header.top {{ border-bottom:1px solid var(--rule); padding:56px 0 30px; }}
header.top .stack {{ display:flex; flex-direction:column; gap:16px; max-width:74ch; }}
.status {{
  display:flex; flex-wrap:wrap; gap:8px 20px; font-family:var(--mono);
  font-size:11.5px; letter-spacing:.06em; color:var(--faint); padding-top:6px;
}}
.status b {{ color:var(--muted); font-weight:500; }}

section {{ padding-top:52px; display:flex; flex-direction:column; gap:20px; }}
.head {{ display:flex; flex-direction:column; gap:7px; }}

/* plates */
figure {{ margin:0; display:flex; flex-direction:column; gap:11px; }}
.plate {{
  background:var(--sheet); border:1px solid var(--rule);
  border-radius:2px; padding:12px; overflow-x:auto;
}}
.plate img {{ display:block; width:100%; min-width:760px; height:auto; }}
figcaption {{ font-size:13.5px; color:var(--muted); max-width:78ch; }}
figcaption b {{ color:var(--ink); font-weight:600; }}

/* numbers */
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:1px;
          background:var(--rule); border:1px solid var(--rule); }}
.stat {{ background:var(--sheet); padding:15px 16px; display:flex; flex-direction:column; gap:3px; }}
.stat .k {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.09em;
            text-transform:uppercase; color:var(--faint); }}
.stat .v {{ font-family:var(--mono); font-size:21px; font-weight:600;
            font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
.stat .n {{ font-size:12.5px; color:var(--muted); }}

/* tables */
.tw {{ overflow-x:auto; border:1px solid var(--rule); background:var(--sheet); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; min-width:600px; }}
th,td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--rule-soft);
         vertical-align:top; }}
thead th {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.09em;
            text-transform:uppercase; color:var(--faint); font-weight:500;
            border-bottom:1px solid var(--rule); white-space:nowrap; }}
tbody tr:last-child td {{ border-bottom:none; }}
td.num, th.num {{ text-align:right; font-family:var(--mono);
                  font-variant-numeric:tabular-nums; white-space:nowrap; }}
tr.pick td {{ background:var(--accent-soft); }}
tr.pick td:first-child {{ box-shadow:inset 3px 0 0 var(--accent); }}
.tag {{ font-family:var(--mono); font-size:10px; letter-spacing:.08em;
        text-transform:uppercase; padding:2px 6px; border:1px solid currentColor;
        border-radius:2px; white-space:nowrap; }}
.tag.keep {{ color:var(--keep); }}
.tag.drop {{ color:var(--signal); }}

/* tiers */
.tiers {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(258px,1fr)); gap:14px; }}
.tier {{ background:var(--sheet); border:1px solid var(--rule); padding:17px 18px;
         display:flex; flex-direction:column; gap:9px; }}
.tier .n {{ font-family:var(--mono); font-size:11px; letter-spacing:.1em;
            text-transform:uppercase; color:var(--accent); }}
.tier p {{ font-size:14px; color:var(--muted); }}
.tier .ratio {{ font-family:var(--mono); font-size:13px; font-variant-numeric:tabular-nums;
                color:var(--ink); border-top:1px solid var(--rule-soft); padding-top:9px; }}

ul.clean {{ margin:0; padding-left:1.15em; display:flex; flex-direction:column; gap:9px; }}
ul.clean li {{ padding-left:2px; }}
ul.clean li b {{ font-weight:640; }}

footer {{ margin-top:60px; padding-top:22px; border-top:1px solid var(--rule);
          font-size:13px; color:var(--faint); display:flex; flex-direction:column; gap:6px; }}
@media (prefers-reduced-motion:reduce) {{ * {{ animation:none!important; transition:none!important; }} }}
</style>
</head>
<body>

<div class="wrap">

<header class="top">
  <div class="stack">
    <span class="eyebrow">World design &middot; pre-implementation review</span>
    <h1>Tokyo-Bay Island v3</h1>
    <p class="lede">Plan A&rsquo;s fictional island, condensed back to its ~2&nbsp;km proposal
      and re-planned as one south-to-north transect. Coastal pattern after
      <span lang="ja">&#26032;&#28511;</span> and the Echigo plain, not Tokyo. Nothing is
      built yet &mdash; this is the plan to argue with first.</p>
    <div class="status">
      <span><b>Frame</b> 2016 &times; 2016 m &middot; 4 &times; 4 &times; 504 m</span>
      <span><b>Engine change</b> <code>GRID_N</code> 6 &rarr; 4</span>
      <span><b>Spec</b> tokyo-bay-island-design-spec-v3.md</span>
    </div>
  </div>
</header>

<section>
  <div class="head">
    <span class="eyebrow">Plate 1 of 2</span>
    <h2>Plan overview</h2>
  </div>
  <figure>
    <div class="plate"><img src="{overview}" alt="Overview map: district themes, road
      hierarchy, rail, landmarks and the race circuit on a 2016 by 2016 metre island."></div>
    <figcaption><b>Read this one first.</b> The transect runs bottom to top: harbour and bay,
      three neon centres split by the river, residential, farmland, mountain. Cell tags show
      each district&rsquo;s <em>measured</em> land fraction, so no square is themed buildable
      when it is mostly sea.</figcaption>
  </figure>
</section>

<section>
  <div class="stats">
    <div class="stat"><span class="k">Land</span><span class="v">2.49</span>
      <span class="n">km&sup2; &middot; v1 proposed 2.4</span></div>
    <div class="stat"><span class="k">World</span><span class="v">2016</span>
      <span class="n">m &middot; 4 &times; 4 districts of 504 m</span></div>
    <div class="stat"><span class="k">Districts built</span><span class="v">14<span
      style="color:var(--faint)">/16</span></span><span class="n">2 void cells</span></div>
    <div class="stat"><span class="k">Flagship lap</span><span class="v">3,331</span>
      <span class="n">m &middot; ~90 s, 6 sectors</span></div>
    <div class="stat"><span class="k">Building instances</span><span class="v">2,060</span>
      <span class="n">GTA III shipped ~3&ndash;4 k</span></div>
    <div class="stat"><span class="k">Unique meshes</span><span class="v">~96</span>
      <span class="n">44 kit + 52 hero</span></div>
  </div>
</section>

<section>
  <div class="head">
    <span class="eyebrow">The reference that changed the plan</span>
    <h2><span lang="ja">&#26032;&#28511;&#24066;</span> &mdash; not Tokyo</h2>
  </div>
  <p class="col">Tokyo was the wrong model for what this island actually is: a mid-size
    coastal city with farmland running to the sea and a mountain standing beside it. Niigata
    is that city. Five of its patterns are now structural here, and each one is cheap to build
    and unmistakably Japanese &mdash; exactly the combination this budget needs.</p>
  <div class="tw"><table>
    <thead><tr><th>Niigata pattern</th><th>How v3 uses it</th><th>Why it earns its place</th></tr></thead>
    <tbody>
      <tr><td><b><span lang="ja">&#20449;&#28611;&#24029;</span> splits the city</b> &mdash;
        old town west bank, new centre east bank, joined by
        <span lang="ja">&#33836;&#20195;&#27211;</span></td>
        <td>The river runs <em>through</em> the core, dividing <b>Neon A</b> from <b>Neon B</b>;
          a 91 m multi-arch stone bridge is the hero crossing</td>
        <td>Makes the three-centre split structural instead of arbitrary, and gives the city an
          internal landmark and chokepoint</td></tr>
      <tr><td><b><span lang="ja">&#30722;&#19992;&#21015;</span> dune ridges</b> with drained
        back-swamp between them</td>
        <td>The eastern farmland is striped: farmhouse rows on the ridges, paddy in the
          troughs, all parallel to the coast</td>
        <td>A real land-use grain instead of uniform scatter &mdash; and stripes read instantly
          at driving speed</td></tr>
      <tr><td><b><span lang="ja">&#28023;&#23736;&#26494;&#26519;</span></b> &mdash; black-pine
        windbreak on the seaward dune</td>
        <td>A pine belt inside the whole ocean-facing coast</td>
        <td>The cheapest Sea-of-Japan signal available, and a continuous occluder on the
          map&rsquo;s most open edge</td></tr>
      <tr><td><b><span lang="ja">&#28511;</span> lagoons</b> stranded when the swamp drained</td>
        <td>One lagoon among the paddies</td>
        <td>Free landmark, free reflection, free scenic pull-off</td></tr>
      <tr class="pick"><td><b><span lang="ja">&#24357;&#24422;&#23665;</span></b> &mdash; an
        isolated peak off the plain, shrine at the foot and <em>okumiya</em> on the summit</td>
        <td>The spur ridge coming down beside Neon C, carrying <b>a shrine at the foot and a
          second on the summit</b></td>
        <td><span class="tag keep">your brief</span> &ldquo;mountain on the neon side&rdquo;
          and &ldquo;shrine on top&rdquo; in one real precedent</td></tr>
    </tbody>
  </table></div>
  <p class="col">With the pass shrine on the main massif, the island carries <b>three shrines
    from one kit</b>, dressed three ways: urban forest at the foot, exposed summit
    <em>okumiya</em>, and snowy mountain pass.</p>
</section>

<section>
  <div class="head">
    <span class="eyebrow">Plate 2 of 2</span>
    <h2>Modeling plate</h2>
  </div>
  <figure>
    <div class="plate"><img src="{plate}" alt="Detailed modeling plate: coastline, terrain
      contours, road and rail network, dune striping, and 2,081 building footprints."></div>
    <figcaption>The tracing reference &mdash; coastline, contours, the network down to
      168&nbsp;m local streets, dune striping, and <b>2,060 building footprints</b>. Drop it on
      a 2016&nbsp;m plane in Blender and it lines up 1:1.</figcaption>
  </figure>
</section>

<section>
  <div class="head">
    <span class="eyebrow">Two calls the smaller size forced</span>
    <h2>What changed from v2, and why</h2>
  </div>
  <div class="tiers">
    <div class="tier">
      <span class="n">Shrunk</span>
      <h3>Imperial Palace &rarr; castle</h3>
      <p>v2 put a 520 &times; 440 m palace at the map centre. At 2016 m that is a quarter of the
        world, so it is now a <b>260 &times; 210 m castle</b> with moat, walls and a keep &mdash;
        keeping the entire reason it was there.</p>
      <div class="ratio">still a hole every road bends around</div>
    </div>
    <div class="tier">
      <span class="n">Rerouted</span>
      <h3>The long bridge runs <em>along</em> the bay</h3>
      <p>At this size the widest open-water gap is ~250 m, so a 620 m span cannot cross
        anything. Routing it parallel to the coast, out to the island&rsquo;s north-east corner,
        buys the length honestly &mdash; and reads better.</p>
      <div class="ratio">550 m &middot; v1 asked 620 &middot; this is the most it can give</div>
    </div>
    <div class="tier">
      <span class="n">Split</span>
      <h3>One core became three centres</h3>
      <p>Neon A (old town), B (electric town) and C (hillside strip) share one kit but are
        separated by the river, the castle and the spur. Three small centres read bigger than
        one blob because you cross open ground between them.</p>
      <div class="ratio">dense envelope 0.29 km&sup2; total</div>
    </div>
  </div>
</section>

<section>
  <div class="head">
    <span class="eyebrow">The counterintuitive one</span>
    <h2>Neon buildings are not bigger than houses</h2>
  </div>
  <p class="col">They are the same size and much taller. A zakkyo shop-office is
    <b>6 &times; 12 m = 72 m&sup2;</b>; a detached suburban house is
    <b>7 &times; 9 m = 63 m&sup2;</b>. Japanese lots are <em>unagi no nedoko</em> &mdash; eel
    beds, 4&ndash;7 m wide and 12&ndash;15 m deep. Density comes from narrow frontage and zero
    setback, never from large buildings. What separates the core from the suburbs is height
    (3&ndash;8 floors vs 2), gaps (none vs 0.5&ndash;1 m), and frontage rhythm (10 shopfronts
    per 60 m block face vs 7 houses).</p>
  <p class="col">What <em>does</em> change per theme is the block &mdash; and earlier passes got
    this wrong by using one 168 m block everywhere, which is exactly why the neon read like the
    suburbs in a different colour.</p>
  <div class="tw"><table>
    <thead><tr><th>Theme</th><th class="num">Block</th><th>Real-world basis</th></tr></thead>
    <tbody>
      <tr class="pick"><td>Neon A / B / C</td><td class="num">84 m</td>
        <td>Dense centre, 50&ndash;90 m, cross-streets every block</td></tr>
      <tr><td>Residential</td><td class="num">168 m</td><td>Suburb, 100&ndash;170 m</td></tr>
      <tr><td>Port</td><td class="num">252 m</td><td>Truck turning room</td></tr>
      <tr><td>Farmland</td><td class="num">336 m</td><td>Field parcels, not blocks</td></tr>
    </tbody>
  </table></div>
  <p class="col">Because a real neon district is not uniformly eel-beds, one block in seven now
    carries a single <b>24 &times; 34 m anchor</b> &mdash; department store, office, station
    building. Nine across the three centres. They are what you navigate by inside the density.</p>
</section>

<section>
  <div class="head">
    <span class="eyebrow">Coast &amp; bay</span>
    <h2>A deeper bay is the right trade</h2>
  </div>
  <p class="col">The bay is now a drowned river mouth running ~850 m north into the city. It
    <b>removes ~0.17 km&sup2; of land while adding coastline</b> &mdash; less to build, more to
    look at, more edge to drive along. And yes, a city split by water with a large bridge
    carrying the main road is a real Japanese pattern, several times over:
    <b>&#38263;&#23822;</b> (deep harbour with mountains straight behind &mdash; the closest
    match, since v3 also has the spur standing over Neon C), <b>&#23614;&#36947;</b> (a channel
    through town: small old crossings upstream, the big span downstream),
    <b>&#31070;&#25144;</b> and <b>&#27178;&#28014;</b>. v3 uses the Onomichi arrangement of two
    crossings on the same water &mdash; a 94 m arch bridge upstream, a 243 m bay bridge
    downstream carrying the main arterial. Cutting either forces a real detour around the bay
    head, which is v1&rsquo;s racing fork arriving for free.</p>
  <p class="col">The coastline itself is now drawn from <b>two</b> polygons: a smooth 28-vertex
    skeleton the design is authored against (the ring road offsets from it), and a 224-vertex
    fractal coast that is drawn and collided. Coastal detail can be retuned without moving a
    single road. The reclaimed edges stay ruled straight &mdash; that contrast is most of what
    reads as a working port.</p>
</section>

<section>
  <div class="head">
    <span class="eyebrow">Road system</span>
    <h2>Four tiers, real Japanese dimensions</h2>
  </div>
  <div class="tw"><table>
    <thead><tr><th>Tier</th><th>What</th><th class="num">Carriageway</th><th>Spacing</th></tr></thead>
    <tbody>
      <tr><td><b>T1</b></td><td>Elevated expressway</td><td class="num">22 m</td>
        <td>One closed loop + three spurs, deck +12 m</td></tr>
      <tr><td><b>T2</b></td><td>Arterial (<em>d&#333;ri</em>)</td><td class="num">27 m</td>
        <td>504 m district seams <b>+ two extra mid-band lines</b></td></tr>
      <tr><td><b>T3</b></td><td>Local street</td><td class="num">14 m</td><td>168 m</td></tr>
      <tr><td><b>T4</b></td><td>Alley (<em>roji</em>)</td><td class="num">4.5 m</td>
        <td>45&ndash;60 m, core only, generated</td></tr>
    </tbody>
  </table></div>
  <p class="col">The extra T2 lines are the one dimension change the smaller world forces:
    504&nbsp;m spacing alone is too coarse when the map is four districts across. In the dense
    band it now lands near 250&nbsp;m &mdash; the low end of real Tokyo&rsquo;s 300&ndash;600 m
    range, which is correct for a city centre.</p>
</section>

<section>
  <div class="head">
    <span class="eyebrow">Before implementation</span>
    <h2>Five things to settle</h2>
  </div>
  <ul class="clean col">
    <li><b>Era.</b> The Niigata reference points at 1990s&ndash;2000s regional-city Japan rather
      than neon-future Tokyo &mdash; cheaper and more distinctive. Lock it before the signage
      atlas.</li>
    <li><b>Danchi bearing.</b> Pick the sun angle and freeze it before laying the residential
      band; the whole effect is that every slab ignores the street grid together.</li>
    <li><b>Dune-ridge count.</b> The plate draws nine; five or six wider ones may read better at
      speed. Decide by walking one district, not on paper.</li>
    <li><b>Whether Neon C earns its own kit.</b> It reuses A&rsquo;s. Four or five low-rise
      hillside meshes would make the three centres unmistakable &mdash; the cheapest upgrade
      available if the budget has room.</li>
    <li><b>Archive v1 and v2</b> so the repo has exactly one live island plan. v2&rsquo;s PLATEAU
      decimation method stays valid and is reused; its 3&nbsp;km Tokyo layout is history.</li>
  </ul>
</section>

<footer>
  <span>Plates generated by <code>tools/island_v3_plates.py</code> from
    <code>tools/island_v3_geom.py</code> &mdash; edit the geometry module, not the SVG.</span>
  <span>Landmark mesh sources: Project PLATEAU (MLIT), CC BY 4.0.</span>
</footer>

</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tokyo-bay-island-v3-review.html")
    args = ap.parse_args()
    html = PAGE.format(overview=datauri("tokyo-bay-island-overview-v3.svg"),
                       plate=datauri("tokyo-bay-island-modeling-plate-v3.svg"))
    dest = os.path.join(ROOT, args.out)
    d = os.path.dirname(dest)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(dest, "w") as f:
        f.write(html)
    print(f"wrote {dest}  ({len(html)/1024:.0f} KB, self-contained)")


if __name__ == "__main__":
    main()
