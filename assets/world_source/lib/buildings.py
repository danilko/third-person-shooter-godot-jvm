#!/usr/bin/env python3
"""
buildings.py — building factories assembled from kit SOURCE pieces via GN instancing.

Each building is a root Empty; its walls/slabs/props are point-cloud children placed
in building-local space (origin at the SW corner, footprint extends +X/+Y, front =
the -Y edge where the entrance sits). Rotating the root aims the front at a street.

Types: house (gable roof + garage), block (flat-roof apartment block), apartment
(balconies + stoop), shop (shotengai: shopfront below + residence above), konbini
(canopy + forecourt + lot), shrine (torii + hall + trees).

`place_on_lot()` centres a building in a 7 m cell facing the adjacent road — used by
the grid-driven town assemblers so nothing overlaps a road or another lot.
"""
import math
from mathutils import Matrix
import kit_common as kc

BAY, R_H, K_H = kc.R_BAY, kc.R_H, kc.K_H
ROT_FOR_DIR = {'S': 0, 'E': 90, 'N': 180, 'W': 270}   # aim front (-Y) at road dir
DVEC = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}


# --------------------------------------------------------------- shared parts
def _emit(root, coll, name, pts, piece, batch=None, base_loc=(0, 0, 0), base_rot=0.0,
          loc=(0, 0, 0), rot_z=0.0):
    """Place a small prop instancer — either as its own GN object (parented under the
    building root) or, when `batch` is given, baked into the shared accumulator."""
    if batch is not None:
        batch.add(piece, base_loc, base_rot, loc, rot_z, pts)
    else:
        kc.instancer(name, pts, piece, coll, loc=loc, rot_z=rot_z, parent=root)


def perimeter_parapet(root, coll, name, bx, by, h, floors, piece,
                      batch=None, base_loc=(0, 0, 0), base_rot=0.0):
    zt = floors * h
    sk = dict(batch=batch, base_loc=base_loc, base_rot=base_rot)
    kc.place_side(root, coll, name+"_pF", (bx*BAY, 0, 0), 180, bx, 1, h, lambda *a: piece, z0=zt, **sk)
    kc.place_side(root, coll, name+"_pB", (0, by*BAY, 0), 0, bx, 1, h, lambda *a: piece, z0=zt, **sk)
    kc.place_side(root, coll, name+"_pL", (0, 0, 0), 90, by, 1, h, lambda *a: piece, z0=zt, **sk)
    kc.place_side(root, coll, name+"_pR", (bx*BAY, by*BAY, 0), -90, by, 1, h, lambda *a: piece, z0=zt, **sk)


def slabs(root, coll, name, bx, by, zt, piece="SM_Res_Slab_2x2x03",
          batch=None, base_loc=(0, 0, 0), base_rot=0.0):
    pts_g = [(i*BAY, (k+1)*BAY, 0) for i in range(bx) for k in range(by)]
    pts_r = [(i*BAY, (k+1)*BAY, zt) for i in range(bx) for k in range(by)]
    _emit(root, coll, name+"_grd", pts_g, piece, batch=batch, base_loc=base_loc, base_rot=base_rot)
    _emit(root, coll, name+"_rf", pts_r, piece, batch=batch, base_loc=base_loc, base_rot=base_rot)


def footprint(kind, bx, by, floors):
    if kind == "konbini":
        return bx*BAY, by*BAY
    return bx*BAY, by*BAY


