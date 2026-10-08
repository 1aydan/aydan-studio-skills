# Low poly / faceted (Synty-like, mobile, indie, flat-shaded)

Every polygon is visible and deliberate. Flat-shaded facets, simple flat colours, strong silhouettes from very few
triangles. The style lives or dies on facet consistency and palette.

Triggers: "low poly", "lowpoly", "faceted", "flat shaded", "polygonal", "Synty", "mobile", "minimal".

## Shape language
- Silhouette from the fewest planes possible; use the triangle count where the outline needs it, nowhere else.
- Consistent facet size across the asset - a dense part next to a crude part looks like two styles.
- Cylinders 5-10 sides (kit 6-12), spheres as icospheres or 8x5 UV spheres; no bevels (or 1 segment chamfer on the
  biggest edges only). Kit style `low_poly` sets flat shading and zero bevel.
- Slight randomness on organic things (rocks, trees, terrain): move a few verts, rotate facets - never noise.

## Topology and budgets
- Triangles are fine; n-gons are not (they triangulate unpredictably). No hidden interior faces.
- Budgets: small prop 50-300 tris, large prop 300-1.5k, character 500-3k, vehicle 500-3k, building 200-2k, tree 100-600.

## Surfacing
- Textures option "palette": `texture_bake.palette_texture()` makes one small swatch image per asset (or a shared
  project palette) and collapses every face's UVs onto its colour; the real unwrap stays in UV1 (`UV_Unwrap`) for
  lightmaps. Many assets can share one palette image and one material - great for draw calls.
- Or vertex colours / flat materials if the user says no textures (UVs are still unwrapped).
- 8-24 colours for a whole set; vary value more than hue; gradients only through face colour steps.
- Flat shading in engine: export with face smoothing (the exporter writes the split normals).

## Review focus
- Silhouette sheet + parts render (facet sizes), then palette render. QA warns on smooth shading.
- Pitfalls: accidental smooth shading, inconsistent density, bevels, noise textures, too many colours.
