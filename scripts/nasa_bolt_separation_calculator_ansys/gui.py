from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

try:
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QStyle,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_MAJOR = 6
except ImportError:  # pragma: no cover - fallback for machines with PyQt5 only.
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtGui import QColor, QDesktopServices, QKeySequence
    from PyQt5.QtWidgets import (
        QAction,
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QStyle,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    QT_MAJOR = 5

try:
    from .calculator import (
        AdvancedCheckInputs,
        BoltGeometryOverrides,
        BoltInput,
        BoltGeometry,
        BoltLoadRow,
        CombinedLoadInputs,
        ContactEvidenceLimits,
        ContactEvidenceRow,
        MaterialAllowableOverrides,
        MaterialAllowables,
        NASA_5020B_REVALIDATED_PDF_URL,
        NASA_STANDARD_PAGE_URL,
        PreloadOverrideInputs,
        PreloadInputs,
        ProjectInput,
        SealPressureInputs,
        SlipInputs,
        calculate_project,
        example_project,
        generate_text_report,
        recommended_fssep,
        validate_project,
    )
    from .io_formats import (
        BOLT_TABLE_COLUMNS,
        NONLINEAR_EVIDENCE_COLUMNS,
        bolt_inputs_from_load_rows,
        export_bolt_table_csv,
        import_ansys_loads_csv,
        import_bolt_table_csv,
        import_nonlinear_evidence_csv,
        load_project_json,
        save_project_json,
    )
except ImportError:  # pragma: no cover - direct script execution fallback.
    from calculator import (  # type: ignore
        AdvancedCheckInputs,
        BoltGeometryOverrides,
        BoltInput,
        BoltGeometry,
        BoltLoadRow,
        CombinedLoadInputs,
        ContactEvidenceLimits,
        ContactEvidenceRow,
        MaterialAllowableOverrides,
        MaterialAllowables,
        NASA_5020B_REVALIDATED_PDF_URL,
        NASA_STANDARD_PAGE_URL,
        PreloadOverrideInputs,
        PreloadInputs,
        ProjectInput,
        SealPressureInputs,
        SlipInputs,
        calculate_project,
        example_project,
        generate_text_report,
        recommended_fssep,
        validate_project,
    )
    from io_formats import (  # type: ignore
        BOLT_TABLE_COLUMNS,
        NONLINEAR_EVIDENCE_COLUMNS,
        bolt_inputs_from_load_rows,
        export_bolt_table_csv,
        import_ansys_loads_csv,
        import_bolt_table_csv,
        import_nonlinear_evidence_csv,
        load_project_json,
        save_project_json,
    )


PTL_MODES = ["direct", "axial", "fz", "force_magnitude", "axial_plus_bending"]
BOLT_COLUMNS = BOLT_TABLE_COLUMNS
EVIDENCE_COLUMNS = NONLINEAR_EVIDENCE_COLUMNS
RESULT_COLUMNS = ["bolt_id", "case", "set", "mode", "Pp_min", "FF", "FSsep", "PtL", "demand", "MSsep", "status", "warnings"]
LOCAL_NASA_PDF = Path(__file__).resolve().parent / "resources" / "NASA-STD-5020B-Revalidated.pdf"

BOLT_CSV_TOOLTIP_HTML = """
<div>
  <b>Import full bolt table CSV</b>
  <p>The first row must be this calculator's current header. Export Bolt CSV once to get a template.</p>
  <p><b>Required load columns:</b><br>
  bolt_id, ptl_mode, direct_ptl, case_id, set_id, fx, fy, fz, mx, my, mz, axial,
  shear_mag, moment_arm, units, source_type, source_name, quality_flags, notes</p>
  <p><b>Override columns required in the header, optional per row:</b><br>
  fitting_factor, separation_factor, preload_ppi_nom, preload_gamma, preload_cmin,
  preload_nf, preload_separation_critical, preload_relaxation_loss,
  preload_creep_loss, preload_thermal_loss, geometry_diameter,
  geometry_tensile_area, geometry_shear_area, geometry_minor_diameter_area,
  geometry_section_modulus, material_tensile_yield, material_tensile_ultimate,
  material_shear_ultimate, material_bending_ultimate, material_shear_yield</p>
  <p>Leave override cells blank to inherit Step 1 and Step 2 defaults for that bolt.</p>
</div>
"""

HELP_TOPICS = {
    "method": (
        "NASA-STD-5020B method",
        "This utility implements NASA-STD-5020B Eq. 19 as an axial-only separation check:\n\n"
        "MSsep = Pp_min / (FF * FSsep * PtL) - 1\n\n"
        "Use it to compare final minimum preload with the factored tensile limit-load demand. "
        "The result is not a complete combined-load, seal, gasket, or pressure-containment substantiation."
    ),
    "fitting_factor": (
        "Fitting factor FF",
        "NASA-STD-5020B Section 4.2.2 requires a fitting factor to account for uncertainty in fastener "
        "load paths and stresses. Use the factor levied by the program/project or substantiated analysis. "
        "A common minimum default for separation-critical work is 1.15 unless test/correlated-analysis "
        "evidence justifies another value. FF multiplies PtL in Eq. 19; it is not applied to preload."
    ),
    "separation_factor": (
        "Separation factor FSsep",
        "NASA-STD-5020B Section 4.2.3 and Figure 1 define the minimum separation factor. Choose it from "
        "the consequence of credible separation: catastrophic cases generally use the program ultimate "
        "factor, critical cases use at least max(1.2, program yield factor), and lower-consequence cases "
        "must still envelope applicable test factors. If proof, acceptance, or qualification testing is "
        "performed above limit load, increase FSsep enough to envelope the test condition. The Joint "
        "classification field computes a recommendation from the program yield, program ultimate, or "
        "test envelope factor, but the editable FSsep remains analyst-controlled."
    ),
    "classification_factors": (
        "Program and test factors",
        "NASA-STD-5020B Section 4.2.3 Figure 1 uses FSu, FSy, and a program-levied test factor "
        "to select the minimum separation factor FSsep. The GUI fields below are those Figure 1 "
        "factor inputs. They are not bolt material yield stress, ultimate stress, or preload values.\n\n"
        "Program yield factor FSy: enter the yield factor of safety levied by the program, "
        "project, certification basis, or verification plan. Critical separation uses max(1.2, FSy).\n"
        "Program ultimate factor FSu: enter the ultimate factor of safety levied by the program. "
        "Catastrophic separation uses FSu.\n"
        "Program/test envelope factor: enter the program-levied test factor from Figure 1. Use the "
        "largest proof, acceptance, qualification, or other planned test load multiplier relative to "
        "the same limit-load basis used for PtL. If no over-limit test factor must be enveloped, use 1.0.\n\n"
        "If the program has not assigned these factors yet, keep the conservative project defaults as "
        "placeholders and document the basis notes before using the result as substantiation."
    ),
    "preload": (
        "Preload parameters",
        "NASA-STD-5020B Section 4.3 requires maximum/minimum preload calculations to account for "
        "installation scatter, relaxation, creep, and thermal preload change.\n\n"
        "Ppi_nom: nominal initial preload, normally substantiated by tests of at least six fastening-system "
        "hardware sets.\n"
        "Gamma: preload variation as a decimal. Separation-critical analyses should use the required "
        "test-statistical basis; non-separation-critical cases may use Table 3 defaults only when allowed.\n"
        "cmin: minimum preload coefficient from the installation/preload basis.\n"
        "nf: fastener count used by Eq. 5 when the joint is not separation-critical.\n"
        "Losses: relaxation, creep, and thermal decreases are subtracted from Ppi_min to get Pp_min."
    ),
    "combined_load": (
        "Combined load screen",
        "Use this when the load row includes axial tension plus shear and/or bending moment. "
        "The NASA ultimate option uses NASA-STD-5020B combined-fastener interaction equations "
        "for body-in-shear or threads-in-shear conditions. The von Mises and Tresca options are "
        "yield stress screens and should be labelled as engineering screens in substantiation. "
        "Provide tensile/shear areas, diameter or minor-diameter area, section modulus for bending, "
        "and the material allowables that match the selected theory."
    ),
    "slip": (
        "Joint slip screen",
        "NASA Appendix A.10 gives Eq. 84/85 for concentric joint slip when the joint has equal "
        "nominal preload, same fastener type, equivalent fastener sizes, and load through the pattern "
        "centroid. Use Eq. 86 per fastener when those assumptions are not satisfied or when per-bolt "
        "Ansys force rows are available. Unsubstantiated friction is capped by the calculator at "
        "0.20 for clean uncoated non-lubricated metal or 0.10 otherwise."
    ),
    "seal_pressure": (
        "Seal / pressure residual compression",
        "Use this for fluid pressure or gasket/seal cases where Eq. 19 alone is not enough. "
        "The calculator computes pressure separating load, residual clamp, and residual contact "
        "pressure, then compares them to user-entered minimum seal/contact requirements. It does "
        "not invent leak-rate, gasket, or seal acceptance limits."
    ),
    "nonlinear_evidence": (
        "Nonlinear Ansys evidence",
        "Import contact/gap/contact-pressure/load-redistribution evidence from Ansys as CSV. "
        "Use this when partial contact opening, nonlinear separation, contact-pressure loss, or load "
        "redistribution is important. Acceptance limits are analyst-entered and should come from the "
        "project's contact, seal, or load-sharing criteria."
    ),
}

NOMENCLATURE_HTML = """
<!doctype html>
<html>
<head>
  <style>
    body {
      background: #fbfdff;
      color: #18202a;
      font-family: Segoe UI, Arial, sans-serif;
      font-size: 14px;
      margin: 0;
    }
    h1 { color: #123052; font-size: 26px; margin: 0 0 8px 0; }
    h2 { color: #123052; font-size: 19px; margin: 22px 0 10px 0; }
    h3 { color: #1d3d63; font-size: 16px; margin: 0 0 8px 0; }
    p { color: #2d3745; line-height: 1.35; margin: 6px 0 10px 0; }
    .page { background: #fbfdff; padding: 18px 22px 26px 22px; }
    .intro {
      background: #eaf2ff;
      border: 1px solid #b9cbe5;
      border-radius: 8px;
      color: #172235;
      padding: 12px;
      margin-bottom: 18px;
    }
    .formula-card {
      background: #ffffff;
      border: 1px solid #c8d6e8;
      border-radius: 8px;
      padding: 14px;
      margin: 10px 0 16px 0;
    }
    table.formula {
      border: 0;
      margin: 8px auto 10px auto;
      font-family: Cambria Math, Cambria, Times New Roman, serif;
      font-size: 24px;
      color: #111827;
    }
    table.formula td {
      border: 0;
      padding: 2px 8px;
      text-align: center;
      vertical-align: middle;
      background: #ffffff;
      color: #111827;
    }
    .equation-line {
      background: #f4f7fb;
      border: 1px solid #d8e2ee;
      border-radius: 6px;
      color: #111827;
      font-family: Cambria Math, Cambria, Times New Roman, serif;
      font-size: 20px;
      padding: 8px 10px;
      margin: 8px 0;
    }
    table.defs {
      border-collapse: collapse;
      width: 100%;
      margin: 8px 0 16px 0;
      color: #18202a;
    }
    table.defs th {
      background: #dfeaf7;
      border: 1px solid #aebfd4;
      color: #0f253f;
      font-weight: 700;
      padding: 8px 10px;
      text-align: left;
    }
    table.defs td {
      background: #ffffff;
      border: 1px solid #b7c5d6;
      color: #1d2733;
      padding: 8px 10px;
      vertical-align: top;
    }
    .symbol {
      color: #0f253f;
      font-family: Cambria Math, Cambria, Times New Roman, serif;
      font-size: 16px;
      font-weight: 700;
      white-space: nowrap;
    }
    .warn {
      background: #fff4cf;
      border: 1px solid #d7ad3a;
      border-radius: 8px;
      color: #3a2a00;
      padding: 12px;
      margin-top: 18px;
    }
  </style>
</head>
<body>
  <div class="page">
    <h1>Nomenclature And Formula Reference</h1>
    <div class="intro">
      This page summarizes the symbols used by the calculator. The controlling source remains
      NASA-STD-5020B. Use the toolbar buttons or the buttons below this tab to open the bundled
      PDF and check the cited sections.
    </div>

    <h2>Separation Margin, NASA-STD-5020B Section 4.4.3</h2>
    <p><b>Eq. 19 is rendered in the native equation card above this reference text.</b></p>
    <table class="defs">
      <tr><th>Symbol</th><th>Meaning</th><th>How To Determine It</th></tr>
      <tr><td class="symbol">MS<sub>sep</sub></td><td>Separation margin of safety.</td><td>Calculated by this utility. Passing criterion is MS<sub>sep</sub> &ge; 0.</td></tr>
      <tr><td class="symbol">P<sub>p-min</sub></td><td>Final minimum preload after losses.</td><td>Calculated from preload terms below. It is the conservative separation load used by Eq. 19.</td></tr>
      <tr><td class="symbol">FF</td><td>Fitting factor.</td><td>Use the program/project levied value or substantiated analysis basis. Section 4.2.2 explains FF; 1.15 is a common starting value for separation-critical work.</td></tr>
      <tr><td class="symbol">FS<sub>sep</sub></td><td>Separation factor of safety.</td><td>Use Section 4.2.3 and Figure 1. The GUI recommends this from joint classification: catastrophic uses FSu, critical uses max(1.2, FSy), and non-separation-critical uses max(1.0, program-levied test factor).</td></tr>
      <tr><td class="symbol">P<sub>tL</sub></td><td>Limit tensile load for the bolt/load row.</td><td>Enter directly from hand analysis or derive from imported Ansys force/moment rows using the selected PtL mode.</td></tr>
    </table>

    <h2>FSsep Classification Factor Inputs</h2>
    <p>
      These fields drive the recommended separation factor. NASA-STD-5020B Section 4.2.3
      Figure 1 names the program ultimate factor of safety as FSu and the program yield
      factor of safety as FSy. They are load factors from the program/project verification
      basis, not material yield stress, material ultimate stress, preload, or bolt allowables.
    </p>
    <table class="defs">
      <tr><th>GUI Field</th><th>How To Set It</th><th>Where It Is Used</th></tr>
      <tr><td class="symbol">Program yield factor FSy</td><td>Use the yield factor of safety levied by the program, project, certification basis, or verification plan.</td><td>Critical classification recommends max(1.2, FSy) per Figure 1.</td></tr>
      <tr><td class="symbol">Program ultimate factor FSu</td><td>Use the ultimate factor of safety levied by the program or verification plan for the same limit-load basis.</td><td>Catastrophic classification recommends FSu per Figure 1.</td></tr>
      <tr><td class="symbol">Program/test envelope factor</td><td>Use the program-levied test factor from Figure 1. Use the largest proof, acceptance, qualification, or other planned test multiplier relative to the same limit-load basis. Use 1.0 when no over-limit test must be enveloped.</td><td>Non-separation-critical classification recommends max(1.0, program-levied test factor) per Figure 1.</td></tr>
    </table>

    <h2>Preload, NASA-STD-5020B Sections 4.3.1-4.3.3</h2>
    <div class="formula-card">
      <h3>Final minimum preload, Eq. 2</h3>
      <div class="equation-line">P<sub>p-min</sub> = P<sub>pi-min</sub> - P<sub>pr</sub> - P<sub>pc</sub> - P<sub>&Delta;T-min</sub></div>
      <h3>Separation-critical initial minimum preload, Eq. 4</h3>
      <div class="equation-line">P<sub>pi-min</sub> = c<sub>min</sub> (1 - &Gamma;) P<sub>pi-nom</sub></div>
      <h3>Non-separation-critical initial minimum preload, Eq. 5</h3>
      <div class="equation-line">P<sub>pi-min</sub> = c<sub>min</sub> (1 - &Gamma; / &radic;n<sub>f</sub>) P<sub>pi-nom</sub></div>
    </div>
    <table class="defs">
      <tr><th>Symbol / GUI Field</th><th>Meaning</th><th>How To Determine It</th></tr>
      <tr><td class="symbol">P<sub>pi-nom</sub></td><td>Nominal initial preload.</td><td>Use test-substantiated installation data for the actual fastening-system hardware and installation method.</td></tr>
      <tr><td class="symbol">&Gamma;</td><td>Preload variation as a decimal.</td><td>Use the required statistical preload scatter basis. Example: 0.25 means 25 percent scatter.</td></tr>
      <tr><td class="symbol">c<sub>min</sub></td><td>Minimum preload coefficient.</td><td>Use the value from the installation/preload substantiation basis. Leave at 1.0 only when that is justified.</td></tr>
      <tr><td class="symbol">n<sub>f</sub></td><td>Fastener count.</td><td>Used only by the non-separation-critical Eq. 5 reduction term.</td></tr>
      <tr><td class="symbol">P<sub>pr</sub></td><td>Preload loss from relaxation.</td><td>GUI field: relaxation_loss. Subtract expected relaxation from P<sub>pi-min</sub>.</td></tr>
      <tr><td class="symbol">P<sub>pc</sub></td><td>Preload loss from creep.</td><td>GUI field: creep_loss. Subtract expected creep-related preload decrease.</td></tr>
      <tr><td class="symbol">P<sub>&Delta;T-min</sub></td><td>Minimum expected thermal preload decrease.</td><td>GUI field: thermal_loss. Subtract the thermal preload decrease for the controlling environment.</td></tr>
    </table>

    <h2>PtL Derivation Modes</h2>
    <table class="defs">
      <tr><th>Mode</th><th>Rendered Formula</th><th>Use When</th></tr>
      <tr><td class="symbol">direct</td><td>P<sub>tL</sub> = direct_ptl</td><td>You already have the per-bolt tensile limit load.</td></tr>
      <tr><td class="symbol">axial</td><td>P<sub>tL</sub> = |axial|</td><td>The Ansys export has a bolt-local axial force column.</td></tr>
      <tr><td class="symbol">fz</td><td>P<sub>tL</sub> = |f<sub>z</sub>|</td><td>The bolt axis is the local Z direction in the exported coordinate system.</td></tr>
      <tr><td class="symbol">force_magnitude</td><td>P<sub>tL</sub> = &radic;(f<sub>x</sub><sup>2</sup> + f<sub>y</sub><sup>2</sup> + f<sub>z</sub><sup>2</sup>)</td><td>Screening only; Eq. 19 is axial-only, so document why this is conservative.</td></tr>
      <tr><td class="symbol">axial_plus_bending</td><td>P<sub>tL</sub> = |axial| + &radic;(m<sub>x</sub><sup>2</sup> + m<sub>y</sub><sup>2</sup>) / moment_arm</td><td>Screening with a chosen moment arm. Confirm the moment arm and sign convention separately.</td></tr>
    </table>

    <h2>Ansys Load Row Symbols</h2>
    <table class="defs">
      <tr><th>Column</th><th>Meaning</th></tr>
      <tr><td class="symbol">f<sub>x</sub>, f<sub>y</sub>, f<sub>z</sub></td><td>Force components from Mechanical probe, beam, remote point, bolt pretension, or manual table export.</td></tr>
      <tr><td class="symbol">m<sub>x</sub>, m<sub>y</sub>, m<sub>z</sub></td><td>Moment components about the exported coordinate system.</td></tr>
      <tr><td class="symbol">axial</td><td>Preferred bolt-local tensile/compressive component when available.</td></tr>
      <tr><td class="symbol">shear_mag</td><td>Magnitude of non-axial shear. Nonzero shear is reported as a review warning.</td></tr>
      <tr><td class="symbol">quality_flags</td><td>Analyst notes such as local-axis checks, probe/source assumptions, or extraction warnings.</td></tr>
    </table>

    <h2>Step 1 Project Flag Checkboxes</h2>
    <table class="defs">
      <tr><th>Checkbox</th><th>Effect</th><th>Required Follow-Up</th></tr>
      <tr><td class="symbol">Seal or gasket affects joint function</td><td>Adds an Eq. 19 method warning and enables Step 4 Seal / Pressure.</td><td>Enter the residual clamp/contact-pressure criteria needed for the seal or gasket.</td></tr>
      <tr><td class="symbol">Pressure or fluid containment</td><td>Adds a pressure-containment warning and enables Step 4 Seal / Pressure.</td><td>Enter pressure, effective pressure area, contact area, and acceptance criteria.</td></tr>
      <tr><td class="symbol">Combined shear, bending, eccentricity, or moment</td><td>Adds an axial-only Eq. 19 warning and enables Step 4 Combined Load.</td><td>Enter bolt geometry, material allowables, and select the combined-load theory.</td></tr>
    </table>

    <h2>Combined Load Screen, NASA-STD-5020B Section 4.4.4</h2>
    <p>
      The NASA ultimate option uses the combined fastener interaction equations below when their
      shear-plane and bending assumptions match the joint. The yield options are separate engineering
      screens using axial plus bending stress and shear stress.
    </p>
    <div class="formula-card">
      <h3>Stress terms used by the GUI</h3>
      <div class="equation-line">&sigma;<sub>a</sub> = |P<sub>tL</sub>| / A<sub>t</sub></div>
      <div class="equation-line">&sigma;<sub>b</sub> = &radic;(M<sub>x</sub><sup>2</sup> + M<sub>y</sub><sup>2</sup>) / Z</div>
      <div class="equation-line">&tau; = P<sub>sL</sub> / A<sub>s</sub></div>
    </div>
    <table class="defs">
      <tr><th>Mode</th><th>Formula</th><th>Inputs / Notes</th></tr>
      <tr><td class="symbol">NASA Eq. 20</td><td>(P<sub>su</sub>/P<sub>su-allow</sub>)<sup>2.5</sup> + (P<sub>tu</sub>/P<sub>tu-allow</sub> + f<sub>bu</sub>/F<sub>tu</sub>)<sup>1.5</sup> &le; 1</td><td>Full-diameter body in shear plane, no plastic bending credit.</td></tr>
      <tr><td class="symbol">NASA Eq. 21</td><td>(P<sub>su</sub>/P<sub>su-allow</sub>)<sup>2.5</sup> + (P<sub>tu</sub>/P<sub>tu-allow</sub>)<sup>1.5</sup> + f<sub>bu</sub>/F<sub>bu</sub> &le; 1</td><td>Full-diameter body in shear plane with plastic-bending interaction.</td></tr>
      <tr><td class="symbol">NASA Eq. 22</td><td>(P<sub>su</sub>/P<sub>su-allow</sub>)<sup>1.2</sup> + (P<sub>tu</sub>/P<sub>tu-allow</sub> + f<sub>bu</sub>/F<sub>tu</sub>)<sup>2</sup> &le; 1</td><td>Threads in shear plane, no plastic bending credit.</td></tr>
      <tr><td class="symbol">NASA Eq. 23</td><td>(P<sub>su</sub>/P<sub>su-allow</sub>)<sup>1.2</sup> + (P<sub>tu</sub>/P<sub>tu-allow</sub>)<sup>2</sup> + f<sub>bu</sub>/F<sub>bu</sub> &le; 1</td><td>Threads in shear plane with plastic-bending interaction.</td></tr>
      <tr><td class="symbol">von Mises</td><td>&sigma;<sub>eq</sub> = &radic;((&sigma;<sub>a</sub> + &sigma;<sub>b</sub>)<sup>2</sup> + 3&tau;<sup>2</sup>)</td><td>Yield screen. The GUI applies FF and combined-load FS before comparing to tensile yield.</td></tr>
      <tr><td class="symbol">Tresca</td><td>&sigma;<sub>eq</sub> = max(|&sigma;<sub>1</sub> - &sigma;<sub>2</sub>|, |&sigma;<sub>1</sub>|, |&sigma;<sub>2</sub>|)</td><td>Yield screen using principal stresses from normal stress plus shear stress.</td></tr>
    </table>

    <h2>Joint Slip, NASA-STD-5020B Appendix A.10</h2>
    <div class="formula-card">
      <h3>Concentric joint slip</h3>
      <div class="equation-line">Eq. 84: MS<sub>slip</sub> = &mu;n<sub>f</sub>P<sub>p-min</sub> / [FS(P<sub>sL-joint</sub> + &mu;P<sub>tL-joint</sub>)] - 1</div>
      <div class="equation-line">Eq. 85: MS<sub>slip</sub> = &mu;n<sub>f</sub>P<sub>p-min</sub> / (FS P<sub>sL-joint</sub>) - 1</div>
      <div class="equation-line">Eq. 86: MS<sub>slip-i</sub> = &mu;P<sub>p-min-i</sub> / [FF FS(P<sub>sL-i</sub> + &mu;P<sub>tL-i</sub>)] - 1</div>
    </div>
    <table class="defs">
      <tr><th>Symbol</th><th>Meaning / Use</th></tr>
      <tr><td class="symbol">&mu;</td><td>Friction coefficient. Without substantiation, the GUI caps it at 0.20 for clean uncoated non-lubricated metal and 0.10 otherwise.</td></tr>
      <tr><td class="symbol">P<sub>sL</sub></td><td>Limit shear load. For Eq. 86, the GUI uses each Step 3 bolt row's shear_mag or sqrt(fx^2 + fy^2).</td></tr>
      <tr><td class="symbol">Eq. 84/85 assumptions</td><td>Use only for concentric tension/shear through the bolt-pattern centroid, equal nominal preload, same fastener type, and equivalent fastener sizes.</td></tr>
    </table>

    <h2>Seal / Pressure Residual Compression</h2>
    <div class="formula-card">
      <h3>User-criterion residual compression check</h3>
      <div class="equation-line">P<sub>pressure</sub> = pressure &times; A<sub>effective</sub></div>
      <div class="equation-line">P<sub>residual</sub> = n<sub>f</sub>P<sub>p-min</sub> - P<sub>pressure</sub></div>
      <div class="equation-line">p<sub>contact-residual</sub> = P<sub>residual</sub> / A<sub>gasket/contact</sub></div>
    </div>
    <p>
      The GUI compares residual clamp and residual contact pressure to user-entered limits. The
      calculator does not supply leak-rate, gasket compression, or seal acceptance limits.
    </p>

    <h2>Nonlinear Ansys Evidence</h2>
    <table class="defs">
      <tr><th>CSV Column</th><th>Meaning / Acceptance Use</th></tr>
      <tr><td class="symbol">max_gap</td><td>Maximum contact opening from the nonlinear Mechanical result. Compared to the user-entered max gap when that limit is nonzero.</td></tr>
      <tr><td class="symbol">min_contact_pressure</td><td>Minimum residual contact pressure. Compared to the user-entered minimum contact-pressure criterion when nonzero.</td></tr>
      <tr><td class="symbol">separated_area_fraction</td><td>Fraction of the checked region that is separated. Compared to the user-entered maximum fraction.</td></tr>
      <tr><td class="symbol">redistributed_ptl</td><td>Per-bolt tensile load after nonlinear redistribution. Compared to a user-entered maximum when nonzero.</td></tr>
    </table>

    <div class="warn">
      <b>Method limit:</b> Eq. 19 remains an axial separation check. The Advanced tab adds separate
      screens for combined strength, slip, residual seal/pressure compression, and nonlinear evidence,
      but the report still depends on the analyst confirming that the selected equations, allowables,
      friction basis, seal criteria, and Ansys evidence match the joint.
    </div>
  </div>
</body>
</html>
"""


def _alignment_center() -> Qt.AlignmentFlag | Qt.Alignment:
    return Qt.AlignmentFlag.AlignCenter if QT_MAJOR == 6 else Qt.AlignCenter


def _stretch_header(header: QHeaderView) -> None:
    if QT_MAJOR == 6:
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
    else:
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)


