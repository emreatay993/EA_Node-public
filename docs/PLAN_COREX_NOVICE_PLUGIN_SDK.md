# COREX Novice Function Plugin SDK — Clean-Break Implementation Plan

## Summary

Replace COREX’s public class/descriptor plugin API with a novice-oriented, function-based SDK:

```python
import corex


@corex.node(
    id="custom.scale.a7c31e9b",
    name="Scale",
    category=("Math",),
)
@corex.input("value", value_type=float, required=True)
@corex.output("scaled", value_type=float)
@corex.slider(
    "factor",
    default=2.0,
    minimum=0.0,
    maximum=10.0,
    section="Settings",
)
def scale(ctx, value, settings):
    return {
        "scaled": value * settings.factor,
    }
```

Public plugin discovery will parse source statically without importing it. Validated source will be copied into an immutable content-addressed generation and imported only inside a process-isolated execution worker.

Convert every function-honest repo-owned built-in and add-on node to this SDK. Retain private trusted descriptors only for compiler-special, dynamic-topology, passive/custom-surface, generated-family, and backend-manifest behavior.

Implementation begins by creating `docs/PLAN_COREX_NOVICE_PLUGIN_SDK.md`. That file must contain this approved plan plus an embedded live task ledger:

| Task | Initial state | Write owner |
|---|---|---|
| T01–T17 | Pending | Unassigned |

The orchestrator updates a task to Completed only after its scoped diff, verification, and required independent review are reconciled.

## Live Task Ledger

Source handoff: `codex-plan-01a03779-f09e-70b2-825b-a371a8b0ccc2-01a03779-f0.md` was saved outside the repository before implementation and verified at `SHA-256 8F2CE2A0A89E067D3EAFD920BD58E513EE86D035334067AEE121E3F8BF1DADD4`. This document is the canonical in-repository copy.

