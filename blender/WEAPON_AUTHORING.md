# Weapon authoring — the standard

The short version: **the model IS the weapon.** It is stored at its real size, with its origin on
the grip and every transform applied, so nothing downstream — not the build, not the scene, not the
character — has to scale, rotate or move it.

| file | what it is |
|---|---|
| [`tools/weapon_models.json`](tools/weapon_models.json) | the table: each weapon's length, grip position and **real reference** |
| `assets/weapons/<id>.blend` | the weapon itself |
| `assets/weapons/WeaponLibrary.blend` | the **library** ("zoo"): every weapon + the character, side by side |
| [`tools/build_weapon.py`](tools/build_weapon.py) | proves each `.blend` conforms, exports `<id>.glb` |
| [`tools/build_weapon_library.py`](tools/build_weapon_library.py) | rebuilds the library |
| `tools/godot/probe_weapon_scale.gd`, `probe_weapon_sockets.gd` | the in-game gates |

---

## The rules

| rule | value | why |
|---|---|---|
| **scale** | 1 unit = 1 **metre**, the length of a **named real reference** | the character is metric (GodotChan: **1.49 m** to the crown, shoulder joint 1.20 m) and holds the weapon in its hand |
| **forward** | **−Z** is the muzzle / blade (Blender: **+Y**) | the character mesh is −Z forward |
| **up** | **+Y** (Blender: **+Z**) | Godot convention; exported with `export_yup=True` |
| **origin** | the **grip**: the centre of the firing hand's fist on it — pistol grip, stock wrist, knife handle | the character has ONE socket per grip archetype; the origin is what lands on it |
| **transforms** | location 0 / rotation 0 / scale 1 on every object | a surviving transform is something compensating for a wrong model |
| **collection** | all meshes in one collection named `<id>` | the library links the weapon by that name |

**On the arcade question.** The world is deliberately not 1:1 (road lanes are 4.5 m, because a car
in a book-correct lane drives like a lorry in a tunnel). That is a vehicle-scale decision and does
not reach hand props: a weapon is measured against the hand holding it. Weapons are life-size.

**On proportion.** GodotChan is petite, so a 1.0 m shotgun is two-thirds of her height — the same
proportion as a 1.17 m gun on a 1.75 m man. It will read big. If that matters, choose a shorter
*reference* (a short-barrel variant), never a scale factor: a fudge factor is exactly what the second
body (W18) would then need a different one of.

---

## Grip archetypes and sockets

The weapon says where its grip is (the origin). The character says where a hand holds a grip of
that CLASS — `SocketRifle`, `SocketPistol`, `SocketLauncher`, `SocketMelee`, `SocketFist` under
`WeaponAttachment`, and a weapon names its own in `holdSocket`. So a new rifle needs **no character
edit at all**.

**An archetype is a POSE, not a socket.** `weaponPoseIndex` picks the upper-body clip set
(`weapon_archetypes.json`, the index list is APPEND-ONLY), and two archetypes may share one socket
when the hand holds them the same way — `sniper` (index 9) shares `SocketRifle` and the `StockPoint`
mount with `rifle` and differs only in its authored aim pose. Adding one is: an index row, a `holds`
row, three placeholder clips through `character_anim_naming.json` (copies of the nearest real pose, so
the render is unchanged until they are authored) wired into all four weapon-index blendspaces in BOTH
bodies, and `probe_weapon_archetypes.gd`'s sweep extended — an index with no blend point is SILENT,
which is why that probe counts pose clusters rather than trusting the table. The per-weapon fit that genuinely differs lives on the weapon:

