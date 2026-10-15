#!/usr/bin/env python3
"""island_site_access.py -- every site gets a road to its door (PLAN.md 3.23 / tier B8).

    python3 tools/island_site_access.py <record> [--check]

`island_sites.py` sites each landmark by a search that asks for CLEAR ground, so the buildings stand and nothing led to
them: traffic could not reach them and the GPS could not route to them. This step (run by `island_layout.py` after
the streets, before the turnarounds) lays each site's ACCESS: a `block`-preset street (2 lanes, footways -- an access
road is not a through route, and an arterial would invite traffic the site does not want) from a junction on the
network to the site's visitor car park, where it ENDS. The car park itself is placed by `island_sites.py`
(`access_parking`) at that end, derived from this road every run.

An access road is a DEAD END by design -- a 観光駐車場 is entered and left the same way, and cars turn in the lot -- so
it is declared here (`ACCESS`) and the two places that would otherwise object read `access_roads()`:
`island_turnarounds.py` does not put a loop on it, and `island_layout.py`'s open-end assert exempts its lanes.

Access roads (one row each, record frame):
  * `todai_michi` -- the LIGHTHOUSE on the north-east headland, and `michinoeki_michi` -- the 道の駅 on the north
    coast road (2026-09-26): each leaves its road through a T cut in it (`_junction_of`), no junction being there.
  * `ekimae_<station>` -- each HUB station's street (`station_access()`, from the rail reserve; `island_rail_layout
    .HUB_ACCESS` owns them, 2026-09-29).
  * `ekimae_farm` -- FARM STATION's street across the Main line (2026-09-28): the station's ramps meet it, its car
    park fronts it; no lot at its end.
  * `jokamachi_sando` -- SHURI CASTLE (user, 2026-09-22: "ensure a routing to castle"). The castle-town street
    `jokamachi_dori` the plan drew from the castle south to nishi_dori (`island_plan`) was trimmed back to its last
    crossing by `island_network` (a stub past the last junction is trimmed), so nothing reached the castle. The 参道
    (approach) leaves the nishi_dori x jokamachi_dori junction to the NORTH, making it a crossroads, crosses the Blue
    line level beside Castle Town station and ends below the castle's south wall; the castle is walked up to, never
    driven into, and its visitors park at the station's lot (2026-09-29: its own lot stood 2.6 m above the 踏切). The flat strip
    between nishi_dori and the wall is ~130 m deep, too small for a turnaround square (90 m, 30 m clear, flat within
    3 m), which is why the car park, not a loop, is the end.

Idempotent: an access road already in the record is left alone. `--check` exits 1 if an access is missing.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from island_roadgen import *    # noqa: E402,F401,F403
import island_roadgen as rg     # noqa: E402
import point_model as pm        # noqa: E402

MOUTH = 26.0                    # a new mouth this far from its junction's centre (island_trunk_grid.MOUTH)
SPACING = 40.0                  # stations along an access road
PARKING_GAP = 4.0               # the car park's entrance edge this far past the road's end

#: name, site id, the road whose junction it leaves (its station nearest `at`), the end (the car-park entrance, record
#: x, y), the ParkingLot composite placed there, the site's own clear distance it must keep (m, from the site centre)
ACCESS = [
    dict(name="jokamachi_sando", site="shuri_castle", from_road="jokamachi_dori", at=(-610.0, -245.0),
         # STRAIGHT NORTH from the nishi_dori x jokamachi_dori junction and OVER the Blue line (a 踏切 beside Castle
         # Town station, 2026-09-28): the station's two entrance ramps come down to it on either side of the track
         # (island_rail_layout STATION_FRONT), and it ends north of the track at the castle's car park below the
         # castle's south wall -- the castle is a walk up from there. It used to end south of the track 40 m from the
         # station, the station standing in open ground with no way in (user, 2026-09-28).
         # (2026-09-29) it ENDS 10 m past the track with NO car park of its own: the castle's lot stood against the
         # castle wall 2.6 m above the 踏切 with 20 m between them -- a climb no road makes and a crossing the Blue line
         # stood 1.5 m under (probe_rail_track). Drivers park at Castle Town station's lot, which opens onto this
         # street just south of the track, and walk up; the street follows the ground, so it crosses LEVEL.
         # (2026-10-03, the castle's walk in) it ENDS ON THE OUTER GATE'S AXIS: the castle's 歓会門 / 守礼門 line
         # (library_landmarks SH_GATE_Y, piece x SH_ROAD_X = -88, i.e. 9 m outside the site's footprint), the last
         # 29 m along that axis so a visitor looks straight up it at 守礼門. Move the gates, move these two points.
         # (S18, 2026-10-15: the 踏切 batch, user "straight across the track") the castle SQUARED (yaw 90) and 30 m
         # east, so its gate axis is x -610: the street is ONE straight line from the junction to the gate's axis
         # end (piece x SH_ROAD_X = -88 -> record y -40 - 88). It used to kink 14 deg at the track (">") to reach the
         # tilted axis.
         end=(-610.0, -128.0), parking=None),
    # FARM STATION'S STREET (駅前通り, 2026-09-28): the farm row hata_yoko_1220 continued east from its nodo_waku
    # junction, over the Main line (a 踏切 beside the station's end buildings, whose ramps come down to it), ending
    # just past the track; the station's car park stands on it (island_rail_layout STATION_FRONT)
    dict(name="ekimae_farm", site="station_farm", from_road="nodo_waku", at=(1045.0, 1220.0),
         end=(1136.0, 1220.0), parking=None),
    # the LIGHTHOUSE (灯台) on the north-east headland (PLAN.md 3.30 L3, user 2026-09-26): a lane off the coast ring
    # to a small car park short of the tip; the tower itself is a later model on the reserved site (island_plan)
    dict(name="todai_michi", site="lighthouse", from_road="ring_kita", at=(1250.0, 1297.0),
         end=(1360.0, 1292.0), parking="ParkingLot4"),
    # the 道の駅 (roadside station): its car park IS the station's core (the building is a later model on the reserved
    # site). S16 C (2026-10-14): on the NORTH CAPE's terrace -- the crossroads' 4th arm, seaward, opposite kita_touge
    # (`at` is the T kita_touge's add cut: `_junction_of` joins it, REUSE_M), ending at a ParkingLot56 on the terrace.
    # It was entered off kaigan_machi on the farm coast at (442, 1757) with a ParkingLot14.
    dict(name="michinoeki_michi", site="michi_no_eki", from_road="kaigan_dori", at=(-220.0, 2010.0),
         end=(-220.0, 2048.0), parking="ParkingLot56", signal=False, lock=True, mouth=30.0),
    #    (its mouth 30 m from the 3-arm pad's centre, which stands 7 m south of the crossing: ~23 m from kaigan_dori's
    #    centreline, the other arms' setback;
    #    at MOUTH it stood 2.7 m past the coast road's edge and its turns came out R 5.7 -- dry layout c3. The lot
    #    y 2052..2088, the terrace to 2095)
    # THE WEST HAMLET 漁村 (S16 D, 2026-10-14): its one street, a T off kaigan_dori__7 (>= 100 m from its joints: 143 m
    # to the south one at y 47, 357 to the north) running due WEST down onto the hamlet's terrace (island_reshape.hamlet:
    # the coast road's height at the T, HAMLET_Z on the shelf, a 6 % ramp between) and along it to a car park at the
    # quay end. AUTHORED heights (`gyoko_stations`): a parking row's one straight grade stood ~2 m over the terrace's
    # level part, and a draped road is clamped to record 0 (Godot 5.6), 2.6 m over it. Houses front it both sides
    # (island_buildings' `fishing_village` region), the 駐在所 too (island_civic_sites).
    dict(name="gyoko_michi", site="west_hamlet", from_road="kaigan_dori", at=(-1422.0, 190.0),
         stations="gyoko", end=(-1632.0, 190.0), parking="ParkingLot14", signal=False, lock=True, lock_host=True),
    #    (`lock_host`: kaigan_dori's two mouths held at cut_road's MOUTH -- solved, they came in to ~12 m from the T and
    #    the right turn out onto the coast road was R 9.1 on the exported lanes, dry d1 / d2)
    # THE PORT (PLAN.md 3.30 L3, 2026-09-26): the platform's interior streets meet no road at their south end (a quay),
    # so the planner cannot make them; these two dead ends leave the port road kichi_dori__2 (a U along the platform's
    # north strip). The MILITARY BASE's gate road enters on the base's north edge; the LOGISTICS road serves the
    # truck yards between the base and the container terminal.
    # (the MILITARY BASE has NO gate road, 2026-10-05: its gate is on the north fence 20 m south of the port road's
    # square west corner, entered straight on from kichi_dori over a dropped kerb -- island_port_road_square.py says
    # why a gate road does not fit. The old kichi_mon_michi, a T on the port road's bend running 93 m along the east
    # fence, was removed the same day.)
    # the AIRPORT'S SERVICE ROAD (user, 2026-09-29: the airside is fenced all round; "a vehicle service gate on the
    # landside for the hangar, off a service road -- it needs one"): a T off the forecourt loop's south leg, west of
    # the terminal, south to the locked gate in the airside fence (site_airport_fence.py GATE_GX)
    dict(name="kuko_service", site="airport_airfield", from_road="kuko_rotary", at=(1130.0, -1710.0),
         end=(1130.0, -1777.0), parking=None),
    # THE FISH MARKET (PLAN S11 P12, 2026-10-13; the Japanese layout the user approved on docs/previews/market_p12.png).
    # The market stands outside the dike on a quay 2 m over the water, 10 m below the crest, with ONE way in off the
    # dike road ring_kita:
    #  * `ichiba_michi`, the ONE truck ramp (坂路), from the existing signal at x 567 ("市場前", where eki_minami_dori
    #    climbs onto the dike from the land side: its 4th arm). South off the pad, a level R 15 bend, then WEST down the
    #    dike's sea face at ICHIBA_GRADE to the yard, skewed 5.8 deg seaward so it never cuts into the face. Its stations are AUTHORED (`stations`, see ichiba_stations): the
    #    bend as real arc stations faced on the arc, the fall with a 20 m vertical curve at each end -- so
    #    `_resample_square`, the dike's 5 % ramp pass and the grade smoothing all leave it alone (authored_roads()).
    #    It replaces the 2026-10-08 lane on z 703 (69 deg in one station, 5 % from the pad's edge).
    #  (The first build had a second gate, `ichiba_chushajo`: a T at x 375 to a car park on a terrace at the crest's
    #  height. With the yard lowered to a quay's height the ramp falls 10 m and its foot lands where the terrace stood;
    #  the public and the buyers park on the yard's east end instead. `signal` / `allow_cross` stay as ACCESS keys.)
    #  (S13, 2026-10-13: the ramp is 2 + 2 and no longer a dead end. S14, 2026-10-14: it ends on J at its foot, the
    #  yard's one big one-way ring and the public car park's arm -- YARD_LOOP / YARD_PUBLIC.)
    dict(name="ichiba_michi", site="fish_market", from_road="ring_kita", at=(567.0, -672.0),
         stations="ichiba", section="ichiba", loop="ichiba",
         end=(379.0, -729.0), parking=None),
    # BEACH ACCESS over the dike (PLAN.md item 4, user 2026-10-08: "connect to the car parking just like the north east
    # top"). The dike IS the raised ring road, so cars already cross it on top and nothing needs an opening or a 陸閘;
    # what was missing is a way DOWN its sea face to the sand. Each lane is a T off the dike road, turns along the
    # dike's sea toe (where `island_dike.py raise` ramps it down off the crest, like ichiba_michi) and ends in a
    # beach car park on the flat strip between the toe and the sand; its footways are the pedestrian way down.
    # They replace island_reshape.DIKE_ACCESS's six points: "lighthouse" is todai_michi above, "farm" and
    # "residential_ne" share the north lane, "suburb" moved with the suburb fill (its old point is open sea now).
    #  * the FERRIS-WHEEL PARK (the "city" point): off ring_kita__13's west leg, north along the toe at x 893
    #    (S15: its end is no longer a dead end -- the fish market's through link `ichiba_ura_michi` continues it, end to
    #    end, west to the market's K -- so its car park went to the visitor lot off the link, `ichiba_chokubaijo`)
    dict(name="kanransha_michi", site="waterfront_park", from_road="ring_kita", at=(945.0, -899.0),
         via=[(893.0, -899.0)], end=(893.0, -800.0), parking=None),     # S15: end 10 m south (was -790), room
    #    for the link's corner off it (LINK)
    #  * the NORTH COAST beach (farm + residential north-east): west along the toe from x 840 to the farm's beach
    dict(name="kitahama_michi", site="north_beach", from_road="ring_kita", at=(852.0, 1541.0),
         via=[(845.0, 1598.0)], end=(705.0, 1628.0), parking="ParkingLot14"),
    #  * the WEST residential beach: south along the toe at x -1235 from ring_kita__12
    #    (S16 E: `at` is the factory ladder's north leg's T on the ring, island_core_streets koba_waku_w -- a crossroads;
    #    its own T at (-1188, -682) stood 27 m from it)
    dict(name="nishihama_michi", site="west_beach", from_road="ring_kita", at=(-1197.0, -655.0),
         via=[(-1235.0, -690.0)], end=(-1235.0, -795.0), parking="ParkingLot14"),
    #  * the SUBURB beach behind the suburb fill: south off ring_kita__10, west along z 1145
    dict(name="kogaihama_michi", site="suburb_beach", from_road="ring_kita", at=(1065.0, -1085.0),
         via=[(1065.0, -1145.0)], end=(895.0, -1145.0), parking="ParkingLot14"),
    dict(name="butsuryu_michi", site="logistics_yard", from_road="kichi_dori", at=(-280.0, -1230.0),
         end=(-280.0, -1440.0), parking="ParkingLot14"),     # its car park short of the runway band (z 1480)
    #  * the SUMMIT 展望 car park (S15, user: "a small parking lot ... as some japanese mountains does"): off the
    #    summit straight's south-east side a quarter of the way from its west end (the onsen ryokan's plot fronts its
    #    north-west side mid-way, kita_touge's T is near its east end)
    dict(name="sancho_tenbo", site="summit_lookout", from_road="shrine_touge", at=(-733.3, 1066.7),
         end=(-709.3, 1042.7), parking="ParkingLot14", signal=False),
    #  * the FISH MARKET's VISITORS (S15 V-C, user 2026-10-14): they come from the EAST, ring_kita -> kanransha_michi ->
    #    the through link, and never enter the trading yard; their lot north of the link on the 5.6 m strip, beside the
    #    直売所 + 食堂 (x 725-800). LAST: its road leaves the link, which ichiba_michi's loop lays.
    dict(name="ichiba_chokubaijo", site="fish_market_visitors", from_road=None, at=(820.0, -772.0),
         end=(820.0, -740.0), parking="ParkingLot28", signal=False),
]


ICHIBA_X = 567.0                # the market ramp: its arm's line off the x 567 junction (record x)
ICHIBA_MOUTH = 21.0             # its mouth from the junction's centre (the pad's solved setback)
ICHIBA_ARM = 10.0               # deg: the arm leaves the pad this far WEST of due south (S13 D2b, user: "put the T angle
#                                 slightly more straight so help the right turning angle"): 20 -> 10, an eastbound truck's
#                                 right turn in is 100 deg, not 110. Due south it stands opposite the 3+3 north arm
#                                 (eki_minami_dori, 8 deg off north) and the kit's turn search for a "straight on" with a
#                                 lane drop runs away: the pad solved 57.9 m (75 at 0 deg, 215 at +5) -- 2026-10-13, with
#                                 a 1+1 arm; read the solved setback again whenever this changes
ICHIBA_R = 20.0                 # the level bend onto the dike's face: 2 + 2 lanes of 3.5 m, so the inside lane's inner
#                                 edge turns on R 12.75 (D2b: a truck's inside wheel path >= R 12)
ICHIBA_PI_Z = 710.5             # Godot z of the bend's corner on the arm's line: the arc starts just past the mouth
ICHIBA_SKEW = 6.9               # deg: the ramp runs this far SEAWARD of the dike's own line as it falls. The face is a
#                                 1:2 slope (crest edge z 698 at 11.9, toe z ~719 at the yard's 1.5), so the contour at
#                                 the ramp's own height moves 0.14 m seaward per metre of ramp: a ramp PARALLEL to the
#                                 dike that starts on the face ends cut metres into it (the 2026-10-08 lane on z 703 did).
#                                 Skewed, its land-side edge follows the face down: seaward fill only, never a notch
ICHIBA_GRADE = 0.07             # its fall: 10.4 m in ~170 m (a ramp's limit at 40 km/h; trucks take it at 20)
ICHIBA_VCURVE = 20.0            # a vertical curve this long at the top and at the foot (MLIT: >= 20 m at 20 km/h)
ICHIBA_FOOT_RUN = 4.0           # m of level road past the foot before its bend
#: THE RAMP'S SECTION (S13 D2b, user: "add 2 lane for each way to enter market for the truck and other larger
#: vehicles"): 2 + 2 lanes of 3.5 m (a 4.5 m lane is the city's; a yard ramp at 20 km/h takes the 第3種 3.5), a
#: painted centre, one 2 m footway on the land (north) side -- the public walks down from the crest; the sea side is a
#: fill slope. 18.5 m where the 1 + 1 `block` ramp was 14.
ICHIBA_SECTION = {"lanes_fwd": 2, "lanes_bwd": 2, "lane_width": 3.5, "median_width": 0.5,
                  "shoulder_left_width": 0.5, "shoulder_right_width": 0.5,
                  "left_walk_width": 0.0, "right_walk_width": 2.0, "left_kerb_height": 0.15,
                  "right_kerb_height": 0.15, "design_speed": 20.0}
#: THE YARD'S ROADS -- ONE BIG ONE-WAY RING (S14, user 2026-10-14: "a big loop ... instead of need a u-turn ... more
#: toward japanese markets shape"). S13 ran the ramp through a U and east along the quay as a street, so every fish
#: box crossed a truck street between the hall and the boats; a 産地市場 runs boat -> apron -> 荷捌き所 -> trucks on the
#: LAND side -> road (round-1 review). Now:
#:  * at the ramp's foot a LEVEL LEFT bend of ICHIBA_BEND_R turns it due SOUTH onto J, a plain junction whose arms are
#:    all square (the shape the setback solves; S13's pad at the foot failed because its arms came in ~50 deg apart);
#:  * the RING (YARD_LOOP) leaves J south and comes back into it from the east: one-way, counter-clockwise on the map
#:    (west leg south, south leg east, east leg north, north leg west), every corner a LEFT turn, and out of it a RIGHT
#:    turn onto the ramp's up lanes -- it crosses nothing (right-hand traffic). Truck bays go on the south leg's RIGHT
#:    (the hall's) side, as parking bands of the piece, never lanes;
#:  * J's 4th arm, YARD_PUBLIC, runs WEST to the public car park and 直売所: visitors never enter the ring.
ICHIBA_BEND_R = 20.0            # the foot's bend: R 20 is a 10 t truck's minimum (the planner: R 25 if it fits)
YARD_MOUTH = 12.0               # J's mouths this far from its centre (a square junction solves ~12 m, docs/roads.md)
#: ...except the two of the ring's EXIT, a right turn from its north leg up the ramp: right-hand traffic turns right
#: round J's near (north-east) corner, on about the mouth's distance less the lanes' offset (5.3 m) -- at 12 m that is
#: R 6.2 (S14 dry layout 5), a car's turn, no truck's. At 17.5 the outer lane turns on ~R 12. Both mouths LOCKED (the
#: setback would solve them back to ~12); J moves 5.5 m south with the ramp's mouth.
YARD_EXIT_MOUTH = 17.5
#: the ring, by its CARRIAGEWAY: J's south mouth ends the south-west corner (R `r_in`, so the south leg runs at J's z +
#: YARD_MOUTH + r_in, z ~794) and the east end is ONE half-circle between the legs (R ~16). Radii are the
#: carriageway's: its inside lane turns on r - 1.75, a 10 t truck's inside wheel path wants >= 12.
YARD_LOOP = dict(name="ichiba_michi_loop", east_x=520.0, r_in=16.0)
#: RIGHT-HAND TRAFFIC IS A REVERSAL: every generator authors keep-left and `point_export` reverses every lane, so a
#: one-way road drives AGAINST its station order and its lanes lie to the RIGHT of the way it is driven, all on one
#: side of the line (measured on the exported S14 dry layout: 1.8 and 5.3 m off it). The ring, driven
#: counter-clockwise, is therefore authored CLOCKWISE (from J's east mouth round to its south mouth), and its line
#: runs YARD_SHIFT INSIDE its carriageway. With the line on J's axes at both mouths, the west leg's lanes continue the
#: ramp's down lanes (x 349.7-353.2 against 349.5-353.0) and the north leg comes in on its up lanes' side.
#: (S14 dry layouts 2-4 authored it counter-clockwise: it drove clockwise -- in by a left turn across the up lanes.)
YARD_SHIFT = 3.55
#: the kit's curve between two frozen stations is tightest at its ends (0.65-0.8 of the arc's radius, measured on the
#: centreline of a 90 deg span): an arc gets a station every ARC_STEP_DEG, but none within MOUTH_CLEAR of a mouth
ARC_STEP_DEG = 30.0
MOUTH_CLEAR = 13.0              # > the kit's MIN_MOUTH_CLEAR, 10 m, with room for the solve to slide a mouth ~2 m
#: S15 (the whole-market replan, user decisions 2026-10-14): J is a plain 3-arm T (the public arm `ichiba_chushajo` is
#: gone: visitors come from the east, V-C), and the ring's EAST END is a square 3-arm T, K, instead of a half circle:
#: the south leg arrives from the west, the ring's north-east corner leaves north (its arc ENDS on K's north mouth, so
#: the corner's line radius is the legs' spacing less the mouth, r_in - YARD_SHIFT = 12.45, a carriageway R 16), and
#: the through link leaves east. Every ring road now runs J -> K (no road has both ends on one pad).
YARD_K_X = 525.0                # record x of K's centre (the row ends at x ~525; the nearest pier is sb_off (539, 806))
#: THE THROUGH LINK (S15, the game developer's second exit; user: "the through link"): `ichiba_ura_michi`, 1 + 1, from
#: kanransha_michi's old dead end (893, -790) -- joined END TO END, no arm added anywhere -- west along the 5.6 m strip
#: (z 776), down past the retaining wall at x 608 onto the yard's level, into K's east mouth. Its climb is LINK_CLIMB of
#: run between two LINK_VCURVE vertical curves. Authored from the joint (west), so kanransha_michi's end hands over to
#: its start. Godot (x, z) corners of its plan; the pier clearances are on its centreline (sb_off (616, 762) 17 m,
#: Wangan (636, 789) 13 m, (608, 802) 20 m); a pier left on it is dropped by the build (point_mesh.pier_on_road).
#: (dry layout mk1: a joint at z 790 left the corner 14 m of depth to the strip's line and it solved R 4.8 -- the joint
#: moved south and the line north for R 28)
LINK = dict(name="ichiba_ura_michi", joint=(893.0, 800.0), corner_r=28.0, strip_z=772.0,
            plan=[(840.0, 772.0), (800.0, 772.0), (760.0, 772.0), (720.0, 772.0), (680.0, 772.0), (660.0, 772.0),
                  (640.0, 772.5), (620.0, 775.0), (600.0, 780.0), (580.0, 787.5)])
#: K's two mouths of the link's inbound RIGHT turn (link westbound -> the ring's north arm) are LOCKED, J's exit trick:
#: solved, the arm's slid in to 8 m and the turn was R 6.1 (dry layout mk3), a car's, no truck's
LINK_K_MOUTH = 17.5
LINK_CLIMB = (560.0, 655.0)     # Godot x where its climb starts (the yard) and ends (the strip)
LINK_VCURVE = 20.0
LINK_SECTION = {"lanes_fwd": 1, "lanes_bwd": 1, "lane_width": 3.5, "median_width": 0.0,
                "shoulder_left_width": 0.5, "shoulder_right_width": 0.5, "design_speed": 30.0}
YARD_SECTION = {"lanes_fwd": 2, "lanes_bwd": 0, "lane_width": 3.5, "median_width": 0.0,
                "shoulder_left_width": 0.5, "shoulder_right_width": 0.5,
                "left_walk_width": 0.0, "right_walk_width": 0.0, "left_kerb_height": 0.0,
                "right_kerb_height": 0.0, "design_speed": 20.0}


def _arc(p, t, turn, r, end_is_mouth=False, start_is_mouth=False, right=False):
    """An arc from `p` heading `t` through `turn` rad on radius `r`, turning LEFT (counter-clockwise, record frame) or
    `right`: its stations after `p` [(x, y, tangent)], frozen on the arc, one every <= ARC_STEP_DEG -- but the span
    next to a mouth is at least MOUTH_CLEAR long (the kit holds a mouth short of its setback otherwise, S14 dry layout
    2), the rest shared equally."""
    sg = -1.0 if right else 1.0
    L = r * turn
    first = MOUTH_CLEAR if start_is_mouth else 0.0
    last = MOUTH_CLEAR if end_is_mouth else 0.0
    n = max(1, int(math.ceil(math.degrees(turn) / ARC_STEP_DEG)))
    if first or last:
        rest = L - first - last
        m = max(0, int(math.ceil(rest / (r * math.radians(ARC_STEP_DEG))))) if rest > 1.0 else 0
        cuts = ([first] if first else []) + [first + rest * k / m for k in range(1, m)] if m else ([first] if first else [])
        cuts += [L - last] if last and rest > 1.0 else []
        hs = sorted(set(round(c / r, 9) for c in cuts if 0.0 < c < L)) + [turn]
    else:
        hs = [turn * k / n for k in range(1, n + 1)]
    c = (p[0] - sg * t[1] * r, p[1] + sg * t[0] * r)                   # the centre: to the left of t (right: to its right)
    rx, ry = p[0] - c[0], p[1] - c[1]
    out = []
    for h in hs:
        ch, sh = math.cos(sg * h), math.sin(sg * h)
        out.append((c[0] + rx * ch - ry * sh, c[1] + rx * sh + ry * ch, (t[0] * ch - t[1] * sh, t[0] * sh + t[1] * ch)))
    return out


def _ramp_geometry(ground):
    """The market ramp's plan, record frame: its authored stations [(x, y, z, tangent or None)] mouth first, and the
    yard junction J's centre (x, y) it ends on. Three stations on the level top bend (start, middle, end -- none nearer
    the mouth than `tidy`'s 10 m MIN_MOUTH_CLEAR), then the fall along the skewed line: a 20 m parabola, ICHIBA_GRADE,
    a 20 m parabola onto the yard's ground, ICHIBA_FOOT_RUN of level, and the level foot bend south to J's mouth."""
    import island_dike as ID
    yj = -672.0
    top = ID.crest_at(ICHIBA_X, yj) - rg.NET_Y
    a = math.radians(ICHIBA_SKEW)
    w = (-math.cos(a), -math.sin(a))                                   # down the ramp: west, a little south
    k = math.radians(ICHIBA_ARM)
    t0 = (-math.sin(k), -math.cos(k))                                  # the arm: south-south-west off the pad
    m = (ICHIBA_X + t0[0] * ICHIBA_MOUTH, yj + t0[1] * ICHIBA_MOUTH)   # its mouth, on a ray from the pad's centre
    # the bend's corner: where the arm's line meets the ramp's line (through (ICHIBA_X, ICHIBA_PI_Z) along w)
    den = t0[0] * w[1] - t0[1] * w[0]
    sa = ((ICHIBA_X - m[0]) * w[1] - (-ICHIBA_PI_Z - m[1]) * w[0]) / den
    pi = (m[0] + t0[0] * sa, m[1] + t0[1] * sa)
    phi = math.acos(t0[0] * w[0] + t0[1] * w[1])
    T = ICHIBA_R * math.tan(phi / 2.0)
    s0 = (pi[0] - t0[0] * T, pi[1] - t0[1] * T)                        # the arc's start, on the arm
    e0 = (pi[0] + w[0] * T, pi[1] + w[1] * T)                          # its end, on the ramp's line
    c = (s0[0] + t0[1] * ICHIBA_R, s0[1] - t0[0] * ICHIBA_R)           # its centre: to the arm's right (the west)
    out = [(m[0], m[1], top, t0)]
    if sa - T > 10.0:                                                  # the arc's start, when it clears the mouth
        out.append((s0[0], s0[1], top, t0))
    h = -phi / 2.0                                                     # the arc's middle: s0 turned phi/2 clockwise
    rx, ry = s0[0] - c[0], s0[1] - c[1]
    out.append((c[0] + rx * math.cos(h) - ry * math.sin(h), c[1] + rx * math.sin(h) + ry * math.cos(h), top,
                (t0[0] * math.cos(h) - t0[1] * math.sin(h), t0[0] * math.sin(h) + t0[1] * math.cos(h))))
    out.append((e0[0], e0[1], top, w))

    def on_line(d):
        return (e0[0] + w[0] * d, e0[1] + w[1] * d)
    foot_z = RS_yard_z() - rg.NET_Y                 # the yard's own level (below the network's zero: under the plain)
    D = (top - foot_z) / ICHIBA_GRADE + ICHIBA_VCURVE

    def z_at(d):
        if d <= ICHIBA_VCURVE:
            return top - ICHIBA_GRADE * d * d / (2.0 * ICHIBA_VCURVE)
        if d >= D - ICHIBA_VCURVE:
            return foot_z + ICHIBA_GRADE * (D - d) ** 2 / (2.0 * ICHIBA_VCURVE)
        return top - ICHIBA_GRADE * (d - ICHIBA_VCURVE / 2.0)
    ds = [ICHIBA_VCURVE * k_ / 3.0 for k_ in (1, 2, 3)]
    run = D - 2.0 * ICHIBA_VCURVE
    n = max(1, int(math.ceil(run / 30.0)))
    ds += [ICHIBA_VCURVE + run * k_ / n for k_ in range(1, n + 1)]
    ds += [D - ICHIBA_VCURVE + ICHIBA_VCURVE * k_ / 3.0 for k_ in (1, 2, 3)]
    out += [on_line(d) + (z_at(d), None) for d in ds]
    foot = on_line(D + ICHIBA_FOOT_RUN)
    out.append(foot + (foot_z, w))
    # the bend, level: turning LEFT (south) from w until the road heads due south, its end J's north mouth
    lf = (-w[1], w[0])                                                 # w's left: south, a little east
    c = (foot[0] + lf[0] * ICHIBA_BEND_R, foot[1] + lf[1] * ICHIBA_BEND_R)
    # its last station IS J's north mouth (no straight: the depth goes to the yard); `_arc` keeps the others clear of it
    turn = math.pi / 2.0 - a                                           # 83.1 deg: w + turn = due south
    out += [q[:2] + (foot_z, q[2]) for q in _arc(foot, w, turn, ICHIBA_BEND_R, end_is_mouth=True)]
    J = (out[-1][0], out[-1][1] - YARD_EXIT_MOUTH)
    return out, J


def RS_yard_z():
    import island_reshape as RS
    return RS.MARKET_YARD_Z


def ichiba_stations(ground):
    return _ramp_geometry(ground)[0]


def _bearing(deg):
    """A compass bearing as a unit vector in the RECORD frame (x east, y north)."""
    a = math.radians(deg)
    return (math.sin(a), math.cos(a))


def _straights(rows, x1, y1, t, step=35.0):
    """Stations from the last row to (x1, y1) every <= step m along tangent t."""
    x0, y0 = rows[-1][:2]
    L = math.hypot(x1 - x0, y1 - y0)
    n = max(1, int(math.ceil(L / step)))
    return [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, t) for k in range(1, n + 1)]


def yard_frame(J):
    """(rl, ysl, K): the south-west corner's line radius, the south leg's line y and K's centre, record frame."""
    rl = YARD_LOOP["r_in"] - YARD_SHIFT
    ysl = J[1] - YARD_MOUTH - rl
    return rl, ysl, (YARD_K_X, ysl)