| Task | State | Write owner | Verification / review evidence |
|---|---|---|---|
| T01 | Completed | Root orchestrator | 938-ID inventory and 133-node golden fixture reconciled; catalog tests 3 passed; traceability, links, and maps passed. |
| T02 | Completed | Root orchestrator | Independent review cleared; 71 tests and 68 subtests passed; Ruff, compile, wheel/editable import, packaging, maps, and indexes passed. |
| T03 | Completed | Root orchestrator | Mandatory independent architecture review cleared; 73 tests passed; Ruff, compile, registry/warning regressions, maps, and indexes passed. |
| T04 | Completed | Root orchestrator | Independent security review cleared; 103 tests passed; static non-execution, generation, import-lock, fingerprint, pruning, Ruff, compile, maps, and indexes passed. |
| T05 | Completed | Root orchestrator | Independent cross-layer review cleared; 145 tests and 170 subtests passed; protocol bounds, client retirement, persistence exclusion, Ruff, compile, maps, and indexes passed. |
| T06 | Completed | Root orchestrator | Mandatory runtime/security review cleared; 277 tests and 279 subtests passed across plugin, registry, worker/client, protocol, and catalog gates; spawned-process source-deletion proof, Ruff, compile, maps, and indexes passed. |
| T07 | Completed | T07 implementation subagent | Mandatory package-security and activation reviews cleared; 285 tests and 256 subtests passed; deterministic schema-2 round trip, non-execution, path/hash/member/hard-link limits, rollback, icon provenance, Ruff, compile, maps, and links passed. Two unchanged built-in icon-audit failures were independently classified unrelated. |
| T08 | Completed | T08 implementation team | Mandatory transaction/data-loss and architecture reviews cleared; final lanes passed 230 tests/145 subtests, 93/30, 125/31, and 64/53 with one optional skip. Full registry identity, bounded add-on worker config, guarded admission, persistence-aware reload safety, reversible packages, exact consumer rollback, Ruff, compile, traceability, maps, and links passed. |
| T09 | Completed | T09 implementation team | Independent backend/security and native UI reviews cleared; 135 authoring, dialog, controller, declaration, loader, and guarded-reload tests passed. One-time IDs, no-clobber/attested saves, structured diagnostics, native editor focus/actions, active run/viewer refusal, Ruff, compile, traceability, maps, and links passed. |
| T10 | Completed | T10 conversion team | Independent conversion review cleared; 350 focused migration, runtime, catalog, geometry, registry, authoring, and persistence tests plus 104 subtests passed. Exact 23-ID function-entry cutover, unchanged 133-node golden fixture, inert reserved bundle, process/trusted execution, descriptor/dead-module removal, Ruff, compile, traceability, maps, and links passed. |
| T11 | Completed | T11 implementation team | Independent Signal/parser review cleared; 215 parser, catalog, renderer, registry, process, add-on-boundary, and production QML tests plus 104 subtests passed. Exact Signal Plot/group parity, private internal-only parser metadata, ordered warnings, ImageValue transport, eight generic descriptor retention, Ruff, compile, traceability, maps, and links passed. |
| T12 | Completed | T12 integration conversion team | Independent security/behavior review cleared after the connected-blank presence fix. Final disjoint lanes passed 135 tests/23 subtests, 64 tests, 212 tests/104 subtests, and 24 tests/2 subtests with one optional skip; exact 14-ID conversion, two trusted exceptions, golden parity, worker/persistence, lazy dependency loading, Ruff, compile, traceability, maps, and links passed. |
| T13 | Completed | T13 Tabular conversion team | Independent security/architecture review cleared after the manifest-only trust-collision fix. Final lanes passed 130 tests; 17 tests; 68 tests/145 subtests; 164 tests/104 subtests; 42 tests; 72 tests/3 subtests; 37 tests; and 8 tests. Exact seven-ID golden parity, atomic same-owner bundle publication, trusted-generation attestation, dependency/disable gating, process-worker pipelines, persistence exclusion, lazy discovery, Ruff, compile, traceability, maps, and links passed. |
| T14 | Completed | T14 MARS conversion team | Independent security/behavior review cleared. Final lanes passed 23 tests/2 subtests with one optional real-process skip, 44 tests, 11 tests, 15 tests, and 27 tests. Exact three-ID golden parity, package-local icon provenance with generation-backed code, trusted-generation rejection, real coordinator enable/disable identity, worker runtime, persistence exclusion, unchanged MARS process/artifact helpers, Ruff, compile, traceability, maps, and links passed. |
| T15 | Completed | T15 remaining conversion team | Independent cross-catalog security/behavior review cleared after restoring the complete 133-spec documentation audit and removing dead Windows-auth owner residue. Final lanes passed 329 tests/104 subtests, 105 tests, 91 tests, 107 tests, 55 tests, 154 tests/15 subtests, and 23 tests. Exact 30-ID golden parity, 68-function/55-exception boundary, typed defaults, trusted handles/sessions, discovery isolation, persistence exclusion, Ruff, compile, traceability, maps, and links passed; T17 documentation gaps remain visibly failing. |
| T16 | Completed | T16 clean-break team | Mandatory independent architecture/security review cleared. Final root gate passed 300 tests/138 subtests; exact 17 public `corex` exports, 76 function entries, fail-closed 53 trusted exceptions, and two registered add-ons passed. Public legacy barrels/provenance/discovery were removed; source process-worker smoke returned 37; isolated wheel import passed outside the repository; managed runtime, packaging configuration, Ruff, compile, traceability, maps, and links passed. Windows package smoke remains T17 acceptance. |
| T17 | Completed | T17 closeout team | Independent final diff/evidence review cleared with no remaining findings. Post-correction full verification passed 3,872 fast tests, 220 fast-serial tests, 70 QML Quick tests, 659 GUI tests, 18 GUI-serial tests, 46 slow tests, and 58 shell-isolation tests; clean base packaging passed startup, `corex` function-worker result `37`, and Signal Plot PNG smokes; traceability, links, maps, generated indexes, and local diagram renders passed. |

T01 migration authority: [COREX Novice Plugin SDK Migration Inventory](specs/requirements/COREX_NOVICE_PLUGIN_SDK_MIGRATION_INVENTORY.md) classifies all 938 registered type IDs and records every preserved port/property key.

## Key Changes

### Authoring and metadata flow

```text
Decorated source
    ↓ bounded literal AST discovery
Normalized NodeTypeSpec + PythonFunctionRef
    ↓ fresh registry validation
Immutable content-addressed plugin generation
    ↓ PluginBundleRef in StartRunCommand
Process-isolated worker verifies generation digest
    ↓ lazy module import
Generic function adapter
    ↓
Existing DataTree matching, NodeResult validation and graph execution
```

- Reuse the current declarative `NodeTypeSpec → registry → scene payload → shared QML` path. Do not introduce plugin-specific controls or a second presentation model.
- Extract common literal parsing from the Python Script parser, but preserve the current Python Script signature and execution behavior.
- Loose local plugins need only one `.py` file. Package manifests are generated during export or required for multi-file/assets packages.
- Remove import-based discovery, `ea_node_editor.plugins` entry points, public plugin classes, descriptor exports, and schema-1 packages without compatibility shims.
- Preserve `.cxproj` compatibility whenever existing node type IDs, port keys, and property keys remain unchanged.
- Keep Custom Workflows and `.cxwf` behavior unchanged.

### Static discovery and runtime isolation

- Validation, reload, package import, and package export must never execute public plugin code.
- Public plugin modules execute only in process/external-subprocess workers. Trusted in-process execution must reject workflows containing public function references.
- Reloaded source is copied into an immutable cache such as `runtime/plugin_generations/<bundle-digest>/`.
- Workers import from the validated generation, never directly from mutable author source.
- Source changes after reload do not affect execution until the next successful Validate/Reload.
- Missing bundled imports keep statically discovered nodes visible but locked, with:
  `"<module> is not included in this COREX bundle."`