# ------------------------------------------------------------- building types
def building(coll, name, loc, rot_z, bx=3, by=2, floors=3, batch=None):
    root = None if batch is not None else kc.new_root(name, coll, loc, rot_z)
    sk = dict(batch=batch, base_loc=loc, base_rot=rot_z)
    W, D, h = bx*BAY, by*BAY, R_H
    WALL, WIN, DOOR = "SM_Res_Wall_Solid_2x3", "SM_Res_Wall_Window_2x3", "SM_Res_Wall_Door_2x3"
    def front(j, i, n):
        if j == 0 and i == n//2: return DOOR
        if i in (0, n-1): return WALL
        return WIN
    def other(j, i, n):
        return WIN if (i == n//2 and j > 0) else WALL
    kc.place_side(root, coll, name+"_F", (W, 0, 0), 180, bx, floors, h, front, **sk)
    kc.place_side(root, coll, name+"_B", (0, D, 0), 0, bx, floors, h, other, **sk)
    kc.place_side(root, coll, name+"_L", (0, 0, 0), 90, by, floors, h, other, **sk)
    kc.place_side(root, coll, name+"_R", (W, D, 0), -90, by, floors, h, other, **sk)
    perimeter_parapet(root, coll, name, bx, by, h, floors, "SM_Res_Parapet_Wall", **sk)
    slabs(root, coll, name, bx, by, floors*h, **sk)
    _emit(root, coll, name+"_tk", [(W*0.35, D*0.6, floors*h)], "SM_Res_Prop_Tank", **sk)
    _emit(root, coll, name+"_ac", [(W*0.7, D*0.4, floors*h)], "SM_Res_Prop_AC", **sk)
    return root


def apartment(coll, name, loc, rot_z, bx=5, by=3, floors=4, batch=None):
    root = None if batch is not None else kc.new_root(name, coll, loc, rot_z)
    sk = dict(batch=batch, base_loc=loc, base_rot=rot_z)
    W, D, h = bx*BAY, by*BAY, R_H
    WALL, WIN, DOOR, SLD = ("SM_Res_Wall_Solid_2x3", "SM_Res_Wall_Window_2x3",
                            "SM_Res_Wall_Door_2x3", "SM_Res_Wall_Slider_2x3")
    def front(j, i, n):
        if j == 0 and i == n//2: return DOOR
        if i in (0, n-1): return WALL
        if j > 0 and 1 <= i <= n-2: return SLD
        return WIN
    def other(j, i, n):
        return WIN if (i in (1, n-2) and j > 0) else WALL
    kc.place_side(root, coll, name+"_F", (W, 0, 0), 180, bx, floors, h, front, **sk)
    kc.place_side(root, coll, name+"_B", (0, D, 0), 0, bx, floors, h, other, **sk)
    kc.place_side(root, coll, name+"_L", (0, 0, 0), 90, by, floors, h, other, **sk)
    kc.place_side(root, coll, name+"_R", (W, D, 0), -90, by, floors, h, other, **sk)
    bal = [(i*BAY, 0, j*h) for j in range(1, floors) for i in range(1, bx-1)]
    for pc in ("SM_Res_Balcony_Deck", "SM_Res_Balcony_RailL", "SM_Res_Balcony_RailR", "SM_Res_Balcony_RailTop"):
        _emit(root, coll, f"{name}_b{pc.split('_')[-1]}", bal, pc, loc=(W, 0, 0), rot_z=180, **sk)
    sx = (bx//2)*BAY + 1.0
    for st in ("SM_Res_Stoop_Step1", "SM_Res_Stoop_Step2", "SM_Res_Stoop_Step3"):
        _emit(root, coll, f"{name}_{st.split('_')[-1]}", [(sx, 0, 0)], st, loc=(W, 0, 0), rot_z=180, **sk)
    perimeter_parapet(root, coll, name, bx, by, h, floors, "SM_Res_Parapet_Wall", **sk)
    slabs(root, coll, name, bx, by, floors*h, **sk)
    _emit(root, coll, name+"_tk", [(W*0.3, D*0.6, floors*h)], "SM_Res_Prop_Tank", **sk)
    _emit(root, coll, name+"_ac", [(W*0.7, D*0.4, floors*h)], "SM_Res_Prop_AC", **sk)
    return root


def house(coll, name, loc, rot_z, wb=2, floors=1):
    root = kc.new_root(name, coll, loc, rot_z)
    bx, by, h = wb, 2, R_H
    W, D = bx*BAY, by*BAY
    WALL, WIN, DOOR, GAR = ("SM_Res_Wall_Solid_2x3", "SM_Res_Wall_Window_2x3",
                            "SM_Res_Wall_Door_2x3", "SM_House_Garage_2x3")
    def front(j, i, n):
        if j == 0:
            if n >= 3 and i == 0: return GAR
            if i == (n//2 if n < 3 else n-1): return DOOR
            return WIN if 0 < i < n-1 else WALL
        return WIN if 0 < i < n-1 else WALL
    def other(j, i, n):
        return WIN if (i == n//2 and (n > 2 or j > 0)) else WALL
    kc.place_side(root, coll, name+"_F", (W, 0, 0), 180, bx, floors, h, front)
    kc.place_side(root, coll, name+"_B", (0, D, 0), 0, bx, floors, h, other)
    kc.place_side(root, coll, name+"_L", (0, 0, 0), 90, by, floors, h, other)
    kc.place_side(root, coll, name+"_R", (W, D, 0), -90, by, floors, h, other)
    roof = "SM_House_Roof_4x4" if wb == 2 else "SM_House_Roof_6x4"
    kc.instancer(name+"_roof", [(0, 0, floors*h)], roof, coll, parent=root)
    kc.instancer(name+"_grd", [(i*BAY, (k+1)*BAY, 0) for i in range(bx) for k in range(by)],
                 "SM_Res_Slab_2x2x03", coll, parent=root)
    return root


def shop(coll, name, loc, rot_z, bx=3, by=2, floors=3, batch=None):
    """Shotengai: ground floor shopfront (glass + door + awning), residence above."""
    root = None if batch is not None else kc.new_root(name, coll, loc, rot_z)
    sk = dict(batch=batch, base_loc=loc, base_rot=rot_z)
    W, D, h = bx*BAY, by*BAY, R_H
    WALL, WIN, GLASS, DOOR = ("SM_Res_Wall_Solid_2x3", "SM_Res_Wall_Window_2x3",
                              "SM_Shop_Glass_2x3", "SM_Shop_Door_2x3")
    def front(j, i, n):
        if j == 0:
            return DOOR if i == n//2 else GLASS          # full glazed shopfront
        if i in (0, n-1): return WALL
        return WIN
    def other(j, i, n):
        return WIN if (i == n//2 and j > 0) else WALL
    kc.place_side(root, coll, name+"_F", (W, 0, 0), 180, bx, floors, h, front, **sk)
    kc.place_side(root, coll, name+"_B", (0, D, 0), 0, bx, floors, h, other, **sk)
    kc.place_side(root, coll, name+"_L", (0, 0, 0), 90, by, floors, h, other, **sk)
    kc.place_side(root, coll, name+"_R", (W, D, 0), -90, by, floors, h, other, **sk)
    _emit(root, coll, name+"_awn", [(i*BAY, 0, 0) for i in range(bx)], "SM_Shop_Awning_2",
          loc=(W, 0, 0), rot_z=180, **sk)
    perimeter_parapet(root, coll, name, bx, by, h, floors, "SM_Res_Parapet_Wall", **sk)
    slabs(root, coll, name, bx, by, floors*h, **sk)
    _emit(root, coll, name+"_ac", [(W*0.6, D*0.4, floors*h)], "SM_Res_Prop_AC", **sk)
    return root


def konbini(coll, name, loc, rot_z, fb=4, by=3):
    root = kc.new_root(name, coll, loc, rot_z)
    W, D, h = fb*BAY, by*BAY, K_H
    DOOR, GLASS, WALL = "SM_Kon_Door_2x36", "SM_Kon_Glass_2x36", "SM_Kon_Wall_2x36"
    def front(j, i, n):
        if i == 0: return DOOR
        if i == n-1: return WALL
        return GLASS
    kc.place_side(root, coll, name+"_F", (W, 0, 0), 180, fb, 1, h, front)
    kc.place_side(root, coll, name+"_B", (0, D, 0), 0, fb, 1, h, lambda *a: WALL)
    kc.place_side(root, coll, name+"_L", (0, 0, 0), 90, by, 1, h, lambda *a: WALL)
    kc.place_side(root, coll, name+"_R", (W, D, 0), -90, by, 1, h, lambda *a: WALL)
    kc.place_side(root, coll, name+"_sign", (W, 0, 0), 180, fb, 1, h, lambda *a: "SM_Kon_Sign_2x07", z0=h)
    for tag, el, rz, nb in (("pB", (0, D, 0), 0, fb), ("pL", (0, 0, 0), 90, by), ("pR", (W, D, 0), -90, by)):
        kc.place_side(root, coll, name+"_"+tag, el, rz, nb, 1, h, lambda *a: "SM_Kon_Parapet_Wall", z0=h)
    kc.instancer(name+"_rf", [(i*BAY, (k+1)*BAY, h) for i in range(fb) for k in range(by)], "SM_Kon_Slab_2x2x03", coll, parent=root)
    kc.instancer(name+"_ac", [(W*0.5, D*0.5, h)], "SM_Res_Prop_AC", coll, parent=root)
    kc.instancer(name+"_canopy", [(0, 0, 0)], "SM_Kon_Canopy_3x26", coll, loc=(W, 0, 0), rot_z=180, parent=root)
    kc.instancer(name+"_lot", [(k*2.5, 0, 0) for k in range(4)], "SM_Kon_Stall_25x50", coll, loc=(-0.5, -7.2, 0), parent=root)
    kc.instancer(name+"_atm", [(1.0, -1.4, 0)], "SM_Kon_Prop_ATM", coll, parent=root)
    kc.instancer(name+"_frz", [(3.0, -1.4, 0)], "SM_Kon_Prop_Freezer", coll, parent=root)
    kc.instancer(name+"_bin", [(6.5, -1.4, 0)], "SM_Kon_Prop_Bins", coll, parent=root)
    kc.instancer(name+"_bol", [(x, -1.0, 0) for x in (0.5, 2.0, 5.0, 7.0)], "SM_Kon_Prop_Bollard", coll, parent=root)
    kc.instancer(name+"_vnd", [(7.6, -1.4, 0)], "SM_Env_Vendo_1x18", coll, parent=root)
    return root


def shrine(coll, name, loc, rot_z):
    root = kc.new_root(name, coll, loc, rot_z)
    kc.instancer(name+"_postL", [(-2, 0, 0)], "SM_Env_ToriiPost", coll, parent=root)
    kc.instancer(name+"_postR", [(2, 0, 0)], "SM_Env_ToriiPost", coll, parent=root)
    kc.instancer(name+"_top", [(0, 0, 4.6)], "SM_Env_ToriiTop", coll, parent=root)
    kc.instancer(name+"_nuki", [(0, 0, 3.5)], "SM_Env_ToriiNuki", coll, parent=root)
    hall = house(coll, name+"_hall", (0, 0, 0), 0, wb=2, floors=1)
    hall.parent = root
    hall.matrix_parent_inverse = Matrix.Identity(4)
    hall.location = (-2, 7, 0)
    for tag, x in (("tA", -4.5), ("tB", 4.5)):
        kc.instancer(name+"_"+tag, [(x, 6, 0)], "SM_Env_TreeTrunk", coll, parent=root)
        kc.instancer(name+"_"+tag+"c", [(x, 6, 0)], "SM_Env_TreeCanopy", coll, parent=root)
    return root


# ---- high-rise facade schemes (piece_for(floor, bay, nbays)) ----
def _f_curtain(j, i, n):  return "SM_HR_Spandrel_2x3" if j % 4 == 0 else "SM_HR_Curtain_2x3"
def _f_glass(j, i, n):    return "SM_HR_Panel_Glass_2x3"
def _f_window(j, i, n):   return "SM_HR_Wall_Solid_2x3" if i in (0, n-1) else "SM_HR_Wall_Window_2x3"
def _f_mixed(j, i, n):    return "SM_HR_Wall_Solid_2x3" if i in (0, n-1) else "SM_HR_Mixed_2x3"
SCHEMES = {"curtain": _f_curtain, "glass": _f_glass, "window": _f_window, "mixed": _f_mixed}

SIGN_PIECE = {"media": "SM_Sign_Media_4x6", "vertical": "SM_Sign_Vertical_1x6",
              "stack": "SM_Sign_Stack_2x3", "blade": "SM_Sign_Blade_1x3"}
SIGN_ALONG = {"media": -2.0, "vertical": -0.5, "stack": -1.2, "blade": 0.0}  # x off-centre


def _hr_faces(ox, oy, bx, by):
    """The 4 face edges {tag:(edge_loc, rot, nbays)} for a shaft at origin (ox,oy)."""
    W, D = bx*BAY, by*BAY
    return {"F": ((ox+W, oy, 0), 180, bx), "B": ((ox, oy+D, 0), 0, bx),
            "L": ((ox, oy, 0), 90, by), "R": ((ox+W, oy+D, 0), -90, by)}


def _hr_shaft(root, coll, name, ox, oy, bx, by, j0, j1, h, face_fn, z0):
    """Lay one tower shaft section (floors j0..j1) with `face_fn` on all four faces."""
    for tag, (el, rz, nb) in _hr_faces(ox, oy, bx, by).items():
        kc.place_side(root, coll, f"{name}_{tag}", el, rz, nb, j1-j0, h,
                      lambda j, i, n, f0=j0: face_fn(f0+j, i, n), z0=z0)


def _f_shop(j, i, n):  return "SM_Shop_Door_2x3" if i == n//2 else "SM_Shop_Glass_2x3"


def tower(coll, name, loc, rot_z, bx=4, by=4, floors=12, podium=True, scheme="curtain",
          signs=(), setback_at=None, balcony=False, crown="mech", media=False,
          storefront=False, ac=False):
    """High-rise on the 2 m bay / 3 m floor grid (endpoint pivot, stacks via place_side).
    `scheme` selects the facade mix (curtain/glass/window/mixed, or a face_fn); `signs` =
    [(face,floor,kind)] clads multiple signs on front AND sides (media/vertical/stack/
    blade); `setback_at` steps the upper floors in by one bay (capped); `balcony` adds a
    residential balcony band; `crown` in mech/heli/cap. `storefront`=True puts a glazed
    shotengai SHOPFRONT ground floor (shop glass/door + awning) under the tower — a
    mixed-use base; otherwise an optional 4 m glazed retail podium. `ac`=True dresses the
    tower with `SM_Res_Prop_AC` units (the same prop low-rise `building()`/`apartment()`/
    `shop()` already use) — one per bay per floor on the balcony band if `balcony` is set
    (manshon look), else a sparser every-other-floor strip on the front facade."""
    root = kc.new_root(name, coll, loc, rot_z)
    h, W, D = R_H, bx*BAY, by*BAY
    face_fn = SCHEMES.get(scheme, _f_curtain) if isinstance(scheme, str) else scheme
    z0 = 0.0
    if storefront:                            # mixed-use: shopfront ground floor + awning
        for tag, (el, rz, nb) in _hr_faces(0, 0, bx, by).items():
            fn = _f_shop if tag == "F" else (lambda *a: "SM_Shop_Glass_2x3")
            kc.place_side(root, coll, name+"_sf"+tag, el, rz, nb, 1, h, fn)
        kc.instancer(name+"_awn", [(i*BAY, 0, 0) for i in range(bx)], "SM_Shop_Awning_2",
                     coll, loc=(W, 0, 0), rot_z=180, parent=root)
        z0 = h
    elif podium:
        for tag, (el, rz, nb) in _hr_faces(0, 0, bx, by).items():
            kc.place_side(root, coll, name+"_d"+tag, el, rz, nb, 1, 4.0,
                          lambda *a: "SM_HR_Podium_2x4")
        z0 = 4.0
    use_setback = bool(setback_at) and bx > 2 and by > 2 and setback_at < floors
    if use_setback:
        _hr_shaft(root, coll, name+"_lo", 0, 0, bx, by, 0, setback_at, h, face_fn, z0)
        step_z = z0 + setback_at*h
        for tag, (el, rz, nb) in _hr_faces(0, 0, bx, by).items():
            kc.place_side(root, coll, name+"_step"+tag, el, rz, nb, 1, 1.0,
                          lambda *a: "SM_HR_Setback_Cap", z0=step_z)
        ibx, iby = bx-2, by-2
        _hr_shaft(root, coll, name+"_hi", BAY, BAY, ibx, iby, setback_at, floors, h, face_fn, step_z)
        top = (BAY, BAY, ibx, iby); zt = step_z + (floors-setback_at)*h
    else:
        _hr_shaft(root, coll, name, 0, 0, bx, by, 0, floors, h, face_fn, z0)
        top = (0, 0, bx, by); zt = z0 + floors*h
    # corner mullions up the main (lower) shaft
    ncorner = setback_at if use_setback else floors
    for cx, cy in ((0, 0), (W, 0), (0, D), (W, D)):
        kc.instancer(f"{name}_c{cx:.0f}_{cy:.0f}",
                     [(cx, cy, z0 + j*h) for j in range(ncorner)],
                     "SM_HR_Corner_2x3", coll, parent=root)
    if balcony:
        bal = [(i*BAY, 0, z0 + j*h) for j in range(floors) for i in range(bx)]
        kc.instancer(name+"_bal", bal, "SM_HR_Balcony_Tower", coll,
                     loc=(W, 0, 0), rot_z=180, parent=root)
        if ac:                      # a unit per bay per floor on the balcony band — manshon clutter
            acs = [(i*BAY + BAY*0.5, 0, z0 + j*h + 0.4) for j in range(floors) for i in range(bx)]
            kc.instancer(name+"_ac", acs, "SM_Res_Prop_AC", coll,
                         loc=(W, 0, 0), rot_z=180, parent=root)
    elif ac:                        # no balcony band — a sparser strip straight on the front facade
        acs = [(BAY*0.5 + (i % max(1, bx-1))*BAY, 0, z0 + j*h + 0.4)
               for j in range(0, floors, 2) for i in range(max(1, bx // 2))]
        kc.instancer(name+"_ac", acs, "SM_Res_Prop_AC", coll,
                     loc=(W, 0, 0), rot_z=180, parent=root)
    # closed ROOF slab over the top section (like residential), then parapet cap + crown
    tox, toy, tbx, tby = top
    roof = [(tox + i*BAY, toy + (k+1)*BAY, zt) for i in range(tbx) for k in range(tby)]
    kc.instancer(name+"_roof", roof, "SM_Res_Slab_2x2x03", coll, parent=root)
    for tag, (el, rz, nb) in _hr_faces(tox, toy, tbx, tby).items():
        kc.place_side(root, coll, name+"_cap"+tag, el, rz, nb, 1, 1.1,
                      lambda *a: "SM_HR_Setback_Cap", z0=zt)
    tcx, tcy = tox + tbx*BAY/2.0, toy + tby*BAY/2.0
    if crown == "heli":
        kc.instancer(name+"_heli", [(tcx, tcy, zt)], "SM_HR_Heli", coll, parent=root)
    elif crown == "mech":
        kc.instancer(name+"_mech", [(tcx, tcy, zt)], "SM_HR_RoofMech", coll, parent=root)
    # signage — multiple on front + sides
    allsigns = list(signs) + ([("F", max(1, floors//2), "media")] if media else [])
    for k, (face, fl, kind) in enumerate(allsigns):
        el, rz, nb = _hr_faces(0, 0, bx, by)[face]
        along = nb*BAY/2.0 + SIGN_ALONG.get(kind, 0.0)
        kc.instancer(f"{name}_sgn{k}_{kind}", [(along, 0, z0 + fl*h)], SIGN_PIECE[kind],
                     coll, loc=el, rot_z=rz, parent=root)
    return root


# High-rise floor PLATES are intentionally larger than residential (which sits on ~1 cell):
# office/neon/resi fill a 2x2-cell block (~12 m), so towers read as occupying more grid.
# 'pencil' is the exception — a deliberately slim Akihabara/Kabukicho alley tower.
TOWER_PRESETS = {
    "office": dict(bx=6, by=6, floors=16, scheme="curtain", podium=True, crown="heli",
                   setback_at=11),
    "neon":   dict(bx=5, by=6, floors=13, scheme="mixed", podium=True, media=True,
                   crown="mech", signs=[("R", 8, "blade"), ("L", 5, "vertical"),
                                        ("F", 2, "stack")]),
    "resi":   dict(bx=6, by=5, floors=11, scheme="window", podium=False, balcony=True,
                   crown="cap", ac=True),
    "pencil": dict(bx=3, by=4, floors=18, scheme="glass", podium=True, crown="mech",
                   signs=[("F", 4, "vertical"), ("F", 10, "vertical")], ac=True),
    "mixed":  dict(bx=5, by=5, floors=8, scheme="mixed", storefront=True, crown="cap",
                   signs=[("F", 1, "stack"), ("R", 1, "blade")]),
}


def tower_preset(coll, name, loc, rot_z, kind, rng=None):
    """Build a named high-rise type (office/neon/resi/pencil/mixed), optionally jittering
    the height with `rng`. Returns (bx, by) so the caller can size its reserved block."""
    kw = dict(TOWER_PRESETS[kind])
    if rng is not None:
        kw["floors"] = max(6, kw["floors"] + rng.randint(-3, 4))
    tower(coll, name, loc, rot_z, **kw)
    return kw["bx"], kw["by"]


# ------------------------------------------------------------ grid placement
SIDEWALK_CLEAR = 2.1     # m the front face is set back from the road-facing plot edge: fronts
                        # meet the BACK of the 2 m walk (zero-lot-line Japan), still off the walk
ALLEY_CLEAR = 0.6        # alleys (roji) have no raised walk -> buildings come right to the lane


def _rot2(x, y, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return (c*x - s*y, s*x + c*y)


def _front_setback(D, edge_dist):
    """Pull-back so the building FRONT face lands SIDEWALK_CLEAR behind the road-facing
    plot edge (`edge_dist` = centre->edge along the road axis). Negative for a big plot
    where the footprint sits well inside it."""
    return D/2.0 - (edge_dist - SIDEWALK_CLEAR)


def place_on_lot(coll, name, cell_center, road_dir, kind, bx, by, floors):
    """Place a building in its cell, front facing the road and set back behind the
    sidewalk strip. Keep by<=2 (<=4 m deep) so it fits without overflowing the cell back.
    Returns (loc, rot_deg)."""
    rot = ROT_FOR_DIR[road_dir]
    W, D = footprint(kind, bx, by, floors)
    dx, dy = _rot2(W/2.0, D/2.0, rot)
    ax, ay = DVEC[road_dir]                      # toward road -> pull the opposite way
    setback = _front_setback(D, kc.CELL/2.0)     # one-cell plot: edge at half a cell
    cx, cy = cell_center
    loc = (cx - dx - ax*setback, cy - dy - ay*setback, 0)
    fn = {"house": house, "block": building, "apt": apartment, "shop": shop}[kind]
    if kind == "house":
        fn(coll, name, loc, rot, wb=bx, floors=floors)
    else:
        fn(coll, name, loc, rot, bx=bx, by=by, floors=floors)
    return loc, rot


def place_on_block(coll, name, cells, road_dir, factory, bx, by, **kw):
    """Centre a building (footprint bx x by bays) over a RESERVED multi-cell block, set
    back behind the sidewalk on the road side, so a footprint wider than one 7 m cell
    does NOT overflow into the road/neighbours. `cells` = the reserved block cells;
    `factory(coll,name,loc,rot,bx=,by=,**kw)` builds it facing `road_dir`."""
    rot = ROT_FOR_DIR[road_dir]
    W, D = bx*BAY, by*BAY
    ccx = sum(c[0] for c in cells)/len(cells) * kc.CELL
    ccy = sum(c[1] for c in cells)/len(cells) * kc.CELL
    ax, ay = DVEC[road_dir]
    xs = [c[0] for c in cells]; ys = [c[1] for c in cells]
    span = (max(xs)-min(xs)+1) if ax else (max(ys)-min(ys)+1)   # cells along the road axis
    setback = _front_setback(D, span/2.0 * kc.CELL)
    dx, dy = _rot2(W/2.0, D/2.0, rot)
    loc = (ccx - dx - ax*setback, ccy - dy - ay*setback, 0)
    factory(coll, name, loc, rot, bx=bx, by=by, **kw)
    return loc, rot


# ----------------------------------------------------- contiguous street frontage (density)
def _contig(vals):
    """Contiguous integer runs (incl. singletons) -> [(start, end), ...]."""
    out = []
    if not vals:
        return out
    a = p = vals[0]
    for v in vals[1:]:
        if v == p + 1:
            p = v
        else:
            out.append((a, p)); a = p = v
    out.append((a, p))
    return out


def _frontage_runs(grid):
    """Group lot cells into straight runs that share a road side -> [(road_dir, [cells])].
    Each lot's road_dir is the first road neighbour; runs extend along the street."""
    rdir_of = {}
    for (cx, cy) in grid.lots:
        for d, (dx, dy) in DVEC.items():
            if (cx + dx, cy + dy) in grid.roads:
                rdir_of[(cx, cy)] = d; break
    groups = {}
    for (cx, cy), d in rdir_of.items():
        if d in ('N', 'S'):                       # road N/S -> run along X at fixed cy
            groups.setdefault((d, 'X', cy), []).append(cx)
        else:                                      # road E/W -> run along Y at fixed cx
            groups.setdefault((d, 'Y', cx), []).append(cy)
    runs = []
    for (d, axis, fixed), vals in groups.items():
        for (a, b) in _contig(sorted(vals)):
            cells = [((v, fixed) if axis == 'X' else (fixed, v)) for v in range(a, b + 1)]
            runs.append((d, cells))
    return runs


def _lot_depth(grid, cell, ax, ay):
    """Contiguous lot cells from `cell` going AWAY from the road (dir -(ax,ay)) — how deep a
    building on this frontage may extend before it leaves the lot. STOPS before a cell that fronts
    the OPPOSITE road (its own far neighbour is a road), so a back-to-back block reads as depth 1
    per side and buildings never meet/overlap across the block midline."""
    cx, cy = cell
    d = 1
    while True:
        nx, ny = cx - ax, cy - ay
        if (nx, ny) not in grid.lots or (nx - ax, ny - ay) in grid.roads:
            break
        cx, cy = nx, ny; d += 1
    return d


def _building_collision(coll, name, center, W, D, rot, H):
    """ONE convex collision box per building — decoupled from the mmesh visual so a dense streetwall
    stays far under the physics-body cap (the per-module -colonly path spawned thousands of bodies and
    blew Jolt's 10 240 limit). `-convcolonly` = convex collision, no visual mesh. rot is 0/90/180/270,
    so the footprint's AABB is exact (swap W/D on the perpendicular headings)."""
    bw, bd = (W, D) if int(round(rot)) % 180 == 0 else (D, W)
    o = kc.box(name + "-convcolonly", -bw / 2, bw / 2, -bd / 2, bd / 2, 0.0, H, coll, "col")
    o.location = (center[0], center[1], 0.0)


def fill_frontage(coll, grid, rng, kinds=None, hmin=2, hmax=5):
    """Lay CONTIGUOUS building frontage (shared party walls, NO side gaps) along every
    straight run of lot cells — a packed Japanese streetwall. Buildings of varied width
    (3-4 bays), depth and height abut along the street, fronts on the setback line.
    Lots facing an `alley` road sit right on the lane (no raised walk). Returns count.

    Depth is CLAMPED to the lot's actual depth (`_lot_depth`) so a deep (by=3) building never
    overruns the back onto the opposite walk, and the streetwall ENDS are inset from a crossing
    street (corner lots) so a building's side never sits on the cross-street sidewalk — the two
    reported 'building occupies the walkway' cases."""
    kinds = kinds or ["block", "block", "apt", "shop"]
    batch = kc.Batch()                       # one shared GN cloud per piece, whole streetwall
    n = 0
    for rdir, cells in _frontage_runs(grid):
        ax, ay = DVEC[rdir]
        u = (0, 1) if ax else (1, 0)              # run axis (perp to the road dir)
        cells = sorted(cells, key=lambda c: c[0]*u[0] + c[1]*u[1])
        # alley-facing frontage comes right up to the lane (no 2 m walk)
        nb = (cells[0][0] + ax, cells[0][1] + ay)
        clear = ALLEY_CLEAR if grid.class_of(nb) == 'alley' else SIDEWALK_CLEAR
        # deepest building the shallowest cell in this run can hold without leaving the lot
        run_depth = min(_lot_depth(grid, c, ax, ay) for c in cells)
        max_D = run_depth * kc.CELL - clear
        # inset the streetwall ENDS off a crossing street so a corner building's side isn't on the
        # cross-street walk (a run end whose next cell along u is a road)
        head = clear if (cells[0][0] - u[0], cells[0][1] - u[1]) in grid.roads else 0.0
        tail = clear if (cells[-1][0] + u[0], cells[-1][1] + u[1]) in grid.roads else 0.0
        ox = cells[0][0]*kc.CELL - u[0]*(kc.CELL/2) + u[0]*head
        oy = cells[0][1]*kc.CELL - u[1]*(kc.CELL/2) + u[1]*head
        ulen = len(cells) * kc.CELL - head - tail
        s = 0.0
        while ulen - s >= 5.0:                     # need ~5 m of frontage left
            w = rng.choice([3, 4, 3]); by = rng.choice([2, 2, 3])
            if w*BAY > ulen - s:
                w = max(2, int((ulen - s)//BAY))
            by = max(1, min(by, int(max_D // BAY)))   # clamp depth to the lot (no back overrun)
            W, D = w*BAY, by*BAY
            off = kc.CELL/2 - clear - D/2.0          # perp offset of the building centre
            cux = ox + u[0]*(s + W/2) + ax*off
            cuy = oy + u[1]*(s + W/2) + ay*off
            rot = ROT_FOR_DIR[rdir]
            dx, dy = _rot2(W/2.0, D/2.0, rot)
            kind = rng.choice(kinds)
            fn = {"block": building, "apt": apartment, "shop": shop}[kind]
            floors = rng.randint(hmin, hmax)
            fn(coll, f"F{n}", (cux - dx, cuy - dy, 0), rot, bx=w, by=by,
               floors=floors, batch=batch)
            _building_collision(coll, f"Fcol{n}", (cux, cuy), W, D, rot, floors * kc.R_H)
            n += 1
            s += W                                   # abut the next (shared wall, no gap)
    batch.flush(coll)                                # one instancer per piece for the whole wall
    return n
