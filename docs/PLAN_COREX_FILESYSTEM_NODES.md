# COREX File System Nodes

Status: `COMPLETED - T01-T04 ACCEPTED`; two verified baseline fast-gate failures
remain outside this feature's scope, as recorded below.

## Approved contract

Add eight ordinary function nodes under `Utilities / File System`:

| Type ID | Ordered inputs | Ordered outputs |
| --- | --- | --- |
| `io.combine_file_paths` | Paths (List) | Final path |
| `io.construct_file_path` | Directory, File name, File extension | File path |
| `io.deconstruct_file_path` | File path | Directory, File name, File extension |
| `io.contents_in_directory` | Directory, Search pattern, Subdirectory levels, Content type | Content paths (List) |
| `io.create_directory` | Directory, Create recursive | Directory |
| `io.move_file` | Source path, Target path, Operation mode, Overwrite target file | Successful |
| `io.delete_file` | File path | Successful |
| `io.temporary_file_path` | File name, File extension | File path |

Full paths use COREX Path with Text accepted on inputs. Names, extensions,
and patterns use Text; flags use Boolean; selectors/depth use Integer.
All other ports use Item access. Use snake_case keys and
`created_directory` for Create Directory's output.

- Contents defaults: pattern `*`, depth `0` with slider `0..10`, content
  codes `0=Files`, `1=Directories`, `2=Files and Directories` (default 0).
- Move defaults: `0=Copy`, `1=Move` (default 0), overwrite false.
- Create recursive defaults false. Temporary name/extension are optional;
  omitted components are random. Other component/path inputs are required.
- Plain path/text inputs have no extra inline editor. Shared controls and
  ordinary input-default editing are used; connected controls override properties.
- Join and split paths using host filesystem rules without requiring existence.
  Later rooted Combine segments follow the host join operation. Split returns
  the final extension including its dot; Construct accepts either dot spelling
  and explicitly empty extension. Validate components and unsupported carriers.
- Contents uses literal names plus `*` and `?`, deterministic sorted absolute
  output, depth 0 for root only, and no recursion through links/junctions.
  Traversal errors fail rather than silently truncating output.
- Contents with no directory searches the saved project's parent, or worker
  CWD for an unsaved project. Other relative IO paths retain worker-CWD rules.
- Create is idempotent for directories; missing parents require recursive true.
- Move accepts an existing target directory or a destination filename, requires
  existing parents, and deletes the source only after destination publication.
- Move/Delete operational failure returns `Successful=False` with a warning;
  success returns true. Readiness, invalid configuration, and cancellation retain
  their existing waiting/error/stop behaviour. Reject directory deletion,
  same-file copy/move, and unsupported artifact references before mutation.
- Stage copy bytes and publish without clobber when overwrite is false. Remove
  only operation-owned staging files. If publication succeeds but source unlink
  fails, report false and explain that both files remain.
- Temporary returns an OS-temp path without creating/reserving a file. Explicit
  components remain stable; missing components are regenerated on execution.
  Do not promise automatic cleanup.
- All eight nodes use solution reuse `never`. Use stdlib and shared COREX
  declarations, tooltips, stock icons, and QML controls. No dependency, new
  filesystem service, custom QML control, SDK, or execution-engine expansion.

## Execution and acceptance

The coordinator owns this table and integration. Fresh GPT 5.6 Sol implementation
workers execute sequentially with one active writer. Each task receives an
independent review before acceptance. Preserve unrelated working-tree edits;
publication and packaging are outside scope.

| Task | Deliverable / write scope | State | Owner | Accepted evidence / next action |
| --- | --- | --- | --- | --- |
| T01 | Lexical runtime helpers and focused tests | ACCEPTED | Sol worker T01 | 29 focused tests passed; independent Windows validation findings resolved with stdlib checks |
| T02 | Contents, Create, Temporary runtime and tests | ACCEPTED | Sol worker T02 | 46 passed, 1 privilege-dependent symlink skip; strict reparse/error/cancel regressions and native Windows junction smoke passed; independent findings resolved |
| T03 | Copy/Move/Delete runtime and failure-safety tests | ACCEPTED | Sol worker T03 | 56 passed, 1 inherited skip; independent staging-descriptor/cleanup findings resolved; Ruff passed |
| T04 | Declarations, registration, catalogue, UI/worker/persistence integration, docs | ACCEPTED | Sol worker T04 | Independent review resolved; runtime, worker, QML, catalogue, persistence, and correction checks passed; final evidence below |

