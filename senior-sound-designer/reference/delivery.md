# Delivery - formats, loudness, naming, engines

## Formats (defaults unless the brief says otherwise)
- **WAV, 48 kHz, 24-bit** (masters / engine import). 44.1 kHz only if the project is 44.1. 16-bit only on request.
- **Mono** for anything played at a world position (impacts, weapons, creatures, foley, footsteps, spell impacts) -
  engines spatialize mono; stereo world sounds collapse or get panned oddly. **Stereo** for UI, music, 2D
  ambience beds, and big non-positional stingers (level up, reward fanfares).
- OGG Vorbis (`.ogg`, quality 5-7) only when the user asks for compressed files (web, Godot, mobile).

## Loudness (house defaults - align them with the project's mix if it has one)
Short sounds are measured by **max momentary loudness (LUFS-M, 400 ms)**: integrated LUFS is meaningless under
~1 s. Loops/ambiences/music use **integrated LUFS**. True peak ceiling **-1 dBTP** everywhere.

| Group | Target |
|---|---|
| Explosions, heavy impacts | -10 .. -12 LUFS-M |
| Weapons, creature vocals | -13 .. -14 LUFS-M |
| Swings, magic casts | -14 .. -15 LUFS-M |
| Foley, mechanisms | -16 LUFS-M |
| UI, pickups | -17 .. -18 LUFS-M |
| Footsteps | -20 LUFS-M |
| Ambience beds | -26 LUFS-I |
| Energy / machine loops | -22 LUFS-I |
| Music | -16 .. -18 LUFS-I |

Relative balance matters more than the absolute numbers: footsteps under weapons under explosions, UI clear but
never louder than combat.

## Naming
`SFX_<Thing>_<Action>_<NN>.wav` - PascalCase words, two-digit variation index from 01, no spaces.
Loops end in `_Loop` (`SFX_Dungeon_Ambience_Loop.wav`); mechanism parts `_Start` / `_Loop` / `_Stop`.
Use the brief's own names when given (e.g. `SFX_Sword_Impact_01.wav`). Unreal imports these as SoundWaves of the
same name; group variations in a MetaSound or Sound Cue (random, no repeat). Unity / Godot / FMOD / Wwise: same
file names; random containers per `<Name>_NN` set.

## Fades and edges
- One-shots: 0.5-2 ms fade-in (keeps the transient, kills the edge click), exponential fade-out into silence.
- Loops: no fades - the crossfade is inside the file (`make_loop`); first and last samples must join (QA checks).
- No leading silence on one-shots (lag), < 250 ms dead air at the end.

## Hand-off note (README in the asset folder, and the chat reply)
Per file: name, duration, channels, loudness, intended use, loop or one-shot, suggested engine settings
(pitch random range, attenuation radius, priority / voice limit). State what was generated, what was synthesized,
and which model/seed - so a sound can be regenerated or extended later.
