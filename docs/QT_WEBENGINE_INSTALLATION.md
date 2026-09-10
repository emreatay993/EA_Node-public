# Qt WebEngine Installation Guide

Use this guide when QWebEngine-backed nodes such as `Excalidraw Board` or
`Web Page Viewer` show a fallback message like:

```text
Qt WebEngine is unavailable. DLL load failed while importing QtWebEngineCore:
The specified procedure could not be found.
```

That message means Python found `PyQt6.QtWebEngineCore`, but Windows could not
load the matching Qt WebEngine DLLs. This is usually an installation or DLL
search-path problem, not a graph/node configuration problem.

## Expected Packages

The project declares WebEngine support through `pyproject.toml`:

```text
requires-python = ">=3.11"
PyQt6>=6.5
PyQt6-WebEngine>=6.10
```

Python 3.12 and newer releases are allowed by that metadata. The examples below use Python 3.11
because it is the project-standard source/dev interpreter, but a newer supported
environment can also work when the venv and any offline wheelhouse are created
with the same Python version on the target machine.

For a stable Windows source/dev environment, keep these four packages on the
same version:

```text
PyQt6
PyQt6-Qt6
PyQt6-WebEngine
PyQt6-WebEngine-Qt6
```

The currently verified local setup uses `6.11.0` for all four packages.

## Quick Diagnosis

Run these commands from the repository root on the affected machine:

```powershell
.\venv\Scripts\python.exe -c "import sys, os; print(sys.version); print(sys.executable); print(os.path.realpath(sys.executable))"
.\venv\Scripts\python.exe -m pip show PyQt6 PyQt6-Qt6 PyQt6-WebEngine PyQt6-WebEngine-Qt6
.\venv\Scripts\python.exe -c "import PyQt6.QtCore as QC; print('Qt', QC.QT_VERSION_STR, 'PyQt', QC.PYQT_VERSION_STR); import PyQt6.QtWebEngineCore; print('WebEngine OK')"
```

If the second command fails, repair the project virtual environment before
launching the app.

## VDI And Redirected Scratch Paths

Some VDI environments redirect a visible path such as:

```text
C:\Scratch\PyCharmProjects\EA_Node_Editor\venv\Scripts\python.exe
```

to a backing path such as:

```text
D:\{guid}\SVROOT\Scratch\PyCharmProjects\EA_Node_Editor\venv\Scripts\python.exe
```

When creating a venv there, Python may print:

```text
Actual environment location may have moved due to redirects, links or junctions.
```

That warning alone usually does not cause the `QtWebEngineCore` DLL-load error.
It means the VDI storage layer resolves the requested path to a physical backing
path. Treat it as informational unless the venv cannot run at all.

Two VDI-specific rules matter more:

- Use one Python version consistently. The project supports Python `>=3.11`.
  If your VDI standard is Python 3.12, create the venv with
  `py -3.12 -m venv venv` and build/download any offline wheels with
  `py -3.12 -m pip download ...`.
- Do not copy a populated `venv` between machines or redirected locations.
  Recreate it on the target VDI machine so PyQt and Qt WebEngine DLLs are
  installed for that machine.

If `Remove-Item -Recurse -Force .\venv` fails because files are locked, close
running app instances and IDE terminals, then run:

```powershell
Stop-Process -Name python, py, pythonw -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\venv
```

## Clean Online Repair

Do not copy a `venv` from another machine. Recreate it on the target machine:

If your machine is standardized on Python 3.12, replace `py -3.11` with
`py -3.12` in the commands below.

```powershell
Stop-Process -Name python, py, pythonw -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\venv

py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip

.\venv\Scripts\python.exe -m pip install --force-reinstall --no-cache-dir `
  PyQt6==6.11.0 `
  PyQt6-Qt6==6.11.0 `
  PyQt6-WebEngine==6.11.0 `
  PyQt6-WebEngine-Qt6==6.11.0

.\venv\Scripts\python.exe -m pip install -e ".[all,dev]"
```

Verify WebEngine:

```powershell
.\venv\Scripts\python.exe -c "import PyQt6.QtCore as QC; print(QC.QT_VERSION_STR); import PyQt6.QtWebEngineCore; print('WebEngine OK')"
```

Then launch:

```powershell
.\venv\Scripts\python.exe -m ea_node_editor.bootstrap
```

## Intranet Or Offline Repair

On a machine with internet access, create a WebEngine wheelhouse:

Build the wheelhouse with the same Python version you will use on the intranet
machine. For Python 3.12, replace `py -3.11` with `py -3.12`.

```powershell
py -3.11 -m pip download -d wheelhouse `
  PyQt6==6.11.0 `
  PyQt6-Qt6==6.11.0 `
  PyQt6-WebEngine==6.11.0 `
  PyQt6-WebEngine-Qt6==6.11.0
```

Copy the `wheelhouse` directory to the intranet machine. Then install from the
local wheels:

```powershell
Stop-Process -Name python, py, pythonw -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\venv

py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip

.\venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse `
  PyQt6==6.11.0 `
  PyQt6-Qt6==6.11.0 `
  PyQt6-WebEngine==6.11.0 `
  PyQt6-WebEngine-Qt6==6.11.0

.\venv\Scripts\python.exe -m pip install -e ".[all,dev]"
```

If the final editable install also needs internet-only dependencies, build and
copy a complete project dependency wheelhouse for your environment, then use
`--no-index --find-links` for those packages as well.

## DLL Search Path Conflicts

If WebEngine still fails after reinstalling matching PyQt packages, check
whether another Qt installation is earlier on `PATH`:

```powershell
$env:PATH -split ';' | Select-String -Pattern 'Qt|Ansys|ParaView|QGIS|Python'
```

Common conflicting sources include Ansys, ParaView, QGIS, another Python
distribution, or another Qt application. Launch the app from a clean shell where
the project venv paths are preferred and unrelated Qt DLL directories are not
prepended to `PATH`.

## Runtime Prerequisites

If package versions match and `PATH` is clean, install or repair the Microsoft
Visual C++ Redistributable for current Windows desktop applications, then rerun
the WebEngine import check.

## Success Criteria

The installation is correct when this command succeeds:

```powershell
.\venv\Scripts\python.exe -c "import PyQt6.QtWebEngineCore; import PyQt6.QtWebEngineWidgets; print('WebEngine OK')"
```

After that, QWebEngine-backed nodes should render live WebEngine content instead
of the fallback card.
