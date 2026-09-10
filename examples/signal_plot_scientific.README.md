# Signal Plot scientific examples

From the repository root, generate a small portable workflow:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_signal_plot_scientific_example.py
```

Open `artifacts/examples/signal_plot_scientific.cxproj` in COREX and run it. It
contains three direct chains: CSV Tabular Data Input, a NumPy Python Script, and
a pandas Python Script, each connected to Signal Plot and a Media Panel. The CSV travels with the
adjacent `.data` folder. `--output <path.cxproj>` chooses another destination.
Run the workflow to show all three images in the Media Panels. Image Export can
be connected separately when a PNG file is needed.

The scripts produce 256 rows with sample, sine, cosine and ramp columns. Their
outputs use concrete scientific type IDs and item access. The CSV takes its
numeric X from the first column; arrays and DataFrames follow the same mapping.
Change X mode to Sample index to plot all four numeric columns independently.

Run the complete process/runtime performance workload separately:

```powershell
.\venv\Scripts\python.exe .\scripts\benchmark_signal_plot.py --scientific --rows 2000000
```

This runs ndarray and DataFrame sources through both ProcessExecutionClient and
CorexRuntime twice and prints JSON summaries with elapsed time, combined
parent/child RSS, complete source checks, point counts and reuse decisions. It
requires enough RAM for transport copies. See the [usage guide](../docs/SIGNAL_PLOT_GUIDE.md)
and [recorded evidence](../docs/specs/perf/SIGNAL_PLOT_SCIENTIFIC_INPUTS_QA.md).
