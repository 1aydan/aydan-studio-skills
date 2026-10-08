# AI Skills

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
