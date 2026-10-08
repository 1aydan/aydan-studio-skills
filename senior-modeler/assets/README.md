# assets/ - working files (local, git-ignored)

One folder per asset, created by copying `../templates/new_asset/` to `assets/<slug>/`:

```
assets/<slug>/
  brief.py  build.py  surface.py  review.py  export.py  present.py  handoff.py  notes.md
  concept/        concept images (copied in)
  renders/        r01, r02 ... revision sheets, present/ (team pack), handoff_pose_test.png
  textures/       T_<Name>_BaseColor / _ORM / _Normal / UV_<Name>.png
  export/         SM_<Name>.fbx (+ textures, UCX, LODs)
  <Name>.blend    the working file
```
Run scripts with their own path as `__file__` - see SKILL.md "Running scripts".
