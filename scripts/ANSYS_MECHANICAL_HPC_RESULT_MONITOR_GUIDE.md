# ANSYS Mechanical HPC Result Monitor

## Purpose

`ansys_mechanical_hpc_result_monitor.py` is an IronPython 2.7 operator console for ANSYS Mechanical 2026 R1 (v261). It watches several Windows-visible solver folders, confirms that each MAPDL result/output pair appears complete and stable, then imports, evaluates, and saves the selected Mechanical Solutions one at a time.

The monitor does not submit analyses to a scheduler or copy files. The HPC folders must already be visible to the Windows account running Workbench/Mechanical.

## Supported scope

- Workbench-launched ANSYS Mechanical 2026 R1/v261.
- Mechanical's IronPython 2.7 scripting engine.
- Static Structural, Modal, Transient Structural, and Steady-State Thermal MAPDL analyses only.
- MAPDL structural `.rst` and thermal `.rth` result files.
- Exact, non-recursive Windows folders and filenames.
- Result linking by reference through `Solution.ReadGivenAnsysResultFileByReference(...)`.
- Sequential `EvaluateAllResults()` and Workbench **File > Save Database** checkpoints.

Harmonic Response, Explicit Dynamics, LS-DYNA, rigid dynamics, distributed result sets, other Mechanical releases, scheduler APIs, remote transfers, notifications, unattended services, and concurrent result evaluation are not supported. The analysis list is filtered using v261 `AnalysisType` and `PhysicsType`; unsupported tree branches are not offered.

## Prerequisites

1. Open the Workbench project and Mechanical model that will receive the results.
2. Save the Workbench/Mechanical database before starting. The monitor refuses to start without a real `.mechdb` path and Workbench User Files folder.
3. Keep Workbench, Mechanical, the Windows user session, and the required licenses available.
4. Disable workstation sleep for the unattended period. This script does not prevent sleep or restart Mechanical after a process, license, or machine failure.
5. Make every source folder accessible to the same Windows account as Mechanical.
6. Prefer UNC paths such as `\\server\share\project\run_01` over mapped drive letters. Services, elevated processes, or another login session may not see the same drive mappings.
7. Keep a referenced `.rst`/`.rth` available after import. Mechanical is linked to the source file rather than receiving a private copy.

The receiving analysis must match the producing model and mesh. A result file from a different model can be recognized as a completed file but will fail Mechanical validation or evaluation.

## Install and run

The deliverable is a single script:

`scripts\ansys_mechanical_hpc_result_monitor.py`

Open Mechanical's Scripting console and execute:

```python
execfile(r"<repo-root>\scripts\ansys_mechanical_hpc_result_monitor.py")
```

The modeless **ANSYS Mechanical HPC Result Monitor** window opens. Running the same command again focuses the existing monitor instead of creating a second dispatcher.

Do not run the production monitor from standalone CPython or PyMechanical. PyMechanical may prepare disposable test fixtures, but the monitor's import/evaluate/save sequence is intentionally hosted inside Workbench-launched Mechanical.

## Interface

### Header and status strip

The header identifies the open Mechanical database and counts Waiting, Ready, Active, Completed, Failed, and Attention Required jobs.

The bottom status strip shows:

- An indeterminate busy indicator during import, evaluation, and Save Database. It is deliberately not a percentage.
- Current serialized Mechanical operation.
- Last and next folder scan.
- Number of unavailable folders.
- Latest verified Save Database checkpoint.

### Queue grid

The grid shows queue order, selected analysis/Solution, analysis type, folder and filenames, current status, latest message, waiting time, ready/import/checkpoint times, active elapsed time, and retry consumption.

Status is always written as text; color is only a secondary visual cue. Column headers and non-obvious controls have tooltips.

### Job editor

Each job requires:

- **Analysis**: a supported current Mechanical analysis and its Solution. The displayed family comes from its `AnalysisType` and `PhysicsType`, not the generic CLR class name.
- **Folder**: one exact absolute Windows folder. Subfolders are never searched.
- **Result file**: one leaf filename ending in `.rst` or `.rth`.
- **Output file**: one leaf filename ending in `.out`, commonly `file.out` or `solve.out`.
- **Units**: the explicit unit system used to interpret the external result file. It starts unresolved; Add and Start are blocked until the operator makes a choice.
- **Poll**: seconds between scans for this job.
- **Settle**: seconds during which both file signatures must remain unchanged.
- **Retries**: retries after the initial Mechanical attempt.
- **Retry delay**: seconds before a failed Mechanical phase becomes eligible again.
- **Accept current completed files**: permits files that already existed when monitoring began.

Production defaults are:

| Setting | Default |
|---|---:|
| Poll interval | 300 s |
| Settle interval | 300 s |
| Retries after initial attempt | 3 |
| Retry delay | 600 s |
| Accept current files | Off |

Use **Add** to append a job. Select a queue row to edit, update, remove, or move it. Configuration changes are disabled while monitoring is active; pause safely before editing.

## Unit systems

Choose the unit system used when the result file was written. There is no silent default. The UI uses v261 `UnitSystemIDType` symbols rather than numeric values:

