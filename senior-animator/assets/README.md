# assets/ - working files (local, git-ignored)

One folder per character, created by copying `../templates/new_character/` to `assets/<slug>/` (or by
`draft_rig_config()`; handoffs from senior-modeler create it with `handoff_from_modeler.md`):

```
assets/<slug>/
  rig_config.py  clips.py  export.py  reel.py  notes.md  (handoff_from_modeler.md)
  renders/        contact sheets, playblasts, <Char>_reel.mp4
  export/         SK_<Char>.fbx + A_<Char>_<Clip>.fbx
  <Char>_anim.blend
```
Run scripts with their own path as `__file__` - see SKILL.md "Running scripts".
