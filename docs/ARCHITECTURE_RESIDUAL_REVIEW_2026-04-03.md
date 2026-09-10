# Architecture Residual Review

- Date: `2026-04-03`
- Repository: `EA_Node_Editor`
- Review mode: read-only architecture assessment with orchestrator plus scoped subagent coverage

## Verdict

The architecture is `mixed`.

The repository has a real package split, solid requirement anchors, and better-than-average architecture documentation, but a few structural seams still carry too much authority:

- `ea_node_editor/ui/shell/window.py` remains too large and too central.
- shell lifecycle teardown is still weak enough that fresh-process shell isolation shapes the verification story.
- `graph_scene_bridge.py`, `viewer_session_bridge.py`, and `viewer_session_service.py` still mix projection, command, and policy responsibilities.
- `execution/runtime_snapshot.py` still pulls persistence-oriented normalization into the normal execution boundary.
- `graph/model.py` still knows how to manufacture `WorkspaceMutationService`, which leaves an avoidable domain-service cycle in place.
- `nodes` and `execution` still share runtime and viewer contracts through bidirectional imports instead of a neutral ownership layer.
- architecture verification is effective but still too text-coupled and too manual in the shell-isolation catalog path.

## Highest-Priority Residual Refactors

1. Finish shrinking `ShellWindow` into a lifecycle and top-level Qt host instead of a broad application-command surface.
2. Make shell construction and teardown deterministic enough that packet-owned lifecycle tests can create and close multiple windows in one interpreter process.
3. Split graph-scene and viewer-session bridges into smaller read-model and command-authority seams.
4. Move persistence-specific normalization out of the normal execution-side runtime-snapshot boundary.
5. Remove the `GraphModel` to `WorkspaceMutationService` factory relationship and inject mutation authority from composition-level code.
6. Extract shared runtime handle, artifact, and viewer contracts into a neutral package so `nodes` and `execution` no longer depend on each other directly for packet-owned internals.
7. Replace brittle text-snippet architecture assertions and manual shell-backed test catalogs with semantic, manifest-owned proof.

## Packetization Intent

The residual packet set below turns those findings into a sequential execution program:

- `P01` finishes the remaining shell-host surface retirement.
- `P02` hardens shell lifecycle isolation and repeated in-process construction.
- `P03` decomposes the graph-scene bridge surface.
- `P04` narrows viewer-session projection versus authority.
- `P05` decouples execution-side runtime snapshot assembly from persistence normalization.
- `P06` removes the graph model-to-service construction cycle.
- `P07` extracts shared runtime contracts into a neutral ownership layer.
- `P08` closes the program with semantic verification, shell-catalog hardening, and docs or traceability updates.
