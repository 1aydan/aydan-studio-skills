# Gameplay systems - engine-agnostic craft

Read when designing a gameplay system. Engine specifics (APIs, naming, lifetime) live in `engines/<engine>.md`.
Everything here is "when you need it": start with the simplest version that plays right, add structure only when
a real second use or a real problem shows up.

## Architecture
- **Composition over inheritance.** Small components/nodes with one job (Health, Interactor, Inventory, Hitbox)
  on actors; keep class hierarchies shallow (one base character + variants).
- **Data vs logic.** Tuning and content in data assets / ScriptableObjects / Resources; behaviour in code.
- **One owner per piece of state.** Others read it or get told when it changes. No two systems writing health.
- **Call down, signal up.** Owners call their components/children directly; components report up with
  events/delegates/signals. Siblings talk through the owner. No global event bus unless the project has one.
- **Modal behaviour = state machine.** An enum + switch is enough until states carry their own data/logic; then
  state objects. Keep transitions in one place.
- **Globals only for global services** (save, settings, audio, matchmaking) via the engine's mechanism (Unreal
  subsystems, Unity bootstrapped service/ScriptableObject, Godot autoload) - never for gameplay state lookups.
- **UI observes gameplay** (events/bindings/view models). Gameplay code never references widgets.

## Time and frames
- Rates x delta time; forces and physics movement in the physics/fixed step; never per-frame constants.
- Frame-rate independent smoothing: `value = lerp(value, target, 1 - exp(-sharpness * dt))`.
- Cooldowns/durations: store "ready at" game time or count down by dt; respect pause and time dilation
  (game time vs real time for UI).
- Don't depend on update order between objects; make dependencies explicit (init order, events, ticking groups).

## Player feel
- Act on input the same frame; buffer inputs ~0.1-0.15 s (attack, jump) and allow coyote time ~0.1 s.
- Acceleration/deceleration and separate air control instead of instant velocity; expose them as tunables.
- Hit feedback is layered and tunable: hit-stop (30-100 ms), small camera shake, flash, sound, numbers.
- Camera: smoothing with lag, collision, look-ahead; never fight player input.
- Animation serves gameplay: gameplay decides, animation follows (events/notifies mark active frames). Root motion
  only when the design needs authored movement.

## Movement and character controllers
- Start from the engine's controller (Unreal CharacterMovementComponent, Unity CharacterController / Rigidbody,
  Godot CharacterBody2D/3D + `move_and_slide`); write a custom one only for movement it can't express.
- Kinematic (code owns velocity) for precise platformers/action; physics-driven (forces) for vehicles, ragdolls,
  physics toys. Don't mix both on one body.
- Input -> desired direction (camera-relative for 3D) -> acceleration toward max speed -> gravity -> move. Keep
  each as a tunable: max speed, acceleration, braking, air control, gravity scale, jump height (derive jump
  velocity from height: `v = sqrt(2 * g * h)`).
- Ground checks via the engine (`is_on_floor`, `isGrounded`, movement mode); slopes, steps and moving platforms
  are the engine's job - test them.
- Movement modes (walk, sprint, crouch, air, swim, climb, dash) are states with clear enter/exit rules.

## Cameras
- Use the engine rig (Unreal SpringArm + Camera / camera modes, Unity Cinemachine, Godot SpringArm3D / Camera2D
  smoothing) before custom code.
- Follow with damped lag, collision push-in, look-ahead in the move direction; separate player look input from
  automatic adjustments. Camera shake and FOV kicks are small, short and tunable.
- Update the camera after the target moves (late update / camera manager / process priority) to avoid jitter.

## Combat, abilities, damage
- One damage entry point with a damage info struct (amount, type, instigator, causer, hit point). The health
  component clamps, fires "changed", and handles death exactly once (guard re-entrancy).
- Melee: sweep/overlap only during active frames; one hit per target per swing (reset the hit list per attack).
  Fast projectiles: sweeps/raycasts, not tiny colliders.
- Costs, cooldowns and requirements checked in one `CanActivate`-style place (or the engine's ability system).
- Statuses/buffs are data (duration, stacking rule, magnitude); stacking rules explicit.
- Edge cases to handle on purpose: death during an ability, target destroyed mid-hit, respawn, pause, level reload.

## AI
- State machine first; behaviour/state trees when behaviours grow; utility scoring only for choice-heavy AI.
  Use the engine's tools (Unreal Behavior Tree / StateTree + AI Perception, Unity NavMesh, Godot NavigationAgent).
- Perception and decisions throttled (e.g. 5-10 Hz) and staggered across agents, not every frame.
- Engine navmesh for movement; custom pathfinding only for grid/tactics games.

## Interaction, inventory, save
- Interaction: an interface / duck-typed `interact(instigator)` on interactables; the player finds the focus by
  trace or overlap; the prompt text comes from the interactable.
- Items = definition (data asset by id) + instance data (count, durability). Never put scene references in saves.
- Saves are plain data (ids, numbers, transforms, flags) with a version number; restore by id.

## Spawning, waves, pickups
- Spawn from data (enemy definition + spawn point + count/interval); spawn points are placed in the level.
- Waves: a small state machine (waiting -> spawning -> active -> cleared) driven by counts, not timers alone.
- Pickups: overlap -> apply effect (data) -> feedback -> destroy/return to pool; guard double pickup.

## Progression and economy
- XP curves, prices and drop tables are data (curve/table assets), never formulas scattered in code.
- One place changes currency/XP and fires "changed"; UI and quests listen.
- Unlocks/quests/achievements: id-based flags or counters checked on events, saved as plain data.

## UI logic
- UI binds to gameplay state (events, view models, polling a getter on a timer if that's all the engine offers);
  gameplay never calls into widgets.
- Input context switches when menus open (pause game input, show cursor); restore on close.
- Text and numbers formatted in UI code; localization-ready strings where the project localizes.

## Multiplayer (only when the project is networked)
- Server-authoritative: the server owns health, damage, spawning, inventory, scores. Clients send intent (input,
  requests); validate every client request (range, cooldown, ownership).
- Replicate state for anything late joiners need; RPCs/multicasts for one-off cosmetic events.
- Predict only what latency makes visible (movement, firing feedback) and use the engine's movement prediction.
- Keep replicated state small; think about relevancy and update rates.

## Performance
- Budget: 16.6 ms per frame at 60 fps (33.3 at 30); gameplay code usually gets a few ms of that.
- Hot paths (tick/update, per-hit code): no searches by name/tag/type, no allocations, no string building;
  cache references at init.
- Events and timers over polling; disable tick/update on idle objects.
- Pool frequently spawned objects (projectiles, VFX, damage numbers) when counts or the profiler say so.
- Profile before optimizing (Unreal Insights, Unity Profiler, Godot Profiler/Monitors).

## Debugging and testing
- Debug draws/overlays behind a toggle (cvar, debug menu, input action); logs in a named category.
- Keep pure logic (formulas, rules, state transitions) in plain classes/functions so it can be unit-tested
  without a scene.
- Every delivery gives playtest steps: what to do, what should happen.
