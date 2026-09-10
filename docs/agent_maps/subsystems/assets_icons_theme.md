# Assets, Icons, Title Icons, And Theme Assets

## Purpose
Use this for app assets, app icons, shell/ui icon registry assets, node title icons, theme-aware icon sources, QML theme projection, and graphics theme defaults.

## Start Here
- `ea_node_editor/nodes/builtins/icon_catalog.py`
- `ea_node_editor/assets/`
- `ea_node_editor/assets/node_title_icons/`
- `ea_node_editor/addons/mars/icons/`
- `ea_node_editor/ui/icon_registry.py`
- `ea_node_editor/ui_qml/components/shell/icons/`
- `ea_node_editor/ui_qml/node_title_icon_sources.py`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHeaderLayer.qml`
- `ea_node_editor/ui/theme/`
- `scripts/generate_app_icons.py`
- `scripts/check_node_title_icons.py`

## Do Not Start Here
- Project persistence for app-wide assets/preferences.
- QML header rendering before checking icon source projection.

## Common Changes
- Keep icon catalog, asset files, QML source projection, and tests aligned.
- SSH/SFTP built-ins own six title icons under `assets/node_title_icons/ssh_sftp/`. The retired HPC icon directory is absent; COREX's `HPC` connector keywords do not restore an HPC asset family.
- The trusted Mechanical add-on owns eight central theme-aware SVG masks under `assets/node_title_icons/mechanical/`. Central fallback requires registry provenance rooted inside COREX's own add-on package tree plus the matching central catalog entry; external packages remain confined to their verified asset/generation root even when they spoof a reserved type ID.
- Branded add-on title icons stay with their owning package. MARS resolves `addons/mars/icons/mars_icon_64.png`, the 64 px frame from its official ICO, through package provenance so Qt displays the complete executable artwork without SVG text/clip loss or monochrome tinting.
- Public schema-2 plugin icons are declared, hashed package assets resolved through `PythonFunctionEntry` provenance rooted at the immutable generation. Do not resolve them from mutable author/install paths; loose plugins use the default icon.
- Passive flowchart nodes intentionally do not use the icon catalog or title-icon assets; their library and canvas visuals come from `surface_family="flowchart"` plus `surface_variant`.
- Register shell toolbar icons in `ui/icon_registry.py`; QML should consume them through `uiIcons.sourceSized(...)` instead of drawing duplicate inline glyphs.
- Timestamp toolbar affordances use the shell icon registry (`keep-live`, `clock-update`, `calendar`) so graph-surface actions stay on the shared asset path. Subnode toolbar entry uses the Tabler-sourced `door-enter` icon through the same registry. Annotation text formatting actions also use registered Tabler-sourced shell icons.
- Media Panel video-mode toolbar and fullscreen controls use semantic registered Tabler-sourced `video-*` shell icons, including `video-trim-save`; keep inline QML action names on those registry keys instead of reusing generic browser/title/frame glyphs.
- Durable node linking icons use registered Tabler-sourced shell icons such as `link`, `file-text`, `folder`, `layout-dashboard`, `hierarchy-2`, `plus`, and `x`; QML should consume them through `uiIcons.sourceSized(...)` so theme recoloring stays centralized.
- Node comment actions (canvas popover + inspector section) use registered Tabler-sourced shell icons `reply` (arrow-back-up.svg), `check`, `pin`/`pin-off` (pinned-off.svg), `rotate-clockwise`, `delete`, `send`, and `x` as icon-only buttons with tooltips; keep those registry keys instead of reintroducing text-only buttons or inline glyph duplicates.
- Shell icons sourced from Tabler must keep `TABLER_SOURCES.txt` and `TABLER_LICENSE.txt` aligned, and packaging must include those `.txt` notices with the QML runtime assets.
- Regenerate app icon sets with the documented script when source app icons change.
- For theme-aware title icons, update requirements/proof docs only when formal specs change.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_icon_registry.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_node_title_icon_assets.py tests/test_node_title_icon_sources.py --ignore=venv -q
```

## Breadcrumbs
- [Node Title Icons And Theme Sources](../feature_routes/node_title_icons_theme_sources.md)
- [Graphics Settings, Themes, And Preferences](../feature_routes/graphics_settings_themes_preferences.md)
- [Durable Node Linking](../feature_routes/durable_node_linking.md)
- [SSH/SFTP Nodes](../feature_routes/ssh_sftp_nodes.md)

## Update Triggers
Update when asset generation, title icon routing, SSH/SFTP icon ownership, icon validation, durable node link shell icons, passive flowchart icon-catalog exclusions, theme defaults, or graph header icon rendering changes.

## 2026-07-11 Performance Ownership

- `ui/theme/service.py` caches palette projection until the existing theme revision changes. Tooltip/category projection follows its policy revision; neither owner introduces an independent invalidation channel.
