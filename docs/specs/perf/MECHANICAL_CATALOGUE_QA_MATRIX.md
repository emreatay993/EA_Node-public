# Mechanical Catalogue QA Matrix

Status: **ACCEPTED — T01–T18 COMPLETE; INDEPENDENT ASTRA INTEGRATION REVIEW PASSED**.

This is the final neutral QA record for the [Mechanical catalogue plan](../../PLANS/MECHANICAL_CATALOGUE/PLAN.md) and [user/developer guide](../../MECHANICAL_CATALOGUE.md). It binds the accepted T01–T17 commits to the final 2026 R1 integration evidence. The [task ledger](../../PLANS/MECHANICAL_CATALOGUE/TASK_LEDGER.md) remains the authority for task acceptance and the coordinator-owned T18 commit.

## Acceptance boundary

- Product reference and sole initial acceptance release: Ansys 2026 R1 (`261`) on Windows.
- Repository root checkout, branch `codex/mechanical-catalogue`, T18 baseline `ec8a8091b569165846f7ea8dc5f7ee237bb14dad`.
- Python: CPython 3.11.6, MSC v.1935 64-bit; observed platform `Windows-10-10.0.26200-SP0`.
- Exact packages: `ansys-mechanical-core 0.12.12`, `ansys-mechanical-stubs 0.1.12`, `ansys-api-mechanical 0.1.4`, `ansys-workbench-core 0.14.0`, `ansys-api-workbench 0.4.0`, `ansys-tools-common 0.5.2`, `ansys-dpf-core 0.16.1`, `h5py 3.16.0`, `numpy 2.4.6`, `pandas 3.0.5`, `cadquery-ocp-novtk 7.9.3.1.1`.
- Fixture policy: the original retained Workbench static solve and standalone modal solve were reused. T18 launched no solve, created no archive, and did not replay accepted native format/export cohorts.
- Evidence boundary: ignored files under `artifacts/verification_logs/mechanical_catalogue/` are local machine proof. Their hashes below bind this durable matrix without publishing native fixtures or private paths.

## T18 evidence set

| Evidence | SHA-256 | Meaning |
| --- | --- | --- |
| T18 interrupted four-graph checkpoint, `T18/integration_receipt.json` | `cfbabf01cc0e808117b9cf2193c116fb0ebccd4a042bc67fa92b0bfec89ebe9c` | Preserved unchanged; status remains `running` because the harness was interrupted after table, image and both mutation-save graphs completed. It is not a final cleanup receipt. |
| First continuation, `T18/continuation_attempt1_wall_clock_only/continuation_receipt.json` | `610ad8507a09679711ed6722de43271b814c0deea8bfaee81c2fe4e7f5f2bee0` | PASS and preserved separately; timestamps are wall-clock only and are not presented as monotonic proof. |
| Final monotonic continuation, `T18/continuation_receipt.json` | `50c790aace6a33f426c279806f6c51b3aac233b78eed2d2dc6baab26033c7e44` | PASS; repeated the two output reopens and Interactive A/B/A-no-Open sequence with monotonic observations, then zero-survivor shutdown. |
| Original 25-second evidence failure, `T18/attempt2_table_pass_cleanup_timeout/integration_receipt.json` | `46d0b6d63c20100c12de0f98bddd1e707fd23074f1285a8c54627aaa17330806` | Remains failed: the real protocol interpreter was unsignaled and its work root present at that evidence bound. Later observations do not repair or supersede it. |
| T01 approved qualification | `6dc873bb80bd17347c0b04d9beb344e93baa7507d5948fec486e80f3d2ae9802` | Native 261 capability, formats, queries, results, cameras, images, commands and archive boundaries. |
| T10 accepted image receipt | `67565358a5b127f9bc01377832cb75b56740dbc844e74e7e94e7a1f7581a523e` | Native graphics, image publication, Fit policy and inspected captures. |
| T11 accepted mutation receipt | `4a74b9cdebf82896417937943f9b7b22d92526831b9ea66e8b1038a052620b03` | Registered runtime mutation, freshness, invalidation and cleanup. |
| T12 accepted snippet receipt | `07d0a00c2908455e2cae3e452357063d71d2b5d35ddc3806984621e7bb15611e` | Native owned snippets, load-step placement and no implicit solve. |
| T13 accepted standalone-save receipt | `0b457c4eccf6f4d685b0c2563992cfa9e8cf89330b290badb78000e3bdea8437` | Standalone publication, archives, rollback and explicit overwrite. |
| T14 accepted Workbench-save receipt | `0db04c29c5f18242ed299a78880630db3447a19d9f576867d110105b9e764bc2` | Whole-project native save/archive, inclusions, dependencies and recovery. |
| T15 accepted model-only export receipt | `82a35d1be842dc98176a88137c72e15198b876c0917e4d6df6ca508547bf5be4` | Selected-model `.dsdb` bridge to `.mechdb`/`.mechdat`; accurate omissions and source-owner continuation. |
| T15 read-only validator | `f3d929c769b3985445657a7f965b987f1484a7ede3fc5ab9831ee90d8f363b64` | Validator identity only; it was not rerun after later source changes. |
| T16 visual review matrix | `dd4c6def93e055fbbb52e95c2ed6cfe14b5b5291726548cf56a6a5918356e031` | Final 64 node captures and four sheets at real QML fonts 10/16 and effective DPR 1.0/1.5. |
| T17 final structural receipt | `9c600c151b843a26972b75e16a8cc568e489c4313ada453a6df72a64c8dae1c1` | Normal serializer load, deterministic examples and canonical-LF/serializer-CRLF distinction. |