def yard_ring_in(J):
    """The ring's NORTH half by its STATION LINE [(x, y, tangent)], AUTHORED from J's east mouth east along the north leg
    and round the north-east corner (clockwise) to K's north mouth -- driven the other way (YARD_SHIFT)."""
    E, S_ = (1.0, 0.0), (0.0, -1.0)
    rl, ysl, K = yard_frame(J)
    r = J[1] - (K[1] + YARD_MOUTH)                                      # the corner's arc ENDS on K's north mouth
    rows = [(J[0] + YARD_EXIT_MOUTH, J[1], E)]
    rows += _straights(rows, K[0] - r, J[1], E)
    rows += _arc(rows[-1][:2], E, math.pi / 2.0, r, right=True, end_is_mouth=True)
    return [(x, y, S_ if i == len(rows) - 1 else t) for i, (x, y, t) in enumerate(rows)]


def yard_ring_out(J):
    """The ring's SOUTH half: AUTHORED from K's west mouth west along the south leg and round the south-west corner
    (clockwise) to J's south mouth -- driven J -> K."""
    W, N = (-1.0, 0.0), (0.0, 1.0)
    rl, ysl, K = yard_frame(J)
    rows = [(K[0] - YARD_MOUTH, ysl, W)]
    rows += _straights(rows, J[0] + rl, ysl, W)
    rows += _arc(rows[-1][:2], W, math.pi / 2.0, rl, right=True, end_is_mouth=True)
    return [(x, y, N if i == len(rows) - 1 else t) for i, (x, y, t) in enumerate(rows)]


