# AI Skills

> *"Now I am become Death, the destroyer of worlds."*
> — J. Robert Oppenheimer, quoting the Bhagavad Gita

Agent skills for creative tools. Every skill is a self-contained folder at the root of this repo - copy any of them
straight into `~/.claude/skills/` (all projects) or `<project>/.claude/skills/` (one project).

## Skills by product

### Blender
| Skill | What it does |
|---|---|
| [senior-modeler](senior-modeler/) | Senior generalist 3D modeler: intake questions (style, textures, asset type, target, T/A-pose), 2D concept measurement + silhouette scoring, re-runnable script-built models, picture review sheets from an in-scene preview rig, always-on UVs, baked PBR / palette textures, mesh + UV QA, SM_ FBX/GLB export, team presentation pack, character handoff to the animator. |
| [senior-animator](senior-animator/) | Senior game animator for any skinned character: skeleton analysis, animator control rig (FK/IK, space switches), style-driven clips (stylized, realistic, cartoon, anime) with spring follow-through and root motion, QA (loop seams, ground contact, leg reach, clipping), contact sheets, playblasts, one-video reel, SK_ + per-clip FBX export. |

Requirements: Blender 5.x (tested on 5.2) with the Blender MCP server connected to your agent. Optional: the
Better FBX add-on - used automatically when enabled, otherwise Blender's built-in FBX exporter. Videos are encoded
inside Blender.

Typical flow: "model this concept as a stylized game character" (senior-modeler: intake -> blockout with concept
overlay -> model passes -> UVs/textures -> QA -> export -> present -> handoff), then "animate it" (senior-animator:
reads the handoff, asks style and clips -> rig -> clips -> QA -> reel -> export).

### Audio
| Skill | What it does |
|---|---|
| [senior-sound-designer](senior-sound-designer/) | Makes game-ready sound effects: writes a brief, generates several takes on your GPU with Stable Audio 3, picks the best ones from waveform and spectrogram checks, layers and processes them, then exports named WAV variations with an audition page so you can listen to everything. |

Requirements: Python 3 (stdlib only), ffmpeg/ffprobe on PATH, and the sa3.cpp runtime + Stable Audio 3 models
(small-sfx + medium). Install them once with
`python senior-sound-designer/scripts/setup_sa3.py --home <folder> --variant small-sfx --variant medium`
(writes `senior-sound-designer/local.json`, git-ignored). Tested on an RTX 5070 Ti: ~1-3 s per generation; CPU works
but is ~10x slower. LM Studio can download the GGUF files but cannot run them - it has no audio runtime.

Typical flow: "make a sword impact, a fireball and a menu click, 3 variations each" (senior-sound-designer: brief ->
takes on both models -> pick from review grids -> layer + process -> loudness + true-peak -> QA -> export ->
`review/audition.html`). The agent picks takes from pictures and numbers, not by ear - always do a listening pass.

### Game engines (Unreal, Unity, Godot)
| Skill | What it does |
|---|---|
| [senior-gameplay-engineer](senior-gameplay-engineer/) | General gameplay programmer: designs, writes, fixes, reviews and explains gameplay code and systems (movement, cameras, combat, abilities, AI, interaction, inventory, progression, UI logic, saves, multiplayer). Simple, clean, concise code to each engine's official coding standard (Epic C++ Coding Standard, Unity C# style guide, Godot GDScript/C# style guides) plus its gameplay best practices. Works in your project (reads its version and conventions first) or with no project. Optional QA: headless compile and tests. |