- No dependency installer, pip command, environment mutation, external interpreter selection, or background watcher is included.

### Reload transaction

Use one shared registry-replacement coordinator based on the existing add-on hot-apply ordering:

1. Refuse reload during an active run, viewer request, or viewer session.
2. Parse all active plugin sources into a fresh candidate registry.
3. Validate every open workspace and incident wire against the candidate.
4. Refuse incompatible changes without mutating files, graph state, runtime services, or the current registry.
5. Materialize validated sources into a new immutable generation.
6. Atomically replace installed package files when package import is involved.
7. Replace registry consumers in one ordered transaction.
8. Retire old process/external workers and runtime-preparation caches.
9. Roll back filesystem, registry, services, and generation selection on failure.

Compatible changes:

- Display name, description, keywords, category, label, and other presentation metadata.
- New outputs.
- New optional inputs.
- New controls with valid defaults.
- New `port=True` control override inputs.
- Changed bounds/options only when every existing saved value remains valid.

Incompatible changes for any open instance:

- Removing a port or property.
- Changing port direction, type, access shape, requiredness, or paired-control semantics.
- Changing a property type.
- Invalidating a saved property value.
- Changing an existing output or input to an incompatible canonical data type.
- Introducing a duplicate/conflicting node ID.

## Public Interface Changes

### Public module

Add a packaged top-level `corex` module and include it in editable installs, wheels, managed runtimes, and frozen Windows packages.

Public exports:

```text
node
input
output
text
text_area
number
switch
dropdown
slider
color
path
interval
list
Any
Image
Color
Interval
```

Do not publicly export `NodePlugin`, `PluginDescriptor`, `NodeTypeSpec`, `PortSpec`, `PropertySpec`, factories, registry entries, or backend-manifest implementation types.

### Exact declaration grammar

A loose file may contain multiple top-level node functions.

`@corex.node`:

```python
@corex.node(
    id="custom.<readable-slug>.<8-lowercase-hex>",
    name="Visible name",
    category=("Parent", "Child"),
    description="",
    keywords=("term",),
    icon="",
)
```

Rules:

- Exactly one `@corex.node` must be the first decorator on each node function.
- `id`, `name`, and `category` are required.
- New Plugin generates `custom.<slug>.<8-hex>` once using secure randomness and writes it explicitly into source.
- Generated IDs are never regenerated after renames.
- Built-in conversion may retain trusted existing IDs such as `plot.signal`.
- External source cannot claim reserved built-in namespaces.
- Node functions must be top-level and uniquely named within the declaration module.
- Nested node functions, methods, lambdas, and dynamically generated functions reject.
- Both `def` and `async def` are accepted.

Input:

```python
@corex.input(
    "samples",
    value_type=float,
    structure="list",
    required=True,
    label="Samples",
    description="Signal samples.",
    section="Data",
)
```

Output:

```python
@corex.output(
    "filtered",
    value_type=float,
    structure="list",
    label="Filtered",
    description="Filtered samples.",
)
```

Supported `structure` values are exactly `item`, `list`, and `tree`.

Controls preserve the existing Python Script decorator vocabulary and literal fields:

```text
text, text_area, number, switch, dropdown, slider,
color, path, interval, list
```

Common control fields:

```text
name, default, label, description, section, port
```

Control-specific fields retain current validated meanings:

```text
minimum, maximum, step, options, codes, searchable,
file_filter, direction, item_type
```

Discovery accepts:

- Literal scalars, lists, tuples, dictionaries, and `None`.
- Built-in type names: `bool`, `int`, `float`, `str`.
- Allow-listed `corex.Any/Image/Color/Interval`.
- References to same-module constants whose complete value is literal-only.

Discovery rejects:

- Function calls, comprehensions, arithmetic expressions, f-strings, environment reads, imported aliases, arbitrary attributes, or executable decorator expressions.
- Unknown decorators or fields.
- Duplicate/reserved names.
- Python keywords or invalid identifiers.
- Cross-direction key collisions.
- Excessive source/AST/decorator counts using the existing bounded-parser ceilings.

### Function signature

With no controls:

```python
def scale(ctx, value):
    ...
```

With controls:

```python
def scale(ctx, value, settings):
    ...
```

Rules:

- `ctx` is always the first parameter.
- Declared graph inputs appear once, in declaration order.
- If controls exist, `settings` is required as the final parameter.
- Controls never become direct parameters.
- `port=True` creates an optional graph input but still resolves into `settings.<name>`.
- No default arguments, positional-only parameters, keyword-only parameters, `*args`, or `**kwargs`.
- A disconnected optional graph input is passed as `None`.
- Override selection is by input presence, not truthiness. `None`, `False`, `0`, empty strings, and empty containers remain real supplied values.

