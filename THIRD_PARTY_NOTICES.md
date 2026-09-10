# Third-Party Notices

This file records principal third-party components distributed with COREX
packages. It is distribution documentation, not legal advice and not a
substitute for reviewing the complete packaged binary inventory before a
commercial release.

## Paramiko

- Package: `paramiko>=4,<5`
- Purpose: SSH and SFTP transport for the built-in SSH/SFTP node family.
- License: GNU LGPL version 2.1; see
  `licenses/PARAMIKO-LGPL-2.1.txt`.
- Source: <https://github.com/paramiko/paramiko>

## XY

- Package: `xy==0.0.6`
- Purpose: Browser-free native PNG rendering for the built-in Signal Plot node.
- License: Apache License 2.0; see `licenses/XY-APACHE-2.0-NOTICE.txt` and
  the full text in `licenses/OCP-APACHE-2.0.txt`.
- Source: <https://github.com/reflex-dev/xy>

## CadQuery OCP bindings

- Package: `cadquery-ocp-novtk==7.9.3.1.1` and its matching
  `cadquery-ocp-proxy==7.9.3.1.1`
- Purpose: Python bindings used for STEP, IGES, and BREP import and exact CAD
  queries.
- Binding license: Apache License 2.0; see
  `licenses/OCP-APACHE-2.0.txt`.
- Matching binding source and build files:
  <https://github.com/CadQuery/OCP/tree/7.9.3.1.1>

## Open CASCADE Technology (OCCT)

- Version family: OCCT 7.9.3, carried by the pinned OCP 7.9.3.1.1 wheel.
- Purpose: CAD kernel and data-exchange libraries loaded dynamically by the OCP
  bindings.
- License: GNU LGPL version 2.1 with the Open CASCADE exception; see
  `licenses/OCCT-LGPL-2.1.txt` and
  `licenses/OCCT-LGPL-EXCEPTION.txt`.
- Matching source and build information:
  <https://github.com/Open-Cascade-SAS/OCCT/tree/V7_9_3>
- Packaged library location: `cadquery_ocp_novtk.libs`. The folder remains
  separate from COREX code so ABI-compatible dynamically linked libraries can
  be inspected or replaced together with the corresponding OCP binding build.

## VTK, PyVista, and PyVistaQt

- VTK 9.6.1: BSD 3-Clause; see `licenses/VTK-BSD-3-CLAUSE.txt`.
- PyVista 0.47.3: MIT; see `licenses/PYVISTA-MIT.txt`.
- PyVistaQt 0.11.4: MIT; see `licenses/PYVISTAQT-MIT.txt`.

The exact versions in a release remain those recorded in the package build's
dependency matrix and binary inventory.
