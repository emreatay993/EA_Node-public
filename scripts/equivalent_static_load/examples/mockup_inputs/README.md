# Mockup inputs — every ESL file format, small enough to read

A miniature but **internally consistent** dataset: 10 casing nodes, 3 modes,
2 rig channels, 21 time steps (0…20 ms). Open any file in a text editor — the
values are rounded and the node/channel names cross-reference exactly the way
your real files must.

Built-in ground truth: the modal stress fields are linear combinations of the
two unit fields, and the interface load history is `P_true(t) / 1.6` — so a
derive run on this folder reports **λ (effective DLF) ≈ 1.6** and a near-exact
Tier-2 field match. The governing instant is **t\* = 0.004 s**.

## Try it

```bat
cd <repo-root>
.\venv\Scripts\python.exe -m scripts.equivalent_static_load check           --config scripts\equivalent_static_load\examples\mockup_inputs\mockup_config.json
.\venv\Scripts\python.exe -m scripts.equivalent_static_load suggest-instants --config scripts\equivalent_static_load\examples\mockup_inputs\mockup_config.json
.\venv\Scripts\python.exe -m scripts.equivalent_static_load resultants       --config scripts\equivalent_static_load\examples\mockup_inputs\mockup_config.json --t 0.004
.\venv\Scripts\python.exe -m scripts.equivalent_static_load derive           --config scripts\equivalent_static_load\examples\mockup_inputs\mockup_config.json
.\venv\Scripts\python.exe -m scripts.equivalent_static_load verify           --config scripts\equivalent_static_load\examples\mockup_inputs\mockup_config.json --case t0p004000 --solved-field scripts\equivalent_static_load\examples\mockup_inputs\solved_field_example.csv
```

Or in the GUI: **Load Config…** → pick `mockup_config.json` → walk the steps.
Outputs land in `esl_out/` next to the config (git-ignored).

## The files, one by one

### `modal_stress.csv` — per-mode nodal stress tensors (REQUIRED)

The same export MARS consumes. One row per node; six stress components per
mode, mode blocks side by side:

| column | meaning |
|---|---|
| `NodeID` | node number (duplicates keep the **last** row — MARS parity) |
| `X, Y, Z` | nodal coordinates [length units] — needed for mesh mapping |
| `sx_Mode1 … sxz_Mode1` | mode-1 stress tensor (sx, sy, sz, sxy, syz, sxz) per unit modal coordinate |
| `sx_Mode2 …` | same for mode 2, and so on |

Column matching is case-insensitive contains-match (`sx_`, `sxy_`, …); the
number of modes per component must be equal, and must equal the mode count of
the modal-coordinates file (hard error otherwise — different modal basis).

### `run.mcf` — modal coordinates q_j(t) (REQUIRED, alternative: `.pch`)

```
Mockup MSUP transient - blade-out secondary vibrations   <- free header line(s)
Number of Modes: 3                                       <- required, with colon
Time        Coordinates                                  <- required table header
 0.0000   0.00000   0.00000   0.00000                    <- time, q1, q2, q3
 0.0010   0.36398   0.33126   0.22513
 ...
```

Wrapped continuation lines (MCFOPT) are handled. Requested instants snap to
this time grid.

### `run.pch` — the same q_j(t) in NASTRAN SOL112 punch format

`$DISPLACEMENTS (SOLUTION SET)` sections, one `$POINT ID = j` block per mode,
data rows `time M value …`. Use either `.mcf` or `.pch` — this folder ships
both so you can compare the formats; the config points at `run.mcf`.

### `rig_unit_fields.csv` — unit-load stress fields from the virtual rig model (REQUIRED)

Wide layout, same schema idea as the modal stress CSV but **per channel**
instead of per mode: `sx_Case1 … sxz_Case1, sx_Case2 … sxz_Case2`. The suffix
must equal each channel's `case_label` in the config. Values are the
**as-solved** stresses of one linear static solve per channel (here at
1000 N); the tool normalizes to per-newton influence fields by dividing by
`unit_load`. All channels must share the same node set.

