from __future__ import annotations

import json
import unittest
from pathlib import Path

from ea_node_editor.settings import SCHEMA_VERSION


_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "persistence"


def _load_persistence_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _current_schema_minimal_payload() -> dict[str, object]:
    return _load_persistence_fixture("schema_current_minimal.json")


def _current_schema_inconsistent_payload() -> dict[str, object]:
    return _load_persistence_fixture("schema_current_inconsistent.json")


def _missing_plugin_round_trip_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": "proj_missing_plugin_round_trip",
        "name": "Missing Plugin Round Trip",
        "active_workspace_id": "ws_plugin",
        "workspace_order": ["ws_plugin"],
        "workspaces": [
            {
                "workspace_id": "ws_plugin",
                "name": "Workspace Plugin",
                "active_view_id": "view_plugin",
                "views": [
                    {
                        "view_id": "view_plugin",
                        "name": "V1",
                        "zoom": 1.0,
                        "pan_x": 0.0,
                        "pan_y": 0.0,
                    }
                ],
                "nodes": [
                    {
                        "node_id": "node_unknown",
                        "type_id": "plugin.missing_transform",
                        "title": "Missing Transform",
                        "x": 160.0,
                        "y": 0.0,
                        "collapsed": True,
                        "properties": {"threshold": 0.75},
                        "exposed_ports": {"plugin_in": True},
                        "visual_style": {"fill": "#123456"},
                        "parent_node_id": None,
                        "custom_width": 280.0,
                        "plugin_payload": {"preset": "wide", "stops": ["a", "b"]},
                    },
                ],
                "edges": [],
            }
        ],
        "metadata": {},
    }


if __name__ == "__main__":
    unittest.main()
