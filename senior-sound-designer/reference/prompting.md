# Stable Audio 3 - prompting and generation settings (sa3.cpp)

Learned from test runs on the local install (RTX 5070 Ti, small-sfx F16 + medium Q8_0). Update this file when a
run teaches something new - it is the skill's memory for the model.

## Which model
| Model (`model=`) | Strong at | Weak at | Speed (warm, GPU) |
|---|---|---|---|
| `sfx` (small-sfx 0.5B, SAME-S) | (needs >= 2 s canvases) Foley, organic textures, irregular events (bone rattles, debris), creature vocals, wooden/body impacts, short pickups | Pure metallic impacts (can smear into 2-3 s of noise), very short tonal UI, long steady beds (fades out) | ~1.3 s per clip |
| `medium` (1.5B, SAME-L) | Short canvases (0.8-1.5 s) for very short SFX, clean transients + ring (sword on armor), tonal/musical elements (ascending tones, chimes, level-up flourishes), string twangs, steady ambiences and loops | Rhythmic foley gets machine-regular (skeleton rattles became an even click train) | ~2-3 s per clip |

**Never commit to one model blind.** For each sound generate 3-4 seeds on BOTH models (`build.py takes`), review the
take sheet + audition page, then pick. It costs ~15 s per sound.

## Prompt shape
- Natural sentences work (T5Gemma encoder). Lead with the **source + action**, then the **character of each
  phase** in time order: "A heavy greatsword striking metal armor, sharp metallic clang, deep resonant impact, short
  ringing decay." The model honours time order surprisingly well (rumble -> whoosh -> burst).
- Name materials and sizes: steel, iron-banded oak, dry bone, wet stone, small/massive. Size words move pitch and
  low end more than any parameter.
- Negations ("no impact", "no background noise") are mostly ignored by the distilled default. If an unwanted
  element keeps appearing, use `cfg=2.5-3` with `negative="music, melody, speech, ..."` (doubles the cost per step)
  - or remove it in post (EQ, trim, inpaint).
- "No intelligible speech" for creatures is fine - creature prompts did not produce words in tests.
- Don't ask for "loopable" or "seamless" - loops are made in post (`audio.make_loop`).
- One sound per prompt. For multi-part designs (cast + travel + impact) generate the parts separately and layer.

## Duration and padding
- `duration` is exact, and the model fits the WHOLE described event into the canvas - a short canvas gives a
  compressed, complete event (onset + body + decay), not a cut-off long one.
- **Short SFX (0.1-1.5 s finished): use `medium` at a 0.8-1.5 s canvas.** Tested: sword impact, menu click+chime and
  fireball at 0.8 s and 1.2 s all came back as clean events with natural decays.
- **`sfx` (small-sfx) collapses below ~2 s**: every 0.7-1.2 s canvas came back as continuous noise/texture
  (impact, UI, fireball alike). Use `sfx` only at >= 2 s canvases and trim (`trim_silence` + `crop` + `fade`).
- Prefixing one-shot prompts with "Short, punchy one-shot game sound effect: " is harmless and helps keep events
  tight; the canvas length matters far more.
- `padding=0` (one-shots): the model may end the sound inside the clip -> natural decays, real tails.
- `padding=6` (loops/ambience/music beds): keeps full energy to the last sample -> steady material to crossfade.
- Ambience: generate the loop length + the crossfade (e.g. 30 s for a ~28 s loop with a 2 s crossfade).

## Settings
| Param | Default | When to change |
|---|---|---|
| `steps` | 8 | 16 rarely helps (distilled model); not worth the time |
| `cfg` | None (single pass) | 2.5-3 for prompt adherence / negatives; adds low-end body to impacts |
| `seed` | fixed per take | Seeds are the variation tool - record the chosen ones (picks.json) |
| `init` + `init_noise` | - | Audio-to-audio: 0.2-0.4 = same sound, new texture (variations of a chosen take); 0.6-0.8 = restyle (e.g. turn a synth riser into "magical shimmer") |
| `init` + `inpaint=(s, e)` | - | Fix a span (bad tail, unwanted event), or extend a clip |
| `peak_db` | -1.0 | Raw takes come peak-normalized to -1 dBFS without a limiter - transients stay intact |

## Output
44.1 kHz stereo 16-bit WAV. Treat raw takes as source material: work in float at 48 kHz (`audio.read`), deliver at
the project rate/bit depth (`audio.write`). Never deliver a raw take - it always has pre-roll, unshaped tails and
inconsistent loudness.