### Settings object

`settings` is immutable and exposes:

```python
settings.factor
settings.mode
settings.to_dict()
```

- It contains controls only.
- `port=True` effective values are resolved before construction.
- Mappings freeze to read-only mappings, lists/sequences freeze to tuples, and sets freeze to frozensets.
- `to_dict()` returns a defensive deep mutable copy.
- Unknown direct attributes are rejected during static body validation with file/line/column and a nearest-name suggestion.
- Runtime unknown access raises the same bounded diagnostic.
- Dynamic introspection through `getattr`, `vars`, `__dict__`, or private members is unsupported.
- Control names beginning with `_`, plus `ctx`, `settings`, and `to_dict`, are reserved.
- No generated `.py`, `.pyi`, Protocol, or typing companion files are created.

### Outputs and warnings

Every node returns a `Mapping[str, object]`:

```python
return {
    "scaled": scaled,
    "summary": summary,
}
```

- Non-mapping returns reject.
- Keys must be strings.
- Undeclared keys reject.
- Omitted declared outputs settle EMPTY.
- Explicit `None` is a published Item value.
- Item/List/Tree validation remains owned by the existing execution engine.
- Public plugin code does not return `NodeResult`.

Add:

```python
ctx.warn(
    "Signal contains clipped samples.",
    code="clipped_samples",
)
```

- `message` is a non-empty string of at most 2048 characters.
- `code` defaults to `plugin_warning`, is at most 64 characters, and matches `[a-z][a-z0-9_.-]*`.
- COREX adds run, node, path, and iteration identity.
- Warnings preserve call order across sequential DataTree iterations.
- They use the existing warning presentation path without duplicate log events.

### Private implementation records

Introduce private mutually exclusive registry entry kinds:

```text
TrustedFactoryEntry
PythonFunctionEntry
```

`PythonFunctionEntry` contains an immutable `PythonFunctionRef`:

```text
bundle_id
bundle_digest
module_relative_path
function_name
source_digest
is_async
```

`PluginBundleRef` contains:

```text
owner_id
version
generation_id
bundle_digest
approved_generation_root
function references
unavailable reason
```

- GUI discovery never materializes a public callable.
- Source paths, digests, bundle refs, and implementation records never enter `.cxproj`, graph fragments, or `.cxwf`.
- Trusted descriptor/factory records remain private for explicit internal exceptions and shipped add-ons.

### Package schema 2

Generated `node_package.json`:

```json
{
  "schema_version": 2,
  "name": "strain_tools",
  "version": "1.0.0",
  "author": "",
  "description": "",
  "modules": ["nodes.py"],
  "sources": [
    {
      "path": "nodes.py",
      "sha256": "<hex>"
    }
  ],
  "assets": [
    {
      "path": "assets/strain.svg",
      "sha256": "<hex>"
    }
  ],
  "nodes": [
    {
      "id": "custom.strain_conditioner.a7c31e9b",
      "module": "nodes.py",
      "function": "strain_conditioner"
    }
  ]
}
```

Rules:

- Required: `schema_version`, `name`, `version`, `modules`, `sources`, `assets`, `nodes`.
- Unknown fields reject.
- `modules` identifies files scanned for node declarations.
- `sources` lists every root-level Python source, including helpers.
- `assets` lists every permitted asset.
- `nodes` is a generated identity/function inventory, not a duplicate node-spec manifest.
- Dependencies are not a schema field; absolute imports are checked against the bundled runtime.
- Custom assets require package form; a loose single-file plugin uses the default icon.
- Paths use canonical `/` separators and must remain relative.
- Supported assets: `.svg`, `.png`, `.jpg`, `.jpeg`.
- Package SVGs remain authored/untinted under current provenance behavior.
- Bundle digest is SHA-256 over canonical manifest JSON plus sorted `path + NUL + exact member bytes`; no self-referential digest field is stored.
- Export order and archive timestamps are deterministic.

Limits:

```text
manifest: 64 KiB
each Python source: 256 KiB
each asset: 4 MiB
members: 128
total expanded size: 16 MiB
```

Reject encrypted members, symlinks, absolute paths, traversal, backslashes, dot segments, Windows case-insensitive duplicates, undeclared members, unsupported assets, nested Python packages, and schema-1 archives/directories.

## Execution Tasks

### T01 Freeze requirements, migration inventory, canonical plan and ledger

- Goal: Establish authoritative requirements and an exhaustive migration boundary before source changes.
- Preconditions: Approved plan; preserve unrelated dirty work.
- Conservative write scope: `docs/PLAN_COREX_NOVICE_PLUGIN_SDK.md`, spec requirements/traceability modules, `docs/specs/INDEX.md`, one pre-cutover catalog baseline fixture, affected agent maps.
- Deliverables:
  - Persist this plan with embedded T01–T17 ledger.
  - Replace descriptor-first public requirements with the function-SDK contract.
  - Add an exhaustive table for every registered type ID: `convert` or `internal exception`, including owner, preserved keys, reason, and proving test.
  - Capture the current normalized repo-owned catalog as a deterministic golden baseline.
  - Register the plan under Active Implementation Plans.
