#!/usr/bin/env python3
"""Road hierarchy, rail network and land geometry for the compressed 6 km Tokyo map.

Everything is expressed in GAME metres (centre-origin, X=east, Y=north) so it drops
straight into blender/lib/world_grid.py's coordinate space with no conversion.  Where a
polyline traces a real road, its vertices are real EPSG:6677 anchors pushed through
tokyo6km_layout.warp() — so the Shuto really does bend where the Shuto bends.

Four road tiers, deliberately mapped onto the grid the engine already has:

  T1 HIGHWAY   elevated Shuto analogue. C1 inner loop + 4 radials + the Wangan bayshore.
               Deck +12 m, no at-grade intersections, on/off ramps only.
  T2 ARTERIAL  at grade, 4-6 lanes, ~27 m. ON EVERY DISTRICT SEAM (504 m spacing) —
               i.e. exactly build_world.make_grid()'s arterial backbone, unchanged.
  T3 LOCAL     12-16 m, 2 lanes + parking. One per region line (168 m) => 3 per district
               per axis.
  T4 ALLEY     4-6 m roji. Theme-gated density, dead-end tolerant, no through traffic.
               This is the tier that sells "Japan" and the tier that pays for the LOD.

Rail is an addition, not a road tier: elevated viaducts that double as sightline
occluders (the whole LOD argument) and as level crossings on T2/T3.
"""

from __future__ import annotations

import math

from tokyo6km_layout import (DISTRICT, GRID_N, ORIGIN, WORLD, REAL, game, mtn,
                             theme_at, to_world, warp)

# ---------------------------------------------------------------------------
# T1 — elevated expressway (Shuto analogue)
# ---------------------------------------------------------------------------

DECK_Z = 12.0          # deck top above local ground, metres — clears T2 trucks + rail
RAMP_LEN = 180.0       # on/off ramp taper, metres


def _p(*names):
    return [list(map(lambda v: round(v, 1), game(n))) for n in names]


