"""point_kit.py -- the asset kit and a road's STYLE, without Blender (PLAN.md 3.1 B11).

`point_style` resolves a road's style slots to Blender datablocks. The road build without Blender needs the same
answer as NAMES and DATA, so this is its pure-Python twin, over `assets/world_source/kits/road_kit/road_kit.json` (written
from `road_kit.blend` by `tools/export_road_kit_data.py`, which `build_road_kit.py` runs):

  * a material is a NAME that must exist in the kit; a slot left blank takes the layer's default
    (`DEFAULT_MATERIAL`, `kit_common.MATS`' names) and a name the kit does not have FALLS BACK and is reported
    (`Style.missing`), exactly as `point_style.resolve` does;
  * a profile asset is the section's own points (`Kit.profile`), swept at its authored size by `point_mesh`, and
    its material is the one the asset carries;
  * a PIER asset (`RoadData.pillar_asset`, `Kit.pier`) is a mesh with a rigid cap and a shaft that stretches to the
    ground (PLAN.md 3.5); a name the kit lacks falls back to the box and is reported as `("pillar", "asset", name)`.

One declaration of the slots: `point_style.SLOTS`, imported, so the two resolvers cannot disagree about which
field is which slot.
"""
import hashlib
import json
import os

try:
    from . import point_style as pst
except ImportError:
    import point_style as pst                                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "assets", "world_source", "kits", "road_kit"))
KIT_JSON = os.path.join(KIT_DIR, "road_kit.json")
KIT_BLEND = os.path.join(KIT_DIR, "road_kit.blend")

#: `point_build.MATERIAL_KEYS` -> `kit_common.MATS` / `TILED_MATS` names: a layer's default material.
DEFAULT_MATERIAL = {"asphalt": "M_Asphalt", "concrete": "M_Concrete", "footway": "M_ConcreteTile",
                    "median": "M_Median", "barrier": "M_Barrier", "line_w": "M_LineW", "line_y": "M_LineY"}
#: slot -> its default key in `DEFAULT_MATERIAL` (`point_style.SLOTS`).
SLOT_DEFAULT = {slot: key for slot, _m, _a, key in pst.SLOTS}


