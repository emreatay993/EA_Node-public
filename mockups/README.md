# COREX Mockups

Standalone visual prototypes live here. Run commands from the repository root
with the project virtual environment unless a mockup is plain HTML.

```powershell
.\venv\Scripts\python.exe <script>
```

In PyCharm, use the repository root as the working directory and
`venv\Scripts\python.exe` as the interpreter. For HTML mockups, right-click the
HTML file and choose `Open in Browser`.

## Node creation wizard mockups

Launcher for all four wizard concepts:

```powershell
.\venv\Scripts\python.exe mockups\run_all.py
```

PyCharm: create a Python run configuration with script path
`mockups/run_all.py`.

Useful variants:

```powershell
.\venv\Scripts\python.exe mockups\run_all.py --selftest
.\venv\Scripts\python.exe mockups\run_all.py --shots
```

Individual entry points:

```powershell
.\venv\Scripts\python.exe mockups\design1_stepped_wizard.py
.\venv\Scripts\python.exe mockups\design2_single_page_preview.py
.\venv\Scripts\python.exe mockups\design3_sidebar_sections.py
.\venv\Scripts\python.exe mockups\design4_canvas_inline.py
```

## Laser pointer and notetaking

```powershell
.\venv\Scripts\python.exe mockups\laser_pointer_notetaking_prototype.py
.\venv\Scripts\python.exe mockups\laser_pointer_notetaking_prototype.py --selftest
```

PyCharm: create a Python run configuration with script path
`mockups/laser_pointer_notetaking_prototype.py`.

## Linking feature concepts

```powershell
.\venv\Scripts\python.exe mockups\linking_feature_prototype.py
.\venv\Scripts\python.exe mockups\linking_feature_prototype.py --selftest
```

PyCharm: create a Python run configuration with script path
`mockups/linking_feature_prototype.py`.

## Comment badge concepts

Five lower-right node comment-badge designs (count pill, dog-ear fold, sticky
peek, bubble tail, dot-to-chip) on a shared five-state node strip, including
resize-grip coexistence:

```powershell
.\venv\Scripts\python.exe mockups\comment_badge_showcase_prototype.py
.\venv\Scripts\python.exe mockups\comment_badge_showcase_prototype.py --selftest
.\venv\Scripts\python.exe mockups\comment_badge_showcase_prototype.py --shot mockups\comment_badge_showcase\_shots\concept_a_dark.png --concept a
.\venv\Scripts\python.exe mockups\comment_badge_showcase_prototype.py --shot mockups\comment_badge_showcase\_shots\concept_a_light.png --concept a --light
```

PyCharm: create a Python run configuration with script path
`mockups/comment_badge_showcase_prototype.py`. Screenshot output under
`mockups/comment_badge_showcase/_shots/` is intentionally ignored.

Static render helper for posed concept screenshots:

```powershell
.\venv\Scripts\python.exe mockups\_linking_render.py mockups\linking_feature\_RenderA.png _RenderA.qml dark
.\venv\Scripts\python.exe mockups\_linking_render.py mockups\linking_feature\_RenderB.png _RenderB.qml light
```

## QML feature showcase

```powershell
.\venv\Scripts\python.exe mockups\qml_features_showcase_prototype.py
.\venv\Scripts\python.exe mockups\qml_features_showcase_prototype.py --selftest
.\venv\Scripts\python.exe mockups\qml_features_showcase_prototype.py --shot mockups\qml_features_showcase\showcase.png
.\venv\Scripts\python.exe mockups\qml_features_showcase_prototype.py --shot mockups\qml_features_showcase\breakpoint.png --bp
```

PyCharm: create a Python run configuration with script path
`mockups/qml_features_showcase_prototype.py`. Add `--selftest` or `--shot ...`
under parameters when needed.

## DOCX rendering comparison

```powershell
.\venv\Scripts\python.exe mockups\docx_rendering_comparison\run.py
.\venv\Scripts\python.exe mockups\docx_rendering_comparison\run.py --input C:\path\to\document.docx
.\venv\Scripts\python.exe mockups\docx_rendering_comparison\run.py --selftest
```

PyCharm: create a Python run configuration with script path
`mockups/docx_rendering_comparison/run.py`. Optional renderer outputs are written
under `mockups/docx_rendering_comparison/_outputs/`, which is intentionally
ignored.

This prototype probes optional local renderers at runtime. Microsoft Word,
LibreOffice, commercial renderers, or conversion packages may be skipped if they
are not installed on the machine.

## Tabular data input concepts

Open the interactive HTML chooser:

```powershell
Start-Process .\mockups\tabular_data_input_corex_2026\index.html
```

PyCharm: right-click `mockups/tabular_data_input_corex_2026/index.html` and
choose `Open in Browser`.

Static reference screenshots live under
`mockups/tabular_data_input_corex_2026/_shots/`.

## Comment and folder-explorer HTML mockups

Open these directly in a browser:

```powershell
Start-Process .\mockups\add_comment_mockups.html
Start-Process .\mockups\add_comment_unified.html
Start-Process .\mockups\add_comment_unified_polished_variants.html
Start-Process ".\mockups\COREX Comments - Unified Variants.standalone.html"
Start-Process .\mockups\folder_explorer_option2_mockup.html
```

PyCharm: right-click any HTML file and choose `Open in Browser`.

## Node comment QML mockup

Package-owned QML reference for graph node comment badges, hover peeks, and the
Inspector comments section:

```powershell
.\venv\Scripts\python.exe -m ea_node_editor.mockups.node_comments
.\venv\Scripts\python.exe -m ea_node_editor.mockups.node_comments --theme dark
.\venv\Scripts\python.exe -m ea_node_editor.mockups.node_comments --theme light
.\venv\Scripts\python.exe -m ea_node_editor.mockups.node_comments --screenshot-dir artifacts\mockups\node_comments
```

## Generated outputs

Generated screenshots and DOCX comparison outputs are intentionally ignored:

- `mockups/_shots/`
- `mockups/comment_badge_showcase/_shots/`
- `mockups/docx_rendering_comparison/_shots/`
- `mockups/docx_rendering_comparison/_outputs/`
