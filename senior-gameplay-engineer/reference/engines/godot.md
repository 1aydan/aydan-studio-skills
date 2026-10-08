# Godot 4 - gameplay engineering guide

Standards (official, stable docs = Godot 4.7 as of Oct 2026, latest 4.7.2):
- GDScript style guide - docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html
- Static typing - .../scripting/gdscript/static_typing.html, warnings - .../gdscript/warning_system.html
- C# style guide - .../scripting/c_sharp/c_sharp_style_guide.html
- Best practices - .../tutorials/best_practices/ (scene organization, autoloads, node alternatives, notifications,
  data/logic preferences, project organization, version control)
Default language GDScript; C# needs the .NET editor build (C# 12 / .NET 8; no web export).

## GDScript coding standard
**Formatting**
- UTF-8 without BOM, LF line endings, one LF at end of file. Indent with **tabs**.
- Continuation lines: **2 indent levels**; contents of multiline arrays/dictionaries/enums: 1 level, with a
  **trailing comma** after the last element (none on single-line lists).
- **Two blank lines** around functions and inner classes; one blank line inside functions to split logic.
- Lines under 100 characters (aim for 80). One statement per line (ternary is the only inline exception).
- Wrap long conditions in **parentheses** (not `\`); put `and`/`or` at the start of the continuation line.
- `and`, `or`, `not` - never `&&`, `||`, `!`. No unnecessary parentheses (`if is_alive:` not `if (is_alive):`).
- `# comment` / `## doc comment` with a space; commented-out code without (`#print(x)`). Comments on their own line.
- One space around operators and after commas; none inside call/index brackets; `{ "a": 1 }` for one-line dicts;
  no alignment padding.
- Double quotes (single only if it saves escapes). Numbers: `0.5`, `13.0`, lowercase hex `0x8bf`, `1_000_000`.

**Naming**
| Element | Style | Example |
|---|---|---|
| Files, folders | snake_case (class_name `YAMLParser` -> `yaml_parser.gd`) | `player_controller.gd` |
| Classes (`class_name`), nodes | PascalCase | `class_name PlayerController` |
| Preloaded class constant/var | PascalCase | `const Weapon = preload("res://weapon.gd")` |
| Functions, variables | snake_case | `func apply_damage(amount: int)` |
| Signals | snake_case, **past tense** | `signal health_changed(old: int, new: int)` |
| Constants, enum members | CONSTANT_CASE (enum members one per line) | `const MAX_SPEED := 8.0` |
| Enum names | PascalCase, singular | `enum State { IDLE, RUN, }` |
| Private members, virtuals users override | leading `_` | `var _cooldown_left := 0.0` |
| Input actions, groups | snake_case | `"move_left"`, `"enemies"` |

**Code order**
```
01. @tool, @icon, @static_unload       (@abstract goes before class_name)
02. class_name
03. extends
04. ## doc comment
05. signals
06. enums
07. constants
08. static variables
09. @export variables
10. remaining regular variables
11. @onready variables
12. _static_init()
13. remaining static methods
14. overridden built-in virtuals: _init, _enter_tree, _ready, _process, _physics_process, then the rest
15. overridden custom methods
16. remaining methods
17. inner classes
```
Public before private within each group. A member used by only one method is a local instead; declare locals
next to first use.

**Static typing (write typed GDScript)**
- `:=` when the type is obvious on the line (`var dir := Vector3.ZERO`); explicit when ambiguous
  (`var health: int = 0`); typed params and returns always (`func _process(delta: float) -> void:`).
- `get_node()` / `$` can't infer - state the type: `@onready var bar: ProgressBar = $UI/LifeBar`.
- Typed collections: `Array[Enemy]`, `Dictionary[StringName, int]` (4.4+; both types required, `Variant` for
  "any"). No nested typed collections (`Array[Array[int]]` is invalid).
- `as` returns `null` on mismatch - prefer `if body is Player:` checks. Typed code runs faster (typed opcodes).
- Teams can enforce it: Project Settings > Debug > GDScript (Advanced) - set `untyped_declaration` /
  `unsafe_*` to Warn or Error. Suppress per line with `@warning_ignore("name")`, regions with
  `@warning_ignore_start/_restore` (4.4+). Addons are excluded by `directory_rules` (4.6+) - keep that rule.

## C# in Godot
- Microsoft-style: 4 spaces, **Allman braces**, lines ~100 chars, LF, explicit access modifiers.
- PascalCase types/methods/properties/constants/events; **private fields `_camelCase`**; locals/params camelCase;
  acronyms `UI` / `uiManager`, `Id`. `var` only when the type is obvious.
- Classes deriving from GodotObject (Node, Resource...) **must be `partial`** (GD0001), and the file name must
  match the class name.
- Signals: `[Signal] public delegate void HealthChangedEventHandler(int oldValue, int newValue);` (suffix
  required) -> connect with `+=` (`timer.Timeout += OnTimerTimeout;`), emit with
  `EmitSignal(SignalName.HealthChanged, a, b)` - never `Invoke`. Disconnect custom `+=` connections in
  `_ExitTree` (only engine signals/non-capturing lambdas clean up automatically).
- `[Export]` on fields/properties (rebuild to see them); `[GlobalClass]` for custom nodes/resources (resources
  need a parameterless constructor). `GetNode<T>("Path")` in `_Ready` replaces `@onready`; `GD.Load<T>()` replaces
  `preload`. Use generated `MethodName.X` / `PropertyName.X` / `SignalName.X`, never string literals
  (`CallDeferred("AddChild")` fails - the engine expects snake_case).
- `GodotObject.IsInstanceValid(obj)` for freed objects; struct properties can't be modified in place
  (`Position = Position with { X = 1 }` or reassign).

## Project and file organization
- Group by feature, assets next to their scenes: `characters/player/player.tscn + player.gd + player.png`.
- snake_case files/folders (C# scripts PascalCase after their class); third-party code in `addons/`.
- Exported builds are case-sensitive - a path casing mismatch that works in the editor breaks the build.
- Commit `project.godot`, `.tscn/.tres`, `.import` and **`.uid` files (4.4+)**, `.sln/.csproj`; ignore `.godot/`.

## Architecture
- A scene + its root script = one class. Scripts are for reusable tools (`class_name` + icon); scenes for
  game-specific concepts. Prefer scenes for big hierarchies (built faster than code).
- Scenes are self-contained: **call down, signal up**. Parents call children directly; children emit signals;
  siblings talk through a common ancestor. When a scene needs outside things, the parent injects them (signal
  connection, Callable property, node reference, or `@export var target: Node`).
- Node tree = aggregation (if the parent goes, should the child?). Keep player controllers out of the level scene.
  Break transform inheritance with `top_level = true` or `RemoteTransform3D` instead of reparenting.
- Autoloads only for broad-scope systems that own their own data (save, settings, scene transitions, audio buses).
  Shared helpers -> `static func` on a `class_name` script; shared data -> a custom Resource.
- Not everything is a Node: plain data -> `RefCounted` (auto-freed) or `Resource` (serializable, inspector
  editable); tens of thousands of nodes cost performance.
- State machines: an enum + `match` in the owner script first; node-per-state only when states grow large.
- Validate required setup with `@tool` + `_get_configuration_warnings()` on reusable scenes.

## Lifecycle and lifetime
- Init order: defaults -> initializers -> `_init()` -> exported values -> `@onready` -> `_ready()`.
  `_enter_tree` runs top-down, `_ready` bottom-up (children first), once per node.
- `_process(delta)` for per-frame visuals; `_physics_process(delta)` for movement/physics (fixed step). Checks that
  don't need every frame -> a `Timer`.
- `queue_free()` (end of frame) over `free()`; test freed objects with `is_instance_valid(obj)`, not `== null`.
- `call_deferred()` / `set_deferred()` when changing the tree or physics state inside callbacks.
- Set a node's properties **before** `add_child()` (except tree-dependent ones like `global_position`).
- `change_scene_to_file/packed` swaps at end of frame - `current_scene` is null meanwhile.
- `@export` + `@onready` on one variable is an error (ONREADY_WITH_EXPORT) - pick one.

## Data
- Custom Resources for definitions and tuning: `extends Resource` + `class_name` + `@export` fields -> `.tres`.
  Loaded resources are **shared** - `duplicate()` before mutating per-instance state. Never define a Resource as
  an inner class (won't serialize); every `_init` parameter needs a default.
- `@export_range(0, 10, 0.1, "suffix:m")`, `@export_group`, `@export_enum`, `@export_flags_3d_physics`,
  `@export_tool_button` (4.4+), typed array exports `Array[PackedScene]`. Give exports plain defaults (a preloaded
  default is overwritten by the scene anyway).
- `preload` (static path, at load time) for small fixed dependencies; `load` / `ResourceLoader.load_threaded_*`
  for big or optional content. Split big scenes.
- Node references: `@onready` var (fastest) > `$Path` > `get_node()`; scene-unique `%Name` for nodes the script
  owns (scoped to that scene).

## Input
- InputMap actions (Project Settings > Input Map), never raw keycodes.
- Gameplay input in `_unhandled_input(event)` so UI gets events first; `event.is_action_pressed("jump")` for
  presses, `Input.get_vector("move_left", "move_right", "move_forward", "move_back")` polled in
  `_physics_process` for movement. Mark consumed events with `get_viewport().set_input_as_handled()`.
- Don't poll press events in `_process` (missed/duplicated presses).

## Signals
- `signal died` / `health_changed.emit(old, new)`; connect with Callables: `timer.timeout.connect(_on_timer_timeout)`,
  extra args via `.bind()`. Callback names `_on_<node>_<signal>`.
- Connect once (duplicate connections error); `is_connected()` before `disconnect()`.
  `CONNECT_ONE_SHOT` / `CONNECT_DEFERRED` flags when needed.
- `await some_signal` for sequences; tweens via `create_tween()` (`tween_await`, 4.7+).
- Groups for "all enemies" style broadcasts (`get_tree().call_group(...)`), not for finding a single node.

## Performance
- No `get_node`/`find_child`/`get_nodes_in_group` in per-frame code - cache in `@onready`/`_ready`.
- Typed GDScript is faster; avoid creating nodes/arrays per frame; pool frequently spawned scenes when the profiler
  shows spawn cost. Disable processing on idle nodes (`set_process(false)`, `process_mode`).
- Area/body signals over manual overlap polling; physics queries via `PhysicsDirectSpaceState3D` for one-off traces.
- Profile with the Debugger > Profiler / Monitors before optimizing.

## Multiplayer (high-level API)
- `ENetMultiplayerPeer` -> `multiplayer.multiplayer_peer = peer`; server is peer 1.
- `@rpc("authority" | "any_peer", "call_remote" | "call_local", "reliable" | "unreliable" | "unreliable_ordered",
  channel)` - channel last; call with `f.rpc()` / `f.rpc_id(id)`; `multiplayer.get_remote_sender_id()` to check
  the caller. RPC functions must exist on every peer at the same NodePath.
- `set_multiplayer_authority(id)` per player node; `is_multiplayer_authority()` guards input and simulation.
- `MultiplayerSpawner` replicates spawned scenes; `MultiplayerSynchronizer` replicates listed properties from the
  authority (no Object/Resource properties).
- Server-authoritative: validate every `any_peer` RPC (range, cooldown, ownership); never trust client positions,
  timers or damage.

## Testing and command line
- No official project test framework: GUT and gdUnit4 are community addons - use what the project has, ask before
  adding one. Keep rules/formulas in `RefCounted` classes so they test without a scene.
- `godot --headless --path <project> --import` (4.2.2+) builds the import + class caches;
  `-s <script> --check-only` parses one script; `--export-release "<preset>" <path>`; `--build-solutions` (C#).
  Windows: use the `_console` exe to see output. (`verify.py` wraps these.)

## Pitfalls (Godot 3 -> 4 and version gotchas)
| Godot 3 / wrong | Godot 4 |
|---|---|
| `export var`, `onready var`, `tool`, `setget` | `@export var`, `@onready var`, `@tool`, `var x: int: set = _set_x` / inline `set(value):` |
| `yield(obj, "sig")` | `await obj.sig` |
| `connect("sig", self, "m")`, `emit_signal("sig")` | `sig.connect(m)`, `sig.emit()` |
| `KinematicBody`, `Spatial`, `move_and_slide(vel, up)` | `CharacterBody3D`, `Node3D`, set `velocity` then `move_and_slide()` |
| `instance()`, `PoolStringArray`, `rand_range` | `instantiate()`, `PackedStringArray`, `randf_range` |
| `deg2rad`, `stepify`, `OS.get_ticks_msec()` | `deg_to_rad`, `snapped`, `Time.get_ticks_msec()` |
| `remote`/`master`/`puppet` funcs | `@rpc(...)` |
- 4.7: overriding a method with a typed return needs an explicit `return`; mouse/keyboard device IDs are
  `InputEvent.DEVICE_ID_MOUSE/KEYBOARD`. 4.6: new projects default to Jolt (3D physics). 4.5: `@abstract`,
  variadic `...args`. 4.4: typed dictionaries, `.uid` files, .NET 8. No traits/structs in any stable release.
- Signal arguments are not checked at emit time - keep declaration and emit in sync.

## Review checklist
- [ ] typed GDScript (params, returns, ambiguous vars); names/order per the style guide (or the project's style)
- [ ] scene is self-contained: calls down, signals up; dependencies injected or exported, no `get_parent()` chains
- [ ] input via actions in `_unhandled_input` / physics polling; movement in `_physics_process` with `delta`
- [ ] tunables `@export`ed (ranges, units) or in a Resource; shared Resources duplicated before mutation
- [ ] no per-frame node lookups/allocations; freed objects checked with `is_instance_valid`
- [ ] tree/physics changes in callbacks deferred; properties set before `add_child`
- [ ] multiplayer: authority checks, `any_peer` RPCs validated, paths identical on all peers
- [ ] Godot 4.x API for the project's minor version; C#: `partial`, `EventHandler` signals, generated names
