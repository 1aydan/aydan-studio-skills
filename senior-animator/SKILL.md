---
name: senior-animator
description: Model-agnostic senior game-animator pipeline in Blender via the Blender MCP server - for ANY skinned character (biped, quadruped, winged, hovering pet, props, any facing axis or bone naming): analyze the skeleton, generate and refine an animator control rig (character-relative CTRL bones, FK/IK, space switches, custom shapes, sidebar panel) without changing the game skeleton, author stylized clips as pose-to-pose keys with baked spring follow-through, collision-aware secondary and limb-driven follow, review with a render camera rig and contact sheets, run automated QA (loop seams, ground contact, self-intersection), review everything in one labelled reel video, and export engine-ready FBX (Better FBX when installed, else Blender's FBX; skeletal mesh first, then one FBX per animation, deform bones only). Picks up characters handed off by the senior-modeler skill. Use when asked to rig, animate, or export character/creature/pet animations from Blender for a game engine.
---

# Senior Animator - model-agnostic rig -> animate -> review -> QA -> export

Generic libraries in `scripts/`, thin per-character data in `assets/<slug>/`. **Never put character specifics in a
library or in `reference/`.** A library change must keep every character in `assets/` building (re-run and QA).
`reference/` is genre/style and body-type knowledge only; per-character notes live with the character.

```
senior-animator/
  SKILL.md
  scripts/                       generic libraries - work for any skeleton
    inspect_character.py         inspect() dump, analyze() facing/sides/archetype/chains, draft_rig_config(), snapshot()
    rig_builder.py               build_rig(CFG): character-relative controls for any facing, FK/IK, spaces, shapes, panel
    anim_framework.py            configure(), Anim, @clip, springs + colliders + follow, world-space targets, hooks, QA
    anim_review_camera.py        setup() (hides other preview rigs), set_view(), contact_sheet(), playblast(),
                                 reel() (all clips in one labelled video), teardown()
    fbx_export.py                export() SK + per-clip (Better FBX if enabled, else Blender FBX), verify()
  templates/new_character/       rig_config.py / clips.py / export.py / reel.py starters (or draft_rig_config for the rig)
  assets/<slug>/                 one folder per character = ALL of its working files (git-ignored): rig_config.py,
                                 clips.py, export.py, reel.py, notes.md (+ handoff_from_modeler.md), renders/
                                 (contact sheets, playblasts, reel), export/ (SK_/A_ FBX) and the working .blend
  reference/styles/              genre guides - timing, posing, secondary ranges, pitfalls per style:
    stylized.md                  stylized game action (hero shooter / MOBA / ARPG) - the default
    realistic.md                 grounded / mocap-adjacent / souls-like
    cartoon.md                   toon, squash & stretch, cute pets, mascots
    anime.md                     anime action: snap into held poses, flowing hair/cloth
  reference/archetypes.md        body-type lessons: armed/unarmed biped, engine skeletons, quadruped, flyer, hair/cloth
```
## Running scripts (portable - no hard-coded paths)
`<skill>` = the folder that holds this SKILL.md. Start a character by copying `templates/new_character/` to
`<skill>/assets/<slug>/` (or let `draft_rig_config()` write `assets/<slug>/rig_config.py`). Run every script through
MCP `execute_blender_code` with its own path as `__file__` (`result` must be a dict):
`p = r"<skill>\assets\<slug>\clips.py"; g = {'__file__': p, 'ONLY': [...]}; exec(open(p).read(), g); result = {'built': g['BUILT']}`
The scripts derive `HERE` (the character folder) and `SKILL` from `__file__` and load libraries from
`<skill>/scripts/`. One-off library calls: `p = r"<skill>\scripts\inspect_character.py"; ic = {'__file__': p};
exec(open(p).read(), ic)`. All outputs land in the character folder: `renders/` and `export/`. Save the working
.blend as `assets/<slug>/<Char>_anim.blend` (Save As - never overwrite the file the user or the modeler handed you).

## 0. Characters that come FROM a game engine (Unreal skeletons)
If the animations must play on an EXISTING engine skeleton, the Blender armature must carry the engine's own joint
frames. Import the engine's FBX with Better FBX **Automatic Bone Orientation OFF** (Unreal joints are unoriented: every
bone points +/-Y, right side mirrored). An auto-oriented import looks fine in Blender but every clip explodes on the
original skeleton in the engine. Then:
- bake the import's object scale (often 0.01) into bone/mesh data so the space is meters (`edit_bone.transform`,
  `mesh.transform`; `transform_apply` may no-op from MCP);
