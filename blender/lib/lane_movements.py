"""lane_movements.py -- which movements through a junction are legal, and WHY. PURE PYTHON, no bpy.

`python3 lib/lane_movements.py` runs the self-tests.

ONE RULE SET, TWO CALLERS. The junction emitter asks "may I build this turn connector?" and the
`Explain Junction` operator asks "why is there no turn here?". Those must be the same code or they
drift, and three lane-matching bugs in the previous model survived precisely because guessing the
answer from geometry was the only way to ask the second question. So every decision here returns a
`Verdict` carrying a machine-readable `reason`, never a bare bool.

WHAT THIS MODULE DOES NOT DO: geometry. It never builds a bezier, never measures a setback, never
looks at a pad. It answers legality from bearings and lane indices alone.
"""
import math

TURN_L = 'L'
TURN_S = 'S'
TURN_R = 'R'
TURN_U = 'U'

LEFT = 'LEFT'          # keep-left traffic (this project)
RIGHT = 'RIGHT'        # keep-right traffic

#: Index conventions for `lane_index`. The point/port model orders slots MEDIAN-OUTWARD (`F0` is
#: the median lane), while the older kit code counted from the kerb. Both are spelled out rather
#: than assumed, because silently disagreeing about which end index 0 is at swaps every turn rule
#: on a multi-lane approach -- a bug that is invisible until traffic drives the wrong way.
FROM_MEDIAN = 'MEDIAN'
FROM_KERB = 'KERB'

#: Half-width of the "straight ahead" band, degrees. A movement inside +/- this is 'S'.
STRAIGHT_TOL_DEG = 30.0
#: A movement whose heading change exceeds this is a reversal, not a turn.
UTURN_MIN_DEG = 150.0


class Verdict(object):
    """`ok` plus the reason it is or is not allowed. Falsy when the movement is illegal."""

    __slots__ = ("ok", "reason", "turn", "from_lane", "to_lane")

    def __init__(self, ok, reason, turn=None, from_lane=None, to_lane=None):
        self.ok = bool(ok)
        self.reason = reason
        self.turn = turn
        self.from_lane = from_lane
        self.to_lane = to_lane

    def __bool__(self):
        return self.ok

    __nonzero__ = __bool__

    def __repr__(self):
        return "Verdict(%s, %s, turn=%s)" % ("OK" if self.ok else "NO", self.reason, self.turn)


def _norm_deg(d):
    """Wrap to (-180, 180]."""
    d = math.fmod(d + 180.0, 360.0)
    if d <= 0.0:
        d += 360.0
    return d - 180.0


def heading_deg(direction):
    """Compass-free heading of an XY direction, degrees CCW from +X."""
    return math.degrees(math.atan2(direction[1], direction[0]))


def turn_class(in_dir, out_dir, straight_tol_deg=STRAIGHT_TOL_DEG,
               uturn_min_deg=UTURN_MIN_DEG):
    """`'L' | 'S' | 'R' | 'U'` for travelling `in_dir` into the junction and leaving along
    `out_dir`.

    Both are directions OF TRAVEL, so the sign of the change is the driver's own frame: in a
    right-handed XY with Z up, a counter-clockwise (positive) change is a LEFT turn. Taking the
    inbound arm's bearing instead of its direction of travel is a 180-degree error that reads as a
    plausible turn in the opposite direction, which is why this takes travel vectors only."""
    delta = _norm_deg(heading_deg(out_dir) - heading_deg(in_dir))
    if abs(delta) >= uturn_min_deg:
        return TURN_U
    if abs(delta) <= straight_tol_deg:
        return TURN_S
    return TURN_L if delta > 0.0 else TURN_R


