# Unreal Engine 5 - gameplay engineering guide

Standards (official, UE 5.8 as of Oct 2026 - C++20 default and minimum):
- Epic C++ Coding Standard - dev.epicgames.com/documentation/unreal-engine/epic-cplusplus-coding-standard-for-unreal-engine
- Recommended asset naming - .../recommended-asset-naming-conventions-in-unreal-engine-projects
- Gameplay Framework, UPROPERTY/UFUNCTION, object pointers, asset management, Enhanced Input, networking,
  logging/asserts, modules, testing pages on dev.epicgames.com (topics below)
Default split: C++ base classes for systems and rules, Blueprint subclasses for content, tuning and polish.

## C++ coding standard (Epic)
**Naming** - PascalCase, no underscores between words, U.S. English; types/variables are nouns, methods verbs.
| Prefix | For | Example |
|---|---|---|
| `U` | UObject-derived | `UHealthComponent` |
| `A` | AActor-derived | `AProjectile` |
| `F` | other classes and structs | `FDamageInfo` |
| `E` | enums (`enum class`) | `EWeaponState` |
| `I` | abstract interfaces (no data members) | `IInteractable` |
| `T` | templates (template params use `In`: `InElementType`) | `TArray` |
| `S` | Slate widgets | `SInventoryPanel` |
| `b` | bool variables, incl. params (`bOutFound`) | `bIsDead` |
- Typedefs take the prefix of what they alias. UHT enforces prefixes on reflected types.
- Bool-returning functions ask a question (`IsAlive()`, `CanFire()`); procedures are strong verb + object
  (`ApplyDamage`) - avoid vague `Handle...`/`Process...`; value functions name the value (`GetRemainingAmmo`).
- Written-to reference params get an `Out` prefix (`OutHitResult`). Macros: ALL_CAPS with `UE_` prefix.
- Files named after the type without prefix (`HealthComponent.h` for `UHealthComponent`).
- One variable per declaration line.

**Types**
- Sized types for anything serialized or replicated: `int32`, `uint8`, `int64`, `float`, `double`; `int` only
  where width doesn't matter. `TEXT("...")` around every string literal. `FString` (text), `FName` (ids),
  `FText` (player-facing, localized).
- UE containers (`TArray`, `TMap`, `TSet`) and smart pointers (`TSharedPtr`, `TUniquePtr`); std containers/strings
  only in interop code. `<atomic>`, `<type_traits>`, `<limits>`, `<cmath>` are allowed. Never mix UE and std idioms
  in one API.

**Formatting**
- Tabs (size 4) for indentation. Braces on their own line, always - also for single-statement bodies; brace every
  `if/else` branch. `FType* Ptr` spacing. No space between function name and `(`. End files with a blank line.
- `switch`: every non-empty case ends with `break`/`return`/`continue` or `// falls through`; always a `default`.
- Public interface first in a class, then protected/private. Members private by default; mark classes not meant
  for inheritance `final`.

**Modern C++ rules**
- `nullptr` (never `NULL`), `override` on every override (plus `virtual`), `static_assert`, range-based for
  (`for (const TPair<FName, int32>& Pair : Map)`), `enum class` (Blueprint-exposed enums are `uint8`, flag enums
  use `ENUM_CLASS_FLAGS` + `None = 0`), `MoveTemp`, default member initializers in game code.
- `auto`: avoid - only for lambdas, verbose iterators, hard template types (write `const auto&`). No structured
  bindings.
- Lambdas: short, **explicit captures** (never `[&]`/`[=]`); deferred lambdas never capture locals/members by
  reference and capture UObjects weakly (`TWeakObjectPtr`, `CreateWeakLambda`).
- Const correctness: const refs for inputs, `const` methods that don't mutate, never return a by-value `const`.

**Headers and API**
- `#pragma once`; include what you use (IWYU), forward-declare in headers, `.generated.h` last include.
- `Public/` for headers other modules use, `Private/` for the rest; prefer `PrivateDependencyModuleNames`.
- No `using namespace` at global scope (breaks unity builds). Reflected types (`UCLASS`...) can't be in namespaces;
  non-reflected helpers go in `UE::<Area>` / `...::Private`.
- No bool flag params - use an enum (`ESpawnFlags`) unless the bool is the whole state (`SetEnabled(bool)`).
  Long parameter lists -> a params struct. Pass UObjects by pointer and handle null.