- prove the round trip: export the bare armature and compare every bone's Lcl Translation/Rotation with the engine's
  file (they must be 0.00 cm / 0.00 deg); export the engine's own idle the same way and compare curves over time;
- rig with `aligned=True` IK (joint->joint chain + snap children), IK targets on the hand/foot joints, `seg:` shape
  offsets, explicit spring tip vectors, and finger/hand directions from joints, never from bone tails.
See also `reference/archetypes.md` (engine skeletons).

## 1. Analyze the model (never assume)
- Characters built by the **senior-modeler** skill (a sibling skill folder) arrive with
  `assets/<slug>/handoff_from_modeler.md`: armature `<Name>_SK` + skinned mesh `<Name>`, FACING '-Y', SIDE_TOKENS ('L_', 'R_'),
  bind pose, rigid/soft skin, spring candidates. Read it first; still run analyze() + snapshot() to confirm.
- `get_objects_summary` / `get_blendfile_summary_path_info`; save an unsaved file to a NEW path, never overwrite blindly.
- `inspect_character.analyze(ARM, MESH)` gives, from geometry + hierarchy (not names):
  - `facing` ('-Y' / '+Y' / '-X' / '+X' + confidence): foot mass ahead of the ankles, head ahead of the body.
  - `side_tokens`: the left/right naming tokens found from geometrically mirrored bones (L_/R_, lf_/rt_, .L/.R, Left...).
  - `height`, `ground`, `archetype` (biped / quadruped / winged / other-hover), `ground_limbs` (IK candidates),
    `spring_candidates` (hair, skirts, tails, ears, cloth, armor flaps...), `props` (weapon/prop bones), `fingers`.
  - Use **% of height** for every distance you author (stride, crouch, jump) - characters range from 1 to 60 units.
- `snapshot(MESH, dir)` and LOOK. Confirm the archetype, what each unweighted/odd bone is, and what the weapon/props are.
  Ask the user only for genuinely open choices (weapon grip, combat style, in-place vs root motion, clip interpretations).
- **Pick the style (ask before authoring any clip).** If the request already names a style, map it with the table
  below and confirm it in one line. Otherwise ask the user with `AskUserQuestion` (header "Anim style"), offering:
  | Option | Means | Guide |
  |---|---|---|
  | Stylized (Recommended) | game action: pushed poses, held hangs, punchy hits (Overwatch/League/Hades) | `styles/stylized.md` |
  | Realistic | grounded, close to mocap, physics-driven weight (Souls-like, tactical) | `styles/realistic.md` |
  | Cartoon | squash & stretch, elastic overshoot, cute/mascot appeal | `styles/cartoon.md` |
  | Anime | snap into held poses, flowing hair/cloth (Genshin, arena fighters) | `styles/anime.md` |
  Words to match: stylized/punchy/hero/MOBA -> Stylized; realistic/grounded/mocap/Souls -> Realistic;
  cartoony/toon/cute/bouncy/Pixar -> Cartoon; anime/cel-shaded/sakuga/on twos -> Anime.
  "Other" answers or mixes (e.g. "realistic weight, anime hair"): take timing/posing from one guide and secondary from
  the other, and state the split. Then read the chosen guide(s) + `reference/archetypes.md` and record the style in
  `assets/<slug>/notes.md`.

## 2. Rig - `assets/<slug>/rig_config.py`
- Start from `draft_rig_config(ARM, MESH, path, slug)` (one control per weighted deform bone, COG over the pelvis,
  IK on ground limbs with solved poles, shapes sized from the skin, collections by role) or the template; then edit:
  names, which chains get IK (biped feet/hands: yes; flyer legs: FK), fingers/toes parented to the deform hand/foot,
  props via `spaces` (prop follows hand <-> world), arm/leg pole placement (relaxed elbows/knees).
- `CFG['facing']` = analyze()'s facing. Controls are built pointing backward with roll 0, so for EVERY model the control
  frame is character-relative: local -Y forward, +X character's left, +Z up. All authoring conventions below hold.
- Gate: `REPORT['rest_errors'] == {}`, pole errors ~0; pose a control and see the mesh follow.
- Disconnected limb segments (gap between lower bone tail and hand/foot head, common on UE skeletons): IK
  `target_pivot='tail:<lower bone>'` + `end_mode='rotation'`, or the hand/foot slides off when the wrist turns.