Requirements: Python 3 (stdlib only) and the project's engine installed (found automatically - Epic launcher /
source builds, Unity Hub, or PATH; override in `senior-gameplay-engineer/local.json`). Optional QA uses the engine's
own command-line tools: Unreal `Build.bat` + `UnrealEditor-Cmd` automation tests, Unity batchmode + Test Runner,
Godot `--headless` (+ `dotnet build` for C#). Close the editor on the project before a QA build.

Typical flow: "add a dash with a cooldown to my character" (senior-gameplay-engineer: inspect the project -> ask only
what's open -> short plan for bigger features -> code in the project's style -> optional compile/tests -> files
changed, editor setup, tuning values and playtest steps).

## Getting started - example prompts
For the Blender skills, open Blender with the MCP add-on connected; the sound designer only needs its runtime
installed. Then start a conversation with your agent. You don't need to know the skill names: describe the job and
the matching skill kicks in. It asks its intake questions before building anything.

**Model from concept art (senior-modeler)**
```
Use the senior modeler skill to turn this concept into a game-ready 3D model:
C:\Art\Concepts\toy_nutcracker_front.png
It's a character for an Unreal game. Match the concept as closely as you can,
show me the blockout with the concept overlay before you add detail, and
include textures.
```
It will ask for style, textures, asset type, target engine, real height and (for characters) T-pose or A-pose,
then show a numbered revision (`r01`) with a concept | model | overlay sheet for feedback.

**Animate the result (senior-animator)**
```
Use the senior animator skill on the nutcracker the modeler just handed off.
I need an idle, a walk, one melee attack, a hit react and a death for Unreal.
Keep locomotion in place. When you're done, render the reel so I can review
all the clips in one video.
```
It reads the handoff notes, asks for the animation style and anything still open (weapon, root motion, layered
attacks), then rigs, animates, QA-checks, renders the reel and exports `SK_` + one `A_` FBX per clip.

**Sound effects (senior-sound-designer)**
```
Use the senior sound designer skill to make very short fantasy RPG SFX:
sword swing, sword impact on armor, fireball cast, goblin growl and a menu
select. 3 variations each, 48 kHz 24-bit WAV, named like SFX_Sword_Impact_01.wav.
```
It sets a length target per sound (UI ~0.15-0.4 s, hits ~0.5 s, spells/creatures ~1 s), generates takes on both
models, picks from review grids and QA numbers, layers and processes each sound, exports the variations and hands
you `review/audition.html` to listen to everything in a browser.

**Gameplay code (senior-gameplay-engineer)**
```
Use the senior gameplay engineer skill on F:\Games\MyGame. Add a dodge roll
to the player: tap to roll in the move direction, 0.4 s of i-frames, 1 s
cooldown, and expose the numbers so I can tune them in the editor.
```
It inspects the project (engine, version, language, conventions), asks only what changes the design (cancel
rules, multiplayer), proposes a short plan, writes the code in the project's style and hands you the editor setup,
tuning values and playtest steps. Add "and compile it" to run the optional headless build/tests.

**Other ways in**
- "Model a stylized wooden treasure chest with a lid that opens, baked textures, for Unity." (no concept needed)
- "I opened my character in Blender - rig it and make a run cycle and a jump." (animator on an existing model)
- "Give me the presentation pack for the lantern so I can send it to the team." (modeler, stage 9)
- "Make a 30 second seamless dungeon ambience loop and a magic portal hum loop." (sound designer)
- "Hook the animator's Hit events on the nutcracker's attack clips up to damage in Unreal." (gameplay engineer)
- "Review my Godot player controller against the GDScript style guide." (gameplay engineer)

## Skills that work together
Install them side by side in the same skills folder. They find each other as sibling folders by the `name:` in their
SKILL.md (for example senior-modeler delivers character handoffs into `senior-animator/assets/<slug>/`).

## Skill layout
```
<skill-name>/
  SKILL.md        entry point (name + description frontmatter) - the agent follows it
  scripts/        tested libraries the skill runs
  templates/      per-asset starter scripts
  reference/      style / domain guides the skill reads
  assets/         one folder per asset with ALL its working files - local only (git-ignored except the README)
```
Scripts never hard-code install paths: they are run with their own path as `__file__` and find the skill from
there (see each SKILL.md, "Running scripts").

## Adding a skill
Create `<skill-name>/` at the root with the layout above, add it to the product table here, and keep asset work in
its `assets/` folder.