- Comments explain why; JavaDoc-style `/** */` on public declarations (`@param`, `@return` only when useful).
- Fix warnings; no `#pragma` suppression except as a last resort. Copyright line per the project's notice
  (Project Settings > Description) when the project uses one.

## Asset and project naming
`Prefix_AssetName_Descriptor_Variant`: `BP_` Blueprint, `ABP_` Anim Blueprint, `WBP_` widget, `AC_` actor
component BP, `BI_` interface, `DT_` data table, `CT_` curve table, `E_` enum, `F_` struct, `SM_`/`SK_` meshes,
`SKEL_`, `PHYS_`, `AM_` montage, `AS_` anim sequence, `BS_` blend space, `M_`/`MI_` materials, `T_` textures,
`FXS_`/`FXE_` Niagara, `LS_` sequence. Common (template convention): `IA_` input action, `IMC_` mapping context,
`DA_` data asset. The project's existing scheme wins.

## Gameplay Framework - what goes where
| Class | Lives | Put here |
|---|---|---|
| GameInstance (+ subsystems) | whole process, not replicated | anything that survives level loads (session, settings, save) |
| GameMode | **server only** | rules: spawning, respawn, scoring rules, win conditions, player login |
| GameState | server, replicated to all | match-wide state clients need (score, timer, objectives) |
| PlayerState | per player, replicated to all | per-player state that survives death (name, score, team; ASC for GAS) |
| PlayerController | server + owning client | input context, camera, UI ownership, player intent; persists across pawns |
| Pawn / Character | possessed body | movement, body-specific abilities, components; resets on respawn |
| HUD / UMG widgets | local | presentation only - bind to gameplay state |
- Components (`UActorComponent`, `USceneComponent`) for reusable behaviour (health, interaction, inventory).
- Subsystems instead of bloating engine classes: `UGameInstanceSubsystem`, `UWorldSubsystem` (per world,
  `UTickableWorldSubsystem` if it ticks), `ULocalPlayerSubsystem`; `GetSubsystem<T>()` from the owner.
- Gameplay Tags for states, damage types, ability ids (`UE_DECLARE_GAMEPLAY_TAG_EXTERN` / `UE_DEFINE_GAMEPLAY_TAG`).
- GAS (`GameplayAbilities` plugin) for ability-heavy games (RPG, MOBA, action): abilities, attributes, effects,
  cooldowns, prediction. Don't add it for a handful of simple actions; use it if the project already does.
- AI: AIController + Behavior Tree or StateTree, AI Perception, navmesh.

## C++ and Blueprint
- `UCLASS(Blueprintable)` bases; designers make `BP_` subclasses that set meshes, sounds, values.
- `UFUNCTION(BlueprintCallable)` actions, `BlueprintPure` cheap const getters (pure nodes re-run every use),
  `BlueprintImplementableEvent` cosmetic hooks (no C++ body), `BlueprintNativeEvent` C++ default +
  `_Implementation` (non-virtual declaration; override the `_Implementation`).
- Exposed private members need `meta = (AllowPrivateAccess = "true")`.
- Tuning: `UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Combat", meta = (ClampMin = "0",
  Units = "s"))`. `EditAnywhere` only for per-instance level tweaks. `VisibleAnywhere` for components.
- Never hard-code asset paths (`ConstructorHelpers::FObjectFinder`) for content designers swap - expose a
  `TSubclassOf<>` / soft pointer property and set it in the Blueprint.
- Heavy per-frame logic and math in C++; Blueprint for event-driven glue. Reusable logic in Blueprint classes, not
  the Level Blueprint.

## Object lifetime and pointers
- UObjects stay alive only through `UPROPERTY` references (or other GC-visible refs). A raw member pointer without
  `UPROPERTY` is invisible to GC and can dangle.
| Use | Type |
|---|---|
| owned/strong member reference | `UPROPERTY() TObjectPtr<UFoo> Foo;` |
| function params, locals | raw `UFoo*` |
| non-owning/cached, lambda captures | `TWeakObjectPtr<UFoo>` (`Get()` / `IsValid()`) |
| content loaded on demand | `TSoftObjectPtr<>` / `TSoftClassPtr<>` |
| class to spawn | `TSubclassOf<AActor>` |
| non-UObject holder | `FGCObject::AddReferencedObjects` |
- `IsValid(Obj)` checks null and pending-kill. Destroyed actors' UPROPERTY refs are nulled; raw ones are not.
- Spawn with `GetWorld()->SpawnActor<T>(Class, Transform, Params)`; deferred spawn
  (`SpawnActorDeferred` + `FinishSpawning`) when values must be set before `BeginPlay`.