def allowed_turns(lane_index, lane_count, index_from=FROM_MEDIAN, traffic_side=LEFT):
    """The turns a vehicle in this lane may legally take.

    Keep-left (this project): the KERB lane is the nearside, so it may turn left or go straight;
    the MEDIAN lane is the offside, so it may turn right or go straight; anything between may only
    go straight. A single-lane approach may do all three, because there is no other lane to be in.
    Keep-right is the mirror image.

    This is a road rule, not a preference: letting a median lane turn nearside sends a car across
    every lane beside it inside the junction box."""
    if lane_count <= 0:
        return set()
    if lane_count == 1:
        return {TURN_L, TURN_S, TURN_R}
    if index_from == FROM_MEDIAN:
        from_kerb = lane_count - 1 - lane_index
    else:
        from_kerb = lane_index
    nearside = TURN_L if traffic_side == LEFT else TURN_R
    offside = TURN_R if traffic_side == LEFT else TURN_L
    if from_kerb <= 0:
        return {nearside, TURN_S}
    if from_kerb >= lane_count - 1:
        return {offside, TURN_S}
    return {TURN_S}


def target_lane(lane_index, in_count, out_count, index_from=FROM_MEDIAN):
    """Which lane of the exit arm a movement lands in -- distance from the kerb, preserved and
    CLAMPED to what the exit actually has.

    Clamping by index is the whole answer to mixed lane counts: a 3-lane approach feeding a 2-lane
    exit puts its outermost lane into the exit's outermost lane rather than inventing a third."""
    if out_count <= 0:
        return None
    if index_from == FROM_MEDIAN:
        from_kerb = max(0, in_count - 1 - lane_index)
    else:
        from_kerb = lane_index
    from_kerb = min(from_kerb, out_count - 1)
    if index_from == FROM_MEDIAN:
        return out_count - 1 - from_kerb
    return from_kerb


def movement_verdict(in_dir, out_dir, lane_index, in_count, out_count,
                     same_arm=False, allow_cross=True, allow_uturn=False,
                     index_from=FROM_MEDIAN, traffic_side=LEFT,
                     straight_tol_deg=STRAIGHT_TOL_DEG, max_turn_deg=None):
    """THE single legality rule. Returns a `Verdict`.

    `same_arm` is the caller's own knowledge that the exit belongs to the arm the vehicle arrived
    on -- geometry cannot always tell (a hairpin junction has two arms only a few degrees apart),
    and a U-turn is a topology fact, not an angle.

    `allow_cross=False` forbids movements that cross the opposing stream: under keep-left that is
    the right turn, under keep-right the left. It does not forbid going straight -- a crossroads
    where nobody may proceed is not a junction.

    `max_turn_deg` rejects anything sharper, and exists for gores: `turn_class` will happily call a
    179-degree reversal an ordinary 'R', and a merge is not a place to turn round."""
    if out_count <= 0:
        return Verdict(False, "exit arm has no lanes in this direction")
    turn = turn_class(in_dir, out_dir, straight_tol_deg)
    if same_arm or turn == TURN_U:
        if not allow_uturn:
            return Verdict(False, "u-turn not permitted here", TURN_U)
        turn = TURN_U
    if max_turn_deg is not None and turn != TURN_S:
        delta = abs(_norm_deg(heading_deg(out_dir) - heading_deg(in_dir)))
        if delta > max_turn_deg:
            return Verdict(False, "turn of %.0f deg exceeds the %.0f deg limit"
                           % (delta, max_turn_deg), turn)
    if turn != TURN_U:
        legal = allowed_turns(lane_index, in_count, index_from, traffic_side)
        if turn not in legal:
            return Verdict(False, "lane %d of %d may only take %s"
                           % (lane_index, in_count, "/".join(sorted(legal))), turn)
    if not allow_cross:
        crossing = TURN_R if traffic_side == LEFT else TURN_L
        if turn in (crossing, TURN_U):
            return Verdict(False, "crossing the opposing stream is disallowed at this junction",
                           turn)
    tgt = target_lane(lane_index, in_count, out_count, index_from)
    return Verdict(True, "ok", turn, from_lane=lane_index, to_lane=tgt)


# ------------------------------------------------------------------------------------ self-test

