# Weapon (melee, firearms, bows, staffs, shields, magic foci)

A held hero prop: seen up close (first person) or constantly on screen (third person). Silhouette identity, grip
accuracy and pivot/socket placement matter as much as detail.

## Ask first
- First- or third-person? (detail + texel density: FP 2048 px/m, TP 512-1024 px/m.)
- One- or two-handed, and how it is held (grip positions) - the animator needs them.
- Moving parts (trigger, magazine, slide, bowstring, folding blade, glowing core)? -> separate objects with pivots.

## Real sizes
- One-handed sword 0.9-1.0 m (blade 0.7-0.8, grip 0.15-0.2), greatsword 1.4-1.8 m, dagger 0.3-0.4 m, axe 0.6-0.9 m,
  spear/staff 1.8-2.2 m, round shield 0.6-0.9 m diameter, pistol 0.18-0.25 m, rifle 0.9-1.1 m, bow 1.2-1.8 m.
- Grip diameter 30-40 mm (stylized can go 40-50 so it reads in the fist). Stylized weapons scale up 15-40% overall.

## Construction
- Silhouette first: blade/head shape as an `extrude()` outline (front view), then thickness, bevel the edge as a wide
  chamfer (stylized) or a fine edge bevel (realistic). Never razor-thin geometry - edges need a visible bevel band.
- Guard, pommel, grip wrap: lathe and torus/tube parts; wraps as a spiral `tube()` or a simple ribbed cylinder.
- Firearms: block the receiver, barrel and stock as boxes/cylinders; cut-ins with booleans; keep panel gaps and
  screws on hero weapons only.
- Magic weapons: emissive parts as separate material regions (`glow` recipe) so the engine can drive them.

## Pivots and sockets
- Origin at the GRIP (where the hand closes), the weapon's main axis along +Z or +Y as the project needs - write it in
  notes.md and the brief. Two-handed: note the second grip point.
- Optional empties (exported as sockets in engines that support them): Muzzle, Tip, Trail_Start/End, Grip_L.

## Budgets (tris)
- Third-person 2-8k, first-person 10-40k, low poly 200-1k, mobile 1-3k.

## UV and textures
- Unique texture set per hero weapon; the blade/face that faces the camera gets the most texel space. Mirror the two
  flat faces of a blade only if no unique wear or engraving.

## Review checklist
- Silhouette from front and side (identity at a glance), grip close-up (diameter vs a hand), scale next to the
  human ref, emissive regions, pivot location (render the origin with an axis empty if needed).