- Verification:
  - Baseline registry reproduces the captured fixture.
  - `check_traceability.py`, `check_markdown_links.py`, `check_agent_maps.py`.
- Non-goals: Production source changes and compatibility loaders.
- Packetization notes: `P01 Requirements and Migration Inventory`; must precede all implementation.
- Review gate: Root orchestrator reviews the complete migration table before T02.

### T02 Build the shared literal declaration engine and public `corex` SDK

- Goal: Parse loose decorated functions into normalized declarations without executing source.
- Preconditions: T01.
- Conservative write scope: new top-level `corex` package, declaration-parser modules, Python Script parser extraction, SDK/parser tests, packaging discovery configuration.
- Deliverables:
  - Shared bounded literal AST utilities.
  - Exact public decorators and allow-listed type aliases.
  - Multiple-node-per-file discovery.
  - Same-module literal constant resolution.
  - Signature, identifier, decorator-order, and body `settings.<name>` validation.
  - Immutable Settings implementation.
  - Preserve current Python Script parsing and named-control signature behavior.
  - Ensure `import corex` works from source/editable installs.
- Verification:
  - New `test_plugin_declaration.py`.
  - Existing `test_python_script_declaration.py`.
  - Hostile declaration files prove no side effects occur.
  - Ruff/type/architecture-boundary checks for the new package.
- Non-goals: Worker import, registry replacement, package archives, node conversion.
- Packetization notes: `P02 Public SDK and Parser`.

### T03 Add private function adapters and registry entry kinds

- Goal: Normalize function declarations into the existing registry while separating public source refs from trusted factories.
- Preconditions: T02.
- Conservative write scope: node plugin contracts, registry entry/storage logic, function adapter, execution context warning collection, focused registry/SDK tests.
- Deliverables:
  - `TrustedFactoryEntry` and `PythonFunctionEntry`.
  - `PythonFunctionRef` and `PluginBundleRef`.
  - Generic sync/async function adapter.
  - Input binding, settings binding, mapping-return validation, warning collection.
  - `ctx.warn(...)`.
  - No public function construction in GUI discovery.
- Verification:
  - Registry tests for both entry kinds.
  - Settings immutability/override tests.
  - Mapping/EMPTY/explicit-None tests.
  - Async adapter tests.
  - Ordered warning tests.
- Non-goals: Source discovery roots, worker loading, UI.
- Packetization notes: `P03 Function Adapter and Registry`.
- Review gate: Independent architecture review before T04.

### T04 Replace public plugin discovery with static bundles and immutable generations

- Goal: Discover loose files and installed schema-2 packages without import or entry-point execution.
- Preconditions: T03.
- Conservative write scope: plugin loader, bootstrap inputs, plugin-generation cache, registry fingerprint calculation, loader tests.
- Deliverables:
  - Loose-file and installed-package static discovery.
  - Complete removal of `EntryPoint.load()` and `ea_node_editor.plugins`.
  - Import scanning against the bundled runtime.
  - Locked unavailable entries for missing imports.
  - Content-addressed immutable generation materialization.
  - Plugin fingerprint derived from normalized specs and bundle/function digests.
  - Generation pruning limited to unreferenced inactive generations.
- Verification:
  - Marker-writing hostile modules never execute during discovery/reload validation.
  - Duplicate IDs, invalid constants, missing imports, changed source, and generation reuse tests.
  - Exact missing-dependency message without internal-path leakage.
- Non-goals: Protocol transport or worker import.
- Packetization notes: `P04 Static Discovery and Generations`.

### T05 Add protocol/client registry-generation agreement

- Goal: Carry exact public plugin generations to workers and recycle clients when fingerprints change.
- Preconditions: T04.
- Conservative write scope: execution protocol/DTOs, client, headless runtime, runtime-registry replacement API, protocol tests.
- Deliverables:
  - Bounded `PluginBundleRef` protocol DTOs.
  - `plugin_fingerprint`.
  - `runtime_registry_fingerprint = hash(data_catalog_fingerprint + plugin_fingerprint)`.
  - Explicit `CorexRuntime.replace_registry(registry)`.
  - Client generation retirement on registry replacement.
  - Protocol path validation restricted to approved generation roots.
- Verification:
  - Protocol round trips and bounds.
  - Fingerprint mismatch/recycle tests.
  - No source or refs persisted into project documents.
- Non-goals: Worker module execution.
- Packetization notes: `P05 Protocol and Client Agreement`.

### T06 Implement digest-pinned worker loading

