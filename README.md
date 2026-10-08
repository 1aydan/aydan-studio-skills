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

## Getting started - example prompts
Open Blender with the MCP add-on connected, then start a conversation with your agent. You don't need to know the
skill names: describe the job and the matching skill kicks in. It asks its intake questions before building anything.

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

**Other ways in**
- "Model a stylized wooden treasure chest with a lid that opens, baked textures, for Unity." (no concept needed)
- "I opened my character in Blender - rig it and make a run cycle and a jump." (animator on an existing model)
- "Give me the presentation pack for the lantern so I can send it to the team." (modeler, stage 9)

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
