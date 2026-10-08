# Environment (modular kits, architecture, terrain pieces, rocks, foliage, set dressing)

Assets that BUILD a world: they repeat, tile, snap together and are seen at many distances. Consistency across the set
(grid, scale, texel density, palette) matters more than any single piece.

## Ask first
- Kit or one-off? A modular kit needs a grid and a list of pieces; a hero landmark is modelled like a big prop.
- Engine and grid: Unreal works in cm (grid 50/100/200/400 cm); Unity/Godot in m (0.5/1/2/4 m). Pick one module size
  (e.g. walls 4 m wide x 3-4 m tall) and keep EVERY piece on it.
- Player camera (first/third person, top-down) - decides texel density and how much the floor/ceiling matter.

## Modular architecture
- Pieces: wall (straight, door, window, corner in/out, end), floor tile, ceiling, stairs (rise 0.18 m, run 0.28 m),
  pillar, trim/cornice, roof pieces. Doors 1.0-1.2 x 2.1-2.4 m, windows sill ~0.9 m, ceilings 2.7-3.2 m (realistic),
  bigger for stylized/third-person (3.5-4.5 m).
- Pivots on a grid corner (bottom-left-back) so pieces snap; `set_origin(ob, (x, y, z))`. Export each piece as its
  own SM_ (export join=False or one asset per piece).
- Wall thickness real (0.2-0.3 m); hide the back face only if it is never visible. Seams between pieces align on the
  grid; bevels on piece edges must match where pieces meet (or put trims over the joins).
- Texturing: tiling materials + trim sheets (a texture with horizontal strips of mouldings/edges that many pieces
  share). UVs then map faces onto trim strips instead of a unique atlas - unique bakes do not scale for kits.
  Unique texture sets only for hero pieces. Consistent texel density across the kit (e.g. 512 px/m stylized,
  1024 px/m realistic).

## Natural: rocks, cliffs, terrain pieces
- Start from a few large planes (shape language: angular / layered / rounded per style), then medium breaks, then small
  chips. Rocks sit INTO the ground (bury 10-20%); bottoms can be open/deleted for games.
- Make 3-5 variations that read differently from every rotation (rotate/scale instances in the level).
- Stylized: big flat planes with bevelled edges + top-down colour gradient (moss/dust on top). Realistic: high-poly
  sculpt -> bake to low (`texture_bake.bake(high=[...])`), or photogrammetry cleanup.
- World-aligned top layer (moss, snow) is usually an engine shader - keep a clean UV and vertex colour channel free.

## Foliage (trees, bushes, grass)
- Trunks/branches: tubes (`tube()` with taper) or lathe; leaves as cards (alpha-tested quads with leaf clusters).
- Cards: normals pointing outward from the canopy centre (smooth, sphere-like shading) or they look flat in the
  engine; double-sided material in engine. Keep overdraw down: fewer, larger cards.
- Pivot at the trunk base, z = 0 at the ground. Wind needs vertex colour masks (trunk 0, branch tips 1) - ask.
- Budgets: grass clump 20-100 tris, bush 200-1k, tree 1-8k (+ LODs and impostor).

## Set dressing (barrels, crates, furniture outdoors)
- Treat as props (prop.md) but share the environment palette and texel density; build variants (damaged, open).

## Budgets (tris, games)
- Modular wall 50-2k, floor tile 2-500, hero building exterior 5-30k, rock 200-3k (stylized) / 2-10k (realistic),
  terrain cliff piece 2-15k. Everything with LODs when it is large or frequent.

## Export
- One piece per FBX (SM_<Kit>_<Piece>) with its grid pivot; UCX collision boxes for walls/floors; LODs for big pieces.

## Review checklist
- Snap test: place 2-3 pieces together in Blender (on the grid) and render a small vignette - seams, bevel matches,
  texture continuity. Scale next to `scale_ref='human'`.
- Texel density report across all pieces (same px/m). Silhouette of rocks from 4 angles (no "potato" sameness).
