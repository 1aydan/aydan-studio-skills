# Realistic / PBR (AAA realism, sims, tactical shooters, archviz, product)

Real measurements, physically plausible materials, detail that holds up close. The audience compares it to photos, so
wrong scale, perfect edges and uniform surfaces read as fake.

Triggers: "realistic", "photoreal", "PBR", "AAA", "real-world", "archviz", "product shot", "tactical", "sim".

## Shape and accuracy
- Model from real dimensions (asset_types/*.md has the common ones). Get the scale right first: a chair seat is
  ~0.45 m, a door 0.9 x 2.1 m, a pistol grip ~0.11 m.
- Edges: small bevels (1-5 mm on hard surfaces, kit default 3% of the part, capped at 0.4% of asset size), 2-3
  segments, harden normals / weighted normals. Nothing is perfectly sharp in reality.
- Manufacturing logic: parts are cast, machined, welded, stitched or bolted - show seams, fasteners, draft angles,
  panel gaps (2-5 mm), thickness on every shell (no zero-thickness sheet metal).
- Asymmetry and imperfection come from use: dents, sag, chipped paint - placed where hands, feet and weather touch.

## Topology and budgets
- Game: mid-poly with weighted normals for chunky hard surface; high-to-low baking (`texture_bake.bake(high=[...])`)
  for dense detail (stitching, vents, engraving). Floaters on the high-poly for bolts and panel lines are fine.
- Cylinders 16-64 sides by size; silhouette curves need density, flat caps do not.
- Budgets (current-gen): prop 1-10k tris, hero weapon 10-40k, character 40-100k, vehicle 50-150k, building 5-50k.
  Render/archviz: no budget, but subdivision-ready topology (quads, supporting loops).

## Surfacing
- Recipe `pbr` (materials.py): roughness breakup, edge wear (bevel mask x noise), cavity dirt (AO). Metals:
  metallic 1, albedo 0.5-1.0 (sRGB ~180-255); dielectrics albedo sRGB 30-240, never pure black or white.
- Roughness variation is what makes it read real: fingerprints, scratches, wear on contact areas.
- Texel density: 1024 px/m third-person, 2048 px/m first-person / close-up; keep it consistent between assets in a
  scene (`uv_tools.texel_density`). Use tiling materials / trim sheets on large surfaces (asset_types/environment.md).
- Bake: `ao_in_albedo=0` (AO goes in the ORM red channel only).

## Review focus
- Material renders against a neutral environment, then close-ups of edges and contact points, then scale next to the
  human reference (`setup(scale_ref='human')`).
- Pitfalls: razor-sharp edges, uniform roughness, too-clean surfaces, wrong scale, stretched textures, texel density
  jumps between parts.