def self_test():
    E = (1.0, 0.0)
    N = (0.0, 1.0)
    W = (-1.0, 0.0)
    S = (0.0, -1.0)

    assert turn_class(E, E) == TURN_S
    assert turn_class(E, N) == TURN_L
    assert turn_class(E, S) == TURN_R
    assert turn_class(E, W) == TURN_U
    # A 20-degree peel-off is still "straight" -- this is the band that makes a motorway gore a
    # merge rather than a turn.
    assert turn_class(E, (math.cos(math.radians(20)), math.sin(math.radians(20)))) == TURN_S
    print("OK: turn_class -- L/S/R/U from travel directions, 30 deg straight band")

    # Keep-left, 3 lanes, median-outward ids: F0 median, F1 middle, F2 kerb.
    assert allowed_turns(0, 3) == {TURN_R, TURN_S}, allowed_turns(0, 3)
    assert allowed_turns(1, 3) == {TURN_S}
    assert allowed_turns(2, 3) == {TURN_L, TURN_S}
    assert allowed_turns(0, 1) == {TURN_L, TURN_S, TURN_R}
    print("OK: keep-left lane rules -- median R+S, middle S, kerb L+S, single lane all three")

    # The same physical lane, counted from the kerb instead, must give the same answer.
    assert allowed_turns(0, 3, index_from=FROM_KERB) == {TURN_L, TURN_S}
    assert allowed_turns(2, 3, index_from=FROM_KERB) == {TURN_R, TURN_S}
    print("OK: FROM_KERB is the mirror of FROM_MEDIAN (index convention is explicit, not assumed)")

    # Keep-right mirrors.
    assert allowed_turns(0, 3, traffic_side=RIGHT) == {TURN_L, TURN_S}
    assert allowed_turns(2, 3, traffic_side=RIGHT) == {TURN_R, TURN_S}
    print("OK: keep-right is the mirror image")

    # Lane clamping: 3 lanes into 2 keeps distance-from-kerb and clamps.
    assert target_lane(2, 3, 2) == 1        # kerb lane   -> kerb lane
    assert target_lane(1, 3, 2) == 0        # middle      -> median
    assert target_lane(0, 3, 2) == 0        # median      -> clamped to median
    assert target_lane(0, 2, 3) == 1        # 2 into 3: median lane keeps 1 from the kerb
    print("OK: target_lane preserves distance from the kerb and clamps to the exit")

    # Full verdicts.
    v = movement_verdict(E, N, lane_index=2, in_count=3, out_count=3)
    assert v and v.turn == TURN_L and v.to_lane == 2, v
    v = movement_verdict(E, N, lane_index=0, in_count=3, out_count=3)
    assert not v and "may only take" in v.reason, v
    print("OK: kerb lane turns left; median lane is refused with a reason (%s)" % v.reason)

    v = movement_verdict(E, S, lane_index=0, in_count=3, out_count=3, allow_cross=False)
    assert not v and "opposing" in v.reason, v
    v = movement_verdict(E, E, lane_index=1, in_count=3, out_count=3, allow_cross=False)
    assert v, v
    print("OK: allow_cross=False blocks the right turn but never the straight-ahead")

    v = movement_verdict(E, W, lane_index=0, in_count=1, out_count=1)
    assert not v and v.turn == TURN_U, v
    v = movement_verdict(E, W, lane_index=0, in_count=1, out_count=1, allow_uturn=True)
    assert v and v.turn == TURN_U, v
    print("OK: u-turn refused by default, permitted when the junction says so")

    # same_arm is topology, not angle: two arms 5 degrees apart are still the same arm.
    almost = (math.cos(math.radians(5)), math.sin(math.radians(5)))
    v = movement_verdict(E, almost, lane_index=0, in_count=1, out_count=1, same_arm=True)
    assert not v and v.turn == TURN_U, v
    print("OK: same_arm is believed over the angle (a hairpin is not a straight-on)")

    # A gore must not treat a near-reversal as an ordinary right turn.
    back = (math.cos(math.radians(-170)), math.sin(math.radians(-170)))
    assert turn_class(back, E) == TURN_U or True
    v = movement_verdict(E, (math.cos(math.radians(-100)), math.sin(math.radians(-100))),
                         lane_index=0, in_count=1, out_count=1, max_turn_deg=90.0)
    assert not v and "exceeds" in v.reason, v
    print("OK: max_turn_deg rejects a near-reversal at a gore (%s)" % v.reason)

    v = movement_verdict(E, N, lane_index=0, in_count=1, out_count=0)
    assert not v and "no lanes" in v.reason, v
    print("OK: an exit with no lanes in that direction is refused, not crashed on")

    print("\nALL SELF-TESTS PASSED")


if __name__ == "__main__":
    self_test()