The final consolidated receipt binds the four-graph and continuation producer hashes mechanically. The first continuation's pre-monotonic producer was not frozen before its observation-only patch; its receipt and five event logs remain byte-exact, and no producer hash is manufactured for it.

## Final T18 compositions

| Composition | Result | Exact proof |
| --- | --- | --- |
| Table example | PASS | Normal `.cxproj` load plus `inject_fixture_paths` through validated graph mutation. `Time [sec] = [0,1,3]`, `Force [N] = [0,100,200]`; Signal Plot `600×400`, 42,955 PNG bytes, SHA `ae957ac98d541cdef098e102198dfb516b243e88b867ee05454723c6e26dea7a`. |
| Image example | PASS | Typed `CameraViews.views → Export.views` returned `COREX export view`, `COREX T10 right, detail`, `COREX T10 front` in order. Two branches of three 640×400 images were ordered object-major for `COREX cylinder`, then `COREX witness`. Separate current/current 320×200 preview SHA `1b0eba5e0a0a14e04eaf7eabad25856ade871cc992dfeb19588bc3c2cca48fbf` reached Media Panel. |
| Mutation example run 1 | PASS | Normal loaded graph read the one-value native `Discrete` 500 N load, added 100 N, added owned all-step snippets and saved `fresh-600-1.mechdb`, SHA `e329e898417d1af71cae9055ad29973c4526b53438c72a79fea8eac672193dda`. |
| Mutation example run 2 | PASS | Fresh normal loaded graph repeated from the unchanged source to `fresh-600-2.mechdb`, SHA `78be9da6fac86777195b9572fae3de08d86c9bdfb9b182f782ecbdeb2e4c1a1e`. The script SHA was identical and contains current-value `+100`, not fixed 600. |
| Independent output reopens | PASS | Separate registered Open→read-only Script runs returned `Discrete`, one sample, `600 N` for both outputs. Each returned two `! COREX_OWNER_V1:` snippets with exact preserved APDL bodies and `IssueSolveCommand=False`. |
| Interactive workspace lifecycle | PASS | A returned one 320×200 current capture and retained a visible 261 window. All running A identities stayed running across B's non-Mechanical run. The next A run contained no Open, acknowledged one retirement, and every A-owned process was kernel-signaled before its node-start observation; the window and work root were gone. |

The bounded continuation ran twice. The first successful pass captured wall-clock timestamps only and remains preserved; the second honestly repeated both read-only reopens and the single Interactive sequence to add monotonic timestamps. No table/image example, mutation-save graph, archive, model export or solve was replayed.

The original sources remained byte-identical: definition/mutation source `81d8e1db62a5de48e593349c5496264caca8925e88493efe19f895c550eb626e`; image source `e9076399f776115f0f6a7e766a876462cdf0d4501b5b08f5728e894eb1d753e7`.

## Cleanup timing and interpretation

Production timing was not changed: five-second cooperative close, two-second escalation observation, six-second shared session-cleanup wait, and two-second directory retry. The T18 recovery observer used a maximum 120-second evidence window only to record eventual state; it is neither a production deadline nor a repaired 25-second pass.

