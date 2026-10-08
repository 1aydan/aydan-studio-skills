---
name: senior-modeler
description: Senior generalist 3D modeler pipeline in Blender via the Blender MCP server - props, environment pieces, characters, creatures, weapons and vehicles in any style (stylized, realistic, low poly, cartoon, anime). Intake questions (style, textures, asset type, target, character T/A-pose), 2D concept matching (measure proportions/palette from the image, silhouette IoU scoring per view), script-built re-runnable models with style-driven bevels/shading, a preview stage (camera, lights, floor) inside the model scene with numbered revision sheets (clay, wire, part labels, material, UV checker, face orientation, turntable, concept overlays) for fast picture feedback, always-on UV unwrapping, optional baked PBR or palette textures, automated mesh/UV QA, Better FBX (fallback Blender FBX) / GLB export with verification, team presentation packs (stills, one-page sheet, turntable mp4), and a Senior Animator handoff (fitted deform skeleton, rigid or auto skin, pose test, handoff notes). Use when asked to model, block out, retopologize, UV, texture, review or export a 3D asset from Blender, or to turn concept art into a 3D model.
---

# Senior Modeler - intake -> concept -> blockout -> model -> surface -> review/QA -> export -> present -> animator handoff

Generic libraries in `scripts/`, thin per-asset data in `assets/<slug>/`. **Never put asset specifics in a library or in
`reference/`.** A library change must keep every asset in `assets/` building (re-run build/surface/review).
`reference/` holds style, asset-type, concept and texturing knowledge only; per-asset notes live with the asset.

```
senior-modeler/
  SKILL.md
  scripts/                      generic libraries - work for any asset
    inspect_model.py            inspect() scene dump, analyze() existing model, snapshot()
    concept_match.py            measure/profile/band/runs/color_regions/find_color from a concept, place_reference(), compare() IoU
    model_kit.py                begin(), box/cylinder/sphere/lathe/extrude/torus/tube, mirror_copy, bevel/mirror/boolean...,
                                group()/pose_group() rigid poses, collision()
    materials.py                style recipes (flat, stylized, pbr, toon, glow, glass), palette(), from_concept()
    uv_tools.py                 freeze() + crease_seams() + unwrap() + pack(), texel_density(), uv_qa(), uv_map()
    texture_bake.py             bake() -> T_<Asset>_BaseColor/ORM/Normal(/Emissive), swap(), palette_texture()
    review_stage.py             Preview rig in the model scene: setup(), render(), sheet(), turntable(), review() packs,
                                present() team pack, compare_revisions(), cleanup()
    mesh_qa.py                  qa(objs, BRIEF), summary(), fix()
    model_export.py             export() Better FBX | Blender FBX | glb | obj, verify(), fbx_header()
    handoff.py                  biped() + build_skeleton(), skin_rigid()/skin_auto(), check(), pose_test(), write_handoff()
    img_io.py                   PNG read/write/tile/row (numpy, no PIL)
  templates/new_asset/          brief / build / surface / review / export / present / handoff .py + notes.md starters
  assets/<slug>/                one folder per asset = ALL of its working files (git-ignored):
                                  scripts + notes.md (+ handoff.md), concept/, renders/ (r## revisions, present/),
                                  textures/, export/ and the working <Name>.blend
  reference/styles/             stylized (default) | realistic | low_poly | cartoon | anime
  reference/asset_types/        prop | environment | character | weapon | vehicle  (sizes, construction, budgets, pivots)
  reference/concept_to_3d.md    reading and measuring concepts, fidelity targets, deviations
  reference/texturing.md        UV rules, texel density, maps/packing, normal-map conventions, naming
```
## Running scripts (portable - no hard-coded paths)
`<skill>` = the folder that holds this SKILL.md. Start a new asset by copying `templates/new_asset/` to
`<skill>/assets/<slug>/`. Run any asset script through MCP `execute_blender_code` with its own path as `__file__`
(`result` must be a dict):
`p = r"<skill>\assets\<slug>\build.py"; g = {'__file__': p, 'ONLY': None}; exec(open(p).read(), g); result = {'built': g['BUILT']}`
Every asset script execs its `brief.py` first, which defines `HERE` (the asset folder), `SKILL`, `SLUG` and
`lib(name)` (loads `<skill>/scripts/<name>.py`; `lib('model_kit', into=globals())` for the kit). For one-off library
calls outside an asset script: `p = r"<skill>\scripts\uv_tools.py"; uv = {'__file__': p}; exec(open(p).read(), uv)`.
Outputs always land in the asset folder: `renders/r##/`, `renders/present/`, `textures/`, `export/`; save the working
.blend as `assets/<slug>/<Name>.blend` (Save As - never overwrite a file the user opened).

