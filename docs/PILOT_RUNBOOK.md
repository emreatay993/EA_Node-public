# Pilot Runbook

## Scope

- Audience: internal operators validating a freshly built packaged desktop
  candidate.
- Default pilot target: the `base` package profile.
- Canonical active release docs: `docs/PACKAGING_WINDOWS.md` and
  `docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md`.
- Historical context only: `docs/specs/perf/PILOT_SIGNOFF.md` preserves the
  archived 2026-03-01 pilot snapshot and must not be treated as fresh sign-off.

## Prepare Candidate Build

1. Open PowerShell in the repository root.
2. Build the packaged app:
   `.\scripts\build_windows_package.ps1 -PackageProfile base -Clean`
3. Build the installer bundle:
   `.\scripts\build_windows_installer.ps1 -PackageProfile base`
4. Confirm the packaged executable exists:
   `Test-Path artifacts\pyinstaller\dist\base\COREX_Node_Editor\COREX_Node_Editor.exe`
5. Optional verify-only signing snapshot:
   `.\scripts\sign_release_artifacts.ps1 -PackageProfile base -VerifyOnly`

If you are validating the viewer profile, rerun the same steps with
`-PackageProfile viewer` from a venv that already has `.[ansys,viewer]` or
`.[dev]` installed.

If you are validating the full developer-style profile, rerun the same steps
with `-PackageProfile full` from a venv that already has `.[all,dev]` or
`.[dev]` installed. Expected package output is
`artifacts\pyinstaller\dist\full\COREX_Node_Editor\COREX_Node_Editor.exe`;
installer and signing outputs land under `artifacts\releases\installer\full\`
and `artifacts\releases\signing\full\`.

If the pilot scope includes Tabular Data, build from a venv with `.[tabular]`,
`.[all,dev]`, or `.[dev]` installed so the base package can register
`Data > Tabular Data Input`.

## Install And Start

1. Launch the packaged executable:
   `.\artifacts\pyinstaller\dist\base\COREX_Node_Editor\COREX_Node_Editor.exe`
2. Wait for the main shell to finish loading.
3. Confirm the status strip initializes to an idle or ready state.
4. Open `Settings > Graphics Settings` and confirm the dialog opens without
   errors.

## Smoke Workflows

1. Graphics settings and theme behavior
   - Open `Settings > Graphics Settings`.
   - Switch shell theme, toggle grid and minimap, and accept the dialog.
   - Pass criteria: shell and graph canvas restyle immediately, and the saved
     values still apply after restart.
2. Workspace and graph setup
   - Create a workspace and view, add `Start`, `Logger`, and `End`, and connect
     `Start -> Logger -> End`.
   - Pass criteria: nodes and edges appear correctly; no unexpected dialog.
3. Simple execution flow
   - Run `Start -> Logger -> End`.
   - Pass criteria: execution completes and the status strip returns to
     `Ready (Completed)`.
4. File pipeline flow
   - Build `File Read -> Python Script -> File Write` with a small text sample.
   - Pass criteria: output file is written and content matches the transform.
5. Controlled failure UX
   - Make the `Python Script` raise an error and rerun the flow.
   - Pass criteria: the failure dialog appears and the failed node remains
     inspectable.
6. Save, reopen, and recovery behavior
   - Save as `.cxproj`, close the app, relaunch it, and accept the recovery prompt
     if it appears.
   - Pass criteria: prior state restores correctly and app-wide graphics
     preferences remain active after relaunch.
7. Tabular Data Input availability, when the tabular stack is included
   - Open the node library, expand `Data`, and add `Tabular Data Input`.
   - Point the node at a small local CSV or XLSX sample and open the fullscreen
     preview.
   - Pass criteria: the node registers, preview data is bounded and readable,
     and non-fatal load warnings do not turn the node into a failed execution
     state.
8. Direct tabular plotting, when the tabular and plot stacks are included
   - In the tabular preview, click two numeric column headers to select them.
   - Connect the tabular output directly to a generic `Plot > Line Plot` or
     `Plot > Scatter Plot` node without inserting an adapter node.
   - Pass criteria: the plot renders from the selected columns, saved/reopened
     projects keep the selected-column hints, and export uses the existing plot
     backend data shapes.

## Failure Reporting Template

Use this template in pilot issue reports:

```text
Title: [Pilot] <short failure title>
Date/Time (UTC): <YYYY-MM-DDTHH:MM:SSZ>
Operator: <name>
Package Profile: <base|viewer|web|full>
Build Source: artifacts/pyinstaller/dist/<profile>/COREX_Node_Editor/COREX_Node_Editor.exe
Workflow: <1-6 from runbook>
Expected Result: <expected behavior>
Actual Result: <observed behavior>
Repro Steps:
1) ...
2) ...
3) ...
Artifacts:
- Screenshot(s): <path>
- Console/log text: <path or excerpt>
- Sample project/input files: <path>
Severity: <P0/P1/P2>
```

## Rollback Instructions

1. Stop pilot usage of the current packaged candidate.
2. Announce the rollback timestamp and reason in the pilot channel.
3. Switch operators back to the last approved packaged build.
4. Preserve screenshots, logs, and sample files with the issue report.
5. Update the active follow-up status in
   `docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md` before claiming a fresh
   pilot sign-off.