def yard_loop(J):
    """The ring's CARRIAGEWAY centre [(x, y)] record frame (its lanes lie YARD_SHIFT to the line's left as authored:
    the outside), one point per station, in the order it is DRIVEN: J's south mouth -> K -> J's east mouth."""
    def car(rows):
        return [(x - t[1] * YARD_SHIFT, y + t[0] * YARD_SHIFT) for x, y, t in rows]
    return car(yard_ring_out(J))[::-1] + car(yard_ring_in(J))[::-1]


def link_rows(J):
    """The through link's stations [(x, y, z, tangent)] record frame, authored from the joint with kanransha_michi's
    end to K's east mouth: the corner off the joint, west along the strip, the climb down to the yard, level to K."""
    rl, ysl, K = yard_frame(J)
    jx, jz = LINK["joint"]
    r = LINK["corner_r"]
    N_, W = (0.0, 1.0), (-1.0, 0.0)
    # off the joint heading NORTH (kanransha_michi's own direction), turning LEFT (west) onto the strip's line
    rows = [(jx, -jz, N_)]
    # the arc's inner stations are NOT frozen (tangent None): between frozen stations the kit's curve is tightest at
    # each one (docs/roads.md, the market ring's traps) -- frozen every 30 deg this R 28 solved R 8.6 (dry layout mk2)
    arc = _arc(rows[-1][:2], N_, math.pi / 2.0, r)
    rows += [(x, y, None) for x, y, _t in arc[:-1]] + [arc[-1]]
    # (no station at x 560: 5.5 m from the next one it kinked the bend down to K, R 6.3 -- dry layout mk5)
    pts = [(x, -z) for x, z in LINK["plan"]] + [(K[0] + LINK_K_MOUTH + 12.0, ysl), (K[0] + LINK_K_MOUTH, ysl)]
    for i, (x, y) in enumerate(pts):
        nx_, ny_ = (pts[i + 1] if i + 1 < len(pts) else (x - 1.0, y))
        px_, py_ = (pts[i - 1] if i else rows[-1][:2])
        tx, ty = nx_ - px_, ny_ - py_
        L = math.hypot(tx, ty)
        rows.append((x, y, (tx / L, ty / L) if i else W))
    rows[-1] = rows[-1][:2] + (W,)
    return [(x, y, link_z(x), t) for x, y, t in rows]