## 0. Intake - ask before building (AskUserQuestion, max 4 questions per call)
Map anything the request already says (words below) and confirm it in one line; ask only what is open.
1. **Style** (header "Model style") - read the guide(s) after choosing:
   | Option | Means | Guide |
   |---|---|---|
   | Stylized (Recommended) | readable game art, chunky bevels, painterly PBR (Overwatch/Fortnite/Sea of Thieves) | `styles/stylized.md` |
   | Realistic | real measurements, PBR, fine bevels, wear (AAA, archviz, sims) | `styles/realistic.md` |
   | Low poly | flat-shaded facets, palette colours, tiny budgets (Synty, mobile) | `styles/low_poly.md` |
   | Cartoon | soft rounded toy shapes, exaggerated proportions (Pixar, Animal Crossing) | `styles/cartoon.md` |
   Words: stylized/hand-painted/hero -> Stylized; realistic/PBR/photoreal/AAA -> Realistic; low poly/faceted/flat
   shaded -> Low poly; cartoony/toy/cute/chibi -> Cartoon; anime/cel-shaded/toon-shaded/Genshin -> `styles/anime.md`
   (offer via "Other"). Mixes ("realistic materials, stylized proportions"): shapes from one guide, surfacing from the
   other - state the split. A concept image usually answers this - propose the style you read from it.
2. **Textures** (header "Textures"): "Baked PBR textures (Recommended)" | "Palette texture" (low-poly swatches) |
   "No textures - UVs only". **UVs are always unwrapped** whatever the answer (say so in the option descriptions);
   skip unwrapping only where impossible (volumes, particles) and say why. See `reference/texturing.md`.
3. **Asset type** (header "Asset type") if unclear: Prop | Environment | Character | Vehicle/Weapon ->
   `reference/asset_types/<type>.md` (creatures and robots = character). Read it: sizes, construction, budgets, pivots.
4. **Target** (header "Target"): Game engine - Unreal (Recommended) | Unity/Godot | Render/portfolio | 3D print.
   Sets the budget (style + asset-type tables), units/axes, normal-map convention, export format.
- **Characters also:** "Pose" T-pose vs A-pose (recommend A-pose unless the concept/skeleton/retarget needs T; see
  `asset_types/character.md`), rigid parts vs one deforming mesh, rigged later (hand-off to Senior Animator).
- **Real size** when nothing gives it (concepts carry no scale) - suggest the asset-type default.
- Concept art given? Ask only what the image cannot answer (hidden back side, materials, which details are mandatory).

## 1. Inspect (never assume)
- `get_objects_summary` / `get_blendfile_summary_path_info`; unsaved file -> save to a NEW path when there is work
  worth keeping; never overwrite a user file blindly. `inspect_model.inspect()` (units, add-ons incl. Better FBX).
- Existing model to modify: `analyze(objs)` (size, ground, tri/quad mix, UVs, symmetry, unit sanity) +
  `snapshot(objs, dir)` and LOOK. Destructive changes (applying, joining, `mesh_qa.fix`) on user models need a yes.