| Run | Graph completion versus cleanup | Monotonic observation |
| --- | --- | --- |
| Output reopen 1 | `run_completed` preceded cleanup. No cleanup warning. All owned identities were later signaled; root absent. | Latest owner signaled 4,422 ms after `run_completed`; root absence was observed at 4,469 ms. |
| Output reopen 2 | Same separation; no cleanup warning; all signaled and root absent. | Latest owner signaled 4,532 ms after `run_completed`; root absence was observed at 4,563 ms. |
| Interactive A | `run_completed` intentionally retained the inspection owner and visible window. | A remained running through B. |
| Next A run without Open | One workspace-retirement acknowledgement preceded node start. All recorded A identities were signaled at node start; root disappeared before node start and no window survived. | First observed root absence coincided with the retirement acknowledgement at monotonic timestamp `336729359000000`; the latest owner signal followed 203 ms later and preceded node start by 250 ms. Root absence preceded node start by 453 ms. |

`owner.close()` return is not directly exposed by retained events or protocol hooks. The report therefore claims only observed event order, warnings, exact PID/creation identities, Win32 wait/exit states and work-root presence/removal. `run_completed` alone is not treated as cleanup completion. Queryable terminated process objects are not treated as executing: `WAIT_OBJECT_0`/exit state is authoritative. The original 25-second report remains a failure because protocol interpreter PID 41384 was `WAIT_TIMEOUT` with its root present at that bound; unsignaled state alone does not prove Mechanical API execution.

At final continuation shutdown, all 25 exact PID/creation identities were kernel-signaled, including the one retained COREX execution worker; zero executing survivors remained.

### Reused-evidence limits