def highways():
    """Named expressway polylines.  `closed` marks a lap-able circuit."""
    # C1 Inner Circular — wraps the palace east side, Ginza, Shimbashi, Kanda, exactly
    # like the real 都心環状線.  Traced through real anchors so the corners land right.
    c1 = [
        list(map(round, warp((REAL["palace"][0] + 250, REAL["palace"][1] + 600)))),   # Takebashi
        list(map(round, warp((REAL["kanda"][0] - 100, REAL["kanda"][1] + 120)))),     # Kandabashi
        list(map(round, warp((REAL["nihonbashi"][0] + 300, REAL["nihonbashi"][1])))),  # Edobashi
        list(map(round, warp((REAL["ginza"][0] + 420, REAL["ginza"][1] - 150)))),     # Kyobashi
        list(map(round, warp((REAL["shimbashi"][0] + 250, REAL["shimbashi"][1] - 200)))),
        list(map(round, warp((REAL["tokyo_tower"][0] + 250, REAL["tokyo_tower"][1] + 200)))),
        list(map(round, warp((REAL["roppongi"][0] + 400, REAL["roppongi"][1] + 500)))),  # Tameike
        list(map(round, warp((REAL["palace"][0] - 250, REAL["palace"][1] - 250)))),   # Miyakezaka
    ]
    return [
        dict(id="C1", label="Inner Circular Route (都心環状線)", tier="T1",
             closed=True, lanes_per_dir=2, deck_z=DECK_Z, points=c1,
             role="the lap. Wraps the Tokyo Station / Ginza / Palace core."),

        dict(id="B_WANGAN", label="Bayshore Route (湾岸線)", tier="T1",
             closed=False, lanes_per_dir=3, deck_z=DECK_Z, speed_class="max",
             points=[[3024, -1180]] + _p("ariake", "odaiba", "oi_futo", "keihinjima") +
                    [[1500, -2500]],
             role="top-speed straight. The Wangan run: east edge -> Odaiba -> Oi -> Haneda."),

        # RAINBOW BRIDGE = THE SHORE -> AIRPORT LINK. Real-world it lands on Odaiba, but
        # world_grid.py already seats `slot_rainbowbridge` on the causeway to the airport
        # island (BR_X / ISL_*), and one signature span carrying the whole airport
        # approach is worth more than two forgettable ones. So the bridge runs
        # Shimbashi -> Odaiba -> across the channel -> Haneda, and it is the ONLY road
        # onto the island besides the Keikyu tunnel. Blow it and the airport is cut off.
        dict(id="R11_RAINBOW", label="Rainbow Bridge — shore to airport", tier="T1",
             closed=False, lanes_per_dir=2, deck_z=DECK_Z,
             span_m=920.0, towers=2, lower_deck="Yurikamome guideway + footway",
             points=_p("shimbashi", "rainbow_br", "odaiba") +
                    [[1500, -1900], [1620, -2320], [1760, -2560]],
             role="the signature span AND the only road to Haneda. Closes C1 <-> Wangan "
                  "into the outer circuit and carries the airport run."),

        # KAWAZU-NANADARU LOOP (河津七滝ループ橋). A double-spiral bridge, 80 m across,
        # that gains 45 m in two full turns. It is imported here for a structural reason,
        # not as a souvenir: a compressed map has no room for the 3 km of switchbacks a
        # touge normally needs to climb, and a loop bridge buys the SAME elevation in an
        # 80 m footprint. It is a spatial-compression device that happens to be famous.
        dict(id="LOOP_KAWAZU", label="Kawazu-Nanadaru loop bridge (河津七滝ループ橋)",
             tier="T2", closed=False, lanes_per_dir=1, deck_z=0.0,
             spiral=True, turns=2, diameter_m=80.0, climb_m=45.0, grade_pct=9.0,
             center=[-2210, 1180], base_z=60.0, top_z=105.0,
             points=[[-2450, 900], [-2330, 1060], [-2210, 1180]],
             role="the mountain gateway: 45 m of climb in an 80 m footprint, so the "
                  "touge above it starts high without eating a district of switchbacks."),

        dict(id="R1_HANEDA", label="Route 1 Haneda Line", tier="T1",
             closed=False, lanes_per_dir=2, deck_z=DECK_Z,
             points=_p("shimbashi", "hamamatsucho", "tennozu", "shinagawa", "oimachi",
                       "omori", "kamata", "anamori") + [[1300, -2680]],
             role="inland route to the airport. Second half of the outer circuit."),

        dict(id="R4_SHINJUKU", label="Route 4 Shinjuku Line -> Chuo Expwy", tier="T1",
             closed=False, lanes_per_dir=2, deck_z=DECK_Z,
             points=_p("palace", "ichigaya", "yotsuya", "kabukicho", "nakano") +
                    [[-2450, 900]],
             role="west radial; becomes the mountain approach and dives into the tunnel."),

        dict(id="R5_IKEBUKURO", label="Route 5 Ikebukuro Line", tier="T1",
             closed=False, lanes_per_dir=2, deck_z=DECK_Z,
             points=_p("kanda", "iidabashi", "sugamo", "ikebukuro"),
             role="north-west radial into the residential belt."),

        dict(id="R6_UENO", label="Route 6 Mukojima Line", tier="T1",
             closed=False, lanes_per_dir=2, deck_z=DECK_Z,
             # Ends at Ueno, not Asakusa: a separable X-warp cannot know that the
             # north-east and the south-east need different squeezes, so Asakusa's real
             # easting drags it out to the waterfront column. Ueno is the north rim.
             points=_p("kanda", "akihabara", "ueno", "nishi_nippori"),
             role="north-east radial past Akihabara — the elevated-over-alleys shot."),

        # Starts at the LOOP TOP (105 m), not the valley floor — the loop bridge already
        # bought the first 45 m — so the pass road only has 195 m left to climb and one
        # hairpin pair is saved outright. Still an 8.1% ruling grade, what a real touge
        # runs. It stops at the PASS (300 m); the 620 m summit is scenery, never driven.
        dict(id="TOUGE", label="Okutama pass road (都道 analogue)", tier="T2",
             closed=False, lanes_per_dir=1, deck_z=0.0, switchbacks=True,
             base_z=105.0, pass_z=300.0, ruling_grade_pct=8.1, hairpins=3,
             min_hairpin_radius_m=11.0, lane_w_m=2.75, guardrail="valley side only",
             points=[[-2210, 1180], [-2050, 1250], [-1980, 1290], [-1720, 1500],
                     [-1980, 1660], [-1560, 1810], [-1450, 1750], [-1720, 2040],
                     [-2100, 2180], [-2016, 2450]],
             role="THE TOUGE. 8% ruling grade, 4 hairpin pairs, 1.5 lanes, no guardrail "
                  "on the valley side. Real Okutama slope — annexed, never scaled."),
    ]