### `interface_history.csv` — interface load-time histories (optional, Tier-1 pattern)

```
Time,Fz_front_mount,Fy_front_mount
0.0000,0.0,0.0
0.0010,785.6,-154.6
...
```

Canonical wide format: a `Time` column plus one named column per load channel
(convert the whole-engine team's format into this once). Each rig channel
selects its column via `interface_channel` in the config — here
`P1_fwd_vert → Fz_front_mount`, `P2_fwd_lat → Fy_front_mount`. Off-grid
instants are linearly interpolated (flagged in the report).

### `modal_forces.csv` — per-mode element nodal forces/moments (optional, Route A)

Same layout idea as the modal stress CSV with force/moment components
`enfox, enfoy, enfoz` [N] and `enmox, enmoy, enmoz` [N·mm] per mode. Consumed
by the `resultants` command together with an interface node list to
reconstruct the dynamic interface resultants at t\*.

### `front_mount_nodes.csv` — interface cut node list (Route A)

A single `NodeID` column listing the nodes of one interface cut. The config's
`interfaces[]` entry pairs it with the **whole-engine reference point**
(`ref_point`) that moments are transferred to: M_ref = Σm_i + Σ(r_i−r_ref)×f_i.

### `steady_field.csv` — steady/bias stress field (optional)

`NodeID, sx … sxz`. A pressure/thermal prestress field. Kept **out** of the
ESL target by default (`include_steady_bias: false`) because the rig applies
pressure physically — including it would double-count (methodology §7).

### `max_von_mises.csv` + `time_of_max_von_mises.csv` — MARS envelope outputs (optional)

`NodeID, X, Y, Z, <value>` — per-node peak von Mises and the time it occurs
(exactly what a MARS batch solve writes). Used by `suggest-instants` to
cluster hotspot times-of-max into candidate instants. In this mockup they were
computed honestly from the modal data, so the suggested governing instant is
t\* = 0.004 s.

### `pattern_example.csv` — explicit Tier-1 pattern (optional override)

```
channel,value
P1_fwd_vert,1695.6
P2_fwd_lat,-280.8
```

One row per rig channel (names must match). Alternative to the load history —
typical use: paste Route-A resultants at t\* here; then λ ≈ 1 is expected.
(This example holds L(t\*) = P_true(t\*)/1.6, so deriving with it also gives
λ ≈ 1.6.)

### `solved_field_example.csv` — verification input format

`NodeID, X, Y, Z, sx … sxz` — the nodal stress export of the combined
verification solve (real contacts, pressure on). This example is the target
at t\* scaled by 0.97, so `verify` reports peak ratio ≈ 0.97 and recommends
λ_corr ≈ 1.031 — demonstrating the correction loop.

### `region_nodes_example.csv` — evaluation-region node list (optional)

A `NodeID` column for region mode `node_list_csv` (e.g. exported from a
Mechanical named selection). The mockup config uses `top_vm_percent: 100`
instead, since there are only 10 nodes.

### `mockup_config.json` — ties everything together

Relative paths resolve against the config's folder. Hover any field in the
GUI for the full explanation of the corresponding setting, or see
`example_config.json` one level up for a realistically-sized template.

## Cross-reference rules (the ones that must match)

| this name… | …must equal |
|---|---|
| unit-field column suffix (`sx_Case1`) | channel `case_label` |
| load-history column (`Fz_front_mount`) | channel `interface_channel` |
| pattern CSV `channel` | channel `name` |
| mode count in `modal_stress.csv` | mode count in `run.mcf` / `run.pch` |
| `NodeID`s in `front_mount_nodes.csv` | rows present in `modal_forces.csv` |
| units everywhere | the `units` block (never auto-converted) |
