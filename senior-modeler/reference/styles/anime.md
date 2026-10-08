# Anime / cel-shaded (Genshin, Zelda BotW, Guilty Gear, Honkai)

Designed for a toon shader: flat colour regions, crisp shadow terminators, outlines. Geometry must produce CLEAN
shading - the normals are part of the art.

Triggers: "anime", "cel-shaded", "toon shaded", "Genshin / Honkai / Guilty Gear / BotW-like", "manga", "outline".

## Shape language
- Clean graphic shapes and long elegant lines; detail goes into silhouette and colour regions, not surface noise.
- Hard surface: small bevels (kit default 6%), crisp creases where the shadow line should break.
- Characters: large eyes as separate geometry or texture, simplified nose (a point), hair as clumped ribbons/cards
  with clear strand shapes and tips; clothing folds only where they read as graphic shapes.

## Shading (the important part)
- Smooth normals matter more than geometry: faces should shade like a sphere or cylinder. Use a DataTransfer modifier
  (custom normals from a sphere/proxy) on faces and hair, keep it live until export.
- Mark sharp edges where a cel line should be crisp (clothing hems, armour edges).
- Outlines: inverted hull (duplicate, Solidify with flipped normals ~0.5-1% of size, backface-culled dark material)
  or the engine's outline pass - ask which; inverted hull doubles triangles.

## Topology and budgets
- Character 15-40k tris, hair separate; props 500-6k. Even, flowing quads on faces (no stray poles in the cheeks).

## Surfacing
- Recipe `toon` (materials.py) previews cel shading; the baked texture is FLAT albedo (no AO, no lighting) plus
  optional shadow-tint / ramp textures the shader uses. Bake with `maps=('BaseColor',)` and `ao_in_albedo=0`.
- Palette: flat fills, 1-2 shadow tones per material, limited texture detail (lineart can be painted in albedo).

## Review focus
- Toon-shaded material render from front/side/3q under the review lights; watch the shadow terminator for kinks.
- Pitfalls: noisy normals on faces, AO baked into albedo, too much micro-detail, outlines too thick on small parts.
