# assets/ - per-feature notes (local, git-ignored)

Optional: only for features that span several steps or sessions. The code itself always lives in the game project.

```
assets/<slug>/
  notes.md        brief, plan, decisions, log (copy of ../templates/new_feature/notes.md)
  project.json    inspect_project.py --slug <slug> output (what the feature was built against)
  review/         verify.py --slug <slug> logs + test reports (build.log, test.log, tests_*.xml, ue_tests/)
```