* `SupportPoint` — where the off hand GRIPS (`SupportHandIKModifier` puts the hand's knuckle line, 0.75 of
  the way from wrist to middle knuckle, on it and keeps the hand's authored orientation). Put it on the
  handguard / pump centre line **where the character's arm reaches with the stock shouldered**: GodotChan's
  arm (shoulder to wrist) is 0.416 m, which reaches about 0.23–0.25 m ahead of the pistol grip — the rear
  of a rifle handguard (ASR1 z −0.25, ASR2 −0.23) and the rear edge of a pump (SHG1 −0.30, still 4 cm
  short). `probe_weapon_fit.gd` asserts it per weapon. (Before 2026-09-14 this was the WRIST position.)
* A MOUNT marker, if the archetype mounts (`weapon_archetypes.json` `holds`): `StockPoint` at the butt-pad centre for
  a shouldered long gun, `ShoulderRestPoint` on the underside of a launcher tube where it rests on the shoulder.
  `StockMountIKModifier` puts the first one the weapon declares on its body anchor while aiming; a pistol declares
  none.
* **Fastest way to fit a weapon by eye** (W25): place its model in `merged_animation.blend` in the aim pose, pose the
  hands round it, then `blender -b assets/merged_animation.blend --python blender/tools/pose_weapon_hold.py -- adopt
  --hold <archetype> --placed <ID> --apply` writes the socket, the mount anchor and the `SupportPoint` that
  reproduce it; `remove-object <ID> --save` takes the model out again.
* `Muzzle` — the bore tip, exactly. It is the shot origin and the flash position; a muzzle floating
  past the barrel starts every cover test in mid-air.
* `GripPoint` — **not needed by a conforming weapon, and none of ours has one.** It is the escape
  hatch for an asset whose origin cannot be moved; `probe_weapon_sockets.gd` fails a shipped weapon
  that carries one.

---

## Where it hangs when it is holstered

A holstered weapon puts its **`holsterPoint`** on the socket, or its grip if it declares none — and
the two facts belong to different owners (W28):

* **the SLING is the character's.** How the strap crosses this body's back is one fact shared by
  every long weapon, so it lives in the socket, and the socket is SOLVED in the body's frame by
  `tools/godot/solve_holster_sockets.gd` (22° from vertical, gun flat against the back, the pair
  separated in depth) — never nudged by eye, because its authored transform is in a BONE's frame.
  The right hip is the mirror of the left.
* **the HANG POINT is the weapon's**, and only when the weapon's own proportions need it: `ATL1`'s
  grip is 0.397 m from the rear of its tube, so slung by the grip the tube stood above the
  character's crown. It declares a `HolsterPoint` 0.20 m behind the grip. No other weapon needs one.
* **a weapon's holster list is a fact about its SIZE, not its slot.** `MEW2` (a 0.81 m axe) occupies
  the MELEE slot and hangs on the BACK slings: a hip socket cannot hold it in any pose (by the grip
  its head reaches the ankle, by mid-haft it reaches the character's head).

The gate is `tools/godot/probe_weapon_holster.gd`: it holsters each weapon the game's way and
measures the poke into the character's own hitbox bones, clearance from the head and the measured
crown, ground clearance, and — for a whole loadout — that no two holstered weapons occupy each other.

---

## Finding the grip, and why the library exists

Every weapon here once had its origin wherever a centring offset left it — SHG1's sat on the
receiver, 0.48 m from the butt, and the character carried a separate socket per weapon to hide it.
The table *said* "origin = grip"; nothing measured it, and no-one had ever put two weapons side by
side. That is what the library is for.

Open `assets/weapons/WeaponLibrary.blend` (it opens on the side camera):

* every weapon's **origin sits on one vertical line** — so a grip that is not on the line is wrong;
* under each weapon, a **red bar** is the reference weapon's real overall length, rear-aligned with
  the model, and a **blue tick** is the reference's trigger position (length of pull from the butt).
  A muzzle past the bar or a trigger away from the tick is out of proportion;
* the **character** and a 1.49 m stick stand beside the line-up.

Weapons are *linked* into it, so the weapon's own `.blend` stays the one owner: edit there, reload
the library. For a stocked long gun the fist sits ~6 cm behind the trigger, so expect
grip-to-butt ≈ 0.26–0.30 m (length of pull 0.33–0.36 m minus that).

---

## Adding a weapon

1. **Pick a real reference** and look up its overall length (and length of pull for a long gun). A
   fictional weapon still gets one — it is what the size means.
2. **Model it (or bring raw art in) in `assets/weapons/<id>.blend`:**
   * raw art arrives in any scale and orientation: import it, scale it so its length matches the
     reference, rotate it so the muzzle points **+Y** in Blender, and put the 3D cursor on the grip
     (centre of the fist) → *Object ▸ Set Origin ▸ Origin to 3D Cursor* → move the object to the
     world origin → *Object ▸ Apply ▸ All Transforms*;
   * put every mesh in a collection named `<id>`. The raw file is not kept in the repo afterwards —
     the `.blend` is the source.
3. **Add a row** to `tools/weapon_models.json` → `weapons` with `length_m` (the reference's),
   `grip_to_rear_m` (origin to rearmost point, read off the model), and the `reference` block.
4. **Rebuild the library** and look at it next to the others:
   `blender -b --python blender/tools/build_weapon_library.py`
5. **Export**: `blender -b --python blender/tools/build_weapon.py -- <id>`
6. `godot --headless --path . --import` — **not optional**: Godot does not rescan imports on a
   `--headless --script` run, and a stale import reads as a behavioural bug.
7. **Scene** `src/main/resources/com/openworld/weapon/<id>.tscn`: instance `res://assets/weapons/<id>.glb`
   as a node named `Model` with **no transform**; set `holdSocket` to the archetype's socket; place
   `Muzzle` on the bore tip and `SupportPoint` under the handguard.
8. **Colliders** (below), then the gates:
   `godot --headless --path . --script tools/godot/probe_weapon_scale.gd` and
   `probe_weapon_sockets.gd`.

**A primitive placeholder** (a `BoxMesh`/`CylinderMesh` in the `.tscn`) follows the same rules: add
it under `primitives` with its `size` and the `center` of the primitive relative to the grip, so the
library draws it where the game does.

---

## Colliders

A weapon has **two** and they are not the same shape:

* **the body collider** (direct `CollisionShape3D`) — what the world pickup rests on. The model's
  bounding box, centred on the model, with **no axis thinner than 0.05 m** (we use 0.08). MEW1 shipped
  a 0.04 m box and fell to y = −59 in `World.tscn`. A pickup's collider is not its silhouette.
* **the `PickupArea` shape** — a *detection volume*, deliberately generous (≥ 0.5 m per axis).

While held, neither is in the physics world — the item is a plain `Node3D` and lends its shapes to a
`PickupBody` only while it lies in the world (W15).

---

## What the build refuses

`build_weapon.py` will not export a model that has stopped conforming, and names the rule:

* **an un-applied transform** — `'ASR1' still carries a transform (… scale (1.5, 1.5, 1.5)). Apply it
  (Object > Apply > All Transforms) — the model IS the weapon.`
* **a mesh outside the `<id>` collection** — it would be missing from the library.
* **a length that has drifted** more than 0.5% from `length_m`.
* **an origin that has left the grip** — `grip_to_rear_m` off by more than 1 cm.

All exit non-zero.

## What the gates assert

`probe_weapon_scale.gd` (reads the same JSON): the length within 2%, **the model instance transform
is identity**, the `Muzzle` is on −Z, colliders sane. `probe_weapon_sockets.gd`: **no shipped weapon
carries a `GripPoint`**, the escape hatch still lands a grip on a socket, and a socketed weapon does
not drift. One trap: a weapon added to a bare scene wraps itself in a `PickupBody` and lends it its
collision shapes — call `on_picked_up()` first, as `WeaponController` does.
