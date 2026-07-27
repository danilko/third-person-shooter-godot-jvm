"""Shared path setup for the road_kit_authoring addon.

The addon is dev-installed as a symlink into Blender's user addons directory (see README.md), so
`__file__` may resolve through that symlink — always go through `os.path.realpath` to get back to
the actual location inside the repo before deriving sibling paths.
"""
import os
import sys

ADDON_DIR = os.path.dirname(os.path.realpath(__file__))          # .../assets/world_source/addons/road_kit_authoring
WORLD_SOURCE = os.path.dirname(os.path.dirname(ADDON_DIR))       # .../assets/world_source
LIB_DIR = os.path.join(WORLD_SOURCE, "lib")
KIT_BLEND = os.path.join(WORLD_SOURCE, "kit", "lane_kit.blend")
CURB_KIT_BLEND = os.path.join(WORLD_SOURCE, "kit", "curb_kit.blend")

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import kit_common as kc  # noqa: E402  (import after sys.path setup above)