def link_z(x):
    """The through link's height (record z) at Godot x: the yard's level west of LINK_CLIMB, the strip's (the network's
    zero, 5.6 m) east of it, between them a parabola LINK_VCURVE long at each end and a straight grade (the climb runs
    nearly east-west, so x is its run). ONE owner: island_reshape lays the ground under it from here (LINK_CORRIDOR)."""
    yard = RS_yard_z() - rg.NET_Y
    strip = 0.0
    xa, xb = LINK_CLIMB
    if x >= xb:
        return strip
    if x <= xa:
        return yard
    L, V = xb - xa, LINK_VCURVE
    g = (strip - yard) / (L - V)
    d = x - xa
    return (yard + g * d * d / (2.0 * V) if d <= V else
            strip - g * (L - d) ** 2 / (2.0 * V) if d >= L - V else yard + g * (d - V / 2.0))


#: the link's climb in plan, Godot (x, z), for the LAND stage (island_reshape lays its ramp through the strip's retaining
#: wall): LINK["plan"] west of LINK_CLIMB's end plus the yard end on the south leg's line (z 794.45, measured on the S15
#: dry layouts: J z 769.5 + YARD_MOUTH + r_in - YARD_SHIFT)
LINK_YARD_LINE_Z = 794.45


def link_corridor():
    """[(x, z)] Godot: the link's centreline across its climb, yard end first."""
    pts = [(560.0, LINK_YARD_LINE_Z)] + sorted((p for p in LINK["plan"] if p[0] <= LINK_CLIMB[1] + 10.0))
    return pts


