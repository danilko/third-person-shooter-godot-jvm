#!/usr/bin/env python3
"""The gamepad half of the input map (PLAN.md 1.1 / F1, 2026-10-09) -- ONE table, written into project.godot.

    python3 tools/input/joypad_bindings.py          # rewrite project.godot's [input] joypad events (idempotent)
    python3 tools/input/joypad_bindings.py --check  # exit 1 when project.godot differs from the table

Layout: Steam Deck / Xbox positions (Godot's JoyButton indices are positional: A=0 B=1 X=2 Y=3 Back=4 Guide=5
Start=6 LS=7 RS=8 LB=9 RB=10 Up=11 Down=12 Left=13 Right=14; axes LX=0 LY=1 RX=2 RY=3 LT=4 RT=5). GTA V / PUBG
console practice: triggers aim + fire on foot and throttle + brake/reverse in a car, A jump, B crouch, X reload,
Y enter a vehicle, LB the weapon wheel. One physical input may serve two CONTEXTS (RT = fire on foot, throttle in a
car) only through two actions, each read by its own context (PlayerController's on-foot / vehicle halves) -- never one
action read in both. Keyboard events are left alone, except on the actions this tool creates (KEYS below).

Every action that a stick drives gets a small deadzone (0.2): Godot rescales the strength from the deadzone to 1, so
a half-pushed stick reads ~0.4 -- PlayerController reads that as a walk. The analog pedals (throttle / reverse) get
0.1 and fire / aim 0.25 (DEADZONE); the default 0.5 made a half trigger read as nothing.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project.godot"

A, B, X, Y, BACK, GUIDE, START, LS, RS, LB, RB, UP, DOWN, LEFT, RIGHT = range(15)
LX, LY, RX, RY, LT, RT = range(6)

# action -> list of ("button", index) / ("axis", axis, sign)
PAD = {
    # on foot
    "forward": [("axis", LY, -1.0)], "back": [("axis", LY, 1.0)],
    "left": [("axis", LX, -1.0)], "right": [("axis", LX, 1.0)],
    "look_left": [("axis", RX, -1.0)], "look_right": [("axis", RX, 1.0)],
    "look_up": [("axis", RY, -1.0)], "look_down": [("axis", RY, 1.0)],
    "aim": [("axis", LT, 1.0)], "fire": [("axis", RT, 1.0)],
    "jump": [("button", A)], "upright": [("button", A)],
    "crouch": [("button", B)], "crawl": [("button", DOWN)],
    "reload": [("button", X)], "use_carrier": [("button", Y)],
    "walk": [("button", LS)], "hold_breath": [("button", LS)],
    "shoulder": [("button", RS)], "radialmenu": [("button", LB)],
    "scope_zoom": [("button", RB)], "detonate": [("button", RB)],
    "holster": [("button", LEFT)], "interact": [("button", RIGHT)],
    "map": [("button", UP)], "view": [("button", BACK)], "pause": [("button", START)],
    # in a vehicle
    "throttle": [("axis", RT, 1.0)], "reverse": [("axis", LT, 1.0)],
    "handbrake": [("button", A)], "drift": [("button", A)],
    "sprint": [("button", LS)],          # the NOS / booster while driving
    "vehicle_fire": [("button", RB)], "rear_view": [("button", RS)],
    "horn": [("button", DOWN)],          # D-pad down: crawl on foot, the horn in a car (PLAN.md F11)
    # menus: Godot 4.7's built-in ui_accept / ui_cancel carry NO pad event (ui_up..ui_right already carry the D-pad
    # and the left stick), so a pad could not press a focused button or back out of a menu
    "ui_accept": [("button", A)], "ui_cancel": [("button", B)],
    # NOT on the pad (on purpose): weapon_slot_0..6 (the wheel on LB picks a slot), drop (rare; D-pad is full),
    # brake (LT is reverse, which brakes first), scope_zoom_in / _out (RB cycles), movement (unused composite)
}

# actions this tool CREATES, with their keyboard / mouse events (physical keycodes / mouse buttons)
KEYS = {
    "throttle": [("key", 87)],            # W
    "reverse": [("key", 83)],             # S
    "vehicle_fire": [("mouse", 1)],       # left mouse
    "horn": [("key", 72)],                # H: holster on foot, the horn in a car (PLAN.md F11)
    "pause": [("key", 4194305)],          # Escape
    "look_left": [], "look_right": [], "look_up": [], "look_down": [],
    # overriding a built-in ui_* action replaces its defaults, so they are restated (by keycode, as Godot has them)
    "ui_accept": [("keycode", 4194309), ("keycode", 4194310), ("keycode", 32)],   # Enter, Kp Enter, Space
    "ui_cancel": [("keycode", 4194305)],                                          # Escape
}

STICK_DEADZONE = 0.2
# triggers: the vehicle's analog pedals start almost at once; fire / aim are a quarter pull (a trigger is a button there)
DEADZONE = {"throttle": 0.1, "reverse": 0.1, "fire": 0.25, "aim": 0.25}


def key_event(code, logical=False):
    k, pk = (code, 0) if logical else (0, code)
    return ('Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,'
            '"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,'
            f'"keycode":{k},"physical_keycode":{pk},"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)')


def mouse_event(button):
    return ('Object(InputEventMouseButton,"resource_local_to_scene":false,"resource_name":"","device":-1,'
            '"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,'
            '"button_mask":0,"position":Vector2(0, 0),"global_position":Vector2(0, 0),"factor":1.0,'
            f'"button_index":{button},"canceled":false,"pressed":true,"double_click":false,"script":null)')


def pad_event(spec):
    if spec[0] == "button":
        return ('Object(InputEventJoypadButton,"resource_local_to_scene":false,"resource_name":"","device":-1,'
                f'"button_index":{spec[1]},"pressure":0.0,"pressed":true,"script":null)')
    return ('Object(InputEventJoypadMotion,"resource_local_to_scene":false,"resource_name":"","device":-1,'
            f'"axis":{spec[1]},"axis_value":{spec[2]:.1f},"script":null)')


def parse(section):
    """[(name, deadzone_text, [event strings])] in file order."""
    out = []
    for m in re.finditer(r'^([a-z_0-9]+)=\{\n"deadzone": ([0-9.]+),\n"events": \[(.*?)\]\n\}\n', section, re.S | re.M):
        events = [e.strip().rstrip(",") for e in re.findall(r'(Object\(.*?"script":null\))', m.group(3), re.S)]
        out.append((m.group(1), m.group(2), events))
    return out


def render(actions):
    blocks = []
    for name, dz, events in actions:
        blocks.append(f'{name}={{\n"deadzone": {dz},\n"events": [' + "\n, ".join(events) + "\n]\n}\n")
    return "".join(blocks)


def build(text):
    start = text.index("[input]\n\n") + len("[input]\n\n")
    end = text.index("\n\n[", start) + 1        # the blank line before the next section stays outside
    section = text[start:end]
    actions = parse(section)
    if render(actions) != section:
        raise SystemExit("joypad_bindings: [input] has entries this tool cannot parse; refusing to rewrite")
    names = [a[0] for a in actions]
    for name in KEYS:
        if name not in names:
            evs = [key_event(k[1]) if k[0] == "key" else key_event(k[1], True) if k[0] == "keycode"
                   else mouse_event(k[1]) for k in KEYS[name]]
            actions.append((name, "0.5", evs))
            names.append(name)
    missing = [n for n in PAD if n not in names]
    if missing:
        raise SystemExit(f"joypad_bindings: actions missing from project.godot: {missing}")
    new = []
    for name, dz, events in actions:
        events = [e for e in events if "InputEventJoypad" not in e]
        events += [pad_event(sp) for sp in PAD.get(name, [])]
        if any(sp[0] == "axis" and sp[1] in (LX, LY, RX, RY) for sp in PAD.get(name, [])):
            dz = str(STICK_DEADZONE)
        if name in DEADZONE:
            dz = str(DEADZONE[name])
        new.append((name, dz, events))
    return text[:start] + render(new) + text[end:]


def main():
    text = PROJECT.read_text()
    new = build(text)
    if "--check" in sys.argv:
        ok = new == text
        print("joypad_bindings: project.godot " + ("matches the table" if ok else "DIFFERS from the table"))
        sys.exit(0 if ok else 1)
    if new != text:
        PROJECT.write_text(new)
    print(f"joypad_bindings: {sum(len(v) for v in PAD.values())} pad events on {len(PAD)} actions written")


if __name__ == "__main__":
    main()