## 2. Concept (when given) - `concept_match.py`, `reference/concept_to_3d.md`
- Copy the image(s) to `assets/<slug>/concept/`; classify: ortho turnaround / single ortho view / illustration.
- `measure`, `band`, `runs` (separate legs/arms at one height), `profile`, `color_regions` (palette + where each colour sits = part boundaries), `find_color(...,
  blobs=True)` (buttons, eyes, studs). All in subject heights x the real height. Write the parts list with the source
  measurement of each part into notes.md; list hidden-side assumptions.
- `place_reference(img, 'front', height_m)` puts the concept behind the model in the viewport for the user.

## 3. Brief - `assets/<slug>/brief.py` (copy `templates/new_asset/`)
One `BRIEF` dict = the intake answers (style, asset_type, textures, engine, tri_budget, height/size, origin, texture
res/texel target, pose, concept views + crops, export options). Every other script reads it. Start notes.md.

## Preview stage (part of every stage from the first review on)
The model scene itself carries the preview set-up, in a **Preview** collection: scene camera `GM_Cam` on a pivot,
key/fill/rim area lights that follow the view, a checker floor sized to the asset (tile size in the render label),
an optional 1.8 m human / 1 m cube scale figure, and a render-only label. `review.py` (re)builds it every run, so
it always fits the current model, and leaves the camera on the hero 3/4 view - open the .blend, press Numpad 0
(or F12) and it is ready to show to the team. Preview objects are not tagged `gm_asset`: QA and export never see
them. Renders hide everything else in the scene and restore the scene's render settings afterwards.

## 4. Blockout -> revision r01 (`build.py`, `review.py STAGE='blockout'`)
- `begin(name, style, size)`; primary forms only, at real size, faces -Y, base on z=0. Numbers come from the brief or
  the concept measurements (comment the source). Build variable things (arm angle, lid open) as parameters.
- `review.py` -> `assets/<slug>/renders/r01/` clay sheet (front/left/back/3q) + per concept view `concept | model | overlay`
  with IoU and worst bands. Targets for orthographic concepts: IoU >= 0.90 at blockout, >= 0.93 final, no band
  width error > 0.02 H. Fix the worst bands, re-run, then SHOW r01 to the user and get proportion feedback before
  detailing (cheapest moment to change shape).

## 5. Model - `build.py` passes (secondary, then tertiary forms)
- Kit: `box(top_scale=)`, `cylinder(r_top=)`, `lathe(profile)` (turned shapes from `concept_match.profile`),
  `extrude(outline)` (flat-cut shapes), `torus`, `tube(pts, r, taper=)` (cords, handles, horns), `sphere(scale=)`,
  `mirror_copy` (left/right parts), `duplicate(linked=True)` (buttons, bolts), `boolean(cutter)`, `subsurf`,
  `solidify`, `array`, `assign(ob, mat, faces=fn)`. Style sets bevel width/segments, cylinder sides and shading.
- Re-run with `ONLY=[...]` to rebuild a few parts; every part is `<Name>_<Part>`, scale 1, modifiers live.
- `review.py STAGE='model'` each pass: clay + wire + **parts** sheet (numbered labels + legend, so feedback can say
  "part 7 thinner"). Record each revision's changes and the user's feedback in notes.md.

## 6. Surface - `surface.py` (UVs always, textures per the brief)
- `uv_tools.unwrap()` freezes generator modifiers first (UVs on the exported geometry), seams -> angle-based else
  smart project, average island scale, one packed atlas (margin in px). `uv_qa` must pass; `uv_map` picture.
- Materials: `materials.palette(...)` / `from_concept(...)` with the style recipe. Textures:
  `pbr` -> `texture_bake.bake()` (Cycles, emission-routed sockets so no lighting is baked) -> `swap(..., 'baked')`;
  `palette` -> `palette_texture()`; `none` -> flat materials, UVs still packed.
- Re-running `build.py` brings back live modifiers and source materials; re-run `surface.py` after it.

