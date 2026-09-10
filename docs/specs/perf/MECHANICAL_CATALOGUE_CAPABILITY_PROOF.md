# Mechanical Catalogue Capability Qualification

Status: **T01 ACCEPTED — INDEPENDENT REVIEW PASSED**. This is the bounded 2026 R1 (`261`) result for the [catalogue plan](../../PLANS/MECHANICAL_CATALOGUE/PLAN.md). The approved result-state policies reconcile the two native 261 limitations without altering their raw failed evidence. TASK_LEDGER.md remains the task-acceptance and commit authority; this does not accept production catalogue implementation or T02–T18.

## Environment and fixtures

The project venv provided PyMechanical 0.12.12, Mechanical stubs 0.1.12, PyWorkbench 0.14.0, Workbench API 0.4.0, tools-common 0.5.2, DPF 0.16.1, NumPy 2.4.6, pandas 3.0.5, and OCP 7.9.3.1. PyWorkbench 0.14.0 is the lowest version tested, not a claimed minimum across older releases.

Two original neutral fixture families were used. The retained Workbench fixture has three systems/two distinct Model containers and one prior static solve with stored times `[1, 2, 3]` s. A genuinely standalone modal fixture was created from the neutral STEP source and solved once because no standalone solved source existed; it has one modal analysis, two bodies, six stored modes, and a 1,310,720-byte RST. Total solver executions across retained evidence are therefore two, one historical Workbench solve and one newly authorized standalone solve. No user model was opened.

All live models, scripts, images, and JSON reports are under ignored `artifacts/verification_logs/mechanical_catalogue/T01/`. `qualification.json` and `qualification_v2.json` remain unchanged historical failed-policy reports. The approved-policy machine-readable result is `qualification_approved.json`, supported by `result_policy_receipt.json`.

## Qualified routes

| Route | Result | Evidence |
| --- | --- | --- |
| Native Workbench `.wbpz` | Passed all-enabled archive/reopen with native inclusion flags and `FailIfMissingFiles=True`; independent reopen retained its RST and `[1,2,3]` result sets. | `workbench_archive_controls.json` |
| Native standalone `.mechpz` | Passed all-enabled plus one-at-a-time exclusions. All-enabled retained the modal RST and user marker; disabling results removed only the RST; disabling user files removed only the marker. Independent native reopen returned a live reader and six frequencies. | `standalone_modal_archive.json` |
| Selected Workbench Model export | Passed only as model-only `.dsdb` bridge to separate same-release `.mechdb`/`.mechdat`. Shared and independent Model boundaries, two bodies, and the load reopened. It makes no archive, result, dependency, user-file, or Workbench-topology claim. | `workbench_export_full.json`, `conversion_completed.json`, `isolated_export_verification.json` |

`.mechpz` is rejected for Workbench sources by the pure route contract. Standalone archives do not consume the Workbench-only external-imported-files option. The historical `missing_results_confirmed.json` is expected boundary evidence for model-only export, neither a pass nor a blocker.

## Positive live findings

- The fixed COREX query predicates retained the earlier 61 bounded checks and never called `Tree.Filter`, `Tree.Find`, or `IsObjInTreeView`. The amended grammar and typed-identity bypass are pinned by focused tests.
- A native External Model `Setup.AddDataFile` → Mechanical Model transfer produced two nonempty opaque IDs, including `Setup::File1::COREX_IMPORTED_NODES_Nodes`. Exact identity matching preserves the native string; case-altered and partial forms do not match. The same fixture proved external-file archive inclusion, explicit exclusion, and failure/no archive when the requested CDB was unavailable.
- Exported saved views were direct `ModelView` children with required names and stable indices. Native duplicate create and rename collisions were explicit; rename/delete worked. A final no-solve cohort deliberately changed the active tree object and camera, then restored the exact active-object ID/order and all public camera fields on both success and an injected enumeration failure.
- Native Workbench result access found the RST, returned stored times `[1,2,3]`, and exposed `PlotData` Body/Node/Values samples. `RetrieveResult()` returned TotalDeformation maxima `0.0231818`, `0.0453399`, and `0.0677287 mm`. ForceReaction returned distinct totals `103.08`, `201.56`, and `301.04 N` for times 1–3 and restored DisplayTime.
- The standalone modal result exposed native ITable keys `Mode` and `Frequency`; independent archive reopen retained both columns and six rows.
- The mesh worksheet row API accepted a named selection and returned its active state/name without generating mesh.
- `Geometry.AddLayeredSection().Layers` exposed the documented worksheet. One native row round-tripped material `Structural Steel`, thickness `1.5`, and angle `45.0` as floats under active unit system `StandardNMM`; adapters must retain the active unit context because these getters do not return Quantity objects.
- Script execution returned three ordered analysis identities for per-environment scope and one model-wide count. APDL snippets used exact native modes `All` and `ByNumber`; generated input contained the all-step marker three times, step 1/3 markers once each, and no `SOLVE` line with `IssueSolveCommand=False`.
- Workbench archives with one switch disabled at a time behaved independently: no-results omitted RST/solver files, no-user omitted the marker, and no-external omitted the imported STEP. A model-only export made after adding a named view and snippet reopened separately with two analyses, two bodies, the load, named selection, snippet, and view.
- The modal viewport image shows the complete cylinder and witness block. `SetFit()` occurred before saving the named view; applying/exporting that view performed no later fit.
- Source/database/result hashes remained unchanged. Immediate Workbench shutdown can lag; identity-aware later checks found recorded owners gone.

## Approved native result-state policies

Live 261 makes ForceReaction.By read-only. The approved adapter therefore accepts only time-driven probes already `By=Time` with unambiguous stored times. It never assigns By; it sets DisplayTime, calls RetrieveResult, restores DisplayTime, verifies By stayed unchanged, and rejects every other addressing mode. The raw failed setter attempt remains retained evidence.

Configured-result evaluation restored the active addressing fields exactly (`By=Time`, `DisplayTime=0 s`, `CalculateTimeHistory=True`). The initial inactive `SetNumber=0` became valid set `3`, and the public setter rejected zero. The approved exception applies only to that initial By/zero combination and requires a valid positive resulting set plus an explicit before/after drift receipt. All other restoration failures remain fatal. Tree-active objects and graphics restoration remain exact and independent; this exception does not claim no observable effect.

Workspace-scoped Interactive lifetime, graph-run cleanup, stale handles, and production node/UI behavior remain later implementation tasks and are not reported as T01 production proof.

## Checks

```powershell
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_probe_contract.py -q
.\venv\Scripts\python.exe scripts/mechanical_catalogue/probe_capabilities.py artifacts/verification_logs/mechanical_catalogue/T01/qualification_approved.json --evidence-root artifacts/verification_logs/mechanical_catalogue/T01
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
```

The focused contract suite passes 17 tests. No agent-map update is needed because T01 adds qualification helpers and proof only; application ownership is unchanged.
