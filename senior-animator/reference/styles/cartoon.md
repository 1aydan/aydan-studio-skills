# Cartoon / toon (squash & stretch, cute pets, party games, mobile)

Appeal over plausibility. Shapes deform, timing is elastic, and personality comes before mechanics. Physics is a
suggestion, but contacts and the floor still have to read.

Triggers: "cartoony", "toon", "cute", "bouncy", "Looney Tunes / Pixar-like", "rubber hose", "chibi", "pet", "mascot".

## Timing (30 fps)
- Big, readable anticipation (often bigger than the action); fast action in 1-3 f; generous overshoot and elastic
  settle (`eo`/`bo`) over 8-15 f.
- Holds are poses with life: keep a moving hold (small drift/breath), never a dead freeze.
- Staging: one idea per beat. Fidgets go look left -> snap look right -> big gesture -> satisfied settle.

## Squash and stretch
- Through scale controls (uniform scale per control only; keep volume: stretch Y 1.2 -> X/Z ~0.91).
- Squash on landings and impacts (1-3 f), stretch on launches and fast moves. Spawn "pop": 0.02 -> ~1.2 -> 1.0 with a
  spin (-360..-540 deg) and an elastic settle.
- Exaggerate secondary on tails and hanging props (2.1-3.4 Hz, damping 0.24-0.28, wide clamps). Ears and limbs stay
  firmer: ears ~3.6-4.4 Hz, damping 0.45, weight 0.6-0.7, clamp 28-35; leg chains 3.2-4.8 Hz, damping 0.5, weight
  0.5-0.6, clamp 15-20. Below ~3 Hz / 0.3 damping they read as gel and swing into the head/body. Add head/body
  colliders for ear tips and lower legs.

## Posing
- Strong lines of action and asymmetry; tilt heads 10-20 deg; overlapping limbs (paws paddle out of phase).
- Hover/flying pets: body on `CTRL_Hover`, root on the ground; float bob ~2 s, paddle ~1 s, pitch lags the bob.
- Charge-ups: curl + tremble with a pulsing scale accent, then a snap release and a big kick-back.
- Deaths/knockouts can be comedic (stiff legs in the air, a last twitch) but must still settle onto the floor.

## Watch for
- Scale on deform bones only exports if the engine supports bone scale. Check that before relying on squash.
- Elastic overshoot on IK targets can pop knees. Overshoot the body, keep the feet planted.