class Kit(object):
    """The kit's materials (glTF material entries by name) and profile sections (by object name)."""

    __slots__ = ("materials", "profiles", "piers", "blend_sha1", "path")

    def __init__(self, materials=None, profiles=None, blend_sha1="", path="", piers=None):
        self.materials = dict(materials or {})
        self.profiles = dict(profiles or {})
        self.piers = dict(piers or {})
        self.blend_sha1 = blend_sha1
        self.path = path

    def material(self, name):
        """The glTF material entry for `name`: the kit's, else a plain grey one carrying the name (so a build
        never loses a surface -- the missing name is reported by the style resolve, not here)."""
        m = self.materials.get(name)
        if m is not None:
            return m
        return {"name": name, "doubleSided": True,
                "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.5, 0.5, 1.0], "metallicFactor": 0.0,
                                         "roughnessFactor": 0.5}}

    def profile(self, name):
        return self.profiles.get(name)

    def pier(self, name):
        return self.piers.get(name)

    def stale(self):
        """True when `road_kit.blend` is not the file the JSON was read from -- the kit was edited and
        `export_road_kit_data.py` (or `build_road_kit.py`) has not been run since."""
        if not self.blend_sha1 or not os.path.exists(KIT_BLEND):
            return False
        with open(KIT_BLEND, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest() != self.blend_sha1


def load(path=KIT_JSON):
    """The kit, or an EMPTY kit when the JSON does not exist (every slot then takes its default by name)."""
    if not path or not os.path.exists(path):
        return Kit(path=path or "")
    with open(path) as fh:
        d = json.load(fh)
    return Kit(d.get("materials"), d.get("profiles"), d.get("blend_sha1", ""), path, d.get("piers"))


class Style(object):
    """One road's resolved look: a material NAME per slot, a profile per asset slot, and what was missing."""

    __slots__ = ("road", "_mats", "_assets", "_missing", "_pier")

    def __init__(self, road, mats, assets, missing, pier=None):
        self.road, self._mats, self._assets, self._missing = road, mats, assets, missing
        self._pier = pier

    def pier(self):
        """`{"name", "stretch_z", "tris"}` or None -- None stands the plain box."""
        return self._pier

    def material(self, slot):
        return self._mats.get(slot)

    def asset(self, slot):
        """`{"name", "material", "splines"}` or None -- None sweeps the layer parametrically."""
        return self._assets.get(slot)

    def missing(self):
        return list(self._missing)


def resolve(road, kit):
    """`RoadData` -> `Style`, the rule `point_style.resolve` applies to datablocks, applied to names."""
    mats, assets, missing = {}, {}, []
    for slot, mat_field, asset_field, default_key in pst.SLOTS:
        name = (getattr(road, mat_field, "") or "").strip()
        if name and name not in kit.materials:
            missing.append((slot, "material", name))
            name = ""
        mats[slot] = name or DEFAULT_MATERIAL[default_key]
        if not asset_field:
            continue
        aname = (getattr(road, asset_field, "") or "").strip()
        if aname:
            prof = kit.profile(aname)
            if prof is None:
                missing.append((slot, "asset", aname))
            else:
                assets[slot] = dict(prof, name=aname)
    pier = None
    pname = (getattr(road, "pillar_asset", "") or "").strip()
    if pname:
        entry = kit.pier(pname)
        if entry is None:
            missing.append(("pillar", "asset", pname))
        else:
            pier = dict(entry, name=pname)
    return Style(road, mats, assets, missing, pier)


def self_test():
    class Road(object):
        pass
    kit = Kit({"M_Asphalt": {}, "M_Brick": {}}, {"RKA_PROFILE_kerb_std": {"material": "M_Concrete", "splines": []}})
    r = Road()
    r.surface_mat, r.kerb_asset, r.footway_mat, r.barrier_asset = "M_Brick", "RKA_PROFILE_kerb_std", "M_Nope", "X"
    r.pillar_asset = ""
    s = resolve(r, kit)
    assert s.material("surface") == "M_Brick" and s.material("footway") == "M_ConcreteTile", s._mats
    assert s.material("median") == "M_Median" and s.asset("kerb")["name"] == "RKA_PROFILE_kerb_std"
    assert sorted(s.missing()) == [("barrier", "asset", "X"), ("footway", "material", "M_Nope")], s.missing()
    assert s.pier() is None
    kit.piers["RKA_PIER_t"] = {"stretch_z": -1.0, "tris": {}}
    r.pillar_asset = "RKA_PIER_t"
    assert resolve(r, kit).pier()["name"] == "RKA_PIER_t"
    r.pillar_asset = "RKA_PIER_nope"
    assert ("pillar", "asset", "RKA_PIER_nope") in resolve(r, kit).missing() and resolve(r, kit).pier() is None
    print("OK: a named slot resolves, a blank one takes its default, a missing one falls back and is reported "
          "(piers too)")
    real = load()
    assert real.materials, "no kit JSON at %s -- run tools/export_road_kit_data.py" % KIT_JSON
    assert all(v in real.materials for v in DEFAULT_MATERIAL.values()), "the kit lacks a default material"
    assert not real.stale(), "road_kit.json is stale: road_kit.blend changed -- run tools/export_road_kit_data.py"
    assert real.piers, "road_kit.json has no RKA_PIER_* -- run build_road_kit.py --add-piers"
    print("OK: road_kit.json carries every default material and matches road_kit.blend (%d materials, %d profiles, "
          "%d piers)" % (len(real.materials), len(real.profiles), len(real.piers)))
    return 2


if __name__ == "__main__":
    print("point_kit.py: %d checks PASS" % self_test())
