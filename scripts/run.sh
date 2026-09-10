#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${EA_NODE_EDITOR_PYTHON:-python}"

cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" -m ea_node_editor.bootstrap "$@"
