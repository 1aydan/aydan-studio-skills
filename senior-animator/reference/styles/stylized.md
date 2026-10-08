# Stylized game action (hero shooters, MOBAs, action RPGs, brawlers)

Readable silhouettes at gameplay distance, exaggerated weight, crisp timing. Physically plausible enough that feet and
weapons never cheat visibly, but every pose is pushed past real life.

Triggers: "stylized", "game-y", "Fortnite / Overwatch / League / Hades-like", "punchy", "hero", "MOBA", "ARPG".

## Timing (30 fps)
| Tier | Anticipation | Strike | Impact hold | Recovery | Total |
|---|---|---|---|---|---|
| Light | 4-6 f | 2-3 f | 0-2 f | quick, 10-15 f | ~22-34 f |
| Medium | ~8 f + step | 2-3 f | 2-4 f | ~15-20 f | ~32-44 f |
| Heavy | 12-16 f with a held "hang" (3-5 f) | expo-in, 2-3 f | 4-6 f with COG/chest shake | long, off-balance settle | ~50-62 f |
- Abilities/casts: 40-65 f; put the event (Fire/Cast/Burst) at the release, not the hold.
- Loops: idle 60 f (2 s breath/bob), run cycle 20 f (two steps), hover/fly 30 f.
- Easing: blocking keys `qo/qi`, strikes `xi` (expo in), overshoot settles `bo`/`eo`. Avoid linear except root travel
  that must match a capsule.

## Posing
- Push lines of action: coil 50-70 deg onto the back leg for big swings; over-rotate the follow-through past the target.
- Smear/breakdown key one frame before contact on wide arcs (stretch the arc, not the mesh).
- Silhouette first: a windup must read from the gameplay camera. An open raised palm facing camera reads as a wave -
  cock it palm-down/back.
- Ranged releases snap to a FLAT aim (emitter on the aim line), then recoil and settle. Pitching the whole body
  40 deg nose-down reads as a headbutt - keep total pitch <= ~12 deg and move the power into translation/scale.
- Runs must scale to the character: stride ~0.4 x height, foot lift ~0.17 x height, COG dip ~0.08 x height.
  Smaller than that reads as a jog. Athletic run = knee drive, rear kick, dip after contact, float in flight, pelvis yaw
  + drop, chest counter-rotation, stabilized head, arm pump (in chest space) with wrist lag.

## Secondary
- Hair/cloth reads heavier than real: 1.6-2.4 Hz, damping 0.42-0.5, gravity 0.45-0.7, tight clamps.
- Light appendages (antennae, tassels): 2.5-3.5 Hz, damping ~0.25. Ears and leg chains firmer (3.5-4.5 Hz, damping
  ~0.45-0.5, weight 0.55-0.7, clamp 15-35) or they read as gel and clip; collide ear tips with the head, lower legs with the body.
- Jiggle (belly, collar, snout): 2.8-4.5 Hz, damping 0.3-0.35, weight 0.8-0.9, clamp 15-25 deg.
- Body overlap (head/chest/pelvis springs): weight 0.3-0.5, clamp 8-12 deg. Enough to feel alive, and the aim still holds.
- Hanging props (mics, lanterns, charms) need a gravity blend (~0.65) or flips throw them horizontal.

## Gameplay constraints
- Attacks played over locomotion -> upper-body layer clips (no spins, leaps or steps; coil/twist <= ~60 deg; shake
  on the chest, not COG). Ask which clips are layered.
- In place by default; only turns carry root yaw unless the user asks for root motion.
- Death/knockdown must end resting on the floor (verify min mesh z per vertex group).
