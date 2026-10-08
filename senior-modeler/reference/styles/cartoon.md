# Cartoon / toy (Pixar-like, Nintendo, Animal Crossing, party games, vinyl toys)

Soft, rounded, appealing. Everything looks squeezable or carved from a single smooth material. Big simple shapes,
exaggerated proportions, almost no small detail.

Triggers: "cartoony", "toon", "cute", "chibi", "toy", "Pixar / Animal Crossing / Mario-like", "bubbly", "chunky", "kid".

## Shape language
- Exaggerate the defining proportion hard (big heads, tiny feet, huge hands, fat handles). Pinch and swell: forms bulge
  in the middle and taper at the ends; avoid straight parallel sides.
- Rounded everything: wide bevels (kit default 22% of the smallest dimension, 4 segments) or subdivision
  (`subsurf(ob, 1-2)` on simple cages). No sharp corners, no thin parts (minimum thickness ~5% of asset size).
- Simple primitives assembled with clear overlaps read as "toy". Wooden toys: lathe-turned shapes, flat-cut
  profiles, painted (not textured) details, visible joints between parts.
- Faces: big eyes low on the head, simple shapes for features (dots, ovals, cones), cheeks as discs.

## Topology and budgets
- Smooth, even quads; subdivision-friendly if it will subdivide. Character 5-20k, prop 500-4k (games).
- Cylinders 16-48 sides; silhouettes must look round from every angle.

## Surfacing
- Recipe `stylized` with low noise (0.02-0.04), strong top light (0.2-0.25), soft cavity (0.25); or flat colours with
  baked AO for a clean toy look. Satin roughness (0.35-0.6) - toys are painted and lacquered.
- Saturated, friendly palette; avoid pure black (use dark blue/brown) and pure white.
- Painted details (eyes, mouth, trims) as separate geometry pieces or material regions - not texture painting.

## Review focus
- Silhouette appeal from front and 3/4, roundness in clay (no faceting on curves), proportions vs concept.
- Pitfalls: faceted curves (too few segments), mechanical straight lines, realistic micro-detail, thin fragile parts.
