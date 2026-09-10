# MARS Add-on

COREX can run the MARS modal response solver without loading solver code into
the desktop or workflow worker. The `mars.corex` add-on installs MARS into the
COREX Python environment and launches its `MARSBatch` console entry point as
an isolated process.

## Install and enable

1. Open **Add-On Manager**.
2. Select **MARS**.
3. Click **Install**. COREX selects its Python environment, installs the declared
   local MARS source or bundled wheel without changing COREX-owned dependencies,
   verifies version `1.0.0` and
   `MARSBatch.exe`, then enables the nodes without restarting.
4. Use **Disable** to hide the nodes without uninstalling MARS. A packaged COREX
   update with a different pinned MARS version exposes **Update**.

Installation is blocked while a workflow is active. Source checkouts install
only the sibling `MARS_` repository editable into the active COREX interpreter
with `--no-deps`; they do not create another venv, upgrade pip, or reinstall
COREX. A first source run can therefore show MARS as unavailable until **Install**
has been clicked once for the repo venv. Any existing AppData runtime is ignored
and left untouched during source use.

Packaged COREX cannot reuse its frozen executable as Python, so it keeps one
app-managed AppData environment. It installs the contained COREX wheel first and
then the contained MARS wheel with `--no-deps`; MARS is never downloaded from
PyPI.

## Nodes

All three nodes are under the **MARS** category and use the official MARS app
icon. COREX keeps the icon's original brand colors instead of theme-tinting it.

- **MARS Batch Solve** builds a schema-v1 all-node envelope job. Connect modal
  coordinates and the prepared or RST result families needed by the selected
  outputs. Result, mode, RST, fatigue, plasticity, and runtime settings are
  grouped in the Inspector.
- **MARS Time History** requires a node ID and one non-damage result. It
  returns `history_csv` with physical time and the applicable result columns.
- **MARS Run Job** accepts an existing schema-v1 JSON job. Relative inputs still
  resolve against that job, while COREX overrides its output directory with
  node-owned scratch storage.

Batch and advanced-job nodes expose representative result paths through
`von_mises`, `max_principal`, `min_principal`, `deformation`, `velocity`,
`acceleration`, `force`, `moment`, and `damage`. Only produced ports are emitted.
Every run also returns:

- `manifest`: the portable `mars_result.json` record;
- `files`: all produced files keyed by relative result path;
- `exec_out` and `on_failed` for workflow routing.

Every returned path is a COREX managed artifact reference. Connect it directly
to path consumers such as File Read, Excel Read, or Tabular Data Input.

## Runtime behavior

COREX invokes the absolute `MARSBatch.exe` beside the selected environment's
Python with `shell=False` and fixed arguments. JSONL progress and warnings
appear in workflow logs. A stop
request terminates the process, waits for the configured grace period, and
kills it if necessary. Malformed output, missing terminal results, nonzero exit
codes, timeouts, or paths outside scratch storage fail the node without
registering partial artifacts.

If Workflow Settings selects a different Python for the workflow worker, COREX
passes the desktop-selected add-on Python path into that worker. MARS therefore
continues launching from the environment where Add-On Manager installed it;
preparing a workflow runtime does not duplicate or relocate MARS.

For direct MARS package and JSON schema documentation, see the sibling MARS
repository's `README.md` and `MARS_USER_MANUAL.md`.
