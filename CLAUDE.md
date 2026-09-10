# CLAUDE.md — COREX Node Editor

This project's full agent discipline lives in **[AGENTS.md](AGENTS.md)** — navigation, verification, architecture boundaries, compatibility policy, and exploration rules. Read it for anything non-trivial. This file is the Claude Code entry point; `AGENTS.md` stays the source of truth (Codex reads it natively). The highlights you need most:

- **Run / dev launch:** `.\venv\Scripts\python.exe -m ea_node_editor.bootstrap` (use the project venv for all Python/PyQt/pytest/QML commands).
- **Navigate before grepping:** `.\venv\Scripts\python.exe scripts\nav.py find <term>` — subcommands `route`, `qml`, `source`. It queries the committed indexes and returns the owning agent-map, source/test/QML candidates, focused-verification commands, and map section anchors in a few hundred tokens, instead of grepping the 0.6 MB / 3.4 MB index files. `nav.py source <path>` tells you which map owns a file you already have. Fall back to `docs/agent_maps/INDEX.md` only if the CLI under-resolves.
- **Verify:** `.\venv\Scripts\python.exe scripts\run_verification.py --mode fast` (use `gui` for QML-heavy work, `slow` for perf, `full` for release confidence). After editing any `docs/agent_maps/**` map, also run `.\venv\Scripts\python.exe scripts\check_agent_maps.py`.
- **Architecture boundaries:** keep `ea_node_editor/graph/` independent of UI and persistence; keep execution snapshot assembly in `ea_node_editor/execution/`; keep `.cxproj` document handling in `ea_node_editor/persistence/`. See AGENTS.md §Architecture Boundaries before cross-layer edits.
- **Shared helpers:** small utilities used by 2+ subsystems belong in `ea_node_editor/common/` — check there before adding a subsystem-local copy.