- Goal: Execute only validated generation bytes in process-isolated workers.
- Preconditions: T05.
- Conservative write scope: worker runtime/runner/backends, function adapter integration, worker cache tests.
- Deliverables:
  - Worker re-hashes generation members before load.
  - Digest-derived module names avoid stale `sys.modules`.
  - Unused plugins never import.
  - Sync/async dispatch.
  - Public plugins rejected by trusted in-process execution.
  - Worker-generation cache retirement after registry change.
  - Source mutation after validation cannot affect an active generation.
- Verification:
  - Lazy-import and marker tests.
  - Before/after digest mutation tests.
  - Process-only enforcement.
  - Async, cancellation, DataTree iteration, mapping outputs, and warnings.
- Non-goals: Package/UI changes.
- Packetization notes: `P06 Worker Loading`.
- Review gate: Independent runtime/security review.

### T07 Replace `.cxpkg` with deterministic schema 2

- Goal: Import/export validated packages without executing their source.
- Preconditions: T04 and T06.
- Conservative write scope: package manager, package provenance/icon resolution, package IO tests.
- Deliverables:
  - Exact schema-2 manifest above.
  - Deterministic export.
  - Static declaration/source/asset validation.
  - Archive limits and Windows-safe path checks.
  - Atomic staged activation and rollback.
  - Schema-1 archive and installed-directory rejection with migration-guide link.
  - Package assets available from safe provenance roots.
- Verification:
  - Round-trip package tests.
  - Traversal, symlink, encrypted, duplicate, oversized, undeclared-member, bad-hash, bad-icon, and rollback tests.
- Non-goals: Legacy conversion, dependency installation, nested Python packages.
- Packetization notes: `P07 Package Schema 2`.
- Review gate: Independent package-security review.

### T08 Build compatibility checking and atomic registry replacement

- Goal: Safely reload compatible plugins without mutating open projects.
- Preconditions: T05–T07.
- Conservative write scope: generalized hot-apply/rebuild coordinator, compatibility checker, runtime/service replacement seams, focused tests.
- Deliverables:
  - One replacement coordinator reused by plugin reload and package import.
  - All-workspace node/property/wire compatibility report.
  - Active run/viewer refusal.
  - Fresh candidate registry.
  - Ordered registry/service/runtime/library replacement.
  - Complete rollback on any failure.
- Verification:
  - Every compatible/incompatible change class.
  - Multiple workspaces.
  - Dynamic effective ports.
  - Rollback and consumer parity.
  - Worker/viewer/cache retirement.
- Non-goals: Automatic graph reconciliation or restart-only fallback.
- Packetization notes: `P08 Atomic Reload`.
- Review gate: Independent transaction/data-loss review.

### T09 Add the novice in-app authoring workflow

- Goal: Make a valid reusable node creatable without manual package or descriptor work.
- Preconditions: T02, T04, T08.
- Conservative write scope: native plugin-authoring dialog, File actions, shell/controller wiring, focused UI tests.
- Deliverables:
  - `File → New Plugin...`
  - `File → Reload Plugins`
  - Filename/name fields and generated readable-random ID.
  - Existing PythonCodeEditor with syntax highlighting.
  - Save, Validate, Reload, and Open Plugins Folder.
  - Diagnostics list: file, line, column, severity, node ID, digest, dependency/unavailable state.
  - Success summary: bundle count, node count, digest, unavailable-node count.
- Verification:
  - Generated template parses and reloads.
  - Invalid drafts preserve the current registry.
  - Active-run/viewer refusal.
  - Keyboard editing, focus, validation diagnostics, and shell action wiring.
- Non-goals: QML editor, marketplace, watcher, generated types, pip UI, external environment selection.
- Packetization notes: `P09 Authoring UI`.

### T10 Convert simple ordinary repo-owned nodes

- Goal: Make the public SDK the normal implementation path for COREX itself.
- Preconditions: T03 and migration matrix.
- Conservative write scope: static active core/math/value/unit/spatial node families and their focused tests.
- Deliverables:
  - Decorated function declarations.
  - Preserved type IDs, port/property keys, defaults, access, categories, and behavior.
  - No public classes/descriptors for converted nodes.
- Verification:
  - Golden catalog parity.
  - Focused execution and persistence tests.
  - `.cxproj`, fragment, duplication, and `.cxwf` round trips.
- Non-goals: Signal Plot, integrations, and internal exception nodes.
- Packetization notes: `P10 Simple Built-ins`.

### T11 Convert Signal Plot and function-honest plot nodes

- Goal: Prove the novice SDK handles a large real node with controls, sections, port overrides, warnings, and renderer ownership.
- Preconditions: T10.
- Conservative write scope: Signal Plot/generic plot declarations, renderer adapters, plot tests and docs.
- Deliverables:
  - Signal Plot converted to decorated function syntax.
  - Existing renderer remains separate.
  - Expandable groups and all control metadata preserved.
  - Generated definition-driven plot families remain private descriptors when duplication would be less maintainable.