| UI symbol | System |
|---|---|
| `UnitsMKS` | m, kg, N, s |
| `UnitsCGS` | cm, g, dyn, s |
| `UnitsNMM` | mm, kg, N, s |
| `UnitsBFT` | ft, slug, lbf, s |
| `UnitsBIN` | in, lbf-s²/in, lbf, s |
| `UnitsUMKS` | µm, kg, N, s |
| `UnitsKNMS` | m, tonne, kN, s |
| `UnitsGMMS` | mm, tonne, N, s |

Do not guess. A wrong selection can give dimensionally misleading values even when the file imports.

## Monitoring and readiness rules

Press **Start Monitoring** after adding all jobs.

For each job, **Start Monitoring** schedules immediate baseline capture; the filesystem worker records the result and output `(size, UTC modification time)` signatures on that first scan. With the default pre-existing-file policy, both files must appear or change after that baseline. This prevents an old completed run from being imported accidentally. Enable **Accept current completed files** only when you intentionally want to process an already-finished pair.

A pair becomes Ready only when all conditions are true:

1. The configured folder is available.
2. Both exact filenames exist directly in that folder.
3. Both files are non-empty and readable.
4. Neither file's size nor modification time changes for the entire settle interval.
5. The streamed MAPDL output contains `RUN COMPLETED`.
6. The final `NUMBER OF ERROR MESSAGES ENCOUNTERED` value is zero.
7. The output contains no `*** ERROR ***`, `*** FATAL ***`, abnormal-termination, or error-termination marker.

Fatal/error evidence wins even if `RUN COMPLETED` is also present. A genuine v261 failing run can still print `RUN COMPLETED`, so that banner alone is unsafe.

Any change to either file restarts settling. Ready rows continue to be scanned while they wait behind another Mechanical job. A changed signature or incomplete footer demotes the row, clears its first-ready time, and requires a complete new settle interval; fatal/error evidence changes it to Failed before import. A Ready row restored from state also starts a fresh settle cycle. An unavailable folder stays Waiting and consumes no retry. Readiness is a high-confidence file gate, not proof that SMB caching or an unusual remote writer can never change the file again; Mechanical import is the final validity check.

## Queue and Mechanical sequence

Ready jobs use FIFO order by their first-ready time. Queue order breaks ties. A due retry has priority over a job that has not started, but nothing interrupts an active Mechanical call.

Each job executes these phases:

1. **Importing**: link `.rst`/`.rth` with `ReadGivenAnsysResultFileByReference` and require `IsResultFileSameAsLoaded(...)` to return true. A newly linked Solution may temporarily report `SolveRequired`, so import does not reject that status before evaluation.
2. **Evaluating**: call `EvaluateAllResults()` and then require a readable, known healthy Solution status and solved result-object states. `SolveRequired`, `SolveFailed`, `NotSolved`, `Unsolved`, `PostProcessingRequired`, unevaluated/invalid states, and unreadable status/state values fail closed. The same health check is repeated before save.
3. **Saving**: invoke Workbench's `DS.Script.doFileSaveDatabase()` action and require the actual `.mechdb` signature to advance and stabilize.
4. **Completed**: record the verified checkpoint and allow the next job to start.

All Mechanical tree and result calls execute through `ExtAPI.Application.InvokeUIThread`. A background worker performs only folder/stat/output parsing. Mechanical itself can be unresponsive while `EvaluateAllResults()` runs; the UI deliberately shows the active phase with a native marquee indicator but does not invent a percentage or ETA.

## States

| State | Meaning |
|---|---|
| Draft | Configured but not monitoring. |
| Waiting | Folder/files/footer/baseline condition is incomplete. |
| Settling | Both files exist but the stable-time requirement is not complete. |
| Ready | Pair passed the file gate and is queued for Mechanical. |
| Importing | Mechanical is linking the external result file. |
| Evaluating | Mechanical is evaluating existing result objects. |
| Saving | Workbench Save Database is running and being verified. |
| Retry Waiting | A Mechanical phase failed and has a retry time. |
| Completed | Import, evaluation, and database checkpoint were verified. |
| Failed | Source output failed or safe retries were exhausted. |
| Attention Required | A possibly mutating failure cannot be resolved unattended. |
| Skipped | Operator excluded the job. |
| Paused | Folder scanning and new dispatch are paused. |

## Retry and Attention Required

The configured retry count is in addition to the initial attempt. A failure retries only the failed phase when the prior phase can still be verified:

- Before an evaluation or save retry, the monitor verifies that the requested result remains loaded.
- If that verification fails, the retry restarts from import.
- A verified non-mutating failure may wait while another Ready job proceeds.
- A possibly mutating import/evaluation/save failure blocks later dispatch until its retry is due.
- When possibly mutating retries are exhausted, the job becomes **Attention Required** and the global queue stops.

For an Attention Required or mutation-uncertain job, first reopen the last verified Workbench/Mechanical database or inspect and explicitly accept the current in-memory state. Until that recovery is explicitly acknowledged, **Update**, **Remove**, and **Skip** cannot clear the safety stop. **Retry Now** and **Skip** show a recovery confirmation; after acknowledgement, the requested retry or skip is allowed. Never confirm merely to make the queue move.