- `NewObject<T>(Outer)` for UObjects; never `new`/`delete` UObjects.
- Components created in the constructor with `CreateDefaultSubobject<T>(TEXT("Name"))`.
- Bind delegates to UObjects with `AddUObject`/`AddDynamic` (auto-safe) and unbind in `EndPlay` when the
  source outlives you.

## Data
- `UPrimaryDataAsset` subclasses for definitions (weapons, enemies, items) - id via the Asset Manager, async
  loadable with bundles. Data Tables (`FTableRowBase` rows, `FDataTableRowHandle`) for spreadsheet-style data;
  Curve Tables / `UCurveFloat` for progressions. Don't keep row pointers beyond local scope.
- Load async: `UAssetManager::GetStreamableManager().RequestAsyncLoad(...)` or `LoadPrimaryAsset`; sync
  `LoadObject` hitches - avoid at runtime.
- Config defaults (`UPROPERTY(Config)`) / developer settings (`UDeveloperSettings`) for project-wide knobs.

## Input (Enhanced Input)
- `UInputAction` assets (bool / Axis1D / Axis2D / Axis3D) + `UInputMappingContext` added through
  `UEnhancedInputLocalPlayerSubsystem::AddMappingContext(IMC, Priority)` for the local player.
- Bind in `SetupPlayerInputComponent`: `CastChecked<UEnhancedInputComponent>(PlayerInputComponent)
  ->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AMyCharacter::Move);` with
  `void Move(const FInputActionValue& Value)` and `Value.Get<FVector2D>()`.
- Hold/tap/chords via triggers and modifiers on the asset, not timers in code. Swap contexts for menus/vehicles.
- Build.cs: `"EnhancedInput"`. Debug: `showdebug enhancedinput`.

## Tick and performance
- Turn tick off unless needed: `PrimaryActorTick.bCanEverTick = false;` (constructor). If needed:
  `TickInterval`, `SetActorTickEnabled(false)` when idle, right `TickGroup` (`TG_PostPhysics` for aim/traces).
- Timers over Tick for delays and periodic checks: `GetWorldTimerManager().SetTimer(Handle, this,
  &AFoo::Fire, Rate, bLoop)`; clear in `EndPlay`. Game thread only.
- Events/delegates (`DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam`) over polling.
- No `GetAllActorsOfClass`, `FindComponentByClass`, casts or string/FName building in Tick - cache in `BeginPlay`.
- Profile: `stat game`, `stat unit`, Unreal Insights.

## Networking
- Server-authoritative. `bReplicates = true` (+ `SetReplicateMovement(true)`) in the constructor; replicate state
  that drives visuals, not meshes/FX.
- Properties: `UPROPERTY(ReplicatedUsing = OnRep_Health) float Health;` + `UFUNCTION() void OnRep_Health(float
  OldHealth);`, registered in `GetLifetimeReplicatedProps` (call `Super::` first) with `DOREPLIFETIME` /
  `DOREPLIFETIME_CONDITION(..., COND_OwnerOnly)`. C++ OnRep doesn't run on the server - call it yourself if the
  server needs the same reaction.
- RPCs: `UFUNCTION(Server, Reliable)` etc. - `Reliable`/`Unreliable` is required; implement
  `Name_Implementation`; names prefixed `Server`/`Client`/`Multicast`. Only the owning client can call a Server
  RPC. Reliable only for rare important events; unreliable for frequent/cosmetic. `WithValidation` +
  `_Validate` returning false disconnects the caller - also validate inside the implementation.
- Guard with `HasAuthority()` (server logic) and `IsLocallyControlled()` (local input/UI). Role != ownership.
- Prefer replicated state + OnRep over multicasts (late joiners get state). Use the CharacterMovementComponent for
  predicted movement; GAS for predicted abilities.
- Push model (`bIsPushBased` + `MARK_PROPERTY_DIRTY_FROM_NAME`) and Iris only if the project uses them.

