#!/usr/bin/env bash
# Symlinks blender/addons/road_kit_authoring into every Blender version
# directory found under the config root (covers old versions you've since upgraded past,
# in case you ever roll back or reinstall one), and headlessly enables + saves the addon
# for whichever version the installed `blender` binary actually IS (only one binary is
# normally installed, so only that one version's userpref can be written by this script —
# a leftover directory from a version you no longer have installed just gets the symlink
# and will need one manual Preferences > Add-ons > Enable the first time that version runs
# again).
#
# Why this exists: the addon is dev-installed as a symlink (see addons/road_kit_authoring/
# README.md) so edits here take effect with no reinstall. But Blender keeps addons config
# PER VERSION (~/.config/blender/<X.Y>/scripts/addons/), and a Blender upgrade creates a
# brand-new empty version directory that does NOT inherit the symlink from the old one —
# the addon silently "disappears" after `blender` updates itself, with no error, until you
# notice the Road Kit panel is gone. Re-run this script any time after a Blender update.
#
# Usage: blender/tools/install_blender_addon.sh   (run from anywhere; paths are absolute)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADDON_SRC="$REPO_ROOT/blender/addons/road_kit_authoring"
ADDON_NAME="road_kit_authoring"

if [[ ! -d "$ADDON_SRC" ]]; then
    echo "error: addon source not found at $ADDON_SRC" >&2
    exit 1
fi

CONFIG_ROOT="$HOME/.config/blender"
if [[ ! -d "$CONFIG_ROOT" ]]; then
    echo "error: no Blender config directory at $CONFIG_ROOT (has Blender been run at least once?)" >&2
    exit 1
fi

BLENDER_BIN="$(command -v blender || true)"
running_version=""
if [[ -n "$BLENDER_BIN" ]]; then
    # e.g. "Blender 5.2.0 LTS" -> "5.2"
    running_version="$("$BLENDER_BIN" --version 2>/dev/null | head -1 | grep -oP '(?<=Blender )\d+\.\d+')"
fi

found_any=0
for version_dir in "$CONFIG_ROOT"/*/; do
    version="$(basename "$version_dir")"
    # Blender version dirs look like "5.2"; skip stray non-version entries.
    [[ "$version" =~ ^[0-9]+\.[0-9]+$ ]] || continue
    found_any=1

    addons_dir="$version_dir/scripts/addons"
    mkdir -p "$addons_dir"
    link_path="$addons_dir/$ADDON_NAME"

    if [[ -L "$link_path" ]]; then
        # readlink -f fails (under set -e, aborting the whole run) if the symlink's target
        # directory no longer exists -- exactly the case right after this addon's own source
        # directory gets moved (e.g. this repo's assets/world_source/addons -> blender/addons
        # migration). Tolerate that as "definitely stale", not a fatal error.
        current_target="$(readlink -f "$link_path" 2>/dev/null || true)"
        if [[ -n "$current_target" && "$current_target" == "$ADDON_SRC" ]]; then
            echo "[$version] already linked -> $ADDON_SRC"
        else
            echo "[$version] relinking (was -> $current_target)"
            rm "$link_path"
            ln -s "$ADDON_SRC" "$link_path"
        fi
    elif [[ -e "$link_path" ]]; then
        echo "[$version] skip: $link_path exists and is not a symlink (real addon copy?) — leaving it alone" >&2
        continue
    else
        echo "[$version] linking -> $ADDON_SRC"
        ln -s "$ADDON_SRC" "$link_path"
    fi

    # Headless enable only works for the version the installed binary actually IS —
    # `blender --background` always writes to ITS OWN version's userpref, so this would
    # silently mis-target a stale/other version directory otherwise.
    if [[ -n "$running_version" && "$version" == "$running_version" ]]; then
        "$BLENDER_BIN" --background --python-expr "
import bpy
try:
    bpy.ops.preferences.addon_enable(module='$ADDON_NAME')
    bpy.ops.wm.save_userpref()
    print('[$version] enabled + saved userpref')
except Exception as e:
    print('[$version] enable failed:', e)
" 2>&1 | grep -E "^\[$version\]" || echo "[$version] warning: headless enable failed (enable manually in Preferences > Add-ons)"
    else
        echo "[$version] symlinked only (no matching installed binary to enable it with) — enable manually in Preferences > Add-ons the first time this version runs"
    fi
done

if [[ "$found_any" -eq 0 ]]; then
    echo "error: no version directories found under $CONFIG_ROOT" >&2
    exit 1
fi

echo "Done. Verify: Edit > Preferences > Add-ons > search \"Road Kit Authoring\"."