- `analyze()` archetype / `draft_rig_config()` names are unreliable for single-letter side tokens (`_l`/`_r`): it called a
  UE biped "quadruped" and garbled names (`CTRL_CAvicleR_L`). Check the snapshot and write the config by hand if needed.
- Root motion: put a non-deform `CTRL_World` above `CTRL_Root` and parent the foot IK targets to it, so feet stay
  planted while the root travels. Include `Root` in every `A.pose` so world-space hand targets compensate.

## 3. Clips - `assets/<slug>/clips.py`
Conventions (any model): r.x+ = pitch forward / nose down, r.y+ = roll top to the character's left, r.z+ = turn left;
right side mirrors as (x,-y,-z) rot and (-x,y,z) loc; `_X` in pose dicts = both sides.
- `BASE_P` = the neutral stance every clip starts/ends in (match the art reference). If the game already has an idle
  on the deform bones, use `pose_from_action(ARM, idle, frame, refine=40)` so clips start/end exactly on it. Blend
  near-straight IK arms from FK at the ends (`A.prop('IK_Arm_L', ...)`). Author offsets from it (`base_val` + delta).
  Do not `.mirrored()` clips over an asymmetric idle. `A.pose` blocking keys,
  `A.key` accents, `A.wave` loops (periods must divide the loop), per-key easing (`qi/qo/xi/bo/eo...`).
- **World-space targets** (`world=True`) for IK hands, weapons and feet: aim is exact regardless of body pitch/twist.
  For spins carry world points with the body yaw (rotate point, add yaw to Euler Z) (see `reference/archetypes.md`).
- **Secondary** (`SPRINGS`): tip-chasing springs baked per frame. Weight = gravity term + damping + frequency:
  heavy hair/cloth ~1.6-2.2 Hz, damping 0.4-0.5, gravity 0.5-0.7, tight clamps; light antenna/ear 2.5-3.5 Hz, 0.25.
  Gravity keeps the parent's heading (hanging parts turn with spins).
- **Colliders** (`colliders` + `collide`): capsules on body controls or IK-solved deform bones (`('bone', name, r)`);
  whole strands are collided (not just tips), tunnelling on fast hits is resolved toward the body-relative side,
  radii are auto-calibrated against the bind pose so they never fight the model's own styling.
- **Follow** (`follow`): limb-driven offsets before springs - skirts pushed by thighs, auto clavicle shrug (carry most of
  an overhead lift on the clavicle), pauldrons gently on top.
- Props/settings: `props` keyed every clip; `A.prop()` + `A.after()` hooks with `world_matrix()/key_matrix()` for
  hand-offs between spaces (drop a weapon in world space, pick it up later without pops).
- Events: `A.mark(f, 'Hit'|'Fire'|'Cast'|...)`; mirrored clips via `.mirrored()`; generators for locomotion.
- **Upper-body layer clips** (attacks played over locomotion): `configure(upper_split=dict(root='COG', branch='Spine'))`
  + `Anim(..., upper_body=True)`. Lower body is held at the base pose, root rotation moves onto the spine, root
  translation is dropped. Author them without whole-body spins, leaps or steps (use coil/twist instead, keep spine
  twist under ~60 deg) and put impact shakes on the chest, not the COG. **Ask which clips are layered before authoring.**

## 4. Review - `anim_review_camera.py`
`setup(ARM, follow_bone, aim_height, distance, height_ref=gameplay height)`, `contact_sheet(png, frames, views)`,
`playblast(mp4)`, then **`teardown()`** when done. `setup()` hides other skills' preview rigs that live in the model
scene (the Senior Modeler `Preview` collection: camera, lights, checker floor) so the two floors/cameras never
overlap, and snapshots the scene camera, render engine and their visibility once; `teardown()` restores them and
hides `ANIM_Review` (`teardown(remove=True)` deletes it).
**Reel** - `assets/<slug>/reel.py` (one command): every clip back to back in ONE video,
`Renders/<Char>/anim/<Char>_reel.mp4`. Clips in the CLIPS order (idle, locomotion, attacks, reactions, death last),
loops repeated (LOOPS, default 2), a short hold between clips, and a burnt-in label per clip: name, length,
`LOOP xN` / `root motion` (only when the root really travels) and event markers. Each clip renders once as PNGs, a
temporary sequencer scene assembles and encodes them, then everything temporary is removed and teardown() runs.
Send it to the user after the contact sheets - it is the quickest way to review or share the whole set.
Floor grid + height ring, Workbench, review objects in `ANIM_Review` (never exported). Build a proxy
for any weapon without a mesh (parented to the weapon bone, shaft through the socket) and state the assumption.
Close-up the hands for grips; render stacked sheets of all clips; delete any test duplicates before rendering.

