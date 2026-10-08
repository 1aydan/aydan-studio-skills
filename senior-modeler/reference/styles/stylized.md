# Stylized game art (hero shooters, MOBAs, action RPGs) - the default

Readable shapes at gameplay distance, pushed proportions, clean chunky bevels, painterly or simplified PBR surfaces.
Detail is in the big and medium forms, not in micro surface noise.

Triggers: "stylized", "game-y", "Fortnite / Overwatch / League / Sea of Thieves / Hades / WoW-like", "hand-painted",
"chunky", "readable", "hero".

## Shape language
- Big / medium / small forms in roughly 60 / 30 / 10 proportion. Every part should read in silhouette at 10-20 m.
- Push proportions 10-30% past real life: thicker handles, bigger heads, wider bases, tapered tops. Avoid parallel
  edges - taper and lean them so forms have direction ("straight vs curve", "big vs small").
- Bevels are a style feature: wide (8-12% of a part's smallest dimension, kit default 0.10, capped at 2% of asset
  size), 2 segments, arc miters. No razor edges anywhere - they alias and catch no light.
- Overlapping plates, chunky rims, exaggerated wear chips cut into the silhouette (not painted only).
- Keep the asset centred and grounded: wide stance, weight at the bottom unless it is meant to look top-heavy.

## Topology and budgets (game)
- Mid-poly: bevels in geometry + weighted normals, no high-poly bake needed for most props.
- Cylinders 12-32 sides by size (kit picks); fewer on small parts, more where the silhouette curves.
- Budgets: small prop 300-1.5k tris, hero prop / weapon 2-8k, character 8-25k, vehicle 10-40k, building piece 500-5k.

## Surfacing
- Recipe `stylized` (materials.py): top-light gradient (lighter top, darker bottom), cavity darkening (AO), edge
  highlights (bevel mask), subtle value noise. Bake with `ao_in_albedo=0.25-0.4` for a hand-painted read.
- Colour: limited palette per asset (3-5 hues + neutrals), saturated mids, controlled values (keep albedo 0.1-0.85
  sRGB). Big shapes get the strongest value contrast.
- Roughness mostly 0.5-0.8; metals 0.3-0.45 with roughness variation; avoid mirror-like surfaces.
- Texel density ~512-1024 px/m (third-person), one 1k-2k set for a hero prop. Normal maps optional (bevels already do it).

## Review focus
- Silhouette and value read first (silhouette mode + a desaturated material render), then bevel consistency
  (wire), then colour blocks.
- Pitfalls: noisy realistic detail on simple forms, inconsistent bevel widths between parts, thin parts that vanish
  at distance, everything the same size (no hierarchy).