T01-T03 own `ea_node_editor/nodes/builtins/filesystem.py` and focused filesystem
tests; they do not register incomplete node implementations. T04 owns the inert
declaration module, bundle member, icon catalogue, current catalogue overlay and
assertions, focused presentation/integration tests, and affected docs/maps.

Integration finding: required-input readiness rejected explicit empty strings
before the Construct function could accept an empty extension. T04 therefore
adds internal `PortSpec.allow_empty_string` metadata (default false), enabled
only for the required extension input. Shared property, worker, and canvas
readiness must consume that metadata consistently. None, whitespace-only text,
and empty collections retain existing missing-value behaviour. Public SDK
names stay unchanged; ordinary required inputs retain their old behaviour.
No node-ID exceptions belong in shared readiness or execution code.

For T04, use the existing current-contract overlay's `add_rows`; never edit the
frozen historical catalogue. Introduce a native-function inventory disposition
without changing the historical 78 conversions. Final expected totals: 76
built-in functions, 129 built-in nodes, 139 repo-owned rows, 101 executable
rows, and 45 executable rows with reuse `never`.

## Verification

- Focused disposable-directory tests per task: lexical relative/rooted/drive/UNC/
  Unicode/empty/compound-extension cases; listing modes, depth, filters and links;
  recursive creation and temp non-creation; operational failure, no-clobber,
  same-file aliases, cancellation, staging cleanup, and partial moves.
- T04 proves List binding in a spawned worker, connection to existing file
  consumers, property/connected overrides, persistence round trips, stock icons,
  and actual QML-host control interaction.
- Run filesystem and owning integration/catalogue/function/icon/control suites,
  then `scripts/run_verification.py --mode fast --summarize-output` once at final
  integration. Run map, traceability, and Markdown hygiene checks after doc edits.
- Record final results here once. No packet set is needed; optional later mapping
  is P00 baseline followed by T01-T04 as P01-P04.

## Final evidence

- Focused runtime and integration checks: 280 passed, 1 privilege-dependent
  symlink skip, and 126 subtests passed. Actual registry-derived GraphNodeHost
  slider, coded dropdown, and switch interaction passed. The strengthened
  worker test checks decoded paths, Contents-to-File-Read contents, configured
  and connected empty extensions, and `Successful=False` with its warning.
- Independent reviews covered every task. Windows filename validation,
  cancellation, strict reparse inspection, descriptor closure, staging cleanup,
  and lazy canvas readiness findings were resolved and regression-tested.
- Native Windows junction smoke passed at depth 10: the junction itself was
  listed, its target was not traversed, and target contents were preserved.
- The full fast main phase recorded 4,736 passed, 4 skipped, and 7 failures.
  Five attributable stale catalogue/count/test-double expectations were fixed;
  their focused rechecks passed (55 tests and 3 subtests, plus the one saved-path
  execution test). The remaining fast serial phase passed all 220 tests.
- Two failures reproduce on a clean detached checkout of original HEAD
  `e40da097`: the context-menu ownership assertion in
  `tests/test_architecture_boundaries.py` expects the retired Menu declaration,
  and `tests/test_qml_navigation_index.py` expects 175 components instead of the
  already-present 176. Those unrelated assertions are unchanged; this is not
  an all-green repository fast-gate claim. Local phase logs are under
  `artifacts/verification_logs/20260906_151246/`.
- The current repo-owned catalogue remains exact and is checked directly against
  the 139 live specifications.
- Ruff, map validation, source/test index validation, traceability, Markdown
  links, and whitespace checks passed. Existing unrelated working-tree edits
  were preserved.
