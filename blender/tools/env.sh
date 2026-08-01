# env.sh — single place for the Blender/Godot binary paths every tools/*.sh script shells out to.
# Sourced (never executed directly) as `source "$BP/tools/env.sh"` after BP (blender)
# is computed. Update the binary here once instead of editing every build_*.sh script when Godot
# gets upgraded/reinstalled (2026-07-27, user-reported: the binary moved from the old
# version-suffixed path to a plain one after an update, and had to be fixed in 4 separate scripts).
#
# Both still honor an existing environment override (`GODOT=... tools/build_piece.sh ...`) — this
# file only supplies the DEFAULT when the caller hasn't already set one.
BLENDER="${BLENDER:-blender}"
GODOT="${GODOT:-/data/danilko/bin/godot.linuxbsd.editor.x86_64.jvm}"
