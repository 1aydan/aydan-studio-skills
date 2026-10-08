# Category recipes - layers, processing, readability

Starting points, not rules. Every recipe ends with: trim -> fades -> normalize to the category target -> QA -> listen.
Ops are `audio.fx` chain entries; synth elements are `synth.*`.

## Readability first (why sounds get lost in combat)
- **Transient** = "it happened". If the generated onset is soft, layer `synth.click()` at 0-2 ms, -9..-14 dB.
- **Frequency slot**: give each family a home. Player weapons 1-5 kHz bite; enemy weapons darker; magic owns
  shimmer (6-12 kHz) or sub; UI lives above 150 Hz and never fights the sub. High-pass everything that isn't meant
  to carry weight (`('hp', f, 4)`) - stacked low end from 20 sounds is the #1 mix killer.
- **Length**: frequent sounds short (UI 0.05-0.4 s, footsteps 0.2-0.4 s, swings 0.3-0.6 s). Long tails mask the
  next event.
- **Consistency**: one house chain per project (same HP, comp feel, room) so a set sounds like one game.

| Category | Gen | Typical layers | Processing | Length | Target LUFS-M max |
|---|---|---|---|---|---|
| Impact (metal/wood/flesh) | medium for metal, sfx for wood/body | gen body + `click` (-9) + `thump(70-110 Hz)` (-7) | hp 45, comp -20/4:1/2 ms/90 ms, optional `('drive', 4)` for grit | 0.4-1.5 s | -12 |
| Whoosh / swing | medium first | gen; optional `synth.whoosh` sweetener | hp 110-150, comp light; pitch spread +-0.6 st across variations | 0.3-0.8 s | -15 |
| Projectile (bow, throw) | medium | release (twang/click) + flight whistle; impact as a separate asset | hp 70 | 0.5-1.5 s | -14 |
| Magic cast | both | gen + synth riser / shimmer; sub_drop for heavy spells | hp 55, short room `('reverb', 0.9, 0.10)` for air | 1-3 s | -14 |
| Magic impact / burst | both | gen + click + sub_drop | hp 40, comp, drive | 0.8-2 s | -12 |
| Healing / buff | medium | tonal gen + light reverb | hp 80, `('reverb', 1.6, 0.18)`, gentle | 1.5-3 s | -16 |
| Creature vocal | sfx (vocals), both for roars | gen; big creatures + sub_drop; pitch down (`('pitch', -3..-7)`) for size | hp 45, comp -22/3:1 | 1-4 s | -13 |
| Foley / mechanism | sfx | gen; split long mechanisms into start/loop/stop if gameplay needs it | hp 60 | event length | -16 |
| UI click / select | medium (2 s gen, trim) or `synth` | gen + optional `synth.blip`; click layer | hp 150, cap with `max_len` + fade | 0.05-0.4 s | -17..-18 |
| Pickup / reward | sfx or medium | gen + `synth.blip` sparkle; level-up = medium (tonal flourish) | hp 120, room 1.4 s / 0.12 | 0.4-3 s | -15..-17 |
| Ambience / bed (loop) | medium, padding 6 | gen 30 s; add detail one-shots in-engine instead of baking them | hp 30, `make_loop(xfade=2)` | 20-60 s | LUFS-I -26 |
| Mechanical / energy loop | medium, padding 6 | gen 10-15 s | hp 40, `make_loop(1.5)` | 5-15 s | LUFS-I -22 |
| Explosion | both | gen + click + `sub_drop(80->32)` + debris tail (sfx) | hp 30, comp, drive 3-5 dB, limit | 1.5-4 s | -10 |
| Footsteps | sfx, one prompt per surface | gen many takes, cut single steps; 6-10 variations | hp 70, tight trim | 0.2-0.4 s | -20 |

## Variations (anti-repetition)
- Different **takes** (seeds) are the main source - pick takes that are clearly the same sound but differ in detail.
- Add **pitch spread** (+-0.3..0.8 st) and small level/EQ differences. Engines usually randomize pitch +-5% at
  runtime too - don't double up; check with the user/engine setup.
- Counts: high-frequency sounds (footsteps, hits, UI hovers) 6-10; mid (swings, casts) 3-5; rare (level up) 1-2.
- Audio-to-audio (`init_noise` 0.25-0.4) from a chosen take gives siblings with the same envelope.

## Fixing generations
| Symptom | Fix |
|---|---|
| Pre-roll / lag before the hit | `trim_silence(head_db=-38)` |
| Smeared, soft attack | layer `click`, or comp with slow attack (5-10 ms) to let the transient through |
| Noise bed / hiss | `('denoise', 0.005)`, `('lp', 14000)`, or pick another take |
| Boomy / muddy | `('hp', 80..150, 4)`, `('eq', 250, -3, 1)` |
| Harsh 2-5 kHz | `('eq', 3200, -3, 1.4)`; small reduction beats big cuts |
| Unwanted tail event | `crop` + `fade`, or inpaint that span |
| Too long | `crop` + long exponential `fade` (decay shape, not a cut) |
| Clicks at edges | `fade(0.001, 0.02)` (deliver does this) |
| Loop seam | `make_loop(xfade)`; check `qa.analyze(kind='loop')` wrap_jump <= 4 |