def _style_standard_icon(window: QMainWindow, icon_name: str):
    pixmap = getattr(QStyle.StandardPixmap, icon_name) if QT_MAJOR == 6 else getattr(QStyle, icon_name)
    return window.style().standardIcon(pixmap)


def _qt_key(name: str):
    return getattr(Qt.Key, name) if QT_MAJOR == 6 else getattr(Qt, name)


def _standard_key(name: str):
    return getattr(QKeySequence.StandardKey, name) if QT_MAJOR == 6 else getattr(QKeySequence, name)


def _parse_clipboard_rows(text: str) -> list[list[str]]:
    if not text.strip():
        return []
    sample = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if "\t" in sample else ","
    return [[cell.strip() for cell in row] for row in csv.reader(text.splitlines(), delimiter=delimiter)]


class BoltLoadTableWidget(QTableWidget):
    def __init__(self, columns: Sequence[str], combo_options: dict[str, Sequence[str]]) -> None:
        super().__init__(0, len(columns))
        self._columns = list(columns)
        self._combo_options = combo_options

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.matches(_standard_key("Copy")):
            self.copy_selection()
            return
        if event.matches(_standard_key("Paste")):
            self.paste_clipboard()
            return
        if event.key() in {_qt_key("Key_Delete"), _qt_key("Key_Backspace")}:
            self.clear_selection_values()
            return
        super().keyPressEvent(event)

    def ensure_row(self, row: int) -> None:
        while self.rowCount() <= row:
            self.insertRow(self.rowCount())
        for column_name, options in self._combo_options.items():
            column = self._columns.index(column_name)
            if self.cellWidget(row, column) is None:
                combo = QComboBox()
                combo.addItems(list(options))
                combo.setToolTip("Choose how PtL is obtained for this row.")
                self.setCellWidget(row, column, combo)

    def set_cell_text(self, row: int, column: int, text: str) -> None:
        self.ensure_row(row)
        widget = self.cellWidget(row, column)
        if isinstance(widget, QComboBox):
            if text:
                widget.setCurrentText(text)
            return
        item = self.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            item.setTextAlignment(_alignment_center())
            self.setItem(row, column, item)
        item.setText(text)

    def cell_text(self, row: int, column: int) -> str:
        widget = self.cellWidget(row, column)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        item = self.item(row, column)
        return "" if item is None else item.text().strip()

    def paste_clipboard(self) -> None:
        rows = _parse_clipboard_rows(QApplication.clipboard().text())
        if not rows:
            return
        first = [cell.strip() for cell in rows[0]]
        header_map = [self._columns.index(cell) if cell in self._columns else None for cell in first]
        has_header = bool(first) and all(cell in self._columns for cell in first if cell) and any(cell in self._columns for cell in first)
        data_rows = rows[1:] if has_header else rows
        start_row = self.currentRow() if self.currentRow() >= 0 else self.rowCount()
        start_column = self.currentColumn() if self.currentColumn() >= 0 else 0
        for row_offset, cells in enumerate(data_rows):
            target_row = start_row + row_offset
            self.ensure_row(target_row)
            for cell_offset, text in enumerate(cells):
                if has_header:
                    if cell_offset >= len(header_map) or header_map[cell_offset] is None:
                        continue
                    target_column = header_map[cell_offset]
                else:
                    target_column = start_column + cell_offset
                if target_column is None or target_column >= self.columnCount():
                    continue
                self.set_cell_text(target_row, target_column, text)

    def copy_selection(self) -> None:
        indexes = self.selectedIndexes()
        if not indexes and self.currentRow() >= 0 and self.currentColumn() >= 0:
            indexes = [self.model().index(self.currentRow(), self.currentColumn())]
        if not indexes:
            return
        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        text_rows = []
        for row in rows:
            text_rows.append("\t".join(self.cell_text(row, column) for column in columns))
        QApplication.clipboard().setText("\n".join(text_rows))

    def clear_selection_values(self) -> None:
        indexes = self.selectedIndexes()
        if not indexes and self.currentRow() >= 0 and self.currentColumn() >= 0:
            indexes = [self.model().index(self.currentRow(), self.currentColumn())]
        for index in indexes:
            widget = self.cellWidget(index.row(), index.column())
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            else:
                self.set_cell_text(index.row(), index.column(), "")


class BoltSeparationWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NASA-STD-5020B Bolt Separation Calculator")
        self.resize(1320, 820)
        self._last_report = ""
        self._build_actions()
        self._build_ui()
        self.load_project(example_project())

    def _build_actions(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        open_action = QAction(_style_standard_icon(self, "SP_DialogOpenButton"), "Open project", self)
        open_action.setToolTip("Open a saved calculator project JSON file.")
        open_action.setStatusTip("Loads all project inputs, preload settings, and bolt rows from JSON.")
        open_action.triggered.connect(self.open_project)
        toolbar.addAction(open_action)

        save_action = QAction(_style_standard_icon(self, "SP_DialogSaveButton"), "Save project", self)
        save_action.setToolTip("Save the current calculator project to JSON.")
        save_action.setStatusTip("Writes project metadata, preload inputs, bolt rows, and Ansys load fields.")
        save_action.triggered.connect(self.save_project)
        toolbar.addAction(save_action)

        import_action = QAction(_style_standard_icon(self, "SP_FileDialogDetailedView"), "Import Ansys loads", self)
        import_action.setToolTip("Import Ansys Mechanical probe, beam, remote point, or manual load rows from CSV.")
        import_action.setStatusTip("Replaces the bolt table with one row per imported bolt/load-set row.")
        import_action.triggered.connect(self.import_ansys_loads)
        toolbar.addAction(import_action)

        evidence_action = QAction(_style_standard_icon(self, "SP_FileDialogContentsView"), "Import nonlinear evidence", self)
        evidence_action.setToolTip("Import Ansys contact/gap/contact-pressure/load-redistribution evidence CSV.")
        evidence_action.setStatusTip("Fills Step 4 nonlinear evidence rows and enables the evidence check.")
        evidence_action.triggered.connect(self.import_nonlinear_evidence)
        toolbar.addAction(evidence_action)

        calc_action = QAction(_style_standard_icon(self, "SP_DialogApplyButton"), "Calculate", self)
        calc_action.setToolTip("Validate inputs, calculate NASA-STD-5020B Eq. 19 margins, and run enabled advanced checks.")
        calc_action.setStatusTip("Runs axial separation plus enabled advanced screens and refreshes results/report tabs.")
        calc_action.triggered.connect(self.calculate)
        toolbar.addAction(calc_action)

        help_action = QAction(_style_standard_icon(self, "SP_MessageBoxQuestion"), "Method help", self)
        help_action.setToolTip("Show detailed guidance for Eq. 19, fitting factor, separation factor, and preload inputs.")
        help_action.setStatusTip("Opens a built-in help summary with NASA-STD-5020B section pointers.")
        help_action.triggered.connect(lambda: self._show_help_topic("method"))
        toolbar.addAction(help_action)

        local_pdf_action = QAction(_style_standard_icon(self, "SP_FileIcon"), "Open NASA PDF", self)
        local_pdf_action.setToolTip("Open the bundled local NASA-STD-5020B PDF. Relevant sections: 4.2.2, 4.2.3, 4.3, and 4.4.3.")
        local_pdf_action.setStatusTip("Opens resources/NASA-STD-5020B-Revalidated.pdf in your default PDF viewer.")
        local_pdf_action.triggered.connect(self._open_local_nasa_pdf)
        toolbar.addAction(local_pdf_action)

        online_pdf_action = QAction(_style_standard_icon(self, "SP_DirLinkIcon"), "NASA online", self)
        online_pdf_action.setToolTip("Open the official NASA standards page/PDF online for the current active standard.")
        online_pdf_action.setStatusTip("Opens the official NASA-STD-5020B PDF URL in your browser.")
        online_pdf_action.triggered.connect(self._open_online_nasa_pdf)
        toolbar.addAction(online_pdf_action)

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._project_tab(), "Step 1 - Project")
        self.tabs.addTab(self._preload_tab(), "Step 2 - Default Preload")
        self.tabs.addTab(self._bolts_tab(), "Step 3 - Bolts")
        self.tabs.addTab(self._advanced_tab(), "Step 4 - Advanced")
        self.tabs.addTab(self._results_tab(), "Step 5 - Results")
        self.tabs.addTab(self._report_tab(), "Step 6 - Report")
        self.tabs.addTab(self._nomenclature_tab(), "Nomenclature")
        self.statusBar().showMessage("Ready. Start at Step 1, then move left-to-right through the tabs.")

    def _show_help_topic(self, topic_key: str) -> None:
        title, text = HELP_TOPICS[topic_key]
        source_text = (
            f"\n\nPrimary source sections to check in the PDF:\n"
            f"- Section 4.2.2: fitting factor FF\n"
            f"- Section 4.2.3 and Figure 1: separation factor FSsep\n"
            f"- Sections 4.3.1-4.3.3: preload terms and substantiation\n"
            f"- Section 4.4.3: separation margin Eq. 19\n\n"
            f"- Section 4.4.4: combined fastener loading\n"
            f"- Section 4.4.6 and Appendix A.10: friction and slip margins\n"
            f"- Seal/gasket and pressure-retaining joints: use design-specific seal analysis and evidence\n\n"
            f"Local PDF: {LOCAL_NASA_PDF}\n"
            f"NASA page: {NASA_STANDARD_PAGE_URL}\n"
            f"NASA PDF: {NASA_5020B_REVALIDATED_PDF_URL}"
        )
        QMessageBox.information(self, title, text + source_text)

    def _open_local_nasa_pdf(self) -> None:
        if not LOCAL_NASA_PDF.exists():
            QMessageBox.warning(
                self,
                "NASA PDF not found",
                f"The bundled PDF was not found at:\n{LOCAL_NASA_PDF}\n\nUse the online NASA action instead.",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOCAL_NASA_PDF.resolve()))):
            QMessageBox.warning(self, "Open failed", f"Could not open local PDF:\n{LOCAL_NASA_PDF}")

    def _open_online_nasa_pdf(self) -> None:
        if not QDesktopServices.openUrl(QUrl(NASA_5020B_REVALIDATED_PDF_URL)):
            QMessageBox.warning(self, "Open failed", f"Could not open NASA PDF URL:\n{NASA_5020B_REVALIDATED_PDF_URL}")

    def _help_button(self, topic_key: str) -> QPushButton:
        button = QPushButton("?")
        button.setFixedWidth(30)
        title, text = HELP_TOPICS[topic_key]
        button.setToolTip(f"{title}\n\n{text}\n\nClick to open detailed help and NASA source links.")
        button.setStatusTip(f"Show guidance for {title}.")
        button.clicked.connect(lambda: self._show_help_topic(topic_key))
        return button

    def _with_help(self, widget: QWidget, topic_key: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget, 1)
        layout.addWidget(self._help_button(topic_key))
        return container

    def _guide_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            "QLabel { background: #eef4ff; border: 1px solid #b7c9e8; "
            "border-radius: 4px; padding: 10px; color: #152238; }"
        )
        return label

    def _project_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Step 1: identify the analysis, choose the safety factors, and flag conditions where "
                "NASA-STD-5020B Eq. 19 is not enough by itself. Eq. 19 is an axial separation check; "
                "seals, pressure containment, shear, bending, and eccentricity need engineering review. "
                "Use the '?' buttons beside FF and FSsep for section-level guidance, or use the toolbar "
                "to open the bundled NASA-STD-5020B PDF."
            )
        )

        group = QGroupBox("Project and separation factors")
        form = QFormLayout(group)
        self.project_name = QLineEdit()
        self.project_name.setToolTip("Name shown in saved JSON and generated reports.")
        self.project_name.setStatusTip("Use a clear name such as the flange, casing, load case, or design revision.")
        self.analyst = QLineEdit()
        self.analyst.setToolTip("Optional analyst/checker name for the report header.")
        self.force_units = QComboBox()
        self.force_units.addItems(["N", "lbf", "kN"])
        self.force_units.setToolTip("Force unit label only; the calculator assumes all imported forces are already consistent.")
        self.moment_units = QComboBox()
        self.moment_units.addItems(["N-mm", "N-m", "lbf-in"])
        self.moment_units.setToolTip("Moment unit label only; use a consistent moment arm for derived PtL modes.")
        self.fitting_factor = self._double_spin(0.01, 10.0, 1.15, 3)
        self.fitting_factor.setToolTip(
            HELP_TOPICS["fitting_factor"][1]
            + "\n\nRelevant source: NASA-STD-5020B Section 4.2.2. Click the '?' button for source links."
        )
        self.separation_factor = self._double_spin(0.01, 10.0, 1.2, 3)
        self.separation_factor.setToolTip(
            HELP_TOPICS["separation_factor"][1]
            + "\n\nRelevant source: NASA-STD-5020B Section 4.2.3 and Figure 1. Click the '?' button for source links."
        )
        self.joint_classification = QComboBox()
        self.joint_classification.addItems(["catastrophic", "critical", "non-separation-critical", "user-defined"])
        self.joint_classification.setToolTip(
            "Classification used to recommend FSsep. The numeric FSsep remains user-controlled."
        )
        self.program_yield_factor = self._double_spin(0.01, 10.0, 1.2, 3)
        self.program_yield_factor.setToolTip(
            "Program yield factor FSy used for critical classification: max(1.2, FSy).\n\n"
            + HELP_TOPICS["classification_factors"][1]
        )
        self.program_ultimate_factor = self._double_spin(0.01, 10.0, 1.4, 3)
        self.program_ultimate_factor.setToolTip(
            "Program ultimate factor FSu used for catastrophic classification.\n\n"
            + HELP_TOPICS["classification_factors"][1]
        )
        self.test_envelope_factor = self._double_spin(0.01, 10.0, 1.0, 3)
        self.test_envelope_factor.setToolTip(
            "Program-levied test factor from Figure 1. Use the proof, acceptance, qualification, "
            "or other test factor that FSsep should envelope for non-separation-critical cases.\n\n"
            + HELP_TOPICS["classification_factors"][1]
        )
        self.classification_factor_guidance = QLabel(
            "NASA-STD-5020B Figure 1 factor inputs: critical uses max(1.2, FSy), catastrophic "
            "uses FSu, and non-separation-critical uses max(1.0, program-levied test factor). "
            "These are project/program load-factor requirements, not material allowables. "
            "Use the test factor that envelopes the largest proof/acceptance/qualification "
            "multiplier relative to the same limit-load basis."
        )
        self.classification_factor_guidance.setWordWrap(True)
        self.classification_factor_guidance.setStyleSheet(
            "QLabel { background: #eef4ff; border: 1px solid #b7c9e8; border-radius: 4px; "
            "padding: 7px; color: #152238; }"
        )
        self.classification_factor_guidance.setToolTip(
            HELP_TOPICS["classification_factors"][1] + "\n\nClick the '?' buttons for source links."
        )
        self.recommended_fssep = QLineEdit()
        self.recommended_fssep.setReadOnly(True)
        self.recommended_fssep.setToolTip("Read-only recommended FSsep from the selected joint classification and factor basis.")
        self.apply_recommended_fssep = QPushButton("Apply recommended FSsep")
        self.apply_recommended_fssep.setToolTip("Copy the recommended FSsep into the editable Separation factor FSsep field.")
        self.apply_recommended_fssep.clicked.connect(self._apply_recommended_fssep)
        self.fssep_recommendation_label = QLabel()
        self.fssep_recommendation_label.setWordWrap(True)
        self.fssep_recommendation_label.setStyleSheet(
            "QLabel { background: #fff7e0; border: 1px solid #d8bd64; border-radius: 4px; "
            "padding: 7px; color: #332700; }"
        )
        self.fssep_basis_notes = QTextEdit()
        self.fssep_basis_notes.setFixedHeight(72)
        self.fssep_basis_notes.setToolTip("Optional notes documenting why the selected classification and FSsep are appropriate.")
        self.seal_or_gasket = QCheckBox("Seal or gasket affects joint function")
        self.seal_or_gasket.setToolTip(
            "Check this when leakage/seal compression controls. Eq. 19 may not predict separation accurately.\n\n"
            "This also enables Step 4 - Advanced > Seal / Pressure so residual compression criteria are checked."
        )
        self.pressure_containment = QCheckBox("Pressure or fluid containment")
        self.pressure_containment.setToolTip(
            "Check this for pressure/fluid containment cases requiring seal-specific analysis or testing.\n\n"
            "This also enables Step 4 - Advanced > Seal / Pressure so pressure separating load is checked."
        )
        self.combined_loading = QCheckBox("Combined shear, bending, eccentricity, or moment")
        self.combined_loading.setToolTip(
            "Check this when imported loads are not purely axial. Results will carry review warnings.\n\n"
            "This also enables Step 4 - Advanced > Combined Load so shear/bending interaction is screened."
        )

        form.addRow("Project name", self.project_name)
        form.addRow("Analyst", self.analyst)
        form.addRow("Force units", self.force_units)
        form.addRow("Moment units", self.moment_units)
        form.addRow("Fitting factor FF", self._with_help(self.fitting_factor, "fitting_factor"))
        form.addRow("Separation factor FSsep", self._with_help(self.separation_factor, "separation_factor"))
        form.addRow("Joint classification", self.joint_classification)
        form.addRow("", self._with_help(self.classification_factor_guidance, "classification_factors"))
        form.addRow("Program yield factor FSy", self._with_help(self.program_yield_factor, "classification_factors"))
        form.addRow("Program ultimate factor FSu", self._with_help(self.program_ultimate_factor, "classification_factors"))
        form.addRow("Program/test envelope factor", self._with_help(self.test_envelope_factor, "classification_factors"))
        form.addRow("Recommended FSsep", self.recommended_fssep)
        form.addRow("", self.apply_recommended_fssep)
        form.addRow("FSsep basis notes", self.fssep_basis_notes)
        form.addRow("", self.fssep_recommendation_label)
        form.addRow("", self.seal_or_gasket)
        form.addRow("", self.pressure_containment)
        form.addRow("", self.combined_loading)
        self.seal_or_gasket.stateChanged.connect(self._sync_project_flags_to_advanced)
        self.pressure_containment.stateChanged.connect(self._sync_project_flags_to_advanced)
        self.combined_loading.stateChanged.connect(self._sync_project_flags_to_advanced)
        self.joint_classification.currentTextChanged.connect(self._update_fssep_recommendation)
        self.separation_factor.valueChanged.connect(self._update_fssep_recommendation)
        self.program_yield_factor.valueChanged.connect(self._update_fssep_recommendation)
        self.program_ultimate_factor.valueChanged.connect(self._update_fssep_recommendation)
        self.test_envelope_factor.valueChanged.connect(self._update_fssep_recommendation)
        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def _preload_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Step 2: define the default final minimum preload profile. Bolts with different preload "
                "bases can override these values in Step 3 preload_* columns. Separation-critical joints use Eq. 4 with "
                "Ppi_min = cmin * (1 - Gamma) * Ppi_nom. Non-separation-critical multi-bolt joints "
                "use Eq. 5 with the Gamma / sqrt(nf) term. Relaxation, creep, and thermal losses are "
                "then subtracted to get each resolved Pp_min for Eq. 19. Use the '?' buttons for NASA-STD-5020B "
                "Section 4.3 guidance on where each preload parameter comes from."
            )
        )
        group = QGroupBox("Default preload basis")
        form = QFormLayout(group)
        self.ppi_nom = self._double_spin(0.0, 1.0e12, 10000.0, 3)
        self.ppi_nom.setToolTip(
            "Nominal initial preload Ppi_nom from torque/preload test data or an approved basis. "
            "NASA-STD-5020B Section 4.3.2 expects nominal preload substantiation from fastening-system hardware tests."
        )
        self.gamma = self._double_spin(0.0, 10.0, 0.25, 5)
        self.gamma.setSingleStep(0.01)
        self.gamma.setToolTip(
            "Preload variation Gamma as a decimal. Example: 0.25 for +/-25 percent. "
            "For separation-critical work, use the required test-statistical basis; do not silently use generic scatter."
        )
        self.cmin = self._double_spin(0.0, 10.0, 1.0, 5)
        self.cmin.setToolTip(
            "Minimum preload coefficient cmin. Leave at 1.0 unless your installation/preload basis defines another value."
        )
        self.nf = QSpinBox()
        self.nf.setRange(1, 100000)
        self.nf.setToolTip(
            "Number of fasteners in the pattern. Used by Eq. 5 for non-separation-critical joints when preload variation "
            "is reduced by Gamma/sqrt(nf)."
        )
        self.separation_critical = QCheckBox("Use separation-critical preload Eq. 4")
        self.separation_critical.setToolTip(
            "Checked: use Eq. 4 for separation-critical joints. Unchecked: use Eq. 5 with Gamma/sqrt(nf) for "
            "non-separation-critical multi-fastener cases."
        )
        self.separation_critical.stateChanged.connect(self._update_fssep_recommendation)
        self.relaxation_loss = self._double_spin(0.0, 1.0e12, 500.0, 3)
        self.relaxation_loss.setToolTip("Short-term preload relaxation loss subtracted from Ppi_min to calculate Pp_min.")
        self.creep_loss = self._double_spin(0.0, 1.0e12, 0.0, 3)
        self.creep_loss.setToolTip("Creep-related preload loss subtracted from Ppi_min to calculate Pp_min.")
        self.thermal_loss = self._double_spin(0.0, 1.0e12, 0.0, 3)
        self.thermal_loss.setToolTip("Thermal decrease in preload subtracted from Ppi_min to calculate Pp_min.")

        form.addRow("Ppi_nom", self._with_help(self.ppi_nom, "preload"))
        form.addRow("Gamma", self._with_help(self.gamma, "preload"))
        form.addRow("cmin", self._with_help(self.cmin, "preload"))
        form.addRow("nf", self._with_help(self.nf, "preload"))
        form.addRow("", self._with_help(self.separation_critical, "preload"))
        form.addRow("Relaxation loss", self._with_help(self.relaxation_loss, "preload"))
        form.addRow("Creep loss", self._with_help(self.creep_loss, "preload"))
        form.addRow("Thermal loss", self._with_help(self.thermal_loss, "preload"))
        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def _bolts_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Step 3: enter one row per bolt and load set. Step 1 and Step 2 are defaults only; "
                "blank override cells inherit those defaults, while filled cells let each bolt use its own "
                "preload, fitting factor, separation factor, geometry, or material values. "
                "Paste tabular data directly from Excel or CSV, with or without a header row. "
                "Use mode 'direct' when you already know PtL. "
                "Use 'axial' for an imported bolt-local axial value, 'fz' for the local Z force, "
                "'force_magnitude' only as a conservative review case, and 'axial_plus_bending' when you "
                "want to add sqrt(Mx^2 + My^2) / moment_arm to axial tension."
            )
        )
        button_row = QHBoxLayout()
        add_button = QPushButton("Add")
        add_button.setToolTip("Add a blank bolt row.")
        add_button.clicked.connect(self.add_bolt_row)
        duplicate_button = QPushButton("Duplicate")
        duplicate_button.setToolTip("Duplicate the selected bolt row so similar bolts can be edited quickly.")
        duplicate_button.clicked.connect(self.duplicate_bolt_row)
        remove_button = QPushButton("Remove")
        remove_button.setToolTip("Remove selected bolt rows.")
        remove_button.clicked.connect(self.remove_selected_bolts)
        import_button = QPushButton("Import Ansys CSV")
        import_button.setToolTip("Import the required Ansys CSV schema and create one bolt row for each imported load row.")
        import_button.clicked.connect(self.import_ansys_loads)
        import_bolt_button = QPushButton("Import Bolt CSV")
        import_bolt_button.setToolTip(BOLT_CSV_TOOLTIP_HTML)
        import_bolt_button.clicked.connect(self.import_bolt_csv)
        export_button = QPushButton("Export Bolt CSV")
        export_button.setToolTip("Export the current bolt table for review, editing, or reuse.")
        export_button.clicked.connect(self.export_bolt_csv)
        for button in (add_button, duplicate_button, remove_button, import_button, import_bolt_button, export_button):
            button_row.addWidget(button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.bolt_table = BoltLoadTableWidget(BOLT_COLUMNS, {"ptl_mode": PTL_MODES})
        self.bolt_table.setHorizontalHeaderLabels(BOLT_COLUMNS)
        self.bolt_table.setAlternatingRowColors(True)
        self.bolt_table.setToolTip(
            "Editable bolt/load table. Ctrl+V pastes spreadsheet rows; Ctrl+C copies selected cells. "
            "Blank override cells inherit Step 1 and Step 2 defaults."
        )
        _stretch_header(self.bolt_table.horizontalHeader())
        layout.addWidget(self.bolt_table, 1)
        return widget

    def _scroll_area(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _combo(self, values: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentText(current)
        return combo

    def _advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Step 4: enable only the additional checks that apply to this joint. Eq. 19 stays the "
                "primary axial separation margin. These advanced tabs add separate screens for combined "
                "fastener strength, joint slip, seal or pressure residual compression, and nonlinear Ansys "
                "contact evidence."
            )
        )
        tabs = QTabWidget()
        tabs.addTab(self._combined_load_page(), "Combined Load")
        tabs.addTab(self._slip_page(), "Joint Slip")
        tabs.addTab(self._seal_pressure_page(), "Seal / Pressure")
        tabs.addTab(self._nonlinear_evidence_page(), "Nonlinear Evidence")
        layout.addWidget(tabs, 1)
        return widget

    def _combined_load_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(
            self._guide_label(
                HELP_TOPICS["combined_load"][1]
                + " Use the bolt table shear and moment columns from Step 3 for the per-bolt load terms."
            )
        )

        basis = QGroupBox("Screen basis")
        basis_form = QFormLayout(basis)
        self.combined_enabled = QCheckBox("Enable combined-load screen")
        self.combined_enabled.setToolTip(HELP_TOPICS["combined_load"][1])
        self.combined_theory = self._combo(["nasa_ultimate", "von_mises_yield", "tresca_yield"], "nasa_ultimate")
        self.combined_theory.setToolTip(
            "nasa_ultimate uses NASA-STD-5020B Eq. 20-23. "
            "von_mises_yield and tresca_yield are labelled engineering yield screens."
        )
        self.combined_factor = self._double_spin(0.01, 100.0, 1.0, 3)
        self.combined_factor.setToolTip("Additional factor of safety applied in this combined-load screen.")
        self.combined_shear_plane = self._combo(["body", "threads"], "body")
        self.combined_shear_plane.setToolTip(
            "body: full bolt diameter is in the shear plane. threads: use minor-diameter area for shear allowables."
        )
        self.combined_plastic_bending = QCheckBox("Use plastic-bending interaction form")
        self.combined_plastic_bending.setToolTip("Checked: use Eq. 21 or Eq. 23. Unchecked: use Eq. 20 or Eq. 22.")
        basis_form.addRow("", self._with_help(self.combined_enabled, "combined_load"))
        basis_form.addRow("Theory", self.combined_theory)
        basis_form.addRow("Combined-load FS", self.combined_factor)
        basis_form.addRow("Shear plane", self.combined_shear_plane)
        basis_form.addRow("", self.combined_plastic_bending)
        layout.addWidget(basis)

        geometry = QGroupBox("Bolt geometry")
        geometry_form = QFormLayout(geometry)
        self.geom_diameter = self._double_spin(0.0, 1.0e9, 8.0, 6)
        self.geom_tensile_area = self._double_spin(0.0, 1.0e12, 36.6, 6)
        self.geom_shear_area = self._double_spin(0.0, 1.0e12, 50.3, 6)
        self.geom_minor_area = self._double_spin(0.0, 1.0e12, 36.6, 6)
        self.geom_section_modulus = self._double_spin(0.0, 1.0e12, 50.0, 6)
        self.geom_diameter.setToolTip("Bolt shank diameter used by NASA body-in-shear allowable: pi * D^2 * Fsu / 4.")
        self.geom_tensile_area.setToolTip("Tensile stress area used for axial stress and tensile allowable load.")
        self.geom_shear_area.setToolTip("Area used for shear stress in yield screens.")
        self.geom_minor_area.setToolTip("Minor-diameter/thread area used when threads are in the shear plane.")
        self.geom_section_modulus.setToolTip("Section modulus used for bending stress: sqrt(Mx^2 + My^2) / section_modulus.")
        geometry_form.addRow("Diameter", self.geom_diameter)
        geometry_form.addRow("Tensile area", self.geom_tensile_area)
        geometry_form.addRow("Shear area", self.geom_shear_area)
        geometry_form.addRow("Minor-diameter area", self.geom_minor_area)
        geometry_form.addRow("Section modulus", self.geom_section_modulus)
        layout.addWidget(geometry)

        material = QGroupBox("Material allowables")
        material_form = QFormLayout(material)
        self.mat_tensile_yield = self._double_spin(0.0, 1.0e12, 900.0, 6)
        self.mat_tensile_ultimate = self._double_spin(0.0, 1.0e12, 1100.0, 6)
        self.mat_shear_ultimate = self._double_spin(0.0, 1.0e12, 635.0, 6)
        self.mat_bending_ultimate = self._double_spin(0.0, 1.0e12, 1100.0, 6)
        self.mat_shear_yield = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.mat_tensile_yield.setToolTip("Tensile yield stress for von Mises or Tresca yield screens.")
        self.mat_tensile_ultimate.setToolTip("Tensile ultimate stress Ftu for NASA Eq. 20-23.")
        self.mat_shear_ultimate.setToolTip("Shear ultimate stress Fsu for NASA Eq. 20-23.")
        self.mat_bending_ultimate.setToolTip("Bending ultimate stress Fbu for plastic-bending interaction forms.")
        self.mat_shear_yield.setToolTip("Optional direct shear-yield allowable. Leave zero to derive from tensile yield.")
        material_form.addRow("Tensile yield", self.mat_tensile_yield)
        material_form.addRow("Tensile ultimate", self.mat_tensile_ultimate)
        material_form.addRow("Shear ultimate", self.mat_shear_ultimate)
        material_form.addRow("Bending ultimate", self.mat_bending_ultimate)
        material_form.addRow("Shear yield override", self.mat_shear_yield)
        layout.addWidget(material)
        layout.addStretch(1)
        return self._scroll_area(content)

    def _slip_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._guide_label(HELP_TOPICS["slip"][1]))
        group = QGroupBox("Slip inputs")
        form = QFormLayout(group)
        self.slip_enabled = QCheckBox("Enable joint slip screen")
        self.slip_enabled.setToolTip(HELP_TOPICS["slip"][1])
        self.slip_mode = self._combo(["per_fastener", "joint_concentric"], "per_fastener")
        self.slip_mode.setToolTip(
            "per_fastener uses NASA Eq. 86 on each bolt/load row. joint_concentric uses Eq. 84/85 on total joint shear/tension."
        )
        self.friction_coefficient = self._double_spin(0.0, 10.0, 0.10, 5)
        self.friction_coefficient.setToolTip(
            "Friction coefficient. If not substantiated, the calculator caps it at 0.20 for clean uncoated metal or 0.10 otherwise."
        )
        self.friction_substantiated = QCheckBox("Friction value is test/substantiation based")
        self.friction_substantiated.setToolTip("Checked: use the entered friction coefficient without the unsubstantiated NASA cap.")
        self.clean_uncoated_metal = QCheckBox("Clean uncoated non-lubricated metal surfaces")
        self.clean_uncoated_metal.setToolTip("Allows the unsubstantiated cap to be 0.20 instead of 0.10.")
        self.slip_factor = self._double_spin(0.01, 100.0, 1.0, 3)
        self.slip_factor.setToolTip("Slip factor of safety used in NASA Appendix A.10 slip margin equations.")
        self.joint_tensile_limit = self._double_spin(0.0, 1.0e12, 0.0, 3)
        self.joint_tensile_limit.setToolTip("Joint-level tensile limit load for Eq. 84. Use zero for Eq. 85.")
        self.joint_shear_limit = self._double_spin(0.0, 1.0e12, 1000.0, 3)
        self.joint_shear_limit.setToolTip("Joint-level shear limit load for Eq. 84/85 when joint_concentric mode is selected.")
        form.addRow("", self._with_help(self.slip_enabled, "slip"))
        form.addRow("Mode", self.slip_mode)
        form.addRow("Friction coefficient", self.friction_coefficient)
        form.addRow("", self.friction_substantiated)
        form.addRow("", self.clean_uncoated_metal)
        form.addRow("Slip FS", self.slip_factor)
        form.addRow("Joint tensile limit", self.joint_tensile_limit)
        form.addRow("Joint shear limit", self.joint_shear_limit)
        layout.addWidget(group)
        layout.addStretch(1)
        return self._scroll_area(content)

    def _seal_pressure_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._guide_label(HELP_TOPICS["seal_pressure"][1]))
        group = QGroupBox("Seal / pressure inputs")
        form = QFormLayout(group)
        self.seal_pressure_enabled = QCheckBox("Enable seal / pressure residual compression check")
        self.seal_pressure_enabled.setToolTip(HELP_TOPICS["seal_pressure"][1])
        self.pressure_value = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.pressure_area = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.gasket_contact_area = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.min_contact_pressure = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.min_residual_clamp = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.pressure_value.setToolTip("Internal pressure using units consistent with the effective pressure area.")
        self.pressure_area.setToolTip("Effective pressure area that creates separating load: pressure * area.")
        self.gasket_contact_area.setToolTip("Contact or gasket area used to calculate residual contact pressure.")
        self.min_contact_pressure.setToolTip("User-entered minimum residual contact pressure. Leave zero if not used.")
        self.min_residual_clamp.setToolTip("User-entered minimum residual clamp force. Leave zero if not used.")
        form.addRow("", self._with_help(self.seal_pressure_enabled, "seal_pressure"))
        form.addRow("Pressure", self.pressure_value)
        form.addRow("Effective pressure area", self.pressure_area)
        form.addRow("Gasket/contact area", self.gasket_contact_area)
        form.addRow("Min contact pressure", self.min_contact_pressure)
        form.addRow("Min residual clamp", self.min_residual_clamp)
        layout.addWidget(group)
        layout.addStretch(1)
        return self._scroll_area(content)

    def _nonlinear_evidence_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._guide_label(HELP_TOPICS["nonlinear_evidence"][1]))
        limits = QGroupBox("Acceptance limits")
        form = QFormLayout(limits)
        self.evidence_enabled = QCheckBox("Enable nonlinear evidence checks")
        self.evidence_enabled.setToolTip(HELP_TOPICS["nonlinear_evidence"][1])
        self.evidence_max_gap = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.evidence_min_pressure = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.evidence_max_fraction = self._double_spin(0.0, 1.0, 1.0, 6)
        self.evidence_max_ptl = self._double_spin(0.0, 1.0e12, 0.0, 6)
        self.evidence_max_gap.setToolTip("Maximum accepted contact gap. Zero disables this criterion.")
        self.evidence_min_pressure.setToolTip("Minimum accepted residual contact pressure. Zero disables this criterion.")
        self.evidence_max_fraction.setToolTip("Maximum accepted separated area fraction from 0 to 1.")
        self.evidence_max_ptl.setToolTip("Maximum accepted redistributed per-bolt PtL. Zero disables this criterion.")
        form.addRow("", self._with_help(self.evidence_enabled, "nonlinear_evidence"))
        form.addRow("Max gap", self.evidence_max_gap)
        form.addRow("Min contact pressure", self.evidence_min_pressure)
        form.addRow("Max separated fraction", self.evidence_max_fraction)
        form.addRow("Max redistributed PtL", self.evidence_max_ptl)
        layout.addWidget(limits)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add evidence row")
        add_button.setToolTip("Add a blank nonlinear contact/gap evidence row.")
        add_button.clicked.connect(self.add_evidence_row)
        remove_button = QPushButton("Remove selected")
        remove_button.setToolTip("Remove selected nonlinear evidence rows.")
        remove_button.clicked.connect(self.remove_selected_evidence)
        import_button = QPushButton("Import evidence CSV")
        import_button.setToolTip("Import contact/gap/contact-pressure/load-redistribution evidence CSV.")
        import_button.clicked.connect(self.import_nonlinear_evidence)
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        button_row.addWidget(import_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.evidence_table = QTableWidget(0, len(EVIDENCE_COLUMNS))
        self.evidence_table.setHorizontalHeaderLabels(EVIDENCE_COLUMNS)
        self.evidence_table.setAlternatingRowColors(True)
        self.evidence_table.setToolTip("Imported or manually entered nonlinear Ansys contact/gap evidence rows.")
        _stretch_header(self.evidence_table.horizontalHeader())
        layout.addWidget(self.evidence_table, 1)
        return self._scroll_area(content)

    def _rich_label(self, text: str, point_size: int = 14, bold: bool = False) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText if QT_MAJOR == 6 else Qt.RichText)
        label.setAlignment(_alignment_center())
        weight = "700" if bold else "400"
        label.setStyleSheet(
            "QLabel { color: #111827; background: transparent; "
            f"font-family: 'Cambria Math', Cambria, 'Times New Roman'; font-size: {point_size}pt; font-weight: {weight}; }}"
        )
        return label

    def _fraction_widget(self, numerator: str, denominator: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(self._rich_label(numerator, 20))
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine if QT_MAJOR == 6 else QFrame.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain if QT_MAJOR == 6 else QFrame.Plain)
        line.setLineWidth(2)
        line.setStyleSheet("QFrame { color: #111827; background: #111827; min-height: 2px; max-height: 2px; }")
        layout.addWidget(line)
        layout.addWidget(self._rich_label(denominator, 20))
        return widget

    def _fraction_equation_widget(self, lhs: str, numerator: str, denominator: str, rhs: str = "- 1") -> QWidget:
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(self._rich_label(lhs, 18))
        row.addWidget(self._fraction_widget(numerator, denominator))
        if rhs:
            row.addWidget(self._rich_label(rhs, 18))
        row.addStretch(1)
        return row_widget

    def _native_formula_card(self) -> QWidget:
        card = QGroupBox("Rendered formulas")
        card.setStyleSheet(
            "QGroupBox { background: #ffffff; border: 1px solid #c8d6e8; border-radius: 8px; "
            "margin-top: 10px; padding: 12px; color: #123052; font-weight: 700; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        eq19 = QWidget()
        eq19_layout = QVBoxLayout(eq19)
        eq19_layout.setContentsMargins(0, 0, 0, 0)
        eq19_title = QLabel("NASA-STD-5020B Eq. 19 separation margin")
        eq19_title.setStyleSheet("QLabel { color: #123052; font-size: 13pt; font-weight: 700; }")
        eq19_layout.addWidget(eq19_title)
        formula_row = QHBoxLayout()
        formula_row.addStretch(1)
        formula_row.addWidget(self._rich_label("MS<sub>sep</sub> =", 24))
        formula_row.addWidget(
            self._fraction_widget(
                "P<sub>p-min</sub>",
                "FF &times; FS<sub>sep</sub> &times; P<sub>tL</sub>",
            )
        )
        formula_row.addWidget(self._rich_label("- 1", 24))
        formula_row.addStretch(1)
        eq19_layout.addLayout(formula_row)
        pass_label = QLabel(
            "Pass criterion: MS<sub>sep</sub> &ge; 0, equivalently "
            "P<sub>p-min</sub> &ge; FF &times; FS<sub>sep</sub> &times; P<sub>tL</sub>."
        )
        pass_label.setTextFormat(Qt.TextFormat.RichText if QT_MAJOR == 6 else Qt.RichText)
        pass_label.setStyleSheet("QLabel { color: #18202a; font-size: 11pt; }")
        pass_label.setAlignment(_alignment_center())
        eq19_layout.addWidget(pass_label)
        layout.addWidget(eq19)

        preload = QLabel(
            "Eq. 2: P<sub>p-min</sub> = P<sub>pi-min</sub> - P<sub>pr</sub> - P<sub>pc</sub> - P<sub>&Delta;T-min</sub><br>"
            "Eq. 4: P<sub>pi-min</sub> = c<sub>min</sub>(1 - &Gamma;)P<sub>pi-nom</sub><br>"
            "Eq. 5: P<sub>pi-min</sub> = c<sub>min</sub>(1 - &Gamma; / &radic;n<sub>f</sub>)P<sub>pi-nom</sub>"
        )
        preload.setTextFormat(Qt.TextFormat.RichText if QT_MAJOR == 6 else Qt.RichText)
        preload.setStyleSheet(
            "QLabel { background: #f4f7fb; border: 1px solid #d8e2ee; border-radius: 6px; "
            "color: #111827; font-family: 'Cambria Math', Cambria, 'Times New Roman'; font-size: 14pt; padding: 8px; }"
        )
        preload.setAlignment(_alignment_center())
        layout.addWidget(preload)

        combined = QLabel(
            "NASA combined-load screen: U = shear term + tensile/bending term &le; 1 "
            "(Eq. 20-23 selected by shear plane and plastic-bending option)"
        )
        combined.setTextFormat(Qt.TextFormat.RichText if QT_MAJOR == 6 else Qt.RichText)
        combined.setStyleSheet(
            "QLabel { background: #f4f7fb; border: 1px solid #d8e2ee; border-radius: 6px; "
            "color: #111827; font-family: 'Cambria Math', Cambria, 'Times New Roman'; font-size: 13pt; padding: 8px; }"
        )
        combined.setAlignment(_alignment_center())
        layout.addWidget(combined)

        slip_title = QLabel("NASA Appendix A.10 slip margins")
        slip_title.setStyleSheet("QLabel { color: #123052; font-size: 13pt; font-weight: 700; }")
        layout.addWidget(slip_title)
        layout.addWidget(
            self._fraction_equation_widget(
                "MS<sub>slip</sub> =",
                "&mu; n<sub>f</sub> P<sub>p-min</sub>",
                "FS (P<sub>sL-joint</sub> + &mu; P<sub>tL-joint</sub>)",
            )
        )
        layout.addWidget(
            self._fraction_equation_widget(
                "MS<sub>slip-i</sub> =",
                "&mu; P<sub>p-min-i</sub>",
                "FF &times; FS (P<sub>sL-i</sub> + &mu; P<sub>tL-i</sub>)",
            )
        )

        seal = QLabel(
            "Seal/pressure screen: P<sub>pressure</sub> = pressure &times; A<sub>effective</sub>; "
            "P<sub>residual</sub> = n<sub>f</sub>P<sub>p-min</sub> - P<sub>pressure</sub>; "
            "p<sub>contact</sub> = P<sub>residual</sub> / A<sub>contact</sub>"
        )
        seal.setTextFormat(Qt.TextFormat.RichText if QT_MAJOR == 6 else Qt.RichText)
        seal.setWordWrap(True)
        seal.setStyleSheet(
            "QLabel { background: #f4f7fb; border: 1px solid #d8e2ee; border-radius: 6px; "
            "color: #111827; font-family: 'Cambria Math', Cambria, 'Times New Roman'; font-size: 13pt; padding: 8px; }"
        )
        seal.setAlignment(_alignment_center())
        layout.addWidget(seal)
        return card

    def _nomenclature_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Use this tab as the formula and symbol reference while filling Steps 1-4. "
                "It explains Eq. 19, preload equations, PtL derivation modes, advanced screens, and Ansys fields."
            )
        )
        layout.addWidget(self._native_formula_card())

        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(
            "QTextEdit { background-color: #fbfdff; color: #18202a; "
            "border: 1px solid #b7c5d6; selection-background-color: #b7d7ff; }"
        )
        text.setHtml(NOMENCLATURE_HTML)
        text.setToolTip("Rendered nomenclature reference for formulas, fields, and NASA source sections.")
        layout.addWidget(text, 1)

        button_row = QHBoxLayout()
        method_help = QPushButton("Method help")
        method_help.setToolTip("Open detailed method help with NASA-STD-5020B source links.")
        method_help.clicked.connect(lambda: self._show_help_topic("method"))
        local_pdf = QPushButton("Open local NASA PDF")
        local_pdf.setToolTip("Open the bundled NASA-STD-5020B PDF.")
        local_pdf.clicked.connect(self._open_local_nasa_pdf)
        online_pdf = QPushButton("Open NASA online PDF")
        online_pdf.setToolTip("Open the official NASA-hosted PDF.")
        online_pdf.clicked.connect(self._open_online_nasa_pdf)
        button_row.addWidget(method_help)
        button_row.addWidget(local_pdf)
        button_row.addWidget(online_pdf)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return widget

    def _results_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Step 5: press Calculate to validate the inputs and fill this table. A negative MSsep means "
                "Pp_min is less than FF * FSsep * PtL for that bolt/load row. Warnings do not block the math, "
                "but they identify cases where Eq. 19 is not the complete engineering substantiation. "
                "The lower summary separates combined load, slip, seal/pressure, and nonlinear evidence checks."
            )
        )
        self.results_table = QTableWidget(0, len(RESULT_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self.results_table.setAlternatingRowColors(True)
        _stretch_header(self.results_table.horizontalHeader())
        layout.addWidget(self.results_table, 1)
        self.advanced_results_text = QTextEdit()
        self.advanced_results_text.setReadOnly(True)
        self.advanced_results_text.setFixedHeight(190)
        self.advanced_results_text.setToolTip(
            "Advanced-check summary. Detailed text is also included in the Step 6 report after Calculate."
        )
        layout.addWidget(self.advanced_results_text)
        calculate_button = QPushButton("Calculate margins")
        calculate_button.setToolTip(
            "Run validation, calculate Eq. 19 for every bolt, run enabled advanced checks, and refresh the report."
        )
        calculate_button.clicked.connect(self.calculate)
        layout.addWidget(calculate_button)
        return widget

    def _report_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(
            self._guide_label(
                "Step 6: review the generated report and export it. The report records the NASA equation, "
                "source links, inputs, Eq. 19 margins, advanced check results, controlling bolt, and review warnings."
            )
        )
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setToolTip("Generated plain-text report. It updates after Calculate.")
        layout.addWidget(self.report_text, 1)
        button_row = QHBoxLayout()
        export_txt = QPushButton("Export TXT")
        export_txt.setToolTip("Save the report as a plain-text file.")
        export_txt.clicked.connect(lambda: self.export_report("txt"))
        export_html = QPushButton("Export HTML")
        export_html.setToolTip("Save the report as a simple HTML file for sharing.")
        export_html.clicked.connect(lambda: self.export_report("html"))
        button_row.addWidget(export_txt)
        button_row.addWidget(export_html)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return widget

    def _double_spin(self, minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSingleStep(1.0)
        return spin

    def _factor_guidance_project(self) -> ProjectInput:
        return ProjectInput(
            separation_factor=self.separation_factor.value(),
            joint_classification=self.joint_classification.currentText(),
            program_yield_factor=self.program_yield_factor.value(),
            program_ultimate_factor=self.program_ultimate_factor.value(),
            test_envelope_factor=self.test_envelope_factor.value(),
            fssep_basis_notes=self.fssep_basis_notes.toPlainText().strip() if hasattr(self, "fssep_basis_notes") else "",
            preload=PreloadInputs(
                separation_critical=self.separation_critical.isChecked()
                if hasattr(self, "separation_critical")
                else True,
            ),
        )

    def _update_fssep_recommendation(self, *_args: object) -> None:
        if not hasattr(self, "recommended_fssep"):
            return
        project = self._factor_guidance_project()
        recommendation = recommended_fssep(project)
        if recommendation.recommended_fssep is None:
            self.recommended_fssep.setText("user-defined")
            self.apply_recommended_fssep.setEnabled(False)
            warning = "No automatic FSsep is recommended for user-defined classification. Document the basis notes."
            style = "background: #fff7e0; border: 1px solid #d8bd64; color: #332700;"
        else:
            self.recommended_fssep.setText(f"{recommendation.recommended_fssep:.3g}")
            self.apply_recommended_fssep.setEnabled(True)
            if project.separation_factor < recommendation.recommended_fssep:
                warning = (
                    f"Entered FSsep {project.separation_factor:g} is below the recommended "
                    f"{recommendation.recommended_fssep:g}. {recommendation.basis}"
                )
                style = "background: #ffe4e4; border: 1px solid #d78a8a; color: #3b1111;"
            else:
                warning = f"Entered FSsep meets or exceeds the recommendation. {recommendation.basis}"
                style = "background: #e8f6ea; border: 1px solid #8fc495; color: #123319;"
        if (
            project.joint_classification in {"catastrophic", "critical"}
            and hasattr(self, "separation_critical")
            and not self.separation_critical.isChecked()
        ):
            warning += " Preload basis warning: Step 2 is using Eq. 5, but this classification normally pairs with Eq. 4."
            style = "background: #ffe4e4; border: 1px solid #d78a8a; color: #3b1111;"
        self.fssep_recommendation_label.setText(warning)
        self.fssep_recommendation_label.setStyleSheet(f"QLabel {{ {style} border-radius: 4px; padding: 7px; }}")

    def _apply_recommended_fssep(self) -> None:
        recommendation = recommended_fssep(self._factor_guidance_project())
        if recommendation.recommended_fssep is not None:
            self.separation_factor.setValue(recommendation.recommended_fssep)
            self._update_fssep_recommendation()

    def _sync_project_flags_to_advanced(self, *_args: object) -> None:
        if hasattr(self, "combined_enabled"):
            self.combined_enabled.setChecked(self.combined_loading.isChecked())
        if hasattr(self, "seal_pressure_enabled"):
            self.seal_pressure_enabled.setChecked(
                self.seal_or_gasket.isChecked() or self.pressure_containment.isChecked()
            )
        if hasattr(self, "statusBar"):
            if self.combined_loading.isChecked() or self.seal_or_gasket.isChecked() or self.pressure_containment.isChecked():
                self.statusBar().showMessage("Step 1 flags synced to Step 4 advanced checks.")

    def _table_item(self, text: object = "") -> QTableWidgetItem:
        item = QTableWidgetItem("" if text is None else str(text))
        item.setTextAlignment(_alignment_center())
        return item

    def add_bolt_row(self, bolt: BoltInput | None = None) -> None:
        if bolt is None:
            row_number = self.bolt_table.rowCount() + 1
            bolt = BoltInput(bolt_id=f"B{row_number}", direct_ptl=5000.0, ptl_mode="direct")
            bolt.load_row.bolt_id = bolt.bolt_id
        row = self.bolt_table.rowCount()
        self.bolt_table.insertRow(row)
        values = self._bolt_to_row_values(bolt)
        for column, value in enumerate(values):
            if BOLT_COLUMNS[column] == "ptl_mode":
                combo = QComboBox()
                combo.addItems(PTL_MODES)
                combo.setCurrentText(str(value))
                combo.setToolTip("Choose how PtL is obtained for this row.")
                self.bolt_table.setCellWidget(row, column, combo)
            else:
                self.bolt_table.setItem(row, column, self._table_item(value))

    def duplicate_bolt_row(self) -> None:
        selected = self.bolt_table.currentRow()
        if selected < 0:
            return
        bolt = self._row_to_bolt(selected)
        bolt.bolt_id = f"{bolt.bolt_id}_copy"
        bolt.load_row.bolt_id = bolt.bolt_id
        self.add_bolt_row(bolt)

    def remove_selected_bolts(self) -> None:
        rows = sorted({item.row() for item in self.bolt_table.selectedItems()}, reverse=True)
        if not rows and self.bolt_table.currentRow() >= 0:
            rows = [self.bolt_table.currentRow()]
        for row in rows:
            self.bolt_table.removeRow(row)

    def _bolt_to_row_values(self, bolt: BoltInput) -> list[object]:
        load = bolt.load_row
        return [
            bolt.bolt_id,
            bolt.ptl_mode,
            "" if bolt.direct_ptl is None else bolt.direct_ptl,
            load.case_id,
            load.set_id,
            load.fx,
            load.fy,
            load.fz,
            load.mx,
            load.my,
            load.mz,
            load.axial,
            load.shear_mag,
            "" if bolt.moment_arm is None else bolt.moment_arm,
            load.units,
            load.source_type,
            load.source_name,
            load.quality_flags,
            "" if bolt.fitting_factor is None else bolt.fitting_factor,
            "" if bolt.separation_factor is None else bolt.separation_factor,
            "" if bolt.preload_override.ppi_nom is None else bolt.preload_override.ppi_nom,
            "" if bolt.preload_override.gamma is None else bolt.preload_override.gamma,
            "" if bolt.preload_override.cmin is None else bolt.preload_override.cmin,
            "" if bolt.preload_override.nf is None else bolt.preload_override.nf,
            "" if bolt.preload_override.separation_critical is None else bolt.preload_override.separation_critical,
            "" if bolt.preload_override.relaxation_loss is None else bolt.preload_override.relaxation_loss,
            "" if bolt.preload_override.creep_loss is None else bolt.preload_override.creep_loss,
            "" if bolt.preload_override.thermal_loss is None else bolt.preload_override.thermal_loss,
            "" if bolt.geometry_override.diameter is None else bolt.geometry_override.diameter,
            "" if bolt.geometry_override.tensile_area is None else bolt.geometry_override.tensile_area,
            "" if bolt.geometry_override.shear_area is None else bolt.geometry_override.shear_area,
            "" if bolt.geometry_override.minor_diameter_area is None else bolt.geometry_override.minor_diameter_area,
            "" if bolt.geometry_override.section_modulus is None else bolt.geometry_override.section_modulus,
            "" if bolt.material_override.tensile_yield is None else bolt.material_override.tensile_yield,
            "" if bolt.material_override.tensile_ultimate is None else bolt.material_override.tensile_ultimate,
            "" if bolt.material_override.shear_ultimate is None else bolt.material_override.shear_ultimate,
            "" if bolt.material_override.bending_ultimate is None else bolt.material_override.bending_ultimate,
            "" if bolt.material_override.shear_yield is None else bolt.material_override.shear_yield,
            bolt.notes,
        ]

    def _cell_text(self, row: int, column_name: str) -> str:
        column = BOLT_COLUMNS.index(column_name)
        widget = self.bolt_table.cellWidget(row, column)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        item = self.bolt_table.item(row, column)
        return "" if item is None else item.text().strip()

    def _float_value(self, row: int, column_name: str, default: float = 0.0) -> float:
        text = self._cell_text(row, column_name)
        if text == "":
            return default
        return float(text)

    def _optional_float_value(self, row: int, column_name: str) -> float | None:
        text = self._cell_text(row, column_name)
        if text == "":
            return None
        return float(text)

    def _optional_int_value(self, row: int, column_name: str) -> int | None:
        text = self._cell_text(row, column_name)
        if text == "":
            return None
        return int(text)

    def _optional_bool_value(self, row: int, column_name: str) -> bool | None:
        text = self._cell_text(row, column_name).lower()
        if text == "":
            return None
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        raise ValueError(f"{column_name} must be true/false or blank")

    def _row_to_bolt(self, row: int) -> BoltInput:
        bolt_id = self._cell_text(row, "bolt_id")
        load = BoltLoadRow(
            case_id=self._cell_text(row, "case_id"),
            set_id=self._cell_text(row, "set_id"),
            bolt_id=bolt_id,
            fx=self._float_value(row, "fx"),
            fy=self._float_value(row, "fy"),
            fz=self._float_value(row, "fz"),
            mx=self._float_value(row, "mx"),
            my=self._float_value(row, "my"),
            mz=self._float_value(row, "mz"),
            axial=self._float_value(row, "axial"),
            shear_mag=self._float_value(row, "shear_mag"),
            units=self._cell_text(row, "units"),
            source_type=self._cell_text(row, "source_type"),
            source_name=self._cell_text(row, "source_name"),
            quality_flags=self._cell_text(row, "quality_flags"),
        )
        return BoltInput(
            bolt_id=bolt_id,
            ptl_mode=self._cell_text(row, "ptl_mode"),  # type: ignore[arg-type]
            direct_ptl=self._optional_float_value(row, "direct_ptl"),
            load_row=load,
            moment_arm=self._optional_float_value(row, "moment_arm"),
            fitting_factor=self._optional_float_value(row, "fitting_factor"),
            separation_factor=self._optional_float_value(row, "separation_factor"),
            preload_override=PreloadOverrideInputs(
                ppi_nom=self._optional_float_value(row, "preload_ppi_nom"),
                gamma=self._optional_float_value(row, "preload_gamma"),
                cmin=self._optional_float_value(row, "preload_cmin"),
                nf=self._optional_int_value(row, "preload_nf"),
                separation_critical=self._optional_bool_value(row, "preload_separation_critical"),
                relaxation_loss=self._optional_float_value(row, "preload_relaxation_loss"),
                creep_loss=self._optional_float_value(row, "preload_creep_loss"),
                thermal_loss=self._optional_float_value(row, "preload_thermal_loss"),
            ),
            geometry_override=BoltGeometryOverrides(
                diameter=self._optional_float_value(row, "geometry_diameter"),
                tensile_area=self._optional_float_value(row, "geometry_tensile_area"),
                shear_area=self._optional_float_value(row, "geometry_shear_area"),
                minor_diameter_area=self._optional_float_value(row, "geometry_minor_diameter_area"),
                section_modulus=self._optional_float_value(row, "geometry_section_modulus"),
            ),
            material_override=MaterialAllowableOverrides(
                tensile_yield=self._optional_float_value(row, "material_tensile_yield"),
                tensile_ultimate=self._optional_float_value(row, "material_tensile_ultimate"),
                shear_ultimate=self._optional_float_value(row, "material_shear_ultimate"),
                bending_ultimate=self._optional_float_value(row, "material_bending_ultimate"),
                shear_yield=self._optional_float_value(row, "material_shear_yield"),
            ),
            notes=self._cell_text(row, "notes"),
        )

    def add_evidence_row(self, evidence: ContactEvidenceRow | None = None) -> None:
        if not isinstance(evidence, ContactEvidenceRow):
            evidence = ContactEvidenceRow(case_id="LC1", set_id="1", region="joint")
        row = self.evidence_table.rowCount()
        self.evidence_table.insertRow(row)
        values = [
            evidence.case_id,
            evidence.set_id,
            evidence.bolt_id,
            evidence.region,
            evidence.max_gap,
            evidence.min_contact_pressure,
            evidence.separated_area_fraction,
            evidence.redistributed_ptl,
            evidence.quality_flags,
        ]
        for column, value in enumerate(values):
            self.evidence_table.setItem(row, column, self._table_item(value))

    def remove_selected_evidence(self) -> None:
        rows = sorted({item.row() for item in self.evidence_table.selectedItems()}, reverse=True)
        if not rows and self.evidence_table.currentRow() >= 0:
            rows = [self.evidence_table.currentRow()]
        for row in rows:
            self.evidence_table.removeRow(row)

    def _evidence_cell_text(self, row: int, column_name: str) -> str:
        column = EVIDENCE_COLUMNS.index(column_name)
        item = self.evidence_table.item(row, column)
        return "" if item is None else item.text().strip()

    def _evidence_float_value(self, row: int, column_name: str, default: float = 0.0) -> float:
        text = self._evidence_cell_text(row, column_name)
        if text == "":
            return default
        return float(text)

    def _row_to_evidence(self, row: int) -> ContactEvidenceRow:
        return ContactEvidenceRow(
            case_id=self._evidence_cell_text(row, "case_id"),
            set_id=self._evidence_cell_text(row, "set_id"),
            bolt_id=self._evidence_cell_text(row, "bolt_id"),
            region=self._evidence_cell_text(row, "region"),
            max_gap=self._evidence_float_value(row, "max_gap"),
            min_contact_pressure=self._evidence_float_value(row, "min_contact_pressure"),
            separated_area_fraction=self._evidence_float_value(row, "separated_area_fraction"),
            redistributed_ptl=self._evidence_float_value(row, "redistributed_ptl"),
            quality_flags=self._evidence_cell_text(row, "quality_flags"),
        )

    def _evidence_rows_from_table(self) -> list[ContactEvidenceRow]:
        return [self._row_to_evidence(row) for row in range(self.evidence_table.rowCount())]

    def _fill_evidence_table(self, rows: list[ContactEvidenceRow]) -> None:
        self.evidence_table.setRowCount(0)
        for evidence in rows:
            self.add_evidence_row(evidence)

    def _advanced_from_widgets(self) -> AdvancedCheckInputs:
        return AdvancedCheckInputs(
            combined=CombinedLoadInputs(
                enabled=self.combined_enabled.isChecked(),
                theory=self.combined_theory.currentText(),  # type: ignore[arg-type]
                factor_of_safety=self.combined_factor.value(),
                shear_plane=self.combined_shear_plane.currentText(),  # type: ignore[arg-type]
                plastic_bending=self.combined_plastic_bending.isChecked(),
                geometry=BoltGeometry(
                    diameter=self.geom_diameter.value(),
                    tensile_area=self.geom_tensile_area.value(),
                    shear_area=self.geom_shear_area.value(),
                    minor_diameter_area=self.geom_minor_area.value(),
                    section_modulus=self.geom_section_modulus.value(),
                ),
                material=MaterialAllowables(
                    tensile_yield=self.mat_tensile_yield.value(),
                    tensile_ultimate=self.mat_tensile_ultimate.value(),
                    shear_ultimate=self.mat_shear_ultimate.value(),
                    bending_ultimate=self.mat_bending_ultimate.value(),
                    shear_yield=self.mat_shear_yield.value(),
                ),
            ),
            slip=SlipInputs(
                enabled=self.slip_enabled.isChecked(),
                mode=self.slip_mode.currentText(),  # type: ignore[arg-type]
                friction_coefficient=self.friction_coefficient.value(),
                friction_substantiated=self.friction_substantiated.isChecked(),
                clean_uncoated_metal=self.clean_uncoated_metal.isChecked(),
                factor_of_safety=self.slip_factor.value(),
                joint_tensile_limit=self.joint_tensile_limit.value(),
                joint_shear_limit=self.joint_shear_limit.value(),
            ),
            seal_pressure=SealPressureInputs(
                enabled=self.seal_pressure_enabled.isChecked(),
                pressure=self.pressure_value.value(),
                effective_pressure_area=self.pressure_area.value(),
                gasket_contact_area=self.gasket_contact_area.value(),
                min_contact_pressure=self.min_contact_pressure.value(),
                min_residual_clamp=self.min_residual_clamp.value(),
            ),
            evidence_limits=ContactEvidenceLimits(
                enabled=self.evidence_enabled.isChecked(),
                max_gap_allowed=self.evidence_max_gap.value(),
                min_contact_pressure_required=self.evidence_min_pressure.value(),
                max_separated_area_fraction=self.evidence_max_fraction.value(),
                max_redistributed_ptl=self.evidence_max_ptl.value(),
            ),
            contact_evidence=self._evidence_rows_from_table(),
        )

    def _load_advanced(self, advanced: AdvancedCheckInputs) -> None:
        combined = advanced.combined
        self.combined_enabled.setChecked(combined.enabled)
        self.combined_theory.setCurrentText(combined.theory)
        self.combined_factor.setValue(combined.factor_of_safety)
        self.combined_shear_plane.setCurrentText(combined.shear_plane)
        self.combined_plastic_bending.setChecked(combined.plastic_bending)
        self.geom_diameter.setValue(combined.geometry.diameter)
        self.geom_tensile_area.setValue(combined.geometry.tensile_area)
        self.geom_shear_area.setValue(combined.geometry.shear_area)
        self.geom_minor_area.setValue(combined.geometry.minor_diameter_area)
        self.geom_section_modulus.setValue(combined.geometry.section_modulus)
        self.mat_tensile_yield.setValue(combined.material.tensile_yield)
        self.mat_tensile_ultimate.setValue(combined.material.tensile_ultimate)
        self.mat_shear_ultimate.setValue(combined.material.shear_ultimate)
        self.mat_bending_ultimate.setValue(combined.material.bending_ultimate)
        self.mat_shear_yield.setValue(combined.material.shear_yield)

        slip = advanced.slip
        self.slip_enabled.setChecked(slip.enabled)
        self.slip_mode.setCurrentText(slip.mode)
        self.friction_coefficient.setValue(slip.friction_coefficient)
        self.friction_substantiated.setChecked(slip.friction_substantiated)
        self.clean_uncoated_metal.setChecked(slip.clean_uncoated_metal)
        self.slip_factor.setValue(slip.factor_of_safety)
        self.joint_tensile_limit.setValue(slip.joint_tensile_limit)
        self.joint_shear_limit.setValue(slip.joint_shear_limit)

        seal = advanced.seal_pressure
        self.seal_pressure_enabled.setChecked(seal.enabled)
        self.pressure_value.setValue(seal.pressure)
        self.pressure_area.setValue(seal.effective_pressure_area)
        self.gasket_contact_area.setValue(seal.gasket_contact_area)
        self.min_contact_pressure.setValue(seal.min_contact_pressure)
        self.min_residual_clamp.setValue(seal.min_residual_clamp)

        limits = advanced.evidence_limits
        self.evidence_enabled.setChecked(limits.enabled)
        self.evidence_max_gap.setValue(limits.max_gap_allowed)
        self.evidence_min_pressure.setValue(limits.min_contact_pressure_required)
        self.evidence_max_fraction.setValue(limits.max_separated_area_fraction)
        self.evidence_max_ptl.setValue(limits.max_redistributed_ptl)
        self._fill_evidence_table(advanced.contact_evidence)

    def _project_from_widgets(self) -> ProjectInput:
        bolts = [self._row_to_bolt(row) for row in range(self.bolt_table.rowCount())]
        return ProjectInput(
            project_name=self.project_name.text().strip(),
            analyst=self.analyst.text().strip(),
            force_units=self.force_units.currentText(),
            moment_units=self.moment_units.currentText(),
            fitting_factor=self.fitting_factor.value(),
            separation_factor=self.separation_factor.value(),
            joint_classification=self.joint_classification.currentText(),
            program_yield_factor=self.program_yield_factor.value(),
            program_ultimate_factor=self.program_ultimate_factor.value(),
            test_envelope_factor=self.test_envelope_factor.value(),
            fssep_basis_notes=self.fssep_basis_notes.toPlainText().strip(),
            seal_or_gasket=self.seal_or_gasket.isChecked(),
            pressure_containment=self.pressure_containment.isChecked(),
            combined_loading_expected=self.combined_loading.isChecked(),
            advanced=self._advanced_from_widgets(),
            preload=PreloadInputs(
                ppi_nom=self.ppi_nom.value(),
                gamma=self.gamma.value(),
                cmin=self.cmin.value(),
                nf=self.nf.value(),
                separation_critical=self.separation_critical.isChecked(),
                relaxation_loss=self.relaxation_loss.value(),
                creep_loss=self.creep_loss.value(),
                thermal_loss=self.thermal_loss.value(),
            ),
            bolts=bolts,
        )

    def load_project(self, project: ProjectInput) -> None:
        self.project_name.setText(project.project_name)
        self.analyst.setText(project.analyst)
        self.force_units.setCurrentText(project.force_units)
        self.moment_units.setCurrentText(project.moment_units)
        self.fitting_factor.setValue(project.fitting_factor)
        self.separation_factor.setValue(project.separation_factor)
        self.joint_classification.setCurrentText(project.joint_classification)
        self.program_yield_factor.setValue(project.program_yield_factor)
        self.program_ultimate_factor.setValue(project.program_ultimate_factor)
        self.test_envelope_factor.setValue(project.test_envelope_factor)
        self.fssep_basis_notes.setPlainText(project.fssep_basis_notes)
        self.seal_or_gasket.setChecked(project.seal_or_gasket)
        self.pressure_containment.setChecked(project.pressure_containment)
        self.combined_loading.setChecked(project.combined_loading_expected)
        self.ppi_nom.setValue(project.preload.ppi_nom)
        self.gamma.setValue(project.preload.gamma)
        self.cmin.setValue(project.preload.cmin)
        self.nf.setValue(project.preload.nf)
        self.separation_critical.setChecked(project.preload.separation_critical)
        self.relaxation_loss.setValue(project.preload.relaxation_loss)
        self.creep_loss.setValue(project.preload.creep_loss)
        self.thermal_loss.setValue(project.preload.thermal_loss)
        self._load_advanced(project.advanced)
        self._sync_project_flags_to_advanced()
        self._update_fssep_recommendation()
        self.bolt_table.setRowCount(0)
        for bolt in project.bolts:
            self.add_bolt_row(bolt)
        self.statusBar().showMessage("Project loaded. Continue through Steps 1-6.")

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project JSON", "", "JSON files (*.json);;All files (*.*)")
        if not path:
            return
        try:
            self.load_project(load_project_json(path))
        except Exception as exc:  # pragma: no cover - GUI error path.
            QMessageBox.critical(self, "Open failed", str(exc))

    def save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project JSON", "", "JSON files (*.json);;All files (*.*)")
        if not path:
            return
        try:
            save_project_json(self._project_from_widgets(), path)
            self.statusBar().showMessage(f"Saved {path}")
        except Exception as exc:  # pragma: no cover - GUI error path.
            QMessageBox.critical(self, "Save failed", str(exc))

    def import_ansys_loads(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Ansys load CSV", "", "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        try:
            rows = import_ansys_loads_csv(path)
            self.bolt_table.setRowCount(0)
            for bolt in bolt_inputs_from_load_rows(rows, ptl_mode="axial"):
                self.add_bolt_row(bolt)
            self.combined_loading.setChecked(True)
            self.statusBar().showMessage(f"Imported {len(rows)} Ansys load rows from {path}")
        except Exception as exc:  # pragma: no cover - GUI error path.
            QMessageBox.critical(self, "Import failed", str(exc))

    def import_bolt_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import bolt table CSV", "", "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        try:
            bolts = import_bolt_table_csv(path)
            self.bolt_table.setRowCount(0)
            for bolt in bolts:
                self.add_bolt_row(bolt)
            self.statusBar().showMessage(f"Imported {len(bolts)} bolt rows from {path}")
        except Exception as exc:  # pragma: no cover - GUI error path.
            QMessageBox.critical(self, "Bolt CSV import failed", str(exc))

    def import_nonlinear_evidence(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import nonlinear evidence CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return
        try:
            rows = import_nonlinear_evidence_csv(path)
            self._fill_evidence_table(rows)
            self.evidence_enabled.setChecked(True)
            self.statusBar().showMessage(f"Imported {len(rows)} nonlinear evidence rows from {path}")
        except Exception as exc:  # pragma: no cover - GUI error path.
            QMessageBox.critical(self, "Evidence import failed", str(exc))

    def export_bolt_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export bolt table CSV", "", "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        try:
            project = self._project_from_widgets()
            export_bolt_table_csv(project.bolts, path)
            self.statusBar().showMessage(f"Exported {path}")
        except Exception as exc:  # pragma: no cover - GUI error path.
            QMessageBox.critical(self, "Export failed", str(exc))

    def calculate(self) -> None:
        try:
            project = self._project_from_widgets()
            issues = validate_project(project)
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                self._mark_validation_errors(errors)
                text = "\n".join(f"{issue.path}: {issue.message}" for issue in errors[:12])
                QMessageBox.warning(self, "Fix inputs before calculation", text)
                self.statusBar().showMessage("Validation failed. Fix highlighted cells/fields and calculate again.")
                return
            result = calculate_project(project)
        except Exception as exc:
            QMessageBox.critical(self, "Calculation failed", str(exc))
            return
        self._fill_results(result)
        self._last_report = generate_text_report(project, result)
        self.report_text.setPlainText(self._last_report)
        self.tabs.setCurrentWidget(self.results_table.parentWidget())
        self.statusBar().showMessage("Calculation complete. Review Step 5 results and Step 6 report.")

    def _mark_validation_errors(self, errors) -> None:
        error_color = QColor("#ffcccc")
        for row in range(self.bolt_table.rowCount()):
            for column in range(self.bolt_table.columnCount()):
                item = self.bolt_table.item(row, column)
                if item is not None:
                    item.setBackground(QColor("white"))
        for issue in errors:
            if issue.path.startswith("bolts["):
                try:
                    index_text = issue.path.split("[", 1)[1].split("]", 1)[0]
                    row = int(index_text)
                    field = issue.path.rsplit(".", 1)[-1]
                    if field in BOLT_COLUMNS:
                        item = self.bolt_table.item(row, BOLT_COLUMNS.index(field))
                        if item is not None:
                            item.setBackground(error_color)
                except (ValueError, IndexError):
                    continue

    def _fill_results(self, result) -> None:
        self.results_table.setRowCount(0)
        fail_color = QColor("#ffd9d9")
        pass_color = QColor("#dff4df")
        for bolt_result in result.bolt_results:
            margin = bolt_result.margin_result
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            values = [
                bolt_result.bolt_id,
                bolt_result.case_id,
                bolt_result.set_id,
                bolt_result.ptl_mode,
                f"{margin.pp_min:.6g}",
                f"{margin.fitting_factor:.6g}",
                f"{margin.separation_factor:.6g}",
                f"{margin.ptl:.6g}",
                f"{margin.demand:.6g}",
                f"{margin.margin:.6g}",
                "PASS" if margin.passed else "FAIL",
                "; ".join(bolt_result.warnings),
            ]
            for column, value in enumerate(values):
                item = self._table_item(value)
                item.setBackground(pass_color if margin.passed else fail_color)
                self.results_table.setItem(row, column, item)
        self.advanced_results_text.setPlainText(self._advanced_summary_text(result))

    def _advanced_summary_text(self, result) -> str:
        lines: list[str] = []
        lines.append("Combined Load Strength Screen")
        if result.advanced.combined_load:
            for item in result.advanced.combined_load:
                lines.append(
                    f"- {item.bolt_id}: {item.equation}, U={item.utilization:.6g}, "
                    f"MS={item.margin:.6g}, equiv_PtL={item.equivalent_ptl:.6g}, "
                    f"status={'PASS' if item.passed else 'FAIL'}"
                )
                for warning in item.warnings:
                    lines.append(f"  warning: {warning}")
        else:
            lines.append("- Not enabled.")

        lines.append("")
        lines.append("Joint Slip")
        if result.advanced.slip:
            for item in result.advanced.slip:
                target = item.bolt_id or "joint"
                lines.append(
                    f"- {target}: {item.equation}, mu={item.effective_mu:.6g}, "
                    f"MSslip={item.margin:.6g}, status={'PASS' if item.passed else 'FAIL'}"
                )
                for warning in item.warnings:
                    lines.append(f"  warning: {warning}")
        else:
            lines.append("- Not enabled.")

        lines.append("")
        lines.append("Seal / Pressure Residual Compression")
        if result.advanced.seal_pressure is not None:
            seal = result.advanced.seal_pressure
            contact = f"{seal.contact_pressure_margin:.6g}" if seal.contact_pressure_margin is not None else "n/a"
            clamp = f"{seal.residual_clamp_margin:.6g}" if seal.residual_clamp_margin is not None else "n/a"
            lines.append(
                f"- pressure_load={seal.pressure_separating_load:.6g}, residual_clamp={seal.residual_clamp:.6g}, "
                f"residual_contact_pressure={seal.residual_contact_pressure:.6g}, contact_MS={contact}, "
                f"clamp_MS={clamp}, status={'PASS' if seal.passed else 'FAIL'}"
            )
            for warning in seal.warnings:
                lines.append(f"  warning: {warning}")
        else:
            lines.append("- Not enabled.")

        lines.append("")
        lines.append("Nonlinear Ansys Evidence")
        if result.advanced.contact_evidence:
            for item in result.advanced.contact_evidence:
                target = item.bolt_id or "joint"
                region = item.region or "unlabelled region"
                lines.append(
                    f"- {item.case_id}/{item.set_id}/{target} {region}: "
                    f"status={'PASS' if item.passed else 'FAIL'}"
                )
                for warning in item.warnings:
                    lines.append(f"  warning: {warning}")
        else:
            lines.append("- Not enabled or no rows imported.")
        return "\n".join(lines)

    def export_report(self, file_type: str) -> None:
        if not self._last_report:
            self.calculate()
        if not self._last_report:
            return
        suffix = "html" if file_type == "html" else "txt"
        path, _ = QFileDialog.getSaveFileName(self, f"Export report {suffix.upper()}", "", f"*.{suffix}")
        if not path:
            return
        output = Path(path)
        if file_type == "html":
            body = self._last_report.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            output.write_text(f"<html><body><pre>{body}</pre></body></html>\n", encoding="utf-8")
        else:
            output.write_text(self._last_report + "\n", encoding="utf-8")
        self.statusBar().showMessage(f"Exported report to {output}")


def run_app(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv or []))
    app.setStyle("Fusion")
    window = BoltSeparationWindow()
    window.show()
    return app.exec() if QT_MAJOR == 6 else app.exec_()
