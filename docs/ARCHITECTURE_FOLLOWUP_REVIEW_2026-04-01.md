# Architecture Follow-Up Review

- Date: `2026-04-01`
- Repository: `EA_Node_Editor`
- Review mode: read-only architecture assessment with scoped subagent coverage

## Verdict

The architecture is `mixed`.

The repository has a credible package split and some real boundary work, but the implementation still contains a few high-impact knots:

- `ea_node_editor/ui/shell/window.py` is still the effective application hub.
- `ea_node_editor/ui/shell/composition.py` is a second concentration point instead of the only composition root.
- `ui.shell` and `ui_qml` remain tightly interlocked through bridge wrappers, broad context export, and host coupling.
- graph mutation authority is fragmented across `graph`, `ui.shell`, and `ui_qml`.
- `graph.model` still carries persistence concerns, and runtime snapshot creation still round-trips through persistence-oriented serialization.
- viewer session ownership is spread across execution, host-service, bridge, and QML surface layers.

## Highest-Priority Follow-Up Refactors

1. Make shell composition singular: reduce `ShellWindow` to lifecycle and top-level Qt ownership, and keep `composition.py` as the only packet-owned composition root.
2. Finish the shell/QML contract cleanup: retire remaining compatibility bridge wrappers and broad host/controller facades.
3. Remove residual `graph` to `persistence` coupling and keep persistence metadata outside graph-owned models.
4. Build runtime inputs directly from domain objects instead of serializing through the project codec.
5. Collapse graph authoring onto one command authority and remove global boundary-adapter registration.
6. Make viewer session state single-authority in execution code, with bridge and host layers limited to projection and widget hosting.
7. Close out docs and verification with focused proof artifacts instead of preserving stale structural debt.

## Packetization Intent

The follow-up packet set below turns those findings into sequential packets so each worker owns one narrow slice at a time, with explicit handoff points between shell composition, shell surface cleanup, graph/persistence cleanup, runtime cleanup, graph authoring, viewer authority, and final documentation or traceability.