## 7. Review + QA - numbers, then eyes (`review.py STAGE='final'`)
- `mesh_qa.qa(objs, BRIEF)`: transforms (scale 1, no negative scale), flipped/inside-out normals, loose/degenerate/
  duplicate geometry, non-manifold (errors for print), n-gons on deforming meshes, shading vs style, empty/unused
  material slots, names, tri budget, size vs brief, ground contact, origin placement, unit sanity, UV QA, texel
  density vs target, missing/non-power-of-two textures. **Errors block export.**
- Eyes: clay, wire, material, uv checker (squares even and square), normals (all blue), concept overlays, close-ups
  (`CLOSEUPS={'grip': ('front3q', 'Sword_Grip')}`), turntable (`turntable(png | mp4)`), before/after
  (`compare_revisions(name, 'r02', 'r03')`). A user-spotted problem means: sweep the whole asset for the same issue.

## 8. Export - `export.py` (`model_export.py`)
- Better FBX when the add-on is enabled, otherwise Blender's built-in FBX (`exporter='auto'`); glb/obj on request.
  Temporary evaluated copies -> the .blend stays editable. `SM_<Name>` (join) or `SM_<Name>_<Part>` (kits, moving
  parts), `UCX_SM_<Name>_##` collision, optional LOD files, textures copied (normal green flipped for Unreal).
  Per-asset exporter options (FBX version...) go in the brief `export.opts`, never in the library.
- `verify()` re-imports with the built-in importers (never Better FBX over MCP): tris, UVs, materials, size.
- Save the .blend (`assets/<slug>/<Name>.blend`) with the Preview collection (camera on the hero view) and finish notes.md.
- Characters that will be animated: the static SM_ export is a reference only - the skeletal export (SK_<Name>.fbx,
  then clips) belongs to the Senior Animator skill after the handoff (section 10).

