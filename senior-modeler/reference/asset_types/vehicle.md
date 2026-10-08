# Vehicle (cars, carts, boats, aircraft, mechs, spaceships, mounts' saddles)

Large hard-surface assembly with moving parts. Proportion, stance and panel logic carry it; pivots and part
separation make it usable in an engine.

## Ask first
- Drivable / animated? -> wheels, doors, turrets, propellers, suspension as separate parts with pivots on their axes.
- Interior visible? (cockpit only, full interior, or blacked-out windows) - the biggest budget decision.
- Damage states or destructible pieces?

## Real sizes
- Car 4.2-4.8 m long, 1.8 m wide, 1.4-1.5 m tall, wheel diameter 0.6-0.7 m; motorbike 2.1 m; cart 2-3 m with 1 m
  wheels; rowboat 3-4 m; fighter jet 15-20 m; tank 7-10 m. Stylized vehicles squash length 10-25% and enlarge wheels.

## Construction
- Side-view outline first (`extrude()` from the concept's side profile in plane 'YZ'), then cut the plan view, then
  round the volumes (bevels, subsurf on simple cages for car bodies).
- Panels: separate shells with real panel gaps (5-10 mm realistic, wider stylized) or inset grooves; keep body panels
  continuous across doors when the door does not open.
- Wheels: `cylinder` + `torus` (tyre) + hub details; one wheel modelled, the others `duplicate(..., linked=True)`.
  Tyres need enough sides (24-48) because they are seen in profile.
- Mirror the whole vehicle on X; break the symmetry with decals/details at the end.

## Pivots
- Root at ground centre between the axles (z = 0 on the tyre contact), facing -Y. Wheels pivot at the axle centre,
  doors on the hinge line, turrets on the ring axis, propellers on the shaft. Export join=False (SM_<Veh>_<Part>), or
  join the body and keep moving parts separate.

## Budgets (tris)
- Game car 15-60k (+ interior), stylized cart 3-10k, mobile vehicle 3-10k, low poly 500-3k; LODs mandatory.

## UV and textures
- Body: unique atlas or tiling paint + trim sheet for details; wheels share one stacked UV set; decals/livery on a
  second UV set or as decal geometry.

## Review checklist
- Side/top/front orthographic silhouettes vs concept, stance (wheel arches vs tyres), pivot check by rotating each
  moving part in a test render, scale next to the human ref, panel gap consistency in clay close-ups.
