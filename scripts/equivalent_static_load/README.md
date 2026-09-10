# Equivalent Static Load (ESL) — blade-out secondary rig loads

Derives **static rig actuator loads** that reproduce the **critical dynamic
stress state** of an MSUP transient (blade-out secondary / windmilling
vibrations) in the **virtual rig FE model**. Methodology and certification
framing: `MyLife/work/methodology-equivalent-static-loads.md`.

Companion tools in this folder:

- **`mcf_dpf_section_resultants`** — Route A (dynamic interface resultants over
  the full time history, straight from the modal `.rst` via DPF). This tool
  reuses its field-proven `.mcf` parser.
- **`ansys_load_reconstruction`** — the unit-load + least-squares precedent
  (strain gauges); the ESL solver follows the same diagnostics conventions
  (`normal_equations_used: false`, condition number always recorded).

## Launch

```bat
:: GUI (step-rail wizard, Fusion engineering style)
.\venv\Scripts\python.exe -m scripts.equivalent_static_load

:: CLI
.\venv\Scripts\python.exe -m scripts.equivalent_static_load derive --config cfg.json
```

Subcommands: `make-synthetic`, `check`, `suggest-instants`, `resultants`,
`derive`, `verify`. Exit codes: 0 ok · 2 input/config error · 3 solve
infeasible · 4 verification not accepted.

The GUI is self-documenting: every field, label, button, and table column
carries a rich HTML tooltip (with the governing formulas rendered) explaining
what it is, why it matters, and what the defaults imply — hover anything.
All tooltip texts live in `tooltips.py`, aligned with the methodology note.

## Five-minute offline demo (no Ansys needed)

```bat
.\venv\Scripts\python.exe -m scripts.equivalent_static_load make-synthetic --out demo
.\venv\Scripts\python.exe -m scripts.equivalent_static_load check --config demo\config.json
.\venv\Scripts\python.exe -m scripts.equivalent_static_load suggest-instants --config demo\config.json
.\venv\Scripts\python.exe -m scripts.equivalent_static_load derive --config demo\config.json
.\venv\Scripts\python.exe -m scripts.equivalent_static_load verify --config demo\config.json ^
    --case <case_id from output> --solved-field demo\esl_out\case_<id>\esl_field.csv
```

`demo/truth.json` holds the exact expected answers (`P_true`, `lambda_true`);
the derive output must reproduce them (this is also asserted by
`tests/test_equivalent_static_load.py`).

## Inputs

**Readable mockup examples of every format live in
[`examples/mockup_inputs/`](examples/mockup_inputs/README.md)** — a tiny,
internally consistent dataset (10 nodes, 3 modes, 2 channels) that runs
end-to-end (λ ≈ 1.6 by construction) and documents each column and the
cross-reference rules between files.

| Input | Format | Source |
|---|---|---|
| Modal stress CSV | `NodeID, X, Y, Z, sx_Mode1 … sxz_ModeN` | same export used for MARS |
| Modal coordinates | `.mcf` (or NASTRAN `.pch`) | Ansys MSUP transient |
| Unit-load fields | wide CSV `sx_<case_label>…` per channel, or per-case CSVs, or `.rst` (DPF) | one linear static solve per rig channel in the virtual rig model |
| Interface load history (optional, Tier-1 pattern) | wide CSV `Time, <channel>…` | whole-engine team (converted to canonical CSV) |
| Modal forces CSV (optional, Route A) | `NodeID, X, Y, Z, enfox_Mode1 … enmoz_ModeN` | same extraction pipeline |
| MARS envelope CSVs (optional, instant suggestion) | `max_von_mises.csv`, `time_of_max_von_mises.csv` | MARS run |

Unit-load solves may be run at any convenient magnitude — the tool normalizes
by each channel's `unit_load`.

## Method summary

- Target = full 6-component tensor field reconstructed at the chosen instant
  `t*` from the same modal basis as MARS (never MARS's scalar snapshot).
- **Tier 1** (pattern-scaled, "stress-matched DLF"): `P = λ·L(t*)`; λ is the
  effective dynamic amplification factor.
- **Tier 2** (constrained LS): best rig-realizable field match under channel
  bounds (push-only default) and ganged-channel ratios.
- Matching on tensor components; von Mises only for weighting/reporting.
- Validity: peak ratio at the critical node, hotspot table, weighted R²,
  **under-test zones**, residual field CSV for contouring.
- **Verification loop** (Open Item C1): apply `verify_forces_tier*.inp` in the
  rig model, run ONE combined nonlinear static solve, `verify` the exported
  field; `esl_loads_corrected.csv` carries the recommended `λ_corr` iteration.

## Real-data acceptance check

After the first real derive, confirm the reconstruction against MARS: the VM
value at the driver node/instant reported in `instants_used.csv` must equal
the node's value in MARS `max_von_mises.csv`. This ties both tools to the same
modal solution.

## Outputs (per derive run)

`run_manifest.json` (config echo + SHA-256 of every input — the traceability
anchor), `mapping_report.json`, `instants_used.csv`, `esl_report.md`, and per
case: `esl_loads.csv`, `target_field.csv`, `esl_field.csv`,
`residual_field.csv`, `hotspots.csv`, `under_test_nodes.csv`,
`verify_forces_tier*.inp`.

## Tests

```bat
.\venv\Scripts\python.exe -m pytest tests\test_equivalent_static_load.py tests\test_equivalent_static_load_gui.py -n auto
```
