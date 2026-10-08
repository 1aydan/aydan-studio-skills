# Unity 6 - gameplay engineering guide

Standards (official, Unity 6.3 LTS / 6.6 as of Oct 2026 - **C# 9**, .NET Standard 2.1 API level):
- Unity e-book "Use a C# style guide for clean and scalable game code (Unity 6 edition)" -
  unity.com/resources/c-sharp-style-guide-unity-6 (+ sample sheet github.com/thomasjacobsen-unity/Unity-Code-Style-Guide)
- Microsoft C# naming/coding conventions (the baseline Unity's guide builds on) - learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/
- Unity e-books: "Level up your code with design patterns and SOLID", "Create modular game architecture with
  ScriptableObjects", "Optimize your game performance (Unity 6 edition)"; Unity Manual (serialization, execution
  order, asmdefs, Awaitable, Input System, Test Framework)
Unity's own advice: a team/project style guide wins; consistency matters most.

## C# coding standard
**Naming**
| Element | Style | Example |
|---|---|---|
| Classes, structs, enums, enum values, namespaces | PascalCase nouns | `EnemySpawner`, `WeaponType.Rifle` |
| Methods | PascalCase verbs | `ApplyDamage()`, `GetDirection()` |
| Public fields/properties | PascalCase (prefer properties) | `public int MaxHealth => m_maxHealth;` |
| Private instance fields | `m_` + camelCase (Unity default) | `[SerializeField] float m_moveSpeed;` |
| Private statics / constants | `s_` / `k_` + PascalCase | `static int s_activeCount;`, `const int k_MaxItems = 100;` |
| Locals, parameters | camelCase | `float damageTaken` |
| Interfaces | `I` + adjective | `IDamageable`, `IInteractable` |
| Bools | question form | `m_isDead`, `HasTarget`, `CanJump()` |
| Events | verb phrase, before/after tense | `public event Action DoorOpened;` / `OpeningDoor` |
| Flags enums | plural, `None = 0` | `[Flags] enum AttackModes { None = 0, Melee = 1 << 0 }` |
- Alternatives Unity lists: Microsoft `_camelCase` private fields (common in projects), `m_PascalCase` (Unity's
  internal engine/package code), or no prefix with `this.`. **Match the project** (inspect_project reports it);
  new projects use the Unity default above.
- No abbreviations except math/loop counters; no Hungarian notation, snake_case, Unicode identifiers or puns;
  no redundant context (`Score` in `Player`, not `PlayerScore`).
- Events: `System.Action`/`Action<T>` by default; the raising method is `OnDoorOpened()` (calls
  `DoorOpened?.Invoke()`); handlers in observers read `GameEvents_DoorOpened` or `HandleDoorOpened` per project.

**Formatting**
- 4 spaces, Allman braces (each brace on its own line), braces always - also for one-line bodies.
- One declaration per line; lines 80-120 chars; no column alignment; one space after commas and before `(` of
  `if/for/while/switch`, none after method names or inside parentheses.
- `var` only when the type is obvious from the right-hand side. `switch` always has `default`.
- Drop redundant initializers (`= 0`, `= null`). No `#region` (split the class instead).
- Comments explain why, on their own line, `// Capitalized.`; `/// <summary>` on public API; `[Tooltip]` instead of
  comments on serialized fields. No commented-out code, banners or journal comments.
- Namespaces (PascalCase, mirror folders) for project code; `using` at the top, unused ones removed.
- **C# 9 only**: no file-scoped namespaces, global usings, records in serialized types, `init` setters, raw
  strings, collection expressions, primary constructors, `required`.

**Class layout** - fields -> properties -> events -> Unity messages (`Awake`, `OnEnable`, `Start`, `Update`...,
`OnDisable`, `OnDestroy`) -> public methods -> private methods -> nested types. High-level first, helpers below.
- **One MonoBehaviour/ScriptableObject per file, file name = class name**, one namespace per such file.
- Small classes, small methods, few parameters (group 4+ into a struct). No mode-flag params
  (`GetAngleInDegrees` / `GetAngleInRadians`). Extension methods in `XxxExtensions` static classes.

