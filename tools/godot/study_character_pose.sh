#!/usr/bin/env bash
# Measure a character .blend's poses WITHOUT touching the shipped export (PLAN.md A2.0).
#
#   tools/godot/study_character_pose.sh [<blend>] [-- <probe args>]
#
# Default blend: assets/characters/godot_chan/merged_animation.blend. Steps: scratch copy of the blend -> export_character.py
# -> assets/_study/ copies of merged_animation.tscn and CharacterVisuals_GodotChan.tscn re-pointed at
# the scratch export -> `godot --import` -> probe_pose_clip.gd (the clip on a bare AnimationPlayer, no
# tree, no modifiers) -> probe_weapon_fit.gd (through today's rig) -> delete assets/_study/.
#
# KEEP=1 leaves assets/_study/ in place (and prints the visuals path) for further probes.
# The shipped merged_animation.glb is never written: export_character.py derives its output from the
# blend it exports, so the scratch copy exports to assets/_study/merged_animation_study.glb.
#
# Two traps the recipe exists to avoid: a copied scene keeps the `uid=` of the resource it copied, and a
# stale uid wins over the path (the copy silently loads the SHIPPED clip) -- so the header uid and every
# re-pointed ext_resource uid are stripped; and Godot never rescans imports on a --script run, so the
# --import step is not optional.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
source blender/tools/env.sh

BLEND="assets/characters/godot_chan/merged_animation.blend"
if [[ $# -gt 0 && "$1" != "--" ]]; then BLEND="$1"; shift; fi
[[ "${1:-}" == "--" ]] && shift
PROBE_ARGS=("$@")

STUDY=assets/_study
VIS_SRC=src/main/resources/com/openworld/character/CharacterVisuals_GodotChan.tscn
cleanup() { if [[ "${KEEP:-0}" != 1 ]]; then rm -rf "$STUDY"; fi; }
trap cleanup EXIT

rm -rf "$STUDY"; mkdir -p "$STUDY"
cp "$BLEND" "$STUDY/merged_animation_study.blend"
echo "== study of $BLEND (mtime $(date -r "$BLEND" '+%F %T'), sha1 $(sha1sum "$BLEND" | cut -c1-12))"

"$BLENDER" -b "$STUDY/merged_animation_study.blend" --python-exit-code 1 \
    --python blender/tools/export_character.py > "$STUDY/export.log" 2>&1 \
    || { tail -30 "$STUDY/export.log"; exit 1; }
grep '\[export_character\] wrote' "$STUDY/export.log"

# merged_animation.tscn -> points at the study glb; header uid and the glb ext_resource uid stripped.
sed -e '1s/ uid="[^"]*"//' \
    -e 's#\[ext_resource type="PackedScene" uid="[^"]*" path="res://assets/characters/godot_chan/merged_animation.glb"#[ext_resource type="PackedScene" path="res://assets/_study/merged_animation_study.glb"#' \
    assets/characters/godot_chan/merged_animation.tscn > "$STUDY/merged_animation_study.tscn"
sed -e '1s/ uid="[^"]*"//' \
    -e 's#\[ext_resource type="PackedScene" uid="[^"]*" path="res://assets/characters/godot_chan/merged_animation.tscn"#[ext_resource type="PackedScene" path="res://assets/_study/merged_animation_study.tscn"#' \
    "$VIS_SRC" > "$STUDY/CharacterVisuals_Study.tscn"
grep -q '_study/merged_animation_study.glb' "$STUDY/merged_animation_study.tscn"
grep -q '_study/merged_animation_study.tscn' "$STUDY/CharacterVisuals_Study.tscn"

timeout -k 5 600 "$GODOT" --headless --path . --import > "$STUDY/import.log" 2>&1 || true
[[ -f "$STUDY/merged_animation_study.glb.import" ]] || { tail -30 "$STUDY/import.log"; exit 1; }

VIS="res://$STUDY/CharacterVisuals_Study.tscn"
echo; echo "== clip truth (bare AnimationPlayer)"
timeout -k 5 300 stdbuf -oL "$GODOT" --headless --fixed-fps 60 --path . \
    --script tools/godot/probe_pose_clip.gd -- --visuals="$VIS" "${PROBE_ARGS[@]}" 2>&1 \
    | grep -v '^\(Godot Engine\|Vulkan\|WARNING: \|     at: \)' || true
echo; echo "== through today's rig (probe_weapon_fit)"
timeout -k 5 300 stdbuf -oL "$GODOT" --headless --fixed-fps 60 --path . \
    --script tools/godot/probe_weapon_fit.gd -- --visuals="$VIS" 2>&1 \
    | grep -E '^(  |===|visuals|PASS|FAIL)' || true
[[ "${KEEP:-0}" == 1 ]] && echo "kept: $VIS"
