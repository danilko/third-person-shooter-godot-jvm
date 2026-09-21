#!/usr/bin/env bash
# Measure a character .blend's poses WITHOUT touching the shipped export (PLAN.md A2.0).
#
#   tools/godot/study_character_pose.sh [<blend>] [-- <probe args>]
#
# Default blend: assets/characters/shino/shino.blend -- the clip owner and the body the game ships.
# Steps: scratch copy of the blend -> export_character.py -> an assets/_study/ copy of that body's
# CharacterVisuals scene re-pointed at the scratch export -> `godot --import` -> probe_pose_clip.gd
# (the clip on a bare AnimationPlayer, no tree, no modifiers) -> probe_weapon_fit.gd (through
# today's rig) -> delete assets/_study/.
#
# KEEP=1 leaves assets/_study/ in place (and prints the visuals path) for further probes.
# The shipped .glb is never written: export_character.py derives its output from the blend it
# exports, so the scratch copy exports to assets/_study/<stem>_study.glb.
#
# THE VISUALS SCENE IS FOUND BY WHAT IT INSTANCES, not by a table: a generated body scene
# (build_character_visuals.gd) ext_resources its body's `.glb` directly, so the scene to copy is the
# one naming this blend's export. That is one fact, read where it lives, and it is why adding a body
# needs no edit here.
#
# Two traps the recipe exists to avoid: a copied scene keeps the `uid=` of the resource it copied,
# and a stale uid wins over the path (the copy silently loads the SHIPPED clip) -- so the header uid
# and the re-pointed ext_resource uid are stripped; and Godot never rescans imports on a --script
# run, so the --import step is not optional.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
source blender/tools/env.sh

BLEND="assets/characters/shino/shino.blend"
if [[ $# -gt 0 && "$1" != "--" ]]; then BLEND="$1"; shift; fi
[[ "${1:-}" == "--" ]] && shift
PROBE_ARGS=("$@")

STEM="$(basename "$BLEND" .blend)"
GLB_REL="$(dirname "$BLEND")/$STEM.glb"
STUDY=assets/_study
# The scene that instances this body's export. One match, or say which ones matched.
mapfile -t VIS_HITS < <(grep -l "path=\"res://$GLB_REL\"" src/main/resources/com/openworld/character/CharacterVisuals_*.tscn || true)
if [[ ${#VIS_HITS[@]} -ne 1 ]]; then
    echo "study_character_pose: expected exactly one CharacterVisuals_*.tscn instancing res://$GLB_REL, found ${#VIS_HITS[@]}: ${VIS_HITS[*]:-none}" >&2
    exit 1
fi
VIS_SRC="${VIS_HITS[0]}"
cleanup() { if [[ "${KEEP:-0}" != 1 ]]; then rm -rf "$STUDY"; fi; }
trap cleanup EXIT

rm -rf "$STUDY"; mkdir -p "$STUDY"
cp "$BLEND" "$STUDY/${STEM}_study.blend"
echo "== study of $BLEND (mtime $(date -r "$BLEND" '+%F %T'), sha1 $(sha1sum "$BLEND" | cut -c1-12))"
echo "== visuals  $VIS_SRC"

"$BLENDER" -b "$STUDY/${STEM}_study.blend" --python-exit-code 1 \
    --python blender/tools/export_character.py > "$STUDY/export.log" 2>&1 \
    || { tail -30 "$STUDY/export.log"; exit 1; }
grep '\[export_character\] wrote' "$STUDY/export.log"

sed -e '1s/ uid="[^"]*"//' \
    -e "s#\\[ext_resource type=\"PackedScene\"\\( uid=\"[^\"]*\"\\)\\? path=\"res://$GLB_REL\"#[ext_resource type=\"PackedScene\" path=\"res://$STUDY/${STEM}_study.glb\"#" \
    "$VIS_SRC" > "$STUDY/CharacterVisuals_Study.tscn"
grep -q "_study/${STEM}_study.glb" "$STUDY/CharacterVisuals_Study.tscn"

timeout -k 5 600 "$GODOT" --headless --path . --import > "$STUDY/import.log" 2>&1 || true
[[ -f "$STUDY/${STEM}_study.glb.import" ]] || { tail -30 "$STUDY/import.log"; exit 1; }

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
