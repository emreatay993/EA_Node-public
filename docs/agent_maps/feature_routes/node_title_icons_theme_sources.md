# Node Title Icons And Theme Sources

## Purpose
Use this for built-in node title icon metadata, theme-aware icon rendering, icon assets, and icon validation.

## Start Here
- `ea_node_editor/nodes/builtins/icon_catalog.py`
- `ea_node_editor/assets/node_title_icons/`
- `ea_node_editor/ui_qml/node_title_icon_sources.py`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHeaderLayer.qml`
- `scripts/check_node_title_icons.py`

## Notes
- Passive flowchart nodes are shape-backed, not icon-backed. Keep `passive.flowchart.*` out of `icon_catalog.py`; their visuals route through `surface_family="flowchart"` and `surface_variant`.
- SSH/SFTP uses six owned SVGs under `assets/node_title_icons/ssh_sftp/`; no active `hpc/*` catalog entries or assets remain.
- Mechanical uses eight COREX-owned SVG masks under `assets/node_title_icons/mechanical/`. `node_title_icon_sources.py` admits that central path only for trusted registry provenance rooted under COREX's own add-on package tree and a matching catalog entry; external file/package provenance never gains central fallback by matching an ID.
- Public function-package title icons use registry provenance rooted at the verified immutable generation. `graph_scene_payload/builder.py` and `backdrop_partitioner.py` project that provenance without synthesizing a public descriptor; the resolver still rejects path escape and unsupported suffixes.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_node_title_icon_assets.py tests/test_node_title_icon_sources.py --ignore=venv -q
```

## Breadcrumbs
- [Assets, Icons, Title Icons, And Theme Assets](../subsystems/assets_icons_theme.md)
- [Nodes, Registry, Built-ins, And Plugin Loading](../subsystems/nodes_registry_builtins.md)
- [SSH/SFTP Nodes](ssh_sftp_nodes.md)

## Update Triggers
Update when icon assets, icon catalog entries/exclusions, source projection, theme rendering, or icon tests change.