def outer_circuit():
    """The second, longer lap a racing game needs: C1 west + R11 + Wangan + R1."""
    return dict(id="OUTER", label="Bayshore outer circuit",
                legs=["C1(Shimbashi..Tameike)", "R11_RAINBOW", "B_WANGAN", "R1_HANEDA"],
                closes_at="Shimbashi junction",
                role="airport <-> bay <-> core. The long lap.")


# ---------------------------------------------------------------------------
# T2 — arterial backbone (unchanged from build_world.make_grid(), just 12x12)
# ---------------------------------------------------------------------------

ARTERIAL_W = 27.0     # 4 cells (28 m) minus kerb — matches rn.arterial_* width=3..4


def arterials():
    """Every district seam line carries a surface arterial. 13 N-S + 13 E-W."""
    out = []
    named_v = {4: "Meiji-dori", 6: "Sotobori-dori", 7: "Chuo-dori", 9: "Harumi-dori",
               2: "Kannana ring", 1: "Kanpachi ring"}
    named_h = {6: "Yasukuni-dori", 5: "Eitai-dori", 4: "Sakurada-dori",
               2: "Dai-ichi Keihin", 8: "Ome-kaido"}
    for k in range(GRID_N + 1):
        c = to_world(k * DISTRICT)
        out.append(dict(id=f"ART_V{k}", axis="NS", at=c, width_m=ARTERIAL_W,
                        label=named_v.get(k, f"arterial N-S {k}"),
                        points=[[c, -ORIGIN], [c, ORIGIN]]))
        out.append(dict(id=f"ART_H{k}", axis="EW", at=c, width_m=ARTERIAL_W,
                        label=named_h.get(k, f"arterial E-W {k}"),
                        points=[[-ORIGIN, c], [ORIGIN, c]]))
    return out


# ---------------------------------------------------------------------------
# T3/T4 — per-theme street texture rules (what a district builder applies inside a cell)
# ---------------------------------------------------------------------------

# block_retention = the fraction of REAL cross-streets that survive.  It is set to the
# local warp scale, because that is the only way the arithmetic closes: at scale 0.3 you
# cannot keep every real block and you must NOT shrink them — you delete two of every
# three.  This is the single most important authoring number on the page.
STREET_RULES = {
    "city":     dict(local_spacing_m=168.0, alley_spacing_m=45.0, alley_w_m=4.5,
                     block_retention=0.35, max_sightline_m=180.0, dead_end_ratio=0.30,
                     storeys=(6, 14), setback_m=0.0, notes="neon vertical; no setback, "
                     "signage overhangs the alley, buildings meet at zero lot line"),
    "resid":    dict(local_spacing_m=168.0, alley_spacing_m=60.0, alley_w_m=4.0,
                     block_retention=0.45, max_sightline_m=140.0, dead_end_ratio=0.45,
                     storeys=(2, 4), setback_m=0.5, notes="Kamata/Nakano low-rise; "
                     "tightest sightlines on the map — cheapest cells to render"),
    "industry": dict(local_spacing_m=252.0, alley_spacing_m=None, alley_w_m=0.0,
                     block_retention=0.60, max_sightline_m=400.0, dead_end_ratio=0.20,
                     storeys=(1, 3), setback_m=8.0, notes="big footprints, wide turning "
                     "circles for trucks, gantry cranes as the vertical interest"),
    "harbor":   dict(local_spacing_m=252.0, alley_spacing_m=None, alley_w_m=0.0,
                     block_retention=0.70, max_sightline_m=900.0, dead_end_ratio=0.10,
                     storeys=(1, 6), setback_m=12.0, notes="open water does the culling; "
                     "long sightlines are affordable because almost nothing is in them"),
    "rural":    dict(local_spacing_m=336.0, alley_spacing_m=None, alley_w_m=3.5,
                     block_retention=0.55, max_sightline_m=350.0, dead_end_ratio=0.55,
                     storeys=(1, 2), setback_m=4.0, notes="paddy/valley floor, farm "
                     "tracks, single-lane bridges"),
    "mtn":      dict(local_spacing_m=None, alley_spacing_m=None, alley_w_m=0.0,
                     block_retention=1.00, max_sightline_m=250.0, dead_end_ratio=0.80,
                     storeys=(1, 2), setback_m=0.0, notes="terrain IS the occluder; "
                     "ridges cap sightlines for free — no street grid at all"),
    "snow":     dict(local_spacing_m=None, alley_spacing_m=None, alley_w_m=0.0,
                     block_retention=1.00, max_sightline_m=300.0, dead_end_ratio=0.90,
                     storeys=(1, 1), setback_m=0.0, notes="summit cell; fog band does "
                     "the far culling"),
}


