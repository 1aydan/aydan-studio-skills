# UVs and textures - conventions

UVs are ALWAYS made, even when the user wants no textures (texturing later, lightmaps, engine effects need them).

## Texture option (asked at intake)
| Option | What you deliver | Tools |
|---|---|---|
| Baked PBR textures | unique UV atlas + T_<Asset>_BaseColor / _ORM / _Normal (+ _Emissive) + M_<Asset> | uv_tools.unwrap -> materials recipes -> texture_bake.bake -> swap('baked') |
| Palette texture | one tiny swatch image, UV0 on swatches, UV1 = real unwrap | uv_tools.unwrap -> texture_bake.palette_texture |
| No textures (UVs only) | clean packed UVs + flat materials per region (M_<Asset>_<Name>) | uv_tools.unwrap + materials (flat) |

## Unwrapping
- Freeze generators first (`unwrap(freeze_first=True)` applies bevel/mirror/array/boolean...). UVs must be made on the
  exported geometry; re-run build.py to get live modifiers back.
- Seams: kit primitives mark them (caps + one hidden side line). Hide seams where the camera rarely looks: bottoms,
  backs, inside of limbs, under overlaps, along hard edges (a hard edge splits the normal anyway - put the UV seam
  there too, it costs nothing extra).
- Methods: seams -> angle-based (or minimum stretch for organic); no seams -> smart project 66 deg.
- Straighten long strips (belts, trims, cylinders) when tiling or trim textures are used.
- Average island scale, then pack ONE atlas per asset (rotate allowed). Margin: 4 px @512, 8 px @1024-2048, 16 px @4096.

## Texel density (px per metre)
| Use | px/m |
|---|---|
| Mobile / top-down | 128-256 |
| Third-person stylized | 512 |
| Third-person realistic | 1024 |
| First-person / hero close-ups | 2048 |
- `texel_density(objs, res)` reports per object + spread; keep spread < 1.5 within an asset (faces and hero areas may
  get 1.5-2x on purpose). Pick the texture size that hits the target: res ~= target_px_m / sqrt(uv_coverage / area).
- Stacked/mirrored islands save space but share every baked pixel (no unique AO/wear) - set `allow_uv_overlap`.

## Maps and packing
- BaseColor (sRGB), Normal (Non-Color, tangent space), ORM = R ambient occlusion, G roughness, B metallic (Non-Color),
  Emissive (sRGB) only when something glows. Powers of two (512-4096).
- Normal map green channel: Blender, Unity, Godot, glTF = OpenGL (+Y). Unreal = DirectX (-Y): model_export flips the
  green channel when engine='unreal' (or tick "Flip Green Channel" on import - not both).
- Bake margins (dilation) >= the UV margin so mips do not bleed: bake(margin_px=16) at 2k.
- Baked-in lighting is wrong for PBR: only AO (and it lives in ORM.R). Stylized/hand-painted may multiply AO into the
  albedo (`ao_in_albedo`), anime never.

## Naming
- Textures `T_<Asset>_<Map>.png`, materials `M_<Asset>` (baked) / `M_<Asset>_<Name>` (recipes), meshes `SM_<Asset>`,
  collision `UCX_SM_<Asset>_##`. No spaces, no `.001`.

## Reading the UV QA
- `uv_qa` errors: missing UVs, flipped islands, overlaps (unless allowed), triangles outside 0-1, atlas-spanning slivers.
- warnings: padding violations (islands closer than the margin), stretch (density off >2x from the median), low fill.
- `uv_map(objs, png, margin_px=...)`: islands coloured, overlaps red, padding problems yellow. Look at it with the
  `uv` checker render: squares must stay square and similar in size across parts.
