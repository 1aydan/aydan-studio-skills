# Body archetypes - rig and authoring lessons (combine with a style guide in styles/)

## Biped, armed (staff, sword, gun, shield)
- IK hands as world-space targets (`world=True`). Hand targets parented under the chest inherit body pitch/twist,
  so slams end up pointing through the floor.
- World-space hands do not travel with spins, knock-ups or deaths: carry them with the body yaw (rotate the point, add
  the yaw to Euler Z) or place them where the body actually is.
- Weapon without a mesh: build a proxy in `ANIM_Review` (shaft through the fist along index->pinky) and state the
  assumption. Weapon space switch (follow hand <-> world) for drops and pickups; use `world_matrix()/key_matrix()` hooks
  so hand-offs do not pop. A dropped weapon with yaw only may stand on end: tilt 90 deg on the shaft axis to lay it flat.
- Melee arcs keep the weapon butt and forearm clear of the body; add clearance breakdowns. Sweep capsules over ALL
  clips. When the user spots one clip, others usually have the same problem.
- Shoulders: the clavicle carries most of an overhead lift; reduce pauldron follow so it never folds over the collar.
- Strafe runs: the free hand/weapon tends to graze the far thigh, so check those clips explicitly.

## Biped, unarmed / clawed monster
- Claws and fists: cock the palm down and back on wind-ups. Open palms facing camera read as waves.
- Staggered idles (one foot forward, chest pre-turned): measure absolute yaw per bone, since strike twist stacks on
  the idle. Build the opposite-side attack as a mirrored upper body over the same footwork, not `.mirrored()`.
- Jaws: open on the wind-up, snap shut at impact, light jaw spring for a rattle.

## Engine skeletons (UE mannequin and similar)
- Import with Automatic Bone Orientation OFF, prove the rest + idle round-trip (see SKILL.md section 0).
- Single-letter side tokens (`_l`/`_r`) confuse `analyze()` / `draft_rig_config()`: check the snapshot and write the config.
- Disconnected limb segments: `target_pivot='tail:<lower bone>'` + `end_mode='rotation'`.
- Engine IK bones (`ik_foot_*`, `ik_hand_*`) are exported but stay at rest unless the project uses them.
- Hand poses give the WRIST point; offset along the forearm to the joint if the skeleton needs it.

## Quadruped
- Four ground limbs on IK; gait by phase offsets (walk: LH, LF, RH, RF; trot: diagonal pairs). Spine bends toward
  the turn; head counter-stabilizes.
- Death/lying on the side: pose the down-side legs toward world-up and calibrate the COG offset by measuring min mesh z.

## Flyer / hovering creature
- Height on `CTRL_Hover`, Root on the ground. Legs FK (not IK) unless they land.
- Lean into travel: forward 12-15 deg nose-down, back ~12 deg nose-up, strafe bank ~16 deg + yaw ~8 deg; appendages
  drag opposite to travel.
- Deaths lose lift, fall to the floor, bounce and settle. Spawns can drop in from above.
- Jump while hovering: reduce gravity on hanging props during flips, increase it again on death.

## Long hair / skirts / cloth (any archetype)
- Collide whole strands (not just tips) against back, shoulders, head, hips, pauldrons and IK-solved arms; floor plane
  for hair on the ground. Hair resting on a shoulder is fine; hair through the torso is not.
- Skirts: front/back panels pushed by either thigh (one-sided clamps), side panels by their own leg.
- Death face-down: legs straight back + body raised, or the knees bend through the floor (check per-vertex-group min z).
