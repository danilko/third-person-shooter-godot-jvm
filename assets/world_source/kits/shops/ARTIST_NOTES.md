# Shop kit -- notes for the artist

One `.blend` per store type, each holding ONE piece, `<Id>_Interior` (everything inside the walls):

* `Shop_KonbiniS.blend` -- the small konbini (12.7 x 18.2 m): one accessible restroom (customers and staff) at the
  back left; the walk-in cooler ROOM across the back middle (the drink doors are its front, open at the back; a
  stock shelf and a freezer inside; a hinged door from the staff room); the staff room, and the staff aisle behind
  its own hinged door with the staff exit at its end; the counter with 2 coffee machines and 2 hot cases, the
  cigarette wall behind it; open bento cases and the upright freezer on the left wall; a one-seat eat-in counter;
  outside, the sorted bins and 2 vending machines.
* `Shop_KonbiniL.blend` -- the large konbini (21.8 m square): locker room, manager's office and a staff accessible
  restroom, all opening into the closed staff aisle (which runs the whole staff block, a hinged door onto the counter
  floor at its front, the staff exit at its back end); the counter with two registers; the customer
  accessible restroom back left, the walk-in cooler ROOM behind ten drink doors, the store room with the delivery
  door; open bento cases along the back and the aisle wall, a self-serve row (coffee station with 2 machines, hot
  cases), the cigarette wall, a 3-seat eat-in counter, the bin station; 3 vending machines outside.
* `Shop_FamilyRestaurant.blend` -- YOUR hand layout (2026-09-28), kept: the kitchen across the back-left (4 grills,
  4 fryers, 3 prep islands, 3 sinks, fridges), the pass window over the service counter with a swing door beside it
  onto the service floor, the walk-in COOLER / supply room behind the kitchen, the manager's office (safe), staff room
  and staff accessible restroom off the STAFF AISLE -- which is also the delivery corridor: the back door opens into
  the aisle and the corridor behind the kitchen and cooler, never into the kitchen (the kitchen has its own swing door
  onto that corridor); two customer accessible restrooms, the bin station, meal-ticket machines + ATM. The building's
  side walls along the kitchen, the back of house and the restrooms are SOLID (`building_types.json` `modules_rows`),
  the dining room keeps its glass.
* `Shop_Supermarket.blend` -- the food supermarket (食品スーパー, 32.8 x 40 m), a konbini and a kitchen in one: the
  sales floor (produce along the left wall, six gondola runs, a frozen island, dairy / drinks open cases on the right
  wall, the deli counters fed through the deli kitchen's pass windows, meat & fish open cases, six checkout lanes and
  bagging tables, the konbini corner -- service counter with two registers, hot snacks, coffee, ATM, copier, an eat-in
  counter along the glass -- and two customer accessible restrooms by the left entrance); the BACKYARD (バックヤード):
  receiving (荷受け) at the two delivery doors, the back corridor to every room, the walk-in cooler behind the drink
  doors, the freezer, meat & fish prep, the deli kitchen where the food is made, and the staff block (office with the
  safe, lockers, staff accessible restroom) off the STAFF AISLE with its own exit. The loading yard (荷捌き場: a truck at
  a covered dock, roll cages, pallets) is the `SupermarketSite` composite in `building_types.json`.
* New fittings (checkout lane, bagging table, produce table, cart row, deli counter, roll cage ...) are library
  PLACEHOLDERS (`blender/tools/library_interiors.py`, listed in `kits/library/PIECES.md`): replace them in
  `library.blend`.

The shell -- outer walls, shopfront glass, roof, the street entrance and the outer back/side doors -- is NOT in these
files: it is the downtown kit's modules, laid by `tools/building_kit/layout_buildings.py` from `building_types.json`.
The `Reference (not exported)` collection draws it (wire boxes; arrows at its outer doors) so you edit against the real
walls. It is never exported; do not add to it.

## What you may change freely
Move, add, delete or re-model any object; use any library palette material name (`MI_*`). Library pieces arrive as
copies of the library mesh, shared inside this file: `Object > Relations > Make Single User` before changing one.

## What the game assumes -- keep these
* **The frame:** the footprint centre on the floor is the origin; the STREET (front) is -Y, the back +Y, right +X.
* **COL_ Empties** (cubes) are the colliders: location = box centre, scale = half size. Every solid thing you add
  needs one; move/scale them with what they stand for. A decoration with no COL_ is walked through.
* **DOOR_ Empties** (single arrows on the floor at a doorway's centre) are the interior doors, built by the game
  (`world.Door`). The arrow points OUT of the room. Props: `w`, `h` (the opening), `style` -- `swing` (a hinged door:
  store rooms, staff rooms, offices) or `slide` (a SOLID sliding door: every restroom) -- and `slide_dir` (+1 / -1:
  the leaf runs to the RIGHT / LEFT seen from where the arrow points). The wall must continue on that side for the
  leaf's width, and the leaf hangs on the arrow's side of the wall. The hole itself is the wall piece's
  (`Wall_PartitionDoor` 0.85 m, `Wall_PartitionDoorWide` 1.0 m for an accessible room).
* **Keep 1.2 m clear** inside every outer door and on both sides of every DOOR_ (the character's capsule is 0.7 m
  across); `layout_buildings.py` refuses a store that does not.
* An accessible restroom is at least ~2 x 2 m inside with a 1.0 m doorway.
* Things OUTSIDE the front wall (vending machines, bins) may stand at most 0.5 m past it (the forecourt is 1.5 m to
  the footway); give them COL_ boxes like anything else.
* A library piece arrives as a copy shared inside this file; appended again it brings `MI_x.001` material copies --
  harmless (the game reads `MI_x`), but `Make Single User` a mesh before editing one instance only.

## After editing
`tools/building_kit/build_buildings.sh` exports these files with the other kits, rebuilds the store scenes and runs
`probe_buildings.gd`. A regenerate (`blender/tools/build_shop_blends.py`) keeps your edited piece.