## Project organization
- Gameplay code in `Assets/_Project/Scripts/<Feature>/` (or the project's layout) with **Assembly Definitions**
  per area (`Game.Runtime`, `Game.Editor`, `Game.Tests`): faster compiles, explicit dependencies, no cycles.
  Custom asmdefs can't reference `Assembly-CSharp`; tests need gameplay code in an asmdef.
- Editor code in an Editor-only asmdef (Include Platforms: Editor) or `Editor/` folder; editor calls inside
  runtime files only within `#if UNITY_EDITOR`.
- Assets named `PascalCase` with a type hint where the project does (`SO_`/`Data` suffix for ScriptableObjects
  optional); prefabs/scenes/YAML are not hand-edited - give editor steps.

## Architecture
- Components with one job each (`Health`, `Mover`, `Interactor`, `WeaponController`); compose on prefabs. Keep
  inheritance shallow; interfaces (`IDamageable`) for cross-cutting calls (`TryGetComponent<IDamageable>`).
- **ScriptableObjects** for data and config (weapon stats, enemy definitions, tuning) - shared flyweight data,
  treated as read-only at runtime (play-mode edits persist in the editor, runtime changes don't save in builds).
  SO event channels / runtime sets when decoupling across scenes is needed; plain C# events inside a prefab.
- Communication: direct references set in the Inspector (`[SerializeField] Health m_health;`) or `GetComponent`
  in `Awake`; C# events up. Subscribe in `OnEnable`, unsubscribe in `OnDisable`/`OnDestroy` - always.
- Singletons hide dependencies: acceptable for a few true services in small games; prefer serialized references,
  SO channels or a bootstrapper.
- State: enum + switch in the component first; state classes when states carry logic (State pattern).
- Patterns from Unity's e-book when they pay off: Object Pool, Command (undo/replay/input buffering), Observer,
  Strategy (SO-based), MVP for UI.

## Serialization
- `[SerializeField] private` over public fields; properties for read access. `[Range]`, `[Min]`, `[Tooltip]`,
  `[Header]`, units in the name (`m_dashDistanceMeters`) or tooltip.
- Serialized: public/`[SerializeField]` non-static, non-const, non-readonly fields of primitives, enums, Unity
  structs, `[Serializable]` classes/structs (attribute not inherited), `UnityEngine.Object` refs, `T[]`/`List<T>`.
  Not: properties (use `[field: SerializeField]`), nested containers, multidimensional arrays, dictionaries
  before 6.6.
- `[SerializeReference]` only for polymorphic/null/shared managed references (slower).
- **Renaming a serialized field loses data** unless `[FormerlySerializedAs("m_oldName")]`.

## Lifecycle
- Order: `Awake` -> `OnEnable` -> `Start` -> (`FixedUpdate` 0..n -> physics -> `OnTrigger*/OnCollision*`) ->
  `Update` -> animation -> `LateUpdate` -> render; `OnDisable` -> `OnDestroy`.
- `Awake`: own references/setup (runs even if the component is disabled); `Start`: talk to other objects. Order
  between objects is undefined - don't depend on it (`[DefaultExecutionOrder]` only when truly needed).
- No constructors on MonoBehaviours/ScriptableObjects; never `new` a Component (`AddComponent`,
  `Instantiate`, `ScriptableObject.CreateInstance`).
- Physics/Rigidbody in `FixedUpdate` (use `Time.fixedDeltaTime`); input reading and per-frame logic in `Update`
  (`Time.deltaTime`); camera follow in `LateUpdate`.
- `Destroy` at runtime (end of frame); `DestroyImmediate` is editor-only.
- Domain reload is off by default in new 6.6 projects ("Reload Scene only"): statics and static event subscribers
  survive play sessions - reset them with `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType
  .SubsystemRegistration)]`.

## UnityEngine.Object null rules
- Destroyed objects and unassigned inspector fields are "fake null": `== null` is true, the C# reference isn't.
- **Never use `?.`, `??`, `??=`, `is null` on UnityEngine.Object** - they skip Unity's check. Use
  `if (target == null)`, `if (target)`, or `TryGetComponent(out T c)`.
- Guard cached references across scene changes and destroyed targets.

## Async and timing
- Coroutines for simple sequences (stop with the GameObject; disabling the component doesn't stop them); cache
  `WaitForSeconds`.
- Unity 6 `Awaitable` (`await Awaitable.WaitForSecondsAsync(t, destroyCancellationToken)`, `NextFrameAsync`,
  `FixedUpdateAsync`) for async flows - pooled, never await the same instance twice. Pass
  `destroyCancellationToken` so work stops with the object.
- No `Task.Result`/`.Wait()` on the main thread; Unity APIs are main-thread only. `async void` only for event
  handlers (exceptions are otherwise lost).

## Input (Input System package)
- The Input System is the recommended path (old Input Manager is deprecated). Use actions, not raw devices:
  project-wide actions (`InputSystem.actions.FindAction("Move")` once in `Start`, `ReadValue<Vector2>()` /
  `WasPressedThisFrame()` in `Update`), the generated C# class (`Enable()` in `OnEnable`, `Disable()` in
  `OnDisable`), or `PlayerInput` for local multiplayer.
- Never `FindAction` in `Update`; never `Keyboard.current` outside prototypes; check which input handling the
  project uses (inspect_project `input_handling`).

## Data loading
- Addressables (async `Addressables.LoadAssetAsync<T>` + release) for content loaded on demand; `Resources` only
  for tiny bootstrap data. Direct serialized references for content a prefab always needs.

## Performance
- Cache `GetComponent`, `Camera.main`, `FindAction` results in `Awake`/`Start`; no `Find*`/`FindObjectsByType`,
  `GetComponent` or `SendMessage` per frame. `FindObjectOfType` is replaced by `FindFirstObjectByType` /
  `FindAnyObjectByType`.
- Zero allocations per frame: no LINQ, string concatenation, closures/lambdas, boxing or `params` in hot paths;
  reuse lists. `CompareTag("Enemy")` (not `.tag ==`), `Animator.StringToHash` / `Shader.PropertyToID` cached.
- Physics queries: `Physics.RaycastNonAlloc` / `OverlapSphereNonAlloc` with preallocated buffers; layer masks.
- Remove empty Unity messages (`Update() { }` still costs a call). Strip logs via `[Conditional]` wrappers.
- Pool frequent spawns with `UnityEngine.Pool.ObjectPool<T>` (`collectionCheck` in development, `maxSize`).
- Update managers only at hundreds+ of instances; profile first (Profiler on a development build on target,
  `ProfilerMarker` for your code). Budgets: 16.6 ms at 60 fps; leave headroom on mobile.

## Networking (Netcode for GameObjects 3.x)
- `NetworkBehaviour` on a `NetworkObject`; netcode setup in `OnNetworkSpawn` (not `Awake`/`Start`); guard logic with
  `IsSpawned` and `HasAuthority` / `IsOwner`.
- State in `NetworkVariable<T>` (server-write by default; late joiners get it); subscribe `OnValueChanged` in
  `OnNetworkSpawn`, unsubscribe in `OnNetworkDespawn`.
- RPCs: `[Rpc(SendTo.Server, InvokePermission = RpcInvokePermission.Owner)] void FireRpc(...)` - name ends in
  `Rpc`; legacy `[ServerRpc]`/`[ClientRpc]` are superseded. One-off events only; validate everything on the server.
- Use the project's existing netcode (NGO, Mirror, Fish-Net, Photon) - don't mix stacks.

## Testing and command line
- Unity Test Framework (NUnit): EditMode tests for pure logic (`[Test]`), PlayMode tests (`[UnityTest]`
  IEnumerator) only when frames/physics are needed. Test asmdefs reference `UnityEngine.TestRunner` (+
  `UnityEditor.TestRunner` for EditMode) and the gameplay asmdef.
- Keep rules/formulas in plain C# classes so they test without scenes.
- CLI: `Unity.exe -batchmode -nographics -projectPath <p> -runTests -testPlatform EditMode -testResults r.xml
  -logFile log.txt` (**no `-quit`** with `-runTests`); compile check = `-batchmode -nographics -quit -projectPath
  <p> -logFile log.txt` and look for `error CS`. Batchmode can't open a project that is open in the editor
  (`verify.py` wraps these).

## Pitfalls
- `?.`/`??` on Unity objects; forgetting to unsubscribe events (leaks, calls into destroyed objects).
- Renamed serialized fields without `[FormerlySerializedAs]`; class/file name mismatch (component won't attach).
- `Time.deltaTime` inside `FixedUpdate` math or multiplying `Rigidbody` forces by deltaTime twice;
  moving Rigidbodies through `transform` (use `MovePosition`/velocity).
- Static state surviving play sessions with domain reload off.
- Removed/obsolete APIs: `GetInstanceID` (6.5+ use `EntityId`), `FindObjectOfType`, `GameObject.rigidbody`
  shortcuts, `AddComponent(string)`, legacy `Input.GetAxis` in Input System projects, `[ServerRpc]` in NGO 3.x.
- C# 10+ syntax copied from .NET samples doesn't compile (Unity is C# 9).

## Review checklist
- [ ] naming per the project (or Unity default `m_`/`s_`/`k_`), Allman, braces always, file = class
- [ ] `[SerializeField] private` + tooltips/ranges; data in ScriptableObjects; renames keep `FormerlySerializedAs`
- [ ] references cached in `Awake`/`Start`; nothing allocating or searching per frame
- [ ] physics in `FixedUpdate`, input/logic in `Update`, camera in `LateUpdate`; deltaTime used correctly
- [ ] events subscribed in `OnEnable`, unsubscribed in `OnDisable`/`OnDestroy`; no `?.`/`??` on Unity objects
- [ ] Input System actions (no raw devices); async work cancels with `destroyCancellationToken`
- [ ] code in an asmdef; editor code guarded or in an editor asmdef
- [ ] netcode: server/authority checks, NetworkVariables for state, RPCs validated
- [ ] APIs valid for the project's Unity version and C# 9