def ichiba_loop(net, ramp, ground):
    """J at the ramp's foot (a plain 3-arm T), the one-way ring as two roads J -> K (YARD_LOOP: the south half by its
    name, the north half + "_in"; authored clockwise, driven counter-clockwise), K at the ring's east end, and the
    through link east from K (LINK), which `main` joins end to end with kanransha_michi once that exists."""
    _rows, J = _ramp_geometry(ground)
    z = RS_yard_z() - rg.NET_Y
    halves = []
    for name, part in ((YARD_LOOP["name"] + "_in", yard_ring_in(J)), (YARD_LOOP["name"], yard_ring_out(J))):
        r = chain_road(net, name, [(x, y, z) for x, y, _t in part], preset=None)
        r.road_class = "street"
        r.ped_access = True
        r.median_style = pm.MED_NONE
        for f, v in YARD_SECTION.items():
            setattr(r.base, f, v)
        for u, q in zip(r.points, part):
            net.points[u].lanes_fwd, net.points[u].lanes_bwd = 2, 0
            rg.freeze(net, u, q[2])
        halves.append(r)
    ring_in, ring_out = halves
    rows = link_rows(J)
    link = chain_road(net, LINK["name"], [q[:3] for q in rows], preset="block")
    link.road_class = "street"
    for f, v in LINK_SECTION.items():
        setattr(link.base, f, v)
    for u, q in zip(link.points, rows):
        net.points[u].lanes_fwd, net.points[u].lanes_bwd = 1, 1
        if q[3] is not None:
            rg.freeze(net, u, q[3])
    for u in (ramp.points[-1], ring_in.points[0]):                      # the exit's two mouths (YARD_EXIT_MOUTH)
        net.points[u].setback_locked = True
    for u in (ring_in.points[-1], link.points[-1]):                     # K: the link's right turn in (LINK_K_MOUTH)
        net.points[u].setback_locked = True
    make_junction(net, [ramp.points[-1], ring_in.points[0], ring_out.points[-1]], signal=False)          # J
    make_junction(net, [ring_out.points[0], ring_in.points[-1], link.points[-1]], signal=False)         # K
    for u in ring_in.points + ring_out.points:
        q = net.points[u]
        q.ground_z, q.has_ground_z = z, True
    for u, q in zip(link.points, rows):
        p = net.points[u]
        p.ground_z, p.has_ground_z = q[2], True
    return ring_out