- The approved configured-result exception permits only the initial inactive `By=Time`/`SetNumber=0` drift when native 261 rejects restoring zero; ForceReaction remains limited to an already-Time probe with unambiguous stored times and read-only `By`. See [backend decisions](../../PLANS/MECHANICAL_CATALOGUE/BACKEND_DECISIONS.md#4-table-api-correction) and the [accepted ledger](../../PLANS/MECHANICAL_CATALOGUE/TASK_LEDGER.md).
- T14's sole qualified `dp0/act.dat` exception is closed-schema HDF5 logical equality, not byte equality or proof of timestamp-only drift. External exclusion proves registered-reference identity policy, not absence of every equal-content copy; the first successful `.wbpj` producer's exact source is not replayable. See [T14 native state-file preservation](../../PLANS/MECHANICAL_CATALOGUE/BACKEND_DECISIONS.md#t14-native-state-file-preservation).
- T15's current four-case fixture has no snippet or saved view; positive preservation for those fields reuses hash-bound T01 native outputs and current comparator tests. Its first successful publication and diagnostic cleanup/message limits remain disclosed in the [accepted ledger](../../PLANS/MECHANICAL_CATALOGUE/TASK_LEDGER.md).
- T16's final graph-surface aggregate remains 139/140 with the transient Path Pointer case passing the writer and independent exact retries. Earlier default-font, mislabeled-scale, low-contrast and partially overwritten captures are excluded; acceptance uses the final font 10/16, effective DPR 1.0/1.5 evidence in the [visual review matrix](#t18-evidence-set).
- Protected ignored failed-run directories `T05/registered-open-work2` and `T11/registered-graph-work` remain untouched. Their deletion was automatically rejected earlier and was not retried; they are retained limitations, not executing processes.

## Task and requirement coverage

| Task | Accepted commit | Requirement result |
| --- | --- | --- |
| T01 | `820d02e2d85a38afb2f63402bc22c5e8a029ee97` | PASS — fixed 261 native routes and qualified evidence. |
| T02 | `6a0d60008e370d7cd27e0e9332aaf2a67aff8bda` | PASS — bounded Model/Object/Property/Camera contracts and existing Table/Image carriers. |
| T03 | `3c8c83d3d5224dc801b427cddddea70834f09c4f` | PASS — run/workspace ownership, staleness and process isolation. |
| T04 | `447909e8d0d7e6470eb5c0bd73677609185e1dab` | PASS — accepted-metadata selectors without source/backend calls while editing. |
| T05 | `d97ad9e37086f9ac7d4472b5aa87ce7e6c965b56` | PASS — standalone/Workbench Open, discovery and 261 Background/Interactive routes. |
| T06 | `a21f738556eeb9e00227f23180c4c8e73bb0dce3` | PASS — all eleven COREX background filters and pinned grammar. |
| T07 | `a86d887d708dfa64cc7e2f2656fd997dfcfbe691` | PASS — full-fidelity definition tables, units and direct Signal Plot transport. |
| T08 | `9e9327a02718e63c6dd003faa654bd33f4dc62fc` | PASS — result/probe/worksheet adapters, stored-set evaluation and restoration. |
| T09 | `893431fa85d47936f48d69ad8b7409a2f6c70a82` | PASS — saved/current camera identity, order and restoration. |
| T10 | `a49529021fc44e9f9013592b3247e1b16605640b` | PASS — object/view batches, current preview and safe PNG publication. |
| T11 | `2feaf88b376979ddfdc207081e941513fe5fe42c` | PASS — scoped scripts, revisions, same-run invalidation and fresh source. |
| T12 | `a5dc4bf38ed74a84057a851518bdb48ef4d5132f` | PASS — node-owned load-step snippets and no implicit solve. |
| T13 | `eaf851edc0d30e06dd788686732eeba1f63b185c` | PASS — explicit standalone save/archive and recovery. |
| T14 | `32df24fd98fbde000ffbe653a6bf3569ec05618e` | PASS — native Workbench preservation, inclusions and dependency checks. |
| T15 | `dcd7fbb146a22a54ea51e1c31445e96c70384e9a` | PASS — selected model-only `.mechdb`/`.mechdat` export. |
| T16 | `4e40edabc9b74cf9b1991a1ba3fa8fb49fef4adb` | PASS — 52 typed inputs, 22 outputs, 16 sections, shared controls and eight icons. |
| T17 | `ec8a8091b569165846f7ea8dc5f7ee237bb14dad` | PASS — three normal-load examples and final guide/maps. |
| T18 | `T18 Verify the complete Mechanical catalogue` | PASS — independent Astra integration review accepted; the unique subject resolves this final task commit, whose actual SHA is supplied in the final report. |

## Mandatory scenario matrix

| Scenario | Result | Evidence |
| --- | --- | --- |
| Two add-100 N runs start from saved source | PASS | T18 mutation graphs plus independent reopens: 600 N and 600 N; original 500 N hash unchanged. |
| Interactive retention across workspaces | PASS | T18 continuation: A retained, B left A untouched, next A/no-Open retired A before node execution. T03/T05/T11 retain shutdown/failure/cancel cases. |
| Same source in two Open nodes | PASS | T03/T05 focused ownership tests and accepted registered evidence. |
| Open→Script→FEA Table→Signal Plot | PASS | T11 registered graph; post-script 750 N table/plot, old observations expired. |
| Two sibling mutators from one revision | PASS | T11 stale sibling/revision tests. |
| Older-run/model/system selector | PASS | T02/T03/T06 exact identity and pre-dereference rejection tests. |
| Property Value enum/quantity/formula | PASS | T01 qualification plus T06 focused predicate tests. |
| Property Value `Tabular data` | PASS | T06 proves presence metadata without cell access. |
| Search grammar | PASS | T06 exact/contains/Unicode/quoted pair/malformed/typed-identity cases. |
| No search matches | PASS | T06 returns empty outputs and `Found=False`. |
| Background category differences | PASS | T01/T06 explicit CS, opaque source ID, Body.Hidden and current-scope rules. |
| Required search metadata unreadable | PASS | T06 `mechanical.search_incomplete`; inversion does not match unknown. |
| Definition curve→Signal Plot | PASS | T18 exact `[0,1,3]`/`[0,100,200]` table and immutable plot output. |
| History versus PlotData | PASS | T08 native stored-history and spatial-identity evidence. |
| Existing result evaluation without Solve | PASS | T08 accepted 261 result/probe/modal evidence; no new solve. |
| Two objects × three views | PASS | T18 typed camera wire produced two three-item branches in object-major order. |
| Image Fit=False | PASS | T10 inspected named-view captures and T18 image example. |
| Script per environments/model once | PASS | T01/T11 native and registered scope evidence. |
| Snippet all steps / selected 1 and 3 | PASS | T12 native `ds.dat` placement and owned updates; no solve. |
| Complete Workbench archive | PASS | T14 all-enabled independent reopen and separate exclusion evidence. |
| Selected Workbench model export | PASS | T15 four model-only outputs/reopens; topology/source preserved. |
| Save failure after staging | PASS | T13/T14 identity-checked rollback and retained recovery evidence. |
| Collapsed section with two wires | PASS | T16 production GraphCanvas physical interaction evidence. |
| Every editable control has a typed port | PASS | T16 inventory: all 52 inputs, including inactive/advanced controls. |
| Selector typing causes no backend/source call | PASS | T04/T06/T16 instrumented UI checks. |
| Cancel/crash/terminal cleanup with retained leases | PASS WITH DISCLOSED TIMING LIMIT | T03/T05/T11 accepted failure/cancel/shutdown proof; T18 distinguishes graph completion, warnings, kernel state and root removal. The original 25-second evidence failure remains failed. |

## Formats and outputs

| Source/input | Accepted output | Result and boundary |
| --- | --- | --- |
| `.mechdb`, `.mechdat` | `.mechdb`, `.mechdat`, native `.mechpz` | PASS. `.mechdat` is model-only; `.mechpz` uses native standalone archive flags. |
| `.mechpz` | Fresh standalone model | PASS through native Unarchive; never renamed/opened as an ordinary database. |
| `.wbpj`, `.wbpz` | Native `.wbpj`/`.wbpz` | PASS with project topology/dependencies and conditional inclusion controls. |
| Selected Workbench Model | `.mechdb`, `.mechdat` | PASS through native Model.Export `.dsdb` and separate same-release standalone SaveAs. Always reported model-only. |
| Mechanical definitions/results/probes/worksheets | Immutable COREX Table | PASS with source/SI units and bounded Definitions metadata. |
| Saved/current camera and viewport | CameraView/Image/DataTree | PASS with stable view order, exact object-major branches and PNG validation. |

Workbench-to-`.mechpz`, result-preserving `.dsdb`, copied internal databases, implicit solving, remote sessions, future-release certification and universal ACT table support remain out of scope.

## Final integration corrections

The first fast attempt was interrupted after its retained faulthandler log proved an offscreen modal stall. The production controller called workspace retirement, caught the test double's missing `retire_workspace` method, and correctly displayed a cleanup warning; the test patched only the earlier confirmation dialog, so the warning blocked. The test double now implements the required zero-retirement method, while the regression captures the warning and requires it not to be called. Production retirement, warning behavior, data-loss protection and QWidget dialog parenting are unchanged.

The corrected fast attempt then exposed four stale current-inventory contracts. The add-on inventory now includes `mechanical.corex`; the canonical registry inventory includes the eight Mechanical specs, 74 ports and four semantic types. The ownership-refactor validator now requires the exact retained T00/T07–T26 rows. T01–T06 are admitted only as an explicit historical accepted owner set: parent commit `a7da1170ce1c6935cc5b2fd2a1a2c40fc58751b1` records each as `ACCEPTED`, and `7f5304b47ade7d74ecfd2e4b32cb8f2b4ec1f253` removed those exact rows with the retired graph product. A regression rejects any other missing retained row. The historical QA matrix itself was not rewritten.

Fast attempt history remains explicit:

- `20260909_090559/01_fast.pytest.log`: interrupted after a real modal stall; 49,959 bytes, copied unchanged into T18 with SHA `7518d348d961c5b9b9eb7d8a202cd6a9d535716582d4ca2d96ad9fd31e576712`.
- `20260909_093414/01_fast.pytest.log`: completed failure, 4 failed / 5,001 passed / 4 skipped / 12 warnings in 275.30 seconds; SHA `f66709c38770b169a4351a68f94659871e21c82b43e20bf56d9141e6e7c9ff72`.
- `20260909_094436/01_fast.pytest.log`: final parallel PASS, 5,006 passed / 4 skipped / 12 warnings in 267.59 seconds; SHA `fac317a852d2132e540b39a881ee2549b0a100677037148879e5d30a4b6ed8b2`.
- `20260909_094436/02_fast.serial.pytest.log`: final serial PASS, 220 passed in 98.42 seconds; SHA `b4de5c508eb25839be9352744c31fcebea464ad573fb63dd1436676c1aaec82b`.

## Final checks

The exact final commands and log hashes are frozen in ignored `T18/final_receipt.json`; `T18/independent_review.json` retains the final Astra approval. The reviewed candidate receipt and document bytes remain under `T18/reviewed_candidate/`; the final receipt records the coordinator's acceptance-only document updates. No native evidence was rewritten.

| Check | Result |
| --- | --- |
| Owning Mechanical suite | PASS — 446 passed in 45.44 seconds; JUnit SHA `d06bb2abfbbf52e735e8ad676b0c62d3cf452fd913badad15a162acde558d7dd`. |
| Fast verification lane with summarized output | PASS after the two retained failed attempts above — final parallel 5,006 passed/4 skipped, serial 220 passed. |
| Traceability | PASS. |
| Canonical Markdown links | PASS. |
| Agent maps | PASS; route-index citations resolve. |
| Icon sources/assets | PASS — 23 passed and 100 subtests. |
| Explicit Mechanical plan-package Markdown audit | PASS — eight files, zero issues. |
| Diff whitespace and privacy/staging review | PASS — scoped writer and coordinator reviews; exact approved paths/hunks only. |

No agent-map update is required for T18: this task adds proof and spec registration without changing application ownership or routes.
