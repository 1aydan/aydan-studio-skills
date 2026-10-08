# Realistic / grounded (mocap-adjacent, souls-likes, military shooters, sims)

Weight comes from physics, not exaggeration. The audience compares it to mocap, so cheats show: foot sliding, floaty
arcs, symmetric poses and perfectly even timing all read as fake.

Triggers: "realistic", "grounded", "mocap-like", "Souls-like", "tactical", "naturalistic", "believable weight".

## Timing (30 fps)
- Anticipation is short and functional (weight shift, not a wind-up pose): 3-8 f light, 8-14 f heavy.
- No held "hang" at the top. Momentum carries through; holds come only from contact or exhaustion.
- Strikes 3-5 f (slower than stylized); the recovery is long and committed. Heavy weapons pull the body after them.
- Break symmetry and even spacing: offset left/right limbs 1-3 f, vary the breath period, and do not loop idles on a perfect sine.
- Easing: mostly `qo/qi` and Bezier; avoid expo snaps and elastic overshoot (use one small, damped overshoot at most).

## Posing and mechanics
- Plausible joint limits: spine twist <= ~45 deg, no hyperextended knees/elbows, wrists stay within ~60 deg.
- Centre of mass over the support polygon. Every lean has a counter (hips back when the chest goes forward). A step
  happens when the COG leaves the feet, not on a beat.
- Feet: zero slide while planted (IK targets in world, under `CTRL_World` for root motion). Heel-strike -> flat ->
  toe-off; lift the foot before pitching it toe-down, or the toes dig into the floor.
- Leg reach caps root travel: ~0.3 x height hip-to-ankle horizontal per lunge. Past that, add a gather step in the
  wind-up, a second step or a hop. QA the calf-tail vs IK-target gap every frame.
- Runs: stride ~0.3-0.35 x height at a jog, ~0.45 x height at a sprint; COG dip ~0.03-0.05 x height; head stabilized.
- Root motion is common: ease the root to follow the pelvis (not linear) so the capsule never leads or trails the body.

## Secondary
- Hair/cloth at real frequencies: long hair 1.2-1.8 Hz, damping 0.5-0.6, gravity 0.7-0.9; gear straps/pouches 3-5 Hz,
  small clamps. Nothing should bounce more than once or twice.
- Body overlap springs low (weight 0.15-0.3, clamp 5-8 deg); breathing in the chest/clavicles, not a full-body bob.

## Review
- Compare against video reference or the project's shipped mocap when there is one. Start/end on the game's idle
  (`pose_from_action`).
- Look at the clip at 0.5x speed: pops and even spacing show up there first.