## 9. Present - `present.py` (team pack, after the final review)
- `review_stage.present()` -> `assets/<slug>/renders/present/` (overwritten each run; r## folders keep the history):
  label-free material stills (hero, front, left, back3q), `<Name>_sheet.png` (concept | hero | other views) and
  `<Name>_turntable.mp4` (96 frames). Frame aspect follows the asset: tall -> 4:5 portrait, wide -> 16:9, else square.
- Show the sheet to the user; it is what they forward to the team. Run it in the pose the team should see.

## 10. Senior Animator handoff - `handoff.py` (characters, creatures, anything animated with bones)
Ask first (AskUserQuestion) when the brief does not answer it:
- **Skeleton** (header "Skeleton"): "Custom skeleton fitted to the model (Recommended)" | "Existing engine skeleton"
  (UE mannequin etc. - then the model must be fitted to that skeleton's proportions and the animator skill's
  section 0 import rules apply) | "Mesh only - no handoff".
- **Skinning** (header "Skin"): rigid parts (toys, robots, armour: each part 100% on one bone - the brief's
  `deforming=False`) vs smooth automatic weights (one soft mesh). Extra bones for secondary motion (hair, tails, hats,
  plumes, capes, jaw) - list candidates and ask which ones.
Then:
- Landmarks (subject heights from the concept measurements, character's LEFT side + centre) -> `biped(LM,
  arm_segments, leg_segments, extra)`; arms/legs that are ONE rigid piece get 1 segment. Landmarks on posed groups
  follow the bind pose through `posed(point, part)`. `build_skeleton()` -> `<Name>_SK` (rest = bind pose).
  `biped()` pre-bends knees forward / elbows back (2.5% of the limb) - straight chains make IK knees buckle sideways.
- `skin_rigid(name, RULES)` (fnmatch part -> bone, else nearest bone) or `skin_auto(name)` -> one joined mesh
  `<Name>` with the baked material, parented with an Armature modifier; source parts stay hidden and editable.
- `check()` must pass (every vertex weighted, rigid = one bone per vertex, scale 1, no zero-length bones) and the
  `pose_test()` sheet must show every part following its bone (no part left behind, no tearing at joints).
- `write_handoff()` writes `assets/<slug>/handoff.md` here and `<senior-animator>/assets/<slug>/handoff_from_modeler.md`
  (the animator skill is found as a sibling folder by its `name: senior-animator`; if it is not installed next to this
  skill, only the local copy is written - tell the user). Never overwrites the animator's own notes. Contents: file,
  armature/mesh names, FACING '-Y', SIDE_TOKENS ('L_', 'R_'), height, bind pose, skin type, bone list,
  part->bone map, spring candidates, joint limitations, next steps.
- Naming for the animator skill: lowercase bone names with `L_`/`R_` PREFIXES (its analyze() garbles `_l`/`_r` and
  any capital L/R inside centre names like "Root"); deform bones only - it adds CTRL_/MCH_/SNAP_ itself.
- After the animator has built controls, re-running handoff only re-skins (build_skeleton refuses to replace the
  rigged armature). Save the .blend; tell the user to continue with the Senior Animator skill.

## Feedback loop (how revisions work)
- Every review run makes the next `r##` folder; sheets are labelled in-image (asset, view, mode, floor tile size).
  Send the user the sheet(s) for the stage (SendUserFile when available, else paths), ask focused questions
  (proportions? silhouette? colours?), apply, re-render. Keep a revision table in notes.md (rev, changes, IoU, feedback).
- For concept work always show the overlay sheet next to the clay sheet.

## Gotchas (learned building this skill, Blender 5.2)
- The preview rig lives in the model scene (Preview collection); renders snapshot and restore engine, resolution,
  colour management, world, Workbench shading and material overrides. Older files with a separate `GM_Review`
  scene are migrated automatically by `setup()`. `cleanup()` removes the rig if a file must ship without it.
- Object `matrix_world` is stale right after setting location/rotation (no depsgraph update) - use local transforms or
  `view_layer.update()` before reading world matrices.
- Read modifier names BEFORE `modifier_apply` (the RNA struct is freed afterwards).
- A live bevel modifier on UV seams can bleed texels from other islands into the bake - unwrap after `freeze()`.
- Workbench renders text objects with shadows; set `visible_shadow = False` on labels.
- numpy 2: `np.ptp(a)`, not `a.ptp()`. `bpy.ops.render.render(scene=name)` renders a named scene.
- EEVEE engine id is `BLENDER_EEVEE` in 5.x (`BLENDER_EEVEE_NEXT` in 4.2-4.4): use `review_stage._engine()`.
- `Mesh.flip_normals()` does not exist in 5.2; use `bmesh.ops.reverse_faces`.
- n-gons block tangent export (FBX/glTF warn); the exporter triangulates n-gons on its temp copies.
- MCP requests time out (~1-2 min) on big bakes (100+ parts, 2K, AO): Blender keeps working. Wait for
  `T_<Name>_ORM.png` to appear (Bash `until [ -f ... ]` in the background), then continue. For iteration, bake at
  1K or lower `ao_samples`.
- Rigid characters/props: build in the concept pose, `group(parts, 'Arm_L', pivot)`, then `pose_group()` to the
  brief pose. Poses are object transforms only, so they survive surfacing and baking; review.py takes
  `POSES={'Arm_L': (0, 0, 0), ...}` for the concept overlay. Build paired parts on _L only and `mirror_copy` them.
- Better FBX `FBX201800` writes header 7500; built-in FBX writes 7400.

## Deliverable checklist
- [ ] intake answered (style, textures, asset type, target, + pose/size for characters); guides read
- [ ] concept measured, parts list + assumptions in notes.md (if a concept exists)
- [ ] r01 blockout reviewed with the user (concept IoU >= 0.90 for ortho concepts)
- [ ] model passes reviewed (parts sheet), feedback applied and logged
- [ ] UVs unwrapped and packed, uv_qa clean; textures baked/palette/none per brief
- [ ] final QA PASS (or accepted warnings listed), final review pack shown
- [ ] exported + verified; .blend saved; notes.md complete (revisions, deviations, export)
- [ ] present pack rendered (stills, sheet, turntable) and shown to the user
- [ ] characters: handoff done - skeleton + skin check PASS, pose test reviewed, handoff notes in both skills
