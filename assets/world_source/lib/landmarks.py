#!/usr/bin/env python3
"""
landmarks.py — FUTURE district generators (SPEC ONLY, no bodies built yet).

These prove the multi-level Tokyo foundation (highrise kit + elevated-infra kit +
Z-layer overlays + scramble plaza + region interconnect) is sufficient to assemble the
famous scenes, WITHOUT building them this pass. Each function below documents its
signature + exactly which foundation primitives it will compose. A later pass fills the
bodies and wires them into urban zones / a multi-region map.

Shared contract (same as the town assemblers):
  * take a STREET collection `coll` and a world `origin (x,y)` + `rot` (deg),
  * build a `TownGrid` quarter (roads + reserves) for the at-grade layer,
  * place buildings via `buildings.place_on_lot` / `buildings.tower`,
  * lay elevated runs via `assemble.lay_overlay(OverlayLine(...))`,
  * return the grid + any OverlayLines so the zone/region assembler can stitch seams.

Primitive legend (all already built & verified):
  roads_kit:    Road_Lane_3p5, Road_Sidewalk_2, Road_Ground_7, Road_Scramble,
                Road_Straight/Corner/Tee/Cross/End_7
  highrise_kit: SM_HR_Curtain/Spandrel/Corner_2x3, SM_HR_Podium_2x4, SM_HR_Setback_Cap,
                SM_HR_RoofMech, SM_HR_Heli, SM_HR_Balcony_Tower, SM_Sign_Media_4x6,
                SM_Sign_Vertical_1x6, SM_Sign_Stack_2x3, SM_Gate_Arch
  infra kit:    SM_Exps_Deck_2L/Pillar/Ramp/Guardrail, SM_Rail_Viaduct_Deck/Pier,
                SM_Rail_Arch_Brick, SM_Track_Std/Shinkansen, SM_Train_*/SM_Shink_*,
                SM_Sta_Platform/Roof/Stairs
  buildings.py: tower(), apartment(), shop(), konbini(), place_on_lot()
"""

# NOTE: intentionally NO `import bpy` — this is a spec module. Importing it must not
# require Blender. The bodies (added later) will import kit_common/assemble/buildings.


def shibuya_scramble(coll, origin, rot=0):
    """Shibuya Scramble Crossing district.

    Composes:
      * Road_Scramble plaza at the hub (5-way diagonal+orthogonal crossing).
      * 3-4 tower() with media=True (SM_Sign_Media_4x6) ringing the plaza — the
        wraparound screens; SM_Sign_Vertical_1x6 on the narrower flanks.
      * a station plaza edge: SM_Sta_Platform/Roof + Hachiko-side forecourt.
      * dense mid-rise shop() blockfronts on the radiating shotengai.
    Returns (grid, overlay_lines=[]).  [stub — body added in the district pass]
    """
    raise NotImplementedError("spec only — foundation primitives listed in docstring")


def akihabara(coll, origin, rot=0):
    """Akihabara 'Electric Town' district.

    Composes:
      * narrow tall tower() (small bx/by, many floors) packed along the avenue;
      * SM_Sign_Vertical_1x6 + SM_Sign_Stack_2x3 plastered up the facades (neon);
      * an adjacent elevated RAIL viaduct (OverlayLine z=LAYER_RAIL) with a normal
        commuter consist + SM_Sta_* — the JR line hugging the shop blocks.
    Returns (grid, overlay_lines=[rail]).  [stub]
    """
    raise NotImplementedError("spec only")


def maach_ecute(coll, origin, rot=0):
    """mAAch ecute Kanda Manseibashi — shops inside a red-brick rail arch.

    Composes:
      * a run of SM_Rail_Arch_Brick (red-brick viaduct bays) end-to-end;
      * shop()/konbini() glass shopfronts tucked INSIDE each arch opening at grade;
      * SM_Track_Std on top at z=LAYER_RAIL carrying a passing normal train;
      * a riverside SM_Sta_Stairs/platform deck along the front.
    Returns (grid, overlay_lines=[track_on_arch]).  [stub]
    """
    raise NotImplementedError("spec only")


def kabukicho(coll, origin, rot=0):
    """Kabukicho nightlife quarter.

    Composes:
      * SM_Gate_Arch at the district entrance (the iconic red gate);
      * dense mid-rise blocks (building()/shop()) on narrow alleys;
      * SM_Sign_Stack_2x3 + SM_Sign_Vertical_1x6 stacked up every facade (neon/screen);
      * tight Road_Lane_3p5 alleys (1-lane) rather than wide arterials.
    Returns (grid, overlay_lines=[]).  [stub]
    """
    raise NotImplementedError("spec only")


def tower_residential(coll, origin, rot=0):
    """Cut-down tower-mansion residential cluster (Toyosu/Kachidoki vibe).

    Composes:
      * several tall tower() with SM_HR_Balcony_Tower bands (residential balconies),
        podium=True (retail base), media=False;
      * landscaped ground deck between towers (Road_Sidewalk_2 + trees);
      * a pedestrian deck OverlayLine at LAYER_PED (z=5) linking towers (future).
    Returns (grid, overlay_lines=[ped_deck]).  [stub]
    """
    raise NotImplementedError("spec only")


# Registry so a future region assembler can iterate districts by name.
DISTRICTS = {
    "shibuya_scramble": shibuya_scramble,
    "akihabara": akihabara,
    "maach_ecute": maach_ecute,
    "kabukicho": kabukicho,
    "tower_residential": tower_residential,
}