def ichiba_joint(net):
    """kanransha_michi's end hands over to the through link's start (a joint: two stations, one place)."""
    a = net.roads.get("kanransha_michi")
    b = next((r for n, r in net.roads.items() if n == LINK["name"] or n.startswith(LINK["name"] + "__")
              if math.hypot(net.points[r.points[0]].pos[0] - LINK["joint"][0],
                            net.points[r.points[0]].pos[1] + LINK["joint"][1]) < 0.5), None)
    if a is None or b is None:
        raise SystemExit("island_site_access: the fish market's link and kanransha_michi do not meet")
    if not net.points[a.points[-1]].has_link(b.points[0]):
        net.link(a.points[-1], b.points[0])


#: THE HAMLET STREET (see the `gyoko_michi` row): its mouth GYOKO_MOUTH west of the T's centre, level at the coast
#: road's height, then GYOKO_GRADE down with a GYOKO_VCURVE parabola centred on each end of the terrace's ramp (the ground
#: and the road part by GYOKO_GRADE * GYOKO_VCURVE / 8 = 0.15 m at the two knees), then level to the end.
GYOKO_MOUTH = 30.0             # at 24 the right turn OUT onto the coast road came out R 9.1 on the exported lanes (dry d1)
GYOKO_GRADE = 0.06
GYOKO_VCURVE = 20.0
GYOKO_STEP = 25.0


def gyoko_stations(ground):
    import island_reshape as RS
    a = next(r for r in ACCESS if r["name"] == "gyoko_michi")
    (cx, cy), (ex, ey) = a["at"], a["end"]
    L = math.hypot(ex - cx, ey - cy)
    u = ((ex - cx) / L, (ey - cy) / L)
    top, foot = RS.HAMLET_TOP - rg.NET_Y, RS.HAMLET_Z - rg.NET_Y
    k0, k1 = cx - RS.HAMLET_RAMP[1], cx - RS.HAMLET_RAMP[0]          # the ramp's two knees, m from the T's centre
    h = GYOKO_VCURVE / 2.0

    def z_at(d):
        if d <= k0 - h:
            return top
        if d < k0 + h:
            return top - GYOKO_GRADE * (d - k0 + h) ** 2 / (2.0 * GYOKO_VCURVE)
        if d <= k1 - h:
            return top - GYOKO_GRADE * (d - k0)
        if d < k1 + h:
            return foot + GYOKO_GRADE * (k1 + h - d) ** 2 / (2.0 * GYOKO_VCURVE)
        return foot
    ds = sorted(set([GYOKO_MOUTH, k0 - h, k0, k0 + h, k1 - h, k1, k1 + h, L]
                    + [d for d in range(int(GYOKO_MOUTH + GYOKO_STEP), int(L), int(GYOKO_STEP))]))
    keep = []
    for d in ds:                                    # the mouth always; nothing within 5 m of the station before it
        if d >= GYOKO_MOUTH and (not keep or d - keep[-1] >= 5.0):
            keep.append(d)
    ds = keep
    return [(cx + u[0] * d, cy + u[1] * d, z_at(d), u if i == 0 else None) for i, d in enumerate(ds)]