- Verification:
  - Exact catalog/property/group parity.
  - Renderer/image/warning tests.
  - Port/default/UI projection tests.
- Packetization notes: `P11 Plot Nodes`.

### T12 Convert file/process/email/spreadsheet/SSH integrations

- Goal: Convert ordinary integration shells while retaining service, cancellation, artifact, and security helpers.
- Preconditions: T10.
- Conservative write scope: mapped repo-owned integration node declarations and focused runtime tests.
- Deliverables:
  - Function declarations using trusted `ctx` services.
  - Preserved cancellation, staging, artifact, secret, and path behavior.
  - No movement of service ownership into decorators.
- Verification:
  - Process, SSH/SFTP, email, spreadsheet, artifact, cancellation, and security tests.
- Non-goals: Dependency installer, external runner, backend manifests.
- Packetization notes: `P12 Core Integrations`.

### T13 Convert the Tabular add-on’s function-honest nodes

- Goal: Convert executable node shells without collapsing add-on availability or property-edit adapters into the SDK.
- Preconditions: T10.
- Conservative write scope: Tabular declarations/catalog and focused add-on/runtime tests.
- Deliverables:
  - Function declarations where honest.
  - Add-on manifest, dependency gating, preview/provider, property-edit adapter, and hot-apply ownership retained internally.
- Verification:
  - Tabular availability, inputs, refs, previews, plots, package, and reload tests.
- Non-goals: Rewriting the Tabular backend.
- Packetization notes: `P13 Tabular`.

### T14 Convert the MARS add-on’s function-honest nodes

- Goal: Convert MARS node shells while retaining external-process/backend/toolchain/artifact contracts.
- Preconditions: T10.
- Conservative write scope: MARS declarations/catalog and focused runtime tests.
- Deliverables:
  - Decorated node functions.
  - Existing cancellation, progress, artifact, and backend metadata preserved.
  - Future external Python runner remains unimplemented.
- Verification:
  - MARS node, runtime, progress, cancellation, and artifact tests.
- Non-goals: MARS backend redesign or external environment selection.
- Packetization notes: `P14 MARS`.

### T15 Convert remaining feasible engineering/service-backed nodes

- Goal: Complete the repo-owned function-honest conversion.
- Preconditions: T10–T14.
- Conservative write scope: engineering imports/viewer shells, Jupyter/AI/service-backed candidates proven convertible by the migration matrix.
- Deliverables:
  - Function shells for ordinary execution.
  - Viewer sessions, handles, custom surfaces, host services, and passive behavior retained behind trusted internal contracts.
  - Any dishonest conversion is moved to the explicit T16 exception inventory rather than represented by a fake/no-op function.
- Verification:
  - Engineering importer/viewer, handle lease/disposal, Jupyter, AI, surface, artifact, and service tests.
- Non-goals: Custom QML authoring API or arbitrary public handle creation.
- Packetization notes: `P15 Engineering and Services`.

### T16 Lock internal exceptions and remove the legacy public SDK

- Goal: Finish the clean break with an exact, reviewable internal boundary.
- Preconditions: T10–T15 complete.
- Conservative write scope: internal plugin contracts/bootstrap, public exports, packaging config, dead-code/architecture tests, exception inventory.
- Deliverables:
  - Explicit internal allowlist for:
    - Python Script.
    - Trigger.
    - Stream Gate.
    - Subnode shell/pins.
    - Parameter Setup/Pool/Response Pool.
    - Passive/custom-surface nodes.
    - Generated descriptor families where function expansion is less maintainable.
    - Advanced add-on/backend manifests.
  - Remove public `@node_type`, `NodePlugin`, `PluginDescriptor`, `PLUGIN_DESCRIPTORS`, class probing, module executable manifests, and `ea_node_editor.plugins`.
  - Keep trusted descriptor types private and available to internal/add-on code.
  - Zero public legacy-reference audit.
  - Source wheel/frozen package includes `corex`.
- Verification:
  - Dead-code and architecture-boundary tests.
  - Packaging configuration.
  - `import corex` in source, wheel, managed worker, and packaged app.
  - Exact exception inventory equals the migration matrix.
  - Add-on regression proves the private boundary remains intact.
- Packetization notes: `P16 Legacy Removal`.
- Review gate: Independent final architecture review before closeout.

### T17 Documentation, maps, generated artifacts and acceptance closeout

- Goal: Deliver navigable public documentation and retained release evidence.
- Preconditions: T16.
- Conservative write scope: README, Getting Started, plugin/Python Script guides, specs, maps/indexes, architecture diagrams, QA matrix.
- Deliverables:
  - New novice tutorial and Signal Plot/strain examples.
  - Legacy-to-new migration guide with explicit unsupported message.
  - Clear Python Script vs Custom Workflow vs Plugin comparison.
  - Exact package schema and security rules.
  - External-runner capability documented as future/not implemented.
  - Updated Node SDK/execution/persistence/integration/QA requirements and traceability.
  - Regenerated route/source indexes and architecture diagrams.
  - `COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md` registered in the spec index.
  - Ledger marked complete only after all acceptance evidence passes.
