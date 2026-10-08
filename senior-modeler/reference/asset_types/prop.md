# Prop (hand-held items, furniture, containers, interactables, food, tools, set dressing)

A single object the player looks at, picks up or walks past. Most common request. Hard-surface props are about clean
forms and believable construction; organic props (food, cloth, plants in pots) about soft volume and colour.

## Ask first
- Interactable (opens, breaks, is held)? -> separate moving parts with correct pivots (lid hinge, drawer slide, door
  axis), sockets/attach points, and a grip location for held items.
- How close is the camera? (first-person inspection -> more detail and texel density.)
- Variations (colour/damage/open-closed) - build them as parameters in build.py.

## Real-world sizes (sanity)
- Table 0.75 m high, chair seat 0.45 m (back 0.9 m), bed 0.45-0.55 m, counter 0.9 m, shelf depth 0.3-0.4 m,
  door handle at 1.0 m, light switch 1.2 m. Mug 0.1 m, bottle 0.25-0.3 m, book 0.23 x 0.15 m, crate 0.4-0.6 m,
  barrel 0.9 m x 0.6 m, lantern 0.25-0.4 m, chest 0.8 x 0.5 x 0.5 m.
- Stylized props are usually scaled up 10-30% so they read at distance; keep the human reference next to them.

## Construction
- Hard surface: block primary volumes with `box`/`cylinder`/`lathe`/`extrude` -> booleans or extra parts for cut-ins
  -> bevel modifier (style width) + weighted normals. Keep supporting parts (bolts, hinges, straps) as separate pieces
  that intersect the main body - games do not need watertight unions.
- Turned objects (vases, bottles, goblets, columns, chess pieces, toy bodies): `lathe()` with a profile measured from
  the concept (`concept_match.profile()`).
- Flat-cut shapes (signs, shields, blades, badges): `extrude()` from an outline.
- Organic soft props (cushions, bags, food): low-res cage + `subsurf`, or sculpt for realistic; keep volumes taut.
- Thickness everywhere (mugs, lamp shades, cloth edges): `solidify`. No single-sided surfaces on things that turn.

## Pivots and placement
- Static props: origin at the base centre, base on z = 0 (`set_origin(ob, 'base')`), front facing -Y.
- Wall props (frames, sconces): origin at the back centre touching the wall.
- Held props: origin at the grip; write the grip axis in notes.md for the animator (socket alignment).
- Moving parts: each part's origin on its hinge axis; export join=False or as separate assets.

## Budgets (tris, games)
- Tiny clutter 50-500, small prop 300-2k, medium (chair, crate) 500-4k, hero/interactive 2-10k, first-person
  inspectable 5-20k. Low poly: divide by ~5-10.

## UV and textures
- One texture set per prop (or a shared set for a family of small props). Hide seams on the bottom/back and along
  hard edges. Stack identical parts (bolts, legs) only if they never need unique wear.
- Small clutter: atlas many props into one texture, or palette/trim textures.

## Export
- SM_<Prop>.fbx, join=True, UCX convex or box collision (`collision(parts, 'convex')`), LOD1/2 for anything frequent.

## Review checklist
- Silhouette from front/side/top; close-up on joins and fasteners; scale next to the human ref; material read; wire
  for density hierarchy (big curves dense, flat areas light).