**Skip** cannot interrupt an active Mechanical call. **Pause** stops future scans/dispatch but not the current operation. **Stop After Current** lets the active import/evaluate/save chain finish and then prevents another dispatch.

Closing the window during an active Mechanical operation offers only **Keep Open** or **Close After Current**. The script never tries to terminate a running Mechanical API call.

## Save checkpoints and recovery

The monitor writes these files under the Workbench User Files folder reported by Mechanical:

- `ansys_mechanical_hpc_result_monitor_state.json`
- `ansys_mechanical_hpc_result_monitor_state.json.previous`
- `ansys_mechanical_hpc_result_monitor_events.jsonl`

State JSON is replaced atomically and retains one previous copy. A failed replacement leaves the current state file intact and reports the write failure; a temporary file may remain for diagnosis. The JSONL event log is append-only and can be opened with **Open Log**.

The state records project identity, analysis identity, configuration, file signatures, timestamps, phase/retry data, and the latest database checkpoint. It does not contain the Mechanical database itself.

Recovery procedure:

1. Reopen the Workbench project/database at the last known-good save.
2. Open Mechanical and run the monitor script again.
3. Press **Restore Session**.
4. Review every Attention Required or ambiguous analysis row.
5. Start monitoring again only after the queue and model state are correct.

Restore is accepted only for the same project path. An object-ID match is accepted only when the stored tree path, analysis and Solution names, normalized analysis family, raw `AnalysisType`, `PhysicsType`, and CLR type also match. Otherwise the monitor accepts only one unique match for that complete identity; an ambiguous or missing analysis requires manual correction. A stored Completed status is never trusted by itself: the open database checkpoint and loaded result must reconcile.

The monitor is bound to the Workbench project/database and User Files location that were open when its window was created. If **Save As** or a project switch changes either identity, Start and Restore fail closed. Every automatic import, evaluation, and Save Database UI-thread callback checks the same identity again immediately before it can mutate Mechanical, so a queued job cannot silently continue in the switched project. Close the monitor and run the script again so state/log paths and analysis identities are rebuilt for the new project.

There is no automatic project/database reload or automatic resume after Mechanical exits.

## Troubleshooting

### Folder unavailable

- Confirm the UNC path from the same Windows account/session as Workbench.
- Avoid relying on a mapped drive created in another login or elevation context.
- Confirm share and NTFS permissions.
- Check VPN/network availability.
- The monitor will continue checking and will not consume retries for this condition.

### Files remain Waiting

- Confirm the exact filenames and top-level folder.
- Subdirectories are intentionally ignored.
- With the default policy, both files must appear or change after Start Monitoring.
- Confirm the output includes the final zero error count and `RUN COMPLETED`.
- Check whether the HPC writer continues changing size or modification time.

### Output is Failed even though RUN COMPLETED exists

Inspect the JSONL message and solver output. A nonzero final error count or `*** ERROR ***`/`*** FATAL ***` correctly overrides the completion banner.

### Import fails or Solution stays SolveRequired/SolveFailed

- Confirm the receiver was created from the same model and mesh as the producer.
- Confirm `.rst` versus `.rth` and the explicit unit system.
- Confirm the referenced file remains accessible.
- Review Mechanical messages and the MAPDL output.
- Do not bypass Attention Required after a partially changed Solution; reopen the last checkpoint when uncertain.

### Save Database does not verify

- Confirm the Workbench project was saved before monitoring.
- Check write permissions and free disk space for the `.mechdb` and Workbench project folder.
- Check whether another process is locking the database.
- A returned save command without an advancing, stable `.mechdb` signature is treated as failure.

### Mechanical appears frozen during evaluation

`EvaluateAllResults()` is synchronous and can block Mechanical's UI. Wait for the call to return. The monitor will not start another job concurrently and cannot safely cancel the active API call.

## Validation status and limitations

T01 on 2026-08-16 proved the following against installed v261/build 26.1:

- Exact `.rst` and `.rth` by-reference API calls.
- `IsResultFileSameAsLoaded` and result-file properties.
- UI-thread callable behavior.
- Workbench User Files location.
- `DS.Script.doFileSaveDatabase()` and an advancing `.mechdb` timestamp.
- Genuine v261 completion, nonzero-error, and fatal output markers.

T01 used receiver systems without matching model/mesh, so successful evaluation and persisted reopen were intentionally not claimed. T05 must still prove a matching producer/receiver workflow for Static Structural, Modal, Transient Structural, and Steady-State Thermal analyses, including close/reopen recovery.

Local staged acceptance can prove NTFS polling, partial-write protection, parsing, serialization, Mechanical import/evaluation/save, and manual recovery. It does not prove a real scheduler, SMB caching/locking, credentials, disconnect recovery, workstation sleep, unattended licensing, or actual cluster execution.

Before production use, complete T05 and then run at least one representative job against the real HPC share. Keep the result/output pair and event log for review.