# ---------------------------------------------------------------------------
# rail — the addition
# ---------------------------------------------------------------------------

RAIL_Z = 8.0     # viaduct deck; UNDER the expressway deck so the two can cross


def railways():
    return [
        dict(id="YAMANOTE", label="Yamanote loop (山手線)", closed=True, elevated=True,
             deck_z=RAIL_Z, tracks=2, real_length_km=34.5,
             points=_p("kabukicho", "takadanobaba", "ikebukuro", "sugamo",
                       "nishi_nippori", "ueno", "akihabara", "kanda", "tokyo_stn",
                       "shimbashi", "hamamatsucho", "shinagawa", "osaki", "meguro",
                       "ebisu", "shibuya"),
             role="the loop that defines the core. Its viaduct is the primary "
                  "sightline occluder in every city district."),
        dict(id="CHUO", label="Chuo line (中央線)", closed=False, elevated=True,
             deck_z=RAIL_Z + 3.0, tracks=2,
             points=_p("tokyo_stn", "kanda", "ochanomizu", "iidabashi", "yotsuya",
                       "kabukicho", "nakano") + [[-2400, 760], [-2560, 1240],
                                                 [-2680, 1780], [-2450, 2150]],
             role="straight E-W cut across the middle; continues into the gorge as the "
                  "single-track Ome line to the mountain terminus."),
        dict(id="KEIKYU", label="Keikyu / Keihin-Tohoku", closed=False, elevated=True,
             deck_z=RAIL_Z, tracks=2,
             points=_p("shinagawa", "oimachi", "omori", "kamata", "anamori") +
                    [[1250, -2700]],
             role="inland airport rail; level crossings (踏切) on T3 streets."),
        dict(id="MONORAIL", label="Tokyo Monorail Haneda line", closed=False,
             elevated=True, deck_z=RAIL_Z + 6.0, tracks=1,
             points=_p("hamamatsucho") + [[820, -1250], [1000, -1700], [1180, -2150],
                                          [1420, -2600]],
             role="single slender pier line over the water beside the Wangan — the "
                  "signature Haneda approach shot."),
        dict(id="SHINKANSEN", label="Tokaido Shinkansen viaduct", closed=False,
             elevated=True, deck_z=RAIL_Z + 5.0, tracks=2,
             points=_p("tokyo_stn", "shimbashi", "hamamatsucho", "shinagawa", "osaki",
                       "oimachi") + [[-1400, -2350], [-3024, -2600]],
             role="massive continuous concrete viaduct exiting SW — a hard occluder "
                  "wall and a landmark in one."),
        dict(id="YURIKAMOME", label="Yurikamome guideway", closed=False, elevated=True,
             deck_z=RAIL_Z + 2.0, tracks=1,
             points=_p("shimbashi", "rainbow_br", "odaiba", "ariake"),
             role="rides the Rainbow Bridge lower deck."),
    ]


# ---------------------------------------------------------------------------
# land geometry — water, shoreline, island, mountain block
# ---------------------------------------------------------------------------

