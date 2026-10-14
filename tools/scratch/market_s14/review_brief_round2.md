# Fish market round 2 -- shared brief (READ-ONLY review: do not edit any repo file)

Repo: /data/danilko/git/third-person-shooter. Open-world third-person shooter (Godot 4.7 + godot-jvm), a fictional
Tokyo-Bay island, Japanese setting, RIGHT-HAND traffic, placeholder massing. Coordinates: Godot metres, x EAST,
z SOUTH (bigger z = toward the sea), y up, sea level y 0.

## Look at first (Read shows images)
- docs/previews/market_s13_plan.png -- the CURRENT built layout (roads drawn from the road record, land from the grid)
- docs/previews/market_s13_overview.jpg, market_s13_ramp.jpg, market_s13_stairs.jpg -- in-game shots
- then as needed: end of docs/island-world.md ("The fish market rebuilt for cars ..."), docs/roads.md "The yard's
  street and rectangle" (WHY there is no junction at the ramp's foot), tools/island_site_access.py (ICHIBA_*,
  `_ramp_geometry`, `yard_loop`), blender/tools/library_civic.py `fish_market`, tools/island_reshape.py (MARKET_*),
  tools/island_plan.py (reserve "fish_market"), PLAN.md "▶ S13 REBUILD -- USER DECISIONS" / "▶ S13 PROGRESS".

## Hard geometry
- Sea dike: the coast road runs on its crest at y ~12, z ~670-700; the dike face comes down to ~z 721.
- The yard is a low quay at y 1.5, x 262..608, quay wall z 808, sea south. 物揚場 y 1.0 x 290..332, z 790..808 +
  slipway. East of x 608 a 3.6 m retaining wall up to a strip (y 4.1) under the expressway.
- The ONLY vehicle access is a ramp off the dike road at a signalled junction at x ~567: it must drop ~10.5 m at <= 7 %,
  i.e. >= ~150 m of run plus vertical curves. There are only ~85-110 m between the crest road and the quay, so the ramp
  CANNOT come straight down perpendicular to the dike: today it runs west along the dike face (2+2 lanes, footway),
  then a level U (R 30) and back east along z ~797 to a plain T at x 522 into a one-way rectangle x 522..592, z 755..797.
- A junction AT the ramp's foot failed (docs/roads.md): the ramp lands parallel to every yard lane, arms met at ~50 deg,
  the setback threw mouths 38-60 m out. A road may meet the ramp's end at a clean T only if one of them turns to meet
  the other near 90 deg first. Road rules in this project: straight roads + clean single-radius curves, no S-wiggles,
  <= 4-arm junctions, right-hand traffic.
- The Wangan expressway viaduct (deck y ~17.6, ~5 m half-width each side) crosses SW->NE over the sea south of the quay
  (centre roughly x 300 z ~860, x 400 z ~835, x 500 z ~815) and over the yard's east end (a pier at (539, 806)); its
  sb_off ramp descends near x 500-700. Land extended south runs into its piers: measure the DECK EDGE, not the
  centreline. Piers may stand on yard land, never in a lane.
- Land CAN be extended south (the user offers it); everything in the yard can move. Changing land = rebuilding the
  island from the land stage (~2 h + gates) -- acceptable if it is the right design.
- Truck: assume large trucks (10 t / tractor-trailer) must circulate without reversing on a through street.

## Round 1 (three reviewers) agreed
- Japanese 産地市場 order: boat -> quay apron -> 荷捌き所 (hall, sanitary, closed-type: NO vehicles inside, forklifts only;
  people/forklift doors both long sides) -> truck docks on the LAND side -> road. Today the street runs between the
  hall and the quay: wrong.
- A 管理棟 at one end of the hall: 1F offices + 食堂, 2F 見学通路 gallery along the hall's land-side wall, roof =
  津波避難 deck. Public 直売所 + 食堂 + public car park in a zone visitors reach without crossing the work yard (round 1
  put it WEST, at the ramp's foot). Ice making / 給氷 at the quay edge (chute to boats); cold store land side near the
  exit road; 漁具倉庫 by the 物揚場. Steel ladders recessed in the quay wall every ~30 m (to be added).
- Disagreement was how to get the road behind the hall: tighten the U to R 16-18 (tight for trucks) or extend land.

## THE USER'S NEW PROPOSAL (verbatim)
"I guess if then not need to solve the u-turn, but rather do like this:
```
            | enter ramp|

|----------               ---------------------
|
|    |---------------------------------|       |
|    |
|     ---------------------------------|       |      parking lots
|
-----------------------------------------------
          alll buildings
------------------------------------
       quay/sea
```
basically a big loop to try to cover instead of need a u-turn. will this design simplify stuff (and please do more
toward japanese markets shape)"
My reading (check it): the ramp enters at the top, the yard road is one big loop round a central block (truck
waiting / staging), parking lots east, ALL buildings in one row between the loop's south side and the quay.

## What to deliver (under ~900 words)
1. Does the big loop simplify things vs the U? Can the ramp feed it given the 150 m-run constraint (where does the
   ramp come down, how does it join the loop at a clean T or as the loop's own first leg, one-way or two-way)?
2. Japanese-market fit: what the row of buildings along the quay should be, in order west->east, with depths.
3. Land: how far south must the quay go for loop + building row + apron, and does it clear the Wangan deck edge?
4. A recommended plan as an ASCII sketch WITH Godot x/z coordinates for the loop, ramp, junction, every building,
   parking, apron, ladders; then the changes vs today and the top 3 risks.
Say clearly when you are recalling practice vs unsure.
