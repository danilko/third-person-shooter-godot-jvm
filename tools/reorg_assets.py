#!/usr/bin/env python3
"""PLAN.md 3.9 -- restructure `assets/` by domain, with every modular kit in one place.

ONE path map (`MOVES`), in the `tools/reorg_stage1.py` / `reorg_stage2.py` idiom:

  1. `git mv` every tracked file under each old path to its new one (`.import` sidecars move WITH their
     source, so a resource keeps its uid and every `uid://` reference survives the move);
  2. rewrite every text reference to an old path in tracked text files (not archive/, not binaries);
  3. rewrite the split `os.path.join(..., "assets", "world_source", "kit", ...)` forms, which a plain path
     substitution cannot see (`JOIN_EDITS`).

What this script does NOT do, because it is not text: a `.blend`'s relative library links
(`tools/relink_blends.py` fixes those) and Godot's binary `.scn` scenes (re-derived by rebuilding the pieces).
Run with `--dry-run` first; it prints every file it would touch. Idempotent: an old path already gone is skipped.
"""
import os
import re
import subprocess
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

#: old path prefix -> new path prefix (repo-relative). A prefix ending in "/" is a directory; the character's
#: one is a FILE-NAME prefix (merged_animation.blend, merged_animation_f.glb, merged_animation_face.png, ...).
MOVES = [
    ("assets/merged_animation", "assets/characters/godot_chan/merged_animation"),
    ("assets/textures/", "assets/characters/godot_chan/textures/"),
    ("assets/world_source/kit/", "assets/world_source/kits/road_kit/"),
]

#: The same moves as they appear split across `os.path.join` arguments.
JOIN_EDITS = [
    ('"assets", "world_source", "kit"', '"assets", "world_source", "kits", "road_kit"'),
    ('(WORLD_SOURCE, "kit",', '(WORLD_SOURCE, "kits", "road_kit",'),
    ('"assets", "merged_animation', '"assets", "characters", "godot_chan", "merged_animation'),
]

TEXT_EXT = {".py", ".gd", ".sh", ".java", ".kt", ".kts", ".tscn", ".tres", ".json", ".md", ".import", ".cfg",
            ".txt", ".godot", ".gitattributes", ".gitignore", ".uid"}
SKIP_PREFIXES = ("archive/", "demo/", "addons/sky_3d/", "addons/terrain_3d/", "addons/jvm/")


def _pattern(old):
    # a path START: preceded by `res://`, or by nothing that could make it the tail of a longer path
    # (`demo/assets/textures/` and `addons/sky_3d/assets/textures/` are someone else's).
    return re.compile(r"(?:(?<=res://)|(?<![\w/.\-]))" + re.escape(old))


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def moves_for(files):
    plan = []
    for old, new in MOVES:
        for f in files:
            if f.startswith(old):
                plan.append((f, new + f[len(old):]))
    return plan


def is_text(path):
    base = os.path.basename(path)
    return os.path.splitext(base)[1] in TEXT_EXT or base in (".gitattributes", ".gitignore")


def rewrite(text):
    for old, new in MOVES:
        text = _pattern(old).sub(new, text)
    for old, new in JOIN_EDITS:
        text = text.replace(old, new)
    return text


def main(argv):
    dry = "--dry-run" in argv
    files = tracked()
    plan = moves_for(files)
    for src, dst in plan:
        print("mv  %s -> %s" % (src, dst))
        if not dry:
            os.makedirs(os.path.join(REPO, os.path.dirname(dst)), exist_ok=True)
            subprocess.run(["git", "mv", src, dst], cwd=REPO, check=True)
    files = tracked()
    touched = 0
    for f in files:
        if f.startswith(SKIP_PREFIXES) or not is_text(f) or f == "tools/reorg_assets.py":
            continue
        path = os.path.join(REPO, f)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        new = rewrite(text)
        if new != text:
            touched += 1
            print("ref %s" % f)
            if not dry:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new)
    print("%d moved, %d files rewritten%s" % (len(plan), touched, " (dry run)" if dry else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