def land():
    """Blockout volumes the district/road tools seat against."""
    return dict(
        sea_level_z=0.0,
        bay=dict(id="tokyo_bay", kind="water_polygon", z=0.0,
                 # shoreline traced south-east: Toyosu -> Harumi -> bay -> Haneda channel
                 # shoreline: Toyosu -> Harumi -> the Shinagawa/Oi channel -> the Haneda
                 # channel, then back out. The airport sits on its own landfill INSIDE
                 # this water (haneda_island), which is what makes the only two ways in
                 # a viaduct and a tunnel.
                 points=[[3024, -260], [2560, -640], [2180, -1080], [1760, -1240],
                         [1320, -1420], [980, -1620], [860, -1980], [900, -2320],
                         [1080, -2680], [1180, -3024], [3024, -3024]],
                 role="the SE half of the map is water. Free culling, free skyline, "
                      "and the reason the Wangan reads as fast."),
        river=dict(id="tamagawa", kind="water_polyline", width_m=150.0, z=-1.0,
                   points=[[-3024, -2180], [-2300, -2380], [-1500, -2600],
                           [-700, -2820], [100, -2980], [860, -3024]],
                   role="SW boundary + the natural south edge of the residential belt; "
                        "4 bridges are the only crossings (chokepoints)."),
        haneda_island=dict(id="haneda_island", kind="landfill_rect", z=4.0,
                           min=[1008, -3024], max=[2520, -1512],
                           role="reclaimed apron; joined to the mainland only by the "
                                "Wangan viaduct and the Keikyu tunnel."),
        mountain_block=dict(id="okutama_block", kind="annexed_dem",
                            min=[-3024, 1008], max=[-1008, 3024],
                            base_z=60.0, summit_z=620.0,
                            role="TIER B. Rigid-translated real DEM; its ridges are the "
                                 "north-west skybox and the north-west culling wall."),
        tunnel_portal=dict(id="chuo_portal", kind="portal", at=[-2450, 900],
                           heading_deg=300.0, length_m=260.0,
                           role="THE SEAM HIDER. R4/Chuo dives underground here and "
                                "surfaces inside the annexed block — the 55 km cut is "
                                "never in frame."),
    )


def buffers():
    """Transitional buffer zones — the stitches that make the deletions invisible."""
    return [
        dict(id="BUF_YOTSUYA", between=["shinjuku", "tokyostation"],
             cells=[[5, 5], [6, 7]], length_m=1006.0, deleted_real_m=3746.0,
             device="Sotobori moat cut + a 900 m rail trench",
             role="Ichigaya/Yotsuya office plateau deleted. The moat's tree line and "
                  "the Chuo trench break the eyeline so the two cores never co-frame."),
        dict(id="BUF_SHIMBASHI", between=["tokyostation", "harbor"],
             cells=[[7, 3], [9, 4]], length_m=810.0, deleted_real_m=2431.0,
             device="C1 viaduct + Shiodome tower wall",
             role="Ginza to the water. The elevated deck is the horizon, so the "
                  "missing 2.4 km is behind a wall of concrete and glass."),
        dict(id="BUF_SHINAGAWA", between=["harbor", "industry"],
             cells=[[4, 1], [8, 3]], length_m=700.0, deleted_real_m=6100.0,
             device="Shinagawa rail cutting + the Oi container stacks",
             role="THE BIG ONE. Omori/Kamata sprawl (6.1 km of homogeneous low-rise) "
                  "is gone; 40 ft container stacks and the Shinkansen viaduct make a "
                  "hard visual wall across the whole width."),
        dict(id="BUF_TAMA", between=["industry", "haneda"],
             cells=[[8, 0], [9, 2]], length_m=500.0, deleted_real_m=1800.0,
             device="Tama river mouth + the airport perimeter fence",
             role="water and a fence — the cheapest possible stitch, and the real one."),
        dict(id="BUF_GORGE", between=["shinjuku", "mountain"],
             cells=[[2, 7], [4, 9]], length_m=1000.0, deleted_real_m=52000.0,
             device="climbing valley + tunnel portal (see land().tunnel_portal)",
             role="52 km deleted in 1 km of road. Density ramps resid -> rural -> "
                  "nothing, the valley walls close in, then a tunnel takes the seam."),
    ]
