# Anime / stylized-anime action (Genshin-like, arena fighters, character-action games)

Graphic, pose-driven action: very fast transitions between striking held poses, big speed contrast, flowing hair and
cloth that frames the pose.

Triggers: "anime", "Genshin / Honkai / Guilty Gear / Tales-like", "cel-shaded", "on twos", "sakuga", "flashy".

## Timing (30 fps)
- Extreme contrast: 1-2 f transitions into key poses that hold 4-10 f. The held pose carries the read.
- Anticipation is a quick, sharp counter-move (2-4 f) rather than a slow wind-up, except on ultimates/specials, which
  get a long, staged charge with a camera-facing pose.
- Optional "on twos/threes" feel: `configure(interpolation='CONSTANT')` for selected clips, or bake at every 2nd frame.
  Ask before using it, because stepped keys fight blend trees in-engine.
- Combo chains: each hit ends in a pose that can cancel into the next (keep the weapon arc continuous across clips).

## Posing
- Graphic, camera-aware silhouettes: long diagonals, a weapon extended along the line of action, clean negative space
  between limbs and body.
- Hero landings and finishing poses held with hair/cloth still settling.
- Hands expressive (spread fingers on casts, tight fists on strikes); check finger curls with a close-up render.

## Secondary
- Hair and cloth are a big part of the read: long, flowing, slightly slow (1.4-2.0 Hz, damping 0.35-0.45, gravity
  0.4-0.6), wider clamps than realistic. Collide against back/shoulders/arms; hair crossing the torso breaks the pose.
- Ribbons/sleeves/coat tails: chain springs, 1.6-2.4 Hz, follow-through clearly after the body stops.

## Watch for
- Fast 1-2 f transitions can tunnel hair through the body. The collider tunnelling fix helps, but render the worst frames.
- Held poses still need a micro-drift on the chest/head or they look frozen in a 3D engine.
