# Tabular Plot Showcase

`tabular_plot_showcase.cxproj` and `tabular_plot_showcase_direct.cxproj` are self-contained example projects that load different tabular sources and route them into the generic plot node family.

The original showcase keeps the adapter-based flow:

`Tabular Data Input -> Python Script adapter -> Plot node`

The direct showcase exercises hybrid tabular auto-plotting without adapter nodes:

`Tabular Data Input -> Plot node`

The project-managed sources live in each project's sibling `.data` directory:

- `tabular_plot_showcase.data/nodes/<input-node-folder>/in/tabular/source/`
- `tabular_plot_showcase_direct.data/nodes/<input-node-folder>/in/tabular/source/`

Both projects cover CSV, TSV, XLSX, TXT, NPY, NPZ, Parquet, and HDF5 inputs. Run the workflow from `Start` to emit render requests for line, scatter, bar, histogram, heatmap, contour, surface, point cloud, and streamlines plots.

Regenerate both examples with:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_tabular_plot_showcase_example.py
```