STATIONS = {"ichiba": ichiba_stations, "gyoko": gyoko_stations}
SECTIONS = {"ichiba": ICHIBA_SECTION}
LOOPS = {"ichiba": ichiba_loop}


def authored_roads():
    """The access roads whose stations AND heights are authored (`stations`): `island_dike.ramps` sets only their mouth
    on the pad and `island_grades smooth` holds every station (an 80 m moving average flattens a level bend and a 20 m
    vertical curve alike)."""
    return ({a["name"] for a in ACCESS if a.get("stations")} | {YARD_LOOP["name"], YARD_LOOP["name"] + "_in"}
            | {LINK["name"], LINK["name"] + "__x1"})                    # the link, cut by its visitor lot's T


REUSE_M = 15.0                  # a junction whose centre is this close to `at` is joined, not cut beside
VIA_R = 15.0                    # a corner of an access street with `via` points (a block street's kerb return)


def _resample(poly, step):
    """Stations along a polyline every <= `step` m, keeping its first and last point."""
    cum = [0.0]
    for p, q in zip(poly, poly[1:]):
        cum.append(cum[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    n = max(1, int(math.ceil(cum[-1] / step)))
    out = []
    for k in range(n + 1):
        t = cum[-1] * k / n
        j = max(i for i in range(len(cum) - 1) if cum[i] <= t) if t < cum[-1] else len(cum) - 2
        f = (t - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append((poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f))
    return out


LOT_LIFT = 0.05                 # the car park stands this far over the highest ground under it (ground never pokes up)


def parking_size(name):
    """(width, depth) of a ParkingLot composite, from building_types.json (depth is along its +Z, the entrance)."""
    import json
    doc = json.load(open(os.path.join(rg.ROOT, "assets/world_source/buildings/building_types.json")))
    return tuple({t["id"]: t for t in doc["composites"]}[name]["footprint_m"])


LX_HOLD = 12.0                  # m past a 踏切 an access road stays on the ground (the rail record's CROSS_HOLD)


def rail_crossings(pts):
    """[(arc length along `pts`, rail head z)] where the polyline crosses an AT-GRADE rail line (the reserve's corridor
    samples whose rail head stands within 1 m of the ground)."""
    import json
    path = os.path.join(rg.ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")
    if not os.path.exists(path):
        return []
    out = []
    cum = [0.0]
    for p_, q_ in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(q_[0] - p_[0], q_[1] - p_[1]))
    for c in json.load(open(path))["corridors"]:
        q = c["pts"]
        for r0, r1 in zip(q, q[1:]):
            if abs(r0[2] - r0[3]) >= 1.0 or abs(r1[2] - r1[3]) >= 1.0:
                continue
            for i in range(len(pts) - 1):
                a0, a1 = pts[i], pts[i + 1]
                ex, ey = a1[0] - a0[0], a1[1] - a0[1]
                fx, fy = r1[0] - r0[0], r1[1] - r0[1]
                den = ex * fy - ey * fx
                if abs(den) < 1e-9:
                    continue
                t = ((r0[0] - a0[0]) * fy - (r0[1] - a0[1]) * fx) / den
                u = ((r0[0] - a0[0]) * ey - (r0[1] - a0[1]) * ex) / den
                if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                    out.append((cum[i] + t * (cum[i + 1] - cum[i]), r0[2] + (r1[2] - r0[2]) * u))
    return sorted(out)


def lot_frame(end, u, a):
    """The car park at the road end `end` (x, y) heading `u` (unit, record frame): (centre (x, y), width, depth)."""
    w, d = parking_size(a["parking"])
    return (end[0] + u[0] * (PARKING_GAP + d / 2), end[1] + u[1] * (PARKING_GAP + d / 2)), w, d


def lot_top(ground, centre, u, w, d):
    """The height the car park stands at: the highest ground under its footprint (+ PARKING_GAP's apron in front of
    it), plus LOT_LIFT. The block-ground stage fills the terrain up to it (`island_ground`, as it does a lot)."""
    rx, ry = -u[1], u[0]
    hi = None
    for i in range(-4, 5):
        for j in range(-5, 5):
            x = centre[0] + rx * w / 2 * i / 4 + u[0] * (d / 2 + PARKING_GAP) * j / 4
            y = centre[1] + ry * w / 2 * i / 4 + u[1] * (d / 2 + PARKING_GAP) * j / 4
            z = ground.z(x, y) or 0.0
            hi = z if hi is None else max(hi, z)
    return hi + LOT_LIFT


def station_access():
    """THE HUB STATIONS' STREETS (2026-09-29): one row per station box in the rail reserve that carries "access"
    (`island_rail_layout.HUB_ACCESS`, which owns them -- its end is the foot of the station's entrance, so it moves with
    the station). No car park at the end: the reserve places the station's car park beside the street."""
    import json
    path = os.path.join(rg.ROOT, "assets", "world_source", "buildings", "IslandRailReserve.json")
    if not os.path.exists(path):
        return []
    out = []
    for b in json.load(open(path))["boxes"]:
        acc = b.get("access")
        if not acc or not b["id"].startswith("station:"):
            continue
        slug = b["id"].split(":", 1)[1].lower().replace(" ", "_")
        out.append(dict(name="ekimae_" + slug, site="station_" + slug, from_road=acc["from_road"],
                        at=tuple(acc["at"]), via=[tuple(v) for v in acc.get("via", [])], end=tuple(acc["end"]),
                        parking=None))
    return out


def all_access():
    return ACCESS + station_access()


def access_roads():
    """The names of every declared access road (read by island_turnarounds and island_layout)."""
    return {a["name"] for a in all_access()}


def _junction_of(net, road_name, at):
    """The junction the access leaves from: the clique of the station nearest `at` on a road named `road_name` (or
    split from it: `road_name__...`) when that station is a junction mouth, else a T CUT into that road there
    (`cut_road`, the street planner's own way of making one) -- a lighthouse lane leaves the coast ring mid-stretch."""
    cands = [(n, q) for n, r in net.roads.items() if n == road_name or n.startswith(road_name + "__")
             for q in r.points]
    if not cands:
        raise SystemExit("island_site_access: no road %s" % road_name)
    name, u = min(cands, key=lambda c: math.hypot(net.points[c[1]].pos[0] - at[0], net.points[c[1]].pos[1] - at[1]))
    js = [l.target for l in net.points[u].links if l.type == pm.LINK_JUNCTION]
    if js:
        # a JUNCTION is joined only when `at` names it (its centre within REUSE_M): a street authored off a road's
        # mid-stretch whose nearest station happens to be a mouth 27 m away (Bay's, 2026-09-29) cuts its own T instead
        # of becoming a fifth, skewed arm of that crossing
        cx = sum(net.points[q].pos[0] for q in [u] + js) / (len(js) + 1)
        cy = sum(net.points[q].pos[1] for q in [u] + js) / (len(js) + 1)
        if math.hypot(cx - at[0], cy - at[1]) <= REUSE_M:
            return [u] + js
    a, b = cut_road(net, at, name, MOUTH)
    return [a, b]


def add(net, a, ground):
    members = _junction_of(net, a["from_road"], a["at"])
    cx = sum(net.points[u].pos[0] for u in members) / len(members)
    cy = sum(net.points[u].pos[1] for u in members) / len(members)
    if a.get("stations"):
        # AUTHORED stations, laid verbatim (the market ramp): no resampling, no squared corner, its own heights
        rows = STATIONS[a["stations"]](ground)
        road = chain_road(net, a["name"], [q[:3] for q in rows], preset="block")
        sec = SECTIONS.get(a.get("section"), {})
        for f, v in sec.items():
            setattr(road.base, f, v)
        for u, q in zip(road.points, rows):
            if sec:
                net.points[u].lanes_fwd, net.points[u].lanes_bwd = sec["lanes_fwd"], sec["lanes_bwd"]
            if q[3] is not None:
                rg.freeze(net, u, q[3])
        _join(net, a, members, road)
        if a.get("loop"):
            LOOPS[a["loop"]](net, road, ground)
        return road, members
    via = list(a.get("via", ()))
    first = via[0] if via else a["end"]
    dx, dy = first[0] - cx, first[1] - cy
    L = math.hypot(dx, dy)
    mouth = a.get("mouth", MOUTH)
    head = (cx + dx / L * mouth, cy + dy / L * mouth)
    ex, ey = a["end"]
    if via:
        # a street with corners (a hub station's, `station_access`): rounded, resampled like an authored street
        # square corners (user, 2026-10-05): a station on each corner and one 15 m either side, not a resampled fillet
        from island_core_streets import _resample_square
        plan = [head] + [tuple(v) for v in via] + [tuple(a["end"])]
        pts = _resample_square(rg.densify(plan, 4.0), SPACING)
        n = len(pts) - 1
        q = pts[-2]
        L = math.hypot(ex - q[0], ey - q[1]) or 1.0
        ux, uy = (ex - q[0]) / L, (ey - q[1]) / L
    else:
        ux, uy = dx / L, dy / L
        run = L - MOUTH
        n = max(1, int(round(run / SPACING)))
        pts = [(head[0] + ux * run * k / n, head[1] + uy * run * k / n) for k in range(n + 1)]
    # the road CLIMBS to the car park's level rather than draping: the lot is flat and stands at the highest ground
    # under it, so the road's end must arrive at that height (the stamp builds the embankment under it)
    _poly = list(pts)
    z0 = max(0.0, ground.z(*pts[0]) or 0.0)
    xs = rail_crossings(pts)
    if a.get("parking") and xs:
        # ...but a road that crosses an at-grade track on the way crosses it LEVEL (a 踏切 is the road's surface at the
        # rail's height): it follows the ground to LX_HOLD past the last crossing, the crossing itself at the rail
        # head, and climbs to the lot only after that. Climbing straight across put the castle approach 1.5 m over
        # the Blue line (2026-09-29, probe_rail_track's gauge: the road and terrain stood in the train's way)
        centre, w, d = lot_frame(pts[-1], (ux, uy), a)
        top = lot_top(ground, centre, (ux, uy), w, d)
        cum = [0.0]
        for p_, q_ in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot(q_[0] - p_[0], q_[1] - p_[1]))
        hold = max(sc for sc, _z in xs) + LX_HOLD
        want = sorted(set([round(c, 3) for c in cum] + [round(sc, 3) for sc, _z in xs]
                          + [round(min(hold, cum[-1] - 1.0), 3)]))
        pts, zs = [], []
        zh = None
        for sv in want:
            j = max(i for i in range(len(cum) - 1) if cum[i] <= sv) if sv < cum[-1] else len(cum) - 2
            f = (sv - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
            x_ = _poly[j][0] + (_poly[j + 1][0] - _poly[j][0]) * f
            y_ = _poly[j][1] + (_poly[j + 1][1] - _poly[j][1]) * f
            pts.append((x_, y_))
            rz = next((z_ for sc, z_ in xs if abs(sc - sv) < 0.01), None)
            zs.append(rz if rz is not None else max(0.0, ground.z(x_, y_) or 0.0))
        k_h = max(i for i, sv in enumerate(want) if sv <= hold + 1e-6)
        zh = zs[k_h]
        L2 = want[-1] - want[k_h]
        pts3 = [(x_, y_, zs[i] if i <= k_h else zh + (top - zh) * (want[i] - want[k_h]) / max(1e-9, L2))
                for i, (x_, y_) in enumerate(pts)]
    elif a.get("parking"):
        centre, w, d = lot_frame(pts[-1], (ux, uy), a)
        top = lot_top(ground, centre, (ux, uy), w, d)
        pts3 = [(x, y, z0 + (top - z0) * k / n) for k, (x, y) in enumerate(pts)]
    else:
        # no car park at the end: the road drapes (a station's street crosses its track level with it)
        pts3 = [(x, y, max(0.0, ground.z(x, y) or 0.0)) for x, y in pts]
    road = chain_road(net, a["name"], pts3, preset="block")
    _join(net, a, members, road)
    return road, members


def _join(net, a, members, road):
    """The access road's mouth joins its junction. `signal` False = no lights (a minor T); `allow_cross` False = no turn
    across the oncoming lanes at any of its mouths (right-in / right-out: point_export drops the cross movement)."""
    make_junction(net, members + [road.points[0]], signal=a.get("signal", True))
    if a.get("lock"):
        # its mouth held where it was laid (MOUTH from the junction's centre): solved, the cape crossroads' 道の駅 arm came
        # in to 12.5 m and its right turn out to R 4.5 (S16 C, dry layout c2)
        net.points[road.points[0]].setback_locked = True
    if a.get("lock_host"):
        # ...and the HOST road's mouths at the distance they were cut at (the cape's crossroads did the same, S16 C)
        for u in members:
            net.points[u].setback_locked = True
    if not a.get("allow_cross", True):
        for u in members + [road.points[0]]:
            net.points[u].allow_cross = False
    ground = rg.Ground()
    for u in road.points:
        q = net.points[u]
        q.ground_z, q.has_ground_z = ground.z(q.pos[0], q.pos[1]) or 0.0, True


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    path = argv[0]
    net = pm.load_network(path)
    rows = all_access()
    missing = [a for a in rows if a["name"] not in net.roads]
    if "--check" in argv:
        print("island_site_access: %d of %d access roads present" % (len(rows) - len(missing), len(rows)))
        return 1 if missing else 0
    if not missing:
        print("island_site_access: every access road already present")
        return 0
    ground = rg.Ground()
    for a in missing:
        if a.get("from_road") is None:                                  # off the fish market's link (see ACCESS)
            ichiba_joint(net)
            a = dict(a, from_road=LINK["name"])
        road, members = add(net, a, ground)
        p0, p1 = net.points[road.points[0]].pos, net.points[road.points[-1]].pos
        print("island_site_access: %s -> %s: %d stations from (%.0f, %.0f) to (%.0f, %.0f), a %d-arm junction"
              % (a["name"], a["site"], len(road.points), p0[0], p0[1], p1[0], p1[1], len(members) + 1))
    pm.save_network(net, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
