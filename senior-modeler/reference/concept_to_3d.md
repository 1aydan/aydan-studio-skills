# 2D concept -> 3D: getting it as close as possible

The concept is the spec. Fidelity order (fix in this order, never polish details on wrong proportions):
**silhouette > proportions > major forms > colour blocks > secondary details > surface/texture.**

## 1. Read the concept (before any geometry)
- What kind of image is it?
  | Type | What you can trust | How to use |
  |---|---|---|
  | Orthographic turnaround (front/side/back) | proportions, silhouettes, exact widths | crop each view, `measure()`, IoU compare per view |
  | Single front/side ortho (e.g. T-pose sheet) | that view exactly; depth must be inferred | measure front, ask or infer depth, compare front only |
  | 3/4 illustration / key art | shapes, colour, mood; NOT exact proportions (perspective, artist cheats) | match by eye with `set_view((az, el, False))`, side-by-side |
  | Sketch / thumbnail | silhouette idea, gesture | blockout freely, confirm proportions with the user early |
- Copy the concept into `assets/<slug>/concept/` and record its type + crops in brief.py (`CONCEPT`).
- Break it down in notes.md: a parts list (primary / secondary / tertiary forms), materials, what is hidden (back,
  underside, inside of the hat) and your assumption for each. Ask the user about anything that changes the silhouette
  from another view; assume (and state) the rest.
- Concepts carry no scale: ask for the real size (or take it from asset_types/*.md), then everything is
  `measurement x height_m`.

## 2. Measure, do not eyeball
- `measure(img)` -> bbox, aspect, per-row left/right extents (subject heights). Row widths at the key heights give
  the width of every horizontal band (hat, head, shoulders, waist, boots...).
- `band(img, z0, z1)` -> width/centre of a height range (e.g. the hat 0.8-1.0).
- `color_regions(img, k=10-14)` -> the palette (hex + linear) AND where each colour sits (x/z ranges): jacket red
  0.43-0.98, boots black 0.0-0.22 etc. These are part boundaries for free.
- `find_color(img, hex, blobs=True)` -> centroids and sizes of buttons, eyes, studs, stripes (count + spacing).
- `profile(img, z_range=(a, b))` -> lathe profiles for turned parts (hats, bottles, columns, toy bodies).
- Painted concepts have shading: the darker cluster of a colour is usually the same material in shadow. Merge them
  when naming materials (`from_concept`) and pick the mid/lit value for the albedo.
- Put the image in the viewport behind the model: `place_reference(img, 'front', height_m=H)` (axis-aligned only).

## 3. Blockout to the measurements (revision r01)
- Build primitives at the measured sizes - all numbers in build.py come from the measurement dict, with a comment
  naming the source (`# hat: band 0.80-0.97 -> width 0.19 H`).
- Depth (not visible in a front view): use the side view if there is one; otherwise infer from the type (head depth ~=
  head width for humans, toys use cylinders: depth = width) and LIST it as an assumption for the user.
- Render `review(concept={'front': img})`: the sheet shows concept | model | overlay (red = concept only -> model
  missing/narrow; cyan = model only -> too wide/extra) and returns IoU + per-band width errors.
- Targets (orthographic views, silhouette mode): **IoU >= 0.90 blockout, >= 0.93 final**, and no band with a width
  error > 0.02 H (2% of the height) unless it is a deliberate deviation you wrote down. Illustrations: no score -
  side-by-side and the user's eye decide.

## 4. Iterate in passes
1. Fix the worst bands first (the report sorts them), re-render, repeat. Big misses are usually: wrong part heights
   (belt line, crotch, shoulder line), missing flare/taper, wrong hat/head size.
2. Major forms and overlaps (what is in front of what, how parts intersect).
3. Colour blocks: assign the concept palette, render material front view next to the concept, compare region
   boundaries (trim lines, stripes, cuff heights).
4. Secondary details (buttons, trims, straps) placed from `find_color` blobs.
5. Tertiary/surface last.
- Show the user r01 (blockout + concept overlay) before detailing - proportion feedback is cheap at this stage.

## 5. Deviations are allowed - but deliberate
- Gameplay/engine needs (bigger grip, thicker thin parts, A-pose instead of the drawn T-pose, closed geometry where
  the drawing cheats) override the concept. Write each deviation in notes.md and tell the user.
- Perspective in illustrations makes near parts big (hands, weapon tips). Do not copy foreshortening into the model.
- Artists often draw symmetric characters slightly asymmetric by accident: mirror unless asymmetry is clearly
  intentional (a pauldron on one side, a sash).

## 6. Pose mismatch (characters)
- Model in the concept's pose so the silhouette compare stays exact; make the bind pose a parameter (arm angle) and
  switch to the requested T/A-pose after the fidelity pass. Compare the arm-free bands only after switching.
