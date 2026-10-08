# Character (humanoids, creatures, mascots, robots, toy figures)

Anything that will be RIGGED and ANIMATED, or could be later. Topology serves deformation first, silhouette second,
surface detail third. Hand-off target: the Senior Animator skill (`senior-animator`, installed next to this skill).

## Ask first (intake, in addition to style / textures)
- **Bind pose: T-pose or A-pose** (header "Pose"). Recommend **A-pose** (arms ~45 deg down, slight elbow bend) for
  shoulder deformation quality and modern engine skeletons (UE5 Manny/Quinn are A-pose); **T-pose** when the concept
  sheet, the existing skeleton, or a retarget pipeline expects it (UE4 mannequin, many mocap libraries).
  Build the arm angle as a PARAMETER in build.py (`ARM_DOWN_DEG`): model and concept-compare in the concept's pose,
  then set the requested bind pose - so the silhouette check stays exact and the pose is a one-line change.
- Rigged later? deforming skin (one mesh) vs rigid segmented parts (robots, toys, armour - each part parented to one
  bone, no weights needed). Rigid parts are faster and deform perfectly for mechanical / wooden characters.
- Real height (concepts carry no scale): human 1.75-1.85 m, child 1.2 m, dwarf 1.3 m, giant 3-4 m, pet 0.3-0.6 m.
- Facial animation (blend shapes) needed? -> face topology with mouth/eye loops, mouth bag, separate eye spheres.

## Proportions (in heads; 1 head = head height)
- Realistic adult 7.5-8 heads; heroic 8-8.5; stylized game 5-7; cartoon / chibi 2-4; toy nutcracker / figurine 4-6.
- Crotch at ~half the height (realistic), lower on stylized/cartoon (shorter legs read cute, longer legs heroic).
- Shoulder width ~2 heads (male), wrists at crotch level with arms down, elbows at the navel / belt line.
- Measure the concept instead of using these whenever a concept exists (`concept_match.band()` / `color_regions()`).

## Construction
- Model ONE half on the asset's +X side and mirror (`mirror(ob, 'X')`); character faces -Y, centred on X = 0, feet
  on z = 0. Keep centre-line verts exactly on X = 0 (QA symmetry in `inspect_model.analyze`).
- Order: blockout from primitives (head, torso, pelvis, limbs as cylinders/lathe) -> check proportions against the
  concept -> merge into a clean base mesh (deforming) or keep parts (rigid) -> secondary forms (clothing layers, armour)
  -> tertiary (buttons, straps, trims) as separate small parts that follow one bone.
- Clothing is modelled ON the body with real thickness; delete hidden body under tight clothing for games (saves
  tris, avoids poke-through) but keep it where clothing can move away.
- Hands: 4-5 fingers, slightly curled and spread, thumb at ~45 deg; mittens/gloves for stylized and toy characters.
  Feet: flat sole on z = 0, toe spring for boots.

## Topology for deformation (deforming meshes)
- All quads on the skin; triangles only in hidden or rigid spots. Poles (5-edge) away from joints.
- 3 edge loops per bending joint (elbow, knee, finger knuckles), 5+ around the shoulder and hip; loops perpendicular
  to the bone. Loops around eyes and mouth (face rigs). Edge flow follows muscles on realistic characters.
- Even quad size; denser where it bends or the silhouette curves; lighter on flat back/thighs.
- Rigid parts (toys, robots): each part closed, no shared verts, pivot at the joint it rotates around, small gaps or
  overlaps at joints that survive rotation (ball joints, sleeves overlapping cuffs).

## Budgets (tris)
- Mobile 3-8k, stylized/indie game 8-25k, AAA hero 40-100k (+ LODs), crowd NPC 5-15k, cartoon 5-20k, low poly 500-3k.
- Hair: cards (game) or ribbons; count separately (often +20-50%).

## UV and textures
- One texture set for body (+ separate sets for head/hair on hero characters). Face gets 1.5-2x texel density.
- Seams hidden: inside arms/legs, under hair, along clothing seams, under the jaw; symmetrical halves may stack UVs
  (`allow_uv_overlap` in the brief) only when no unique detail is baked (no AO/asymmetric paint).
- Toy / painted-wood look: flat materials per region + baked AO and edge highlights; no noise.

## Export / hand-off (SKILL.md section 10, `handoff.py`)
- Bind pose as requested, at world origin, scale 1, facing -Y (Blender) -> engine forward after FBX axis conversion.
- Handoff builds the deform skeleton from the same landmarks the model was measured with (`biped()`), skins the
  joined mesh (rigid parts: one bone per part; soft: auto weights), checks weights, renders a pose test and writes
  notes for the animator. Plan the joints while modelling: a rigid part can only follow ONE bone, so split parts
  where they must bend (elbow, knee, jaw) or accept one-piece limbs (wooden toys).
- Bones for secondary motion (hair, tails, plumes, capes, hat, epaulettes, jaw) are cheap - add them as `extra`
  and list them as spring candidates.
- The static SM_ export is a reference; the skeletal export (SK_<Name>.fbx + clips) is the animator skill's job.

## Review checklist
- Front/side/back silhouette vs concept (`review(concept={...})`), proportions in heads, symmetry.
- Close-ups: face, hands, feet. Wire render on joints (enough loops?). Scale next to `scale_ref='human'`.
- Pose the arm parameter to the bind pose and re-render (shoulders must not collapse or intersect the torso).