## 5. QA - numbers, then eyes
- `qa_report(body_bone, exclude_groups)`: loop seams == 0, height, min mesh z at start/end (ground contact; find the
  culprit with per-vertex-group min z).
- `qa_clipping(capsules, pairs)` over every frame of every clip: limbs vs body, arm vs arm, weapon vs body, **hair/cloth
  vs back, shoulders and arms**. Fix > ~5 cm; render the worst frames - hair resting on a shoulder is fine, hair
  through the torso is not. A user-spotted clip means: sweep everything, fix the root cause.

## 6. Export - `fbx_export.py` (Better FBX if enabled, else Blender FBX)
`SK_<Char>.fbx` (mesh + armature, rest, no animation), then `A_<Char>_<Clip>.fbx` per tagged action (armature only,
sampled, timeline = action range). Deform bones only, selection only, cm. Per-character options (e.g. an FBX version
the project needs) go in that character's `export.py` `opts`, not in the library. `verify()` re-imports: bone count,
no CTRL/MCH/SNAP leaks, range, probe bone values; check the file header version if one was requested. Files go to
`assets/<slug>/export/`. Save the .blend (`assets/<slug>/<Char>_anim.blend`).

## Animation direction
Style-specific timing, posing and spring ranges are in `reference/styles/`; body-type lessons in `reference/archetypes.md`.
Always: neutral stance per the art reference, distances in % of height, planted feet, uniform scale only.

## Gotchas
- Blender 5.x slotted actions: `act.slots.new`, `anim_utils.action_ensure_channelbag_for_slot`; set action + slot
  (and never set a slot when the action is None). MCP `result` must be a dict. PowerShell aliases `R` (use Python for
  scripted file patches).
- Raw CTRL bones look sideways in Edit mode (they are character-relative, roll 0); only deform bones export.
- `transform_apply` may silently no-op from MCP; transform data directly (`edit_bone.transform`, `mesh.transform`).
- Finger curl axis: find it with a close-up render test before authoring grips.
- `anim_review_camera.setup()` switches the scene to Workbench and its own camera: always `teardown()` before saving,
  or the user's materials look missing and the model's Preview rig stays hidden.
- `verify()` re-imports with Blender's own FBX importer in a temporary scene - never call the Better FBX IMPORTER over
  MCP (it can error or close Blender). Cheap outside check: binary header version (7400 = FBX 2014/2015, 7500 = Better
  FBX `FBX201800`) and no `CTRL_/MCH_/SNAP_/WGT_/GM_/ANIM_` names in the file bytes.
- Root motion: check leg reach (calf tail vs IK foot target gap) on every frame. Longer travel needs earlier back-foot steps or a hop.
- IK/FK switches: if ANY clip keys an `IK_*` prop, list every switch in `configure(props={...: default})` - clips that
  do not key it otherwise inherit the last clip's value (a march ran on FK legs and sank 4 cm).
- `poles_deg_err` is (solved pole angle, residual): the residual must be ~0; the angle (often ~90) is fine. Perfectly
  straight leg chains (no knee pre-bend) still buckle sideways in motion - pre-bend the skeleton's knees forward.
- 'eo' (elastic) keys: Blender's default amplitude 0.8 is absolute, so unchanged channels bounced +-0.8; the framework
  now writes amplitude 0 (bounce proportional to the change). Re-check old characters' 'eo' clips after updating.
- Characters from the Senior Modeler skill: its Preview rig (camera/lights/floor) lives in the model scene -
  `setup()` hides it automatically and `teardown()` brings it back (add other rigs' collection names to
  `OTHER_PREVIEWS` / `setup(hide_previews=...)`).

## Deliverable checklist
- [ ] analyze() + snapshot reviewed; style guide chosen; assumptions confirmed with the user
- [ ] rig built (rest_errors {}), panel registered
- [ ] clips built; loops seam 0; events listed
- [ ] contact sheets + clipping sweep (incl. hair/cloth) reviewed and fixed
- [ ] reel rendered (`reel.py`) and shown to the user
- [ ] review `teardown()` run (scene camera, engine, model Preview rig restored)
- [ ] exported + verified; .blend saved; `assets/<slug>/notes.md` written (clip table, events, decisions, review lessons)
