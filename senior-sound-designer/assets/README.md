# assets/

One folder per sound or sound set, holding ALL of its working files. Git-ignored (except this README): generated
audio, review images and exports stay local.

```
assets/<slug>/
  build.py        re-runnable recipe (from templates/new_sound/)
  notes.md        brief, concept per layer, picks + reasons, QA results, lessons
  picks.json      chosen takes (sets)
  src/ | takes/   raw generations - never edited; delete a file to regenerate it
  export/         game-ready files (SFX_<Name>_NN.wav)
  review/         sheet.png, audition.html (+ img/), qa.json
```