## Logging and assertions
- Own category: `DECLARE_LOG_CATEGORY_EXTERN(LogMyGame, Log, All);` + `DEFINE_LOG_CATEGORY(LogMyGame);`
  - not `LogTemp`. `UE_LOG(LogMyGame, Warning, TEXT("%s"), *Name)` or structured
  `UE_LOGFMT(LogMyGame, Log, "Hit {Target}", TargetName)` (`Logging/StructuredLog.h`).
- `check(Expr)` invariants (compiled out in Shipping - no side effects); `ensure(Expr)` recoverable
  "shouldn't happen" (`if (!ensure(Ptr)) { return; }`); `verify(Expr)` when the expression must always run.
- On-screen debug (`GEngine->AddOnScreenDebugMessage`) and debug draws only behind a cvar/toggle.

## Modules, building, Live Coding
- Game code in `Source/<Module>/` with `Public/` + `Private/`; add engine modules to Build.cs
  (`"EnhancedInput"`, `"GameplayTags"`, `"GameplayAbilities"`, `"UMG"`, `"AIModule"`, `"NetCore"`...).
  Regenerate project files after adding files or Build.cs changes.
- Live Coding (Ctrl+Alt+F11) patches function bodies; new classes, header, reflection (UPROPERTY/UFUNCTION) or
  constructor-default changes need the editor closed and a full build. UBT refuses to build while Live Coding is
  active.
- CLI: `Engine/Build/BatchFiles/Build.bat <Project>Editor Win64 Development -Project="<path>.uproject" -WaitMutex`.

## Testing
- Automation tests in `Private/Tests/`, guarded by `WITH_DEV_AUTOMATION_TESTS`:
  `IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDamageTest, "MyGame.Combat.Damage", EAutomationTestFlags::EditorContext |
  EAutomationTestFlags::EngineFilter)` + `RunTest` with `TestEqual/TestTrue`. Spec tests (`BEGIN_DEFINE_SPEC`,
  `Describe/It`) for BDD style; CQTest (`TEST_CLASS`, `ActorTestSpawner`) for actor/world tests; Functional Tests
  (`AFunctionalTest` in a map) for gameplay scenarios.
- 5.5+: `EAutomationTestFlags` is an enum class; masks are `EAutomationTestFlags_ApplicationContextMask` (old
  `EAutomationTestFlags::ApplicationContextMask` no longer exists).
- CLI: `UnrealEditor-Cmd.exe <Project>.uproject -ExecCmds="Automation RunTests MyGame.;Quit"
  -TestExit="Automation Test Queue Empty" -ReportExportPath=<dir> -unattended -nullrhi -nopause` (`verify.py`).

## Pitfalls
- Raw `UObject*` members without `UPROPERTY` (GC dangling) and `[&]`/`this` captures in delayed lambdas.
- Doing server logic on clients: GameMode is null on clients; check `HasAuthority()` before changing state.
- `BeginPlay` order between actors is not guaranteed - don't assume another actor is initialized; use events or
  `PostInitializeComponents` for own components.
- Constructor runs for the CDO: no gameplay logic, world access or spawning there - do it in `BeginPlay`.
- Hard references in widely used classes pull whole asset chains into memory - soft refs + async load.
- UE4-era APIs: legacy `InputComponent->BindAxis/BindAction` (use Enhanced Input), raw UPROPERTY pointers
  (use `TObjectPtr`), `TEnumAsByte` for `enum class`, `GetWorld()->GetTimerManager()` from non-world objects.
- Changing a `UPROPERTY` name/type breaks saved Blueprint values - use `meta=(DeprecatedProperty)` / core
  redirects when renaming exposed members.

## Review checklist
- [ ] prefixes, `b` bools, verb/question function names, `TEXT()`, sized types, tabs + braces on new lines
- [ ] logic in the right framework class (server rules in GameMode, shared state in GameState/PlayerState)
- [ ] UObject refs: `UPROPERTY TObjectPtr` members, weak for non-owning, soft for optional content
- [ ] tunables `EditDefaultsOnly` with category, clamps, units; no hard-coded asset paths
- [ ] tick disabled unless needed; timers/delegates instead of polling; nothing expensive in Tick
- [ ] Enhanced Input; net: authority checks, OnRep state, RPCs validated and rarely reliable
- [ ] own log category; `check`/`ensure` used correctly; includes minimal, `#pragma once`
- [ ] UE5 APIs for the project's minor version; full build after header/reflection changes
