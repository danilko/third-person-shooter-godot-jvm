"""Put the "Export to Game" button (blender/tools/game_export_ui.py) into a character .blend.

    blender -b assets/characters/shino/shino.blend --python blender/tools/install_game_export_ui.py -- --save

Writes the module as a registered text block (it loads with the file; Blender asks once to allow the
file's scripts). Re-run after editing game_export_ui.py -- the block is a copy. Idempotent.
"""
import os
import sys

import bpy

NAME = "game_export_ui.py"
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
t = bpy.data.texts.get(NAME) or bpy.data.texts.new(NAME)
t.clear()
t.write(open(src).read())
t.use_module = True
print("[install] %s written into %s (registered on load)" % (NAME, bpy.data.filepath))
if "--save" in sys.argv:
    bpy.ops.wm.save_mainfile()
    print("[install] saved")
