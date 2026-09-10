# Ansys Mechanical reaction-force handoff snippets

These APDL snippets are intended for Mechanical command snippets in a structural analysis.
They convert reactions from a displacement-constrained named selection into nodal force
loads for a later load step.

## Files

- `reaction_to_force_next_step.mac`: place in load step `N+1`. It reads reaction forces
  from load step `N`, removes selected displacement constraints, and applies nodal
  `FX`, `FY`, and `FZ` loads. This single-block form must enter `/POST1` in the target
  step; use the two-block button workflow below when ramped source-step result history
  must be preserved.
- `reaction_to_force_two_block_source_prep.mac`: place in load step `N` with the
  Mechanical command object property **Issue Solve Command** set to **No**. It solves
  the source step, reads the final source-step nodal reactions directly from the
  just-solved database, and leaves them in APDL memory for the target block.
- `reaction_to_force_two_block_target_apply.mac`: place in load step `N+1`. It restores
  the in-memory source-step arrays, removes selected displacement constraints, and
  applies nodal `FX`, `FY`, and `FZ` loads without entering `/POST1`.
- `reaction_to_force_ddele_rforce_release.mac`: uses APDL's `DDELE,...,FORCE` behavior
  to ramp released displacement constraints from previous-step reactions. This is a
  release/ramp shortcut, not a manual per-node force hold.
- `button_add_reaction_force_handoff.py`: Mechanical IronPython button script. It prompts
  for a Static or Transient analysis, a valid named selection through an autocomplete
  dropdown, and a source load step, then creates the two block-based command snippets at
  load steps `N` and `N+1`. The APDL blocks are embedded directly in the script, so the
  button does not depend on the `.mac` files at runtime.

## Required edits

In each file, edit the settings block near the top:

- `RTF_NS_NAME='MY_NAMED_SELECTION'`
- `RTF_SOURCE_LS=1` for the single-block next-step extraction snippet
- `RTF_FORCE_SCALE=1.0`, or `-1.0` if your sign convention requires the opposite load
- component and constraint flags for `X`, `Y`, and `Z`

`RTF_NS_NAME` is an APDL scalar character parameter and is limited to 32 characters. If
your solver component name is longer, replace `RTF_NS_NAME` directly in the `*GET` and
`CMSEL` commands with the literal component name.

## Scoping expectations

Mechanical sends geometry face, edge, and vertex named selections to the solver as node
components. Element-face named selections are also sent as nodes by default. If an
element-face named selection is sent as Mesh200, these snippets accept the resulting
MESH200 element component and reduce it to its attached active nodes.

Body, ordinary element, area, line, keypoint, volume, and assembly components are rejected
with `*MSG,ERROR`.

The source load step must have reaction solution output available. The two-block source
block sets `OUTRES,RSOL,ALL`, solves the source step, then reads `RF` values immediately
without issuing `/POST1,SET` between Mechanical load-step solves.

## Solver behavior validated

The button workflow sets the source command object's `IssueSolveCommand` property to
`False` and the target command object's property to `True`. This is required because the
source APDL block performs the source-step `SOLVE` itself, then keeps the extracted
reaction arrays in APDL memory. The target block reads those arrays directly and applies
forces before Mechanical's target-step solve.

The two-block button workflow is intended to run both snippets in the same Mechanical
solve. It deliberately avoids `FINISH`, `/PREP7`, `/POST1`, `PARSAV`, and `PARRES` in
the source/target handoff blocks so Workbench load-step bookkeeping is not restored from
an earlier step. If you solve the source step, close/restart MAPDL, and later solve the
target step separately, the in-memory arrays will not exist; use a purpose-built
selective data-file export/import for that case.

Do not insert `/POST1,SET` between the source and target solves in this workflow. In a
ramped static two-step validation, doing so collapsed the final RST timeline into a
stepped history. Reading `RF` values directly after the source `SOLVE` preserved the
source ramp and the target hold:

- source result times: `0.25, 0.5, 0.75, 1.0`
- target result times: `1.25, 1.5, 1.75, 2.0`
- max target displacement difference from source-end displacement:
  `2.0418111645881254e-12`
- max target nodal von-Mises stress difference from source-end stress: `0.0`

The target snippet issues `KBC,1` before the target solve so the force handoff is a
stepped replacement state rather than a ramped or accumulated force in the target step.

If the original Mechanical displacement object is deactivated in the target step,
Mechanical can emit `DDELE,...,FORCE` before the target command snippet. That command can
create ramped release-force loads from the previous-step reactions. The target snippet
therefore deletes displacement constraints and existing nodal `FX`, `FY`, and `FZ` loads
by explicit saved handoff node ID for the components it is about to replace, then applies
the saved source-step forces. This keeps the target step from carrying both Mechanical's
release loads and the explicit handoff loads without clearing unrelated nodal constraints
or forces outside the handoff nodes.