- Verification:
  - Focused lanes below.
  - Full verification and Windows package smoke.
  - Traceability, links, maps, generated-artifact checks.
- Non-goals: New features discovered during closeout.
- Packetization notes: `P17 Closeout`.
- Review gate: Independent final diff/evidence review.

## Work Packet Conversion Map

If explicitly converted into packets:

1. `P00 Bootstrap`: canonical plan/ledger, prompts, manifest/index tracking only.
2. `P01`–`P17`: map one-to-one to T01–T17.
3. Do not create live packet artifacts otherwise; the canonical plan’s embedded ledger is sufficient.

Execution orchestration:

- Root agent remains orchestrator.
- Exactly one implementation agent owns writes at a time.
- Cross-owner tasks receive at most one focused read-only explorer before edits.
- No editing begins while repository exploration is active.
- Independent review is mandatory after T03, T06, T07, T08, T16, and T17.
- Conversion tasks T10–T15 use single-owner edits, focused proving tests, and the T16 cross-catalog review.
- The orchestrator reconciles every subagent result against current source before updating the ledger.

After every context compaction, before any new edit:

1. Read `docs/PLAN_COREX_NOVICE_PLUGIN_SDK.md` from the beginning, including the full embedded ledger.
2. Run/read `git rev-parse --show-toplevel`, branch, `HEAD`, and `git status --short`.
3. Inspect the scoped diff and staged diff.
4. Reconcile completed tasks and verification evidence.
5. Confirm the current single write owner.
6. State the next task and proving check.
7. Only then resume implementation.

## Test Plan

### Declaration and SDK

- Literal-only parsing without execution.
- Same-module literal constants.
- Unknown/duplicate decorators and IDs.
- Generated ID format.
- Multiple nodes per file.
- Sync and async functions.
- Exact signature rules.
- Optional input `None`.
- Settings immutability, defensive copy, direct-access validation, typo suggestions, and reserved names.
- `port=True` presence semantics for falsey values.
- Mapping outputs, undeclared keys, omitted outputs, explicit `None`, and Item/List/Tree validation.
- Structured warning bounds and ordered collection.
- Existing Python Script regressions unchanged.

### Discovery and execution

- Hostile source writes no marker during discovery, validation, reload validation, import, or export.
- Unused public plugins never import.
- Missing bundled dependencies produce locked nodes and exact messages.
- Source changes before/after digest verification cannot execute.
- Protocol refs/fingerprints are bounded and reject path escape.
- Public plugins cannot run through trusted in-process execution.
- Worker generations recycle on registry fingerprint changes.
- Sync/async/cancellation/iteration behavior remains sequential and atomic.

### Package and reload

- Deterministic schema-2 round trip.
- Schema-1 archive and installed-directory rejection.
- Hash, traversal, symlink, encrypted, duplicate, oversized, undeclared-member, unsupported-asset, and rollback cases.
- Compatible metadata/additive changes.
- Every incompatible change category.
- Multiple workspaces and incident wires.
- Active run/viewer refusal.
- Registry/filesystem/service rollback.
- Safe icon provenance.

### Migration

- Golden catalog parity for every converted type ID.
- Exact internal-exception inventory.
- `.cxproj`, graph fragment, duplication, and `.cxwf` persistence for retained IDs.
- Signal Plot renderer/control parity.
- Integration, Tabular, MARS, engineering, viewer, passive, handle, artifact, and cancellation suites.
- Retained add-on catalog/runtime regression.

### Final commands

Use focused tests during each task, then at T17:

```powershell
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
.\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py
.\venv\Scripts\python.exe .\scripts\export_architecture_diagrams.py
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --summarize-output
.\scripts\build_windows_package.ps1 -PackageProfile base -Clean
```

The package build must exercise `import corex` and run one packaged public-function plugin through the process worker.

## Assumptions

- COREX is unreleased and no external legacy plugin compatibility is required.
- Existing unrelated dirty files are preserved and never overwritten or staged accidentally.
- Node IDs and semantic port/property keys remain stable unless the migration matrix explicitly classifies a deliberate break.
- Private trusted descriptor/factory records remain for explicit internal exceptions; they are not public SDK.
- Public plugins use standard metadata-driven surfaces only.
- Custom Workflows remain copied graph snapshots.
- The bundled COREX Python runtime is the only execution environment in scope.
- Future selectable external Python runners are not implemented, scaffolded, or simulated.
- No dependency installer, watcher, marketplace, generated typing files, custom-node QML factory, or compatibility shim is added.
- Commit/push behavior is outside this plan unless explicitly requested during implementation.
