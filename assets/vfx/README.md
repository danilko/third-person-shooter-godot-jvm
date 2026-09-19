# assets/vfx — explosions, muzzle flashes, smoke, water

Four CC0 packs by Binbun3D (sources and licence: `LICENSE.txt`, credited in `CREDITS.md`), re-organised
into one tree, with the packs' GDScript controllers rewritten in Java (`com.openworld.vfx`). Nothing here
runs GDScript.

```
explosion/     effects/{air,burst,ground,nuke}/vfx_*_explosion_NN.tscn   root script VfxEffect
               shader/*.gdshader
muzzle_flash/  effects/{muzzle_flash,short_flash,big_flash,wide_flash}/*_NN.tscn   root MuzzleFlashVfx
               material/flash_NN/*.tres   shader/{base,glow}.gdshader   texture/flash_{front,long,side}/
smoke/         effects/{smoke,smoke_thin,smoke_big}/*_vfx_NN.tscn   root SmokeVfx
               material/   shader/smoke.gdshader (+ util/*.gdshaderinc)   texture/ (noise)
water/         water.gdshader (PBR + caustics)  water_toon.gdshader (stylized; the world's sea)
               water_common.gdshaderinc (the body both include)  material/  texture/
```

Every effect variant of each pack is kept as a catalogue to pick from; what each scene needs is kept
beside it.

## Who plays what

| effect | where | Java |
|---|---|---|
| blast | each explosive names its own `explosion_vfx`: rocket `ground_01` (`ATL1Projectile.tscn`), grenade `ground_03` (`FRG1Projectile.tscn`, `FRG1.tscn`), destroyed vehicle `burst_01` (each vehicle's `VehicleConfig`); anything else `ExplosionManager.explosion_scene`. SIZED FROM THE DAMAGE RADIUS: fireball over half of it, shockwave out to all of it, from each effect's measured `fireball_radius` / `blast_radius` (`tools/godot/measure_explosion_radii.gd`) | `ExplosionManager.playBlast` → `VfxEffect.play()`, one pool per effect |
| muzzle flash | each weapon scene's `Muzzle/MuzzleVFX` (rifles `muzzle_flash_01`, SMG/pistol `short_flash_01`, revolver/sniper/launcher `big_flash_01`, shotgun `wide_flash_01`) | `WeaponItem.playMuzzleFlash()` on every shot, owner and puppet |
| smoke | `Vehicle.tscn` `DamageVfx/Smoke` (smoke_thin_01), `VehicleWreck.tscn` `Smoke` (smoke_big_01) | `SmokeVfx.setEmitting` from the vehicle's damage tier; a wreck stays on |
| water | `World.tscn`, `DebugWorld.tscn` sea material | shader only |

To use another variant, point the scene at a different file under `effects/`: every variant of a kind
has the same node layout and the same script.

## What changed from the packs

- **The GDScript is gone.** `VFXControllerBB`/`vfx_controller.gd` → `VfxEffect` (play the `main`
  animation from the top, restart the particles) and `MuzzleFlashVfx`; `vfx_light.gd`/`VFXOmniLightBB.gd`
  → `VfxLight` (energy = base × `light_multiplier`, one name where the packs used two); `vfx_smoke_controller.gd`
  → `SmokeVfx`. `VFXEmitterBB.gd` was used by no scene.
- **Root properties that only ever ran in the editor were removed.** The packs' `@tool` setters push a
  root colour into the child materials, but at load the children do not exist yet, so in a game they did
  nothing: what renders is what the materials hold. For explosions and smoke the materials already held the
  root values (checked value by value when this tree was built — one exception, `vfx_air_explosion_01`,
  whose sphere material has emission 3.0 against a root 4.0, and 3.0 is what always rendered), so the root
  properties were dropped. Muzzle flashes are the exception: several variants SHARE a `.tres` with
  different colours and animate its glow alpha, so `MuzzleFlashVfx` copies its materials per instance and
  writes its own `primary_color`/`secondary_color`/light settings into them.
- **Explosion particles are in local space** (`local_coords = true`): in world space they ignored their node's
  scale, so a blast could not be sized. An explosion does not move while it plays, so nothing is lost.
- **One-shot, not looping.** The explosions' `main` animation looped (the packs' editor preview); a blast
  in the game plays once. Nothing autoplays: the caller decides when.
- **Muzzle flashes point down −Z**, the `Muzzle` marker's forward (the pack pointed them down +X), so a
  flash instance carries no transform.
- **`smoke_amount = 0`** on the two `_00` explosions meant "no smoke"; their `Smoke` emitter was already
  hidden, and its amount is 1 (0 is not a legal particle count).
- **Water:** the pack's two shaders differed only in their `#define`s. Both are now define-only files over
  `water_common.gdshaderinc`, which carries this project's distance LOD (far wave/foam layers, mipmapped
  anisotropic sampling; it replaced `world/water.gdshader`, which was the toon variant plus that fix).
- **Removed as unused:** demo scenes, the demo HDR/Suzanne/duck, Material Maker `.ptex` sources, a
  `.blend1`/`.xcf`, preview images, a duplicate `placeholder.png`, and every texture/material no kept
  effect or water material references. The originals are on the itch.io pages in `LICENSE.txt`.

## Gates

- `tools/godot/probe_vfx.gd` (headless): every effect on its Java script and no `.gd` left, flashes on −Z,
  a flash lights and goes dark with per-instance materials, every weapon's flash out of its barrel,
  `ExplosionManager` pooling and reuse, smoke on/off, and the game scenes' wiring.
- `tools/godot/shot_vfx.gd -- <dir>` (needs a display): screenshots of four weapons firing, a blast and both
  plumes beside a 1.49 m figure.
