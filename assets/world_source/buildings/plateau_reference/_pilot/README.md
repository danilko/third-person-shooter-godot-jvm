# PLATEAU texture-extraction pilot (2026-08-08)

One real building, real LOD2 geometry + real embedded facade JPEG texture, pulled directly from
raw CityGML (not the old geometry-only `extract_plateau.py` JSON pipeline, which never carried
textures — see chat/plan history). Proves the pipeline before scaling to the full landmark +
per-district sample list.

- Source: `13100_tokyo23-ku_2022_citygml_1_2_op/udx/bldg/53392633_bldg_6697_2_op.gml`,
  building `bldg_bdc161ef-9ae3-4a6c-b554-8a2ce507e6c8` — picked by ranking every building in a
  handful of candidate files by *textured-facade-area fraction* (53.5% of this one's real area is
  textured — 130/151 polygons), not just "has any texture," which the first, unranked attempt
  showed matters a lot (that one landed on a building only ~5% textured, mostly flat fallback grey).
- `PLATEAU_pilot_bdc161ef.blend` — the extracted building, real texture image packed into the
  `.blend` (portable, no external file dependency). `PLATEAU_pilot_bdc161ef_preview.png` — a
  render for a quick look without opening Blender.
- **Real finding, worth knowing before extracting more:** PLATEAU's LOD2 appearance data is a
  **texture atlas of small oblique-aerial photo crops**, one irregular crop per wall/roof facet,
  packed together with grey "no capture" padding — not a clean rectified facade photo. On a tall
  narrow face the crop can look stretched/smeared (visible in the preview). It's genuinely useful
  as *real material/color reference* (this building's actual rust-orange + glass tones) but is
  low-resolution and geometrically imprecise per facet — exactly the "reference to manually
  extract clean materials from," not a source to use verbatim, which matches the plan already
  discussed rather than being a problem the plan needs to work around.

Next step (not yet done): write a proper `blender/tools/extract_plateau_textures.py` using this
same approach + the area-ratio ranking heuristic, and run it across the full landmark + per-theme
sample list.
