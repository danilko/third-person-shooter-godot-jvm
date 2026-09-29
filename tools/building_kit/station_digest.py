#!/usr/bin/env python3
"""station_digest.py -- which station scenes a rebuild must remake (the sites stage's skip, like the road pieces'
DIRTY_ONLY).

    python3 tools/building_kit/station_digest.py dirty <layout.json> <dirty.json>    -> the stations to rebuild
    python3 tools/building_kit/station_digest.py record <layout.json> <id> [<id>...] -> they built and passed

A station's DIGEST hashes its own layout entry (what `station_layout.py --write` says to build: form, pieces, boxes,
doors, gates, lifts -- itself derived from the rail reserve) and every shared input the scene and its gate read: the
station kit's pieces, the library kit (the restroom fixtures are library props), the scene builder, the layout helper,
the stand probe and the runtime doors it drives. A station whose digest equals the one recorded after its last
PASSING build, and whose scene exists, is skipped: its scene and its `probe_station_paid` verdict cannot have changed.
The record is `assets/world_source/kits/stations/build.json`; commit it with the scenes.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(ROOT, "assets", "world_source", "kits", "stations", "build.json")
SCENES = os.path.join(ROOT, "src", "main", "resources", "com", "openworld", "world", "buildings")
SHARED = ["assets/world_source/kits/stations/pieces.json", "assets/world_source/kits/stations/pieces",
          "assets/world_source/kits/stations/kit.json",
          "assets/world_source/kits/library/pieces.json", "assets/world_source/kits/library/pieces",
          "assets/world_source/kits/library/materials",
          "tools/godot/build_building_scenes.gd", "tools/building_kit/layout_buildings.py",
          "tools/building_kit/station_digest.py", "tools/godot/probe_station_paid.gd",
          "src/main/java/com/openworld/world/Door.java", "src/main/java/com/openworld/world/TicketGate.java",
          "src/main/java/com/openworld/world/Elevator.java", "src/main/java/com/openworld/world/ElevatorRules.java"]


def shared_salt():
    h = hashlib.sha1()
    for rel in SHARED:
        path = os.path.join(ROOT, rel)
        files = ([os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs if not f.endswith(".import")]
                 if os.path.isdir(path) else [path])
        for f in sorted(files):
            if os.path.exists(f):
                h.update(os.path.relpath(f, ROOT).encode())
                with open(f, "rb") as fh:
                    h.update(fh.read())
    return h.hexdigest()


def digests(layout):
    salt = shared_salt()
    return {b["id"]: hashlib.sha1((salt + json.dumps(b, sort_keys=True)).encode()).hexdigest()
            for b in json.load(open(layout))["buildings"]}


def load():
    return json.load(open(MANIFEST)).get("stations", {}) if os.path.exists(MANIFEST) else {}


def main(argv):
    cmd, layout = argv[0], argv[1]
    d = digests(layout)
    if cmd == "dirty":
        done = load()
        doc = json.load(open(layout))
        keep = [b for b in doc["buildings"]
                if done.get(b["id"]) != d[b["id"]] or not os.path.exists(os.path.join(SCENES, b["id"] + "_Shop.tscn"))]
        for b in doc["buildings"]:
            if b not in keep:
                print("   clean %s -- not rebuilt" % b["id"])
        json.dump({"buildings": keep}, open(argv[2], "w"), indent=1)
        print("station_digest: %d of %d station(s) to rebuild" % (len(keep), len(doc["buildings"])))
        return 0
    if cmd == "record":
        done = load()
        for sid in argv[2:]:
            done[sid] = d[sid]
        tmp = MANIFEST + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"stations": done}, fh, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, MANIFEST)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
