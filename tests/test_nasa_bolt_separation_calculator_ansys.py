from __future__ import annotations

from math import pi, sqrt

import pytest

from scripts.nasa_bolt_separation_calculator_ansys.calculator import (
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
    PreloadOverrideInputs,
    PreloadInputs,
    ProjectInput,
    SealPressureInputs,
    SlipInputs,
    calculate_combined_load_result,
    calculate_contact_evidence_results,
    calculate_initial_min_preload,
    calculate_min_preload,
    calculate_project,
    calculate_separation_margin,
    derive_ptl_from_load_row,
    generate_text_report,
    project_from_dict,
    project_to_dict,
    recommended_fssep,
    validate_fssep_against_classification,
    validate_project,
)
from scripts.nasa_bolt_separation_calculator_ansys.io_formats import (
    export_ansys_loads_csv,
    export_bolt_table_csv,
    export_nonlinear_evidence_csv,
    import_ansys_loads_csv,
    import_bolt_table_csv,
    import_nonlinear_evidence_csv,
    load_project_json,
    save_project_json,
)


def test_eq_19_margin_and_pass_fail() -> None:
    result = calculate_separation_margin(pp_min=1000.0, ff=1.0, fs_sep=2.0, ptl=400.0)

    assert result.demand == pytest.approx(800.0)
    assert result.margin == pytest.approx(0.25)
    assert result.passed is True

    failed = calculate_separation_margin(pp_min=700.0, ff=1.0, fs_sep=2.0, ptl=400.0)
    assert failed.margin == pytest.approx(-0.125)
    assert failed.passed is False


def test_eq_19_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="Pp_min"):
        calculate_separation_margin(pp_min=0.0, ff=1.0, fs_sep=1.0, ptl=1.0)
    with pytest.raises(ValueError, match="FF"):
        calculate_separation_margin(pp_min=1.0, ff=0.0, fs_sep=1.0, ptl=1.0)
    with pytest.raises(ValueError, match="FSsep"):
        calculate_separation_margin(pp_min=1.0, ff=1.0, fs_sep=0.0, ptl=1.0)
    with pytest.raises(ValueError, match="PtL"):
        calculate_separation_margin(pp_min=1.0, ff=1.0, fs_sep=1.0, ptl=0.0)


def test_preload_equations_for_critical_and_noncritical() -> None:
    critical = PreloadInputs(
        ppi_nom=1000.0,
        gamma=0.25,
        cmin=1.0,
        nf=4,
        separation_critical=True,
        relaxation_loss=50.0,
        creep_loss=10.0,
        thermal_loss=5.0,
    )
    assert calculate_initial_min_preload(critical) == pytest.approx(750.0)
    assert calculate_min_preload(critical) == pytest.approx(685.0)

    noncritical = PreloadInputs(
        ppi_nom=1000.0,
        gamma=0.25,
        cmin=1.0,
        nf=4,
        separation_critical=False,
    )
    assert calculate_initial_min_preload(noncritical) == pytest.approx(875.0)


def test_direct_and_derived_ptl_modes() -> None:
    row = BoltLoadRow(fx=3.0, fy=4.0, fz=-12.0, mx=30.0, my=40.0, axial=-100.0)

    assert derive_ptl_from_load_row(row, "axial") == pytest.approx(100.0)
    assert derive_ptl_from_load_row(row, "fz") == pytest.approx(12.0)
    assert derive_ptl_from_load_row(row, "force_magnitude") == pytest.approx(13.0)
    assert derive_ptl_from_load_row(row, "axial_plus_bending", moment_arm=10.0) == pytest.approx(105.0)

    with pytest.raises(ValueError, match="moment arm"):
        derive_ptl_from_load_row(row, "axial_plus_bending")


def test_combined_load_nasa_ultimate_eq20_screen() -> None:
    bolt = BoltInput(
        bolt_id="B1",
        load_row=BoltLoadRow(shear_mag=500.0, mx=600.0, my=800.0),
    )
    inputs = CombinedLoadInputs(
        enabled=True,
        theory="nasa_ultimate",
        factor_of_safety=1.0,
        shear_plane="body",
        plastic_bending=False,
        geometry=BoltGeometry(
            diameter=10.0,
            tensile_area=50.0,
            shear_area=80.0,
            minor_diameter_area=40.0,
            section_modulus=100.0,
        ),
        material=MaterialAllowables(
            tensile_yield=800.0,
            tensile_ultimate=1000.0,
            shear_ultimate=600.0,
            bending_ultimate=1000.0,
        ),
    )

    result = calculate_combined_load_result(bolt, ptl=1000.0, inputs=inputs, fitting_factor=1.0)

    shear_allowable = pi * 10.0**2 * 600.0 / 4.0
    shear_term = (500.0 / shear_allowable) ** 2.5
    tensile_ratio = 1000.0 / (1000.0 * 50.0)
    bending_ratio = 10.0 / 1000.0
    expected_utilization = shear_term + (tensile_ratio + bending_ratio) ** 1.5
    assert result.equation == "NASA-STD-5020B Eq. 20"
    assert result.bending_stress == pytest.approx(10.0)
    assert result.utilization == pytest.approx(expected_utilization)
    assert result.margin == pytest.approx(1.0 / expected_utilization - 1.0)
    assert result.passed is True


def test_combined_load_von_mises_yield_screen() -> None:
    bolt = BoltInput(bolt_id="B1", load_row=BoltLoadRow(shear_mag=20.0))
    inputs = CombinedLoadInputs(
        enabled=True,
        theory="von_mises_yield",
        geometry=BoltGeometry(tensile_area=50.0, shear_area=10.0, section_modulus=100.0),
        material=MaterialAllowables(tensile_yield=100.0),
    )

    result = calculate_combined_load_result(bolt, ptl=1000.0, inputs=inputs, fitting_factor=1.0)

    assert result.equation == "von Mises yield screen"
    assert result.equivalent_stress == pytest.approx(sqrt(20.0**2 + 3.0 * 2.0**2))
    assert result.utilization == pytest.approx(result.equivalent_stress / 100.0)


def test_slip_eq84_and_eq86_paths() -> None:
    joint = ProjectInput(
        fitting_factor=1.0,
        separation_factor=1.0,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0, nf=4),
        advanced=AdvancedCheckInputs(
            slip=SlipInputs(
                enabled=True,
                mode="joint_concentric",
                friction_coefficient=0.2,
                friction_substantiated=True,
                factor_of_safety=2.0,
                joint_tensile_limit=50.0,
                joint_shear_limit=100.0,
            )
        ),
        bolts=[BoltInput(bolt_id="B1", direct_ptl=100.0, ptl_mode="direct")],
    )

    joint_result = calculate_project(joint).advanced.slip[0]

    assert joint_result.equation == "NASA-STD-5020B Eq. 84"
    assert joint_result.margin == pytest.approx(0.2 * 4.0 * 1000.0 / (2.0 * (100.0 + 0.2 * 50.0)) - 1.0)

    per_bolt = ProjectInput(
        fitting_factor=1.0,
        separation_factor=1.0,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0),
        advanced=AdvancedCheckInputs(
            slip=SlipInputs(
                enabled=True,
                mode="per_fastener",
                friction_coefficient=0.2,
                friction_substantiated=True,
                factor_of_safety=2.0,
            )
        ),
        bolts=[
            BoltInput(
                bolt_id="B1",
                direct_ptl=100.0,
                ptl_mode="direct",
                load_row=BoltLoadRow(shear_mag=50.0),
            )
        ],
    )

    per_bolt_result = calculate_project(per_bolt).advanced.slip[0]

    assert per_bolt_result.equation == "NASA-STD-5020B Eq. 86"
    assert per_bolt_result.margin == pytest.approx(0.2 * 1000.0 / (2.0 * (50.0 + 0.2 * 100.0)) - 1.0)


def test_seal_pressure_residual_compression_check() -> None:
    project = ProjectInput(
        fitting_factor=1.0,
        separation_factor=1.0,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0, nf=4),
        advanced=AdvancedCheckInputs(
            seal_pressure=SealPressureInputs(
                enabled=True,
                pressure=10.0,
                effective_pressure_area=100.0,
                gasket_contact_area=100.0,
                min_contact_pressure=20.0,
                min_residual_clamp=2500.0,
            )
        ),
        bolts=[BoltInput(bolt_id="B1", direct_ptl=100.0, ptl_mode="direct")],
    )

    seal = calculate_project(project).advanced.seal_pressure

    assert seal is not None
    assert seal.pressure_separating_load == pytest.approx(1000.0)
    assert seal.residual_clamp == pytest.approx(3000.0)
    assert seal.residual_contact_pressure == pytest.approx(30.0)
    assert seal.contact_pressure_margin == pytest.approx(0.5)
    assert seal.residual_clamp_margin == pytest.approx(0.2)
    assert seal.passed is True


def test_nonlinear_evidence_acceptance_criteria_and_quality_flags() -> None:
    project = ProjectInput(
        advanced=AdvancedCheckInputs(
            evidence_limits=ContactEvidenceLimits(
                enabled=True,
                max_gap_allowed=0.05,
                min_contact_pressure_required=1.0,
                max_separated_area_fraction=0.10,
                max_redistributed_ptl=5000.0,
            ),
            contact_evidence=[
                ContactEvidenceRow(
                    case_id="LC1",
                    set_id="1",
                    bolt_id="B1",
                    region="under_head",
                    max_gap=0.01,
                    min_contact_pressure=2.0,
                    separated_area_fraction=0.02,
                    redistributed_ptl=4000.0,
                    quality_flags="mesh reviewed",
                ),
                ContactEvidenceRow(
                    case_id="LC1",
                    set_id="1",
                    bolt_id="B2",
                    region="gasket_land",
                    max_gap=0.08,
                    min_contact_pressure=0.5,
                    separated_area_fraction=0.2,
                    redistributed_ptl=6000.0,
                ),
            ],
        )
    )

    rows = calculate_contact_evidence_results(project)

    assert rows[0].passed is True
    assert any("Evidence flags" in warning for warning in rows[0].warnings)
    assert rows[1].passed is False
    assert len(rows[1].warnings) == 4


def test_project_calculation_selects_controlling_bolt() -> None:
    project = ProjectInput(
        fitting_factor=1.0,
        separation_factor=1.0,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0),
        bolts=[
            BoltInput(bolt_id="B1", direct_ptl=500.0, ptl_mode="direct"),
            BoltInput(bolt_id="B2", direct_ptl=800.0, ptl_mode="direct"),
        ],
    )

    result = calculate_project(project)

    assert result.controlling_bolt_id == "B2"
    assert result.controlling_margin == pytest.approx(0.25)
    assert result.passed is True


def test_per_bolt_table_overrides_drive_margin_and_advanced_screens() -> None:
    project = ProjectInput(
        fitting_factor=1.0,
        separation_factor=1.0,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0),
        advanced=AdvancedCheckInputs(
            combined=CombinedLoadInputs(
                enabled=True,
                theory="nasa_ultimate",
                geometry=BoltGeometry(diameter=10.0, tensile_area=50.0, shear_area=70.0, section_modulus=100.0),
                material=MaterialAllowables(tensile_ultimate=1000.0, shear_ultimate=600.0),
            ),
            slip=SlipInputs(
                enabled=True,
                mode="per_fastener",
                friction_coefficient=0.2,
                friction_substantiated=True,
                factor_of_safety=1.0,
            ),
        ),
        bolts=[
            BoltInput(
                bolt_id="B1",
                direct_ptl=500.0,
                ptl_mode="direct",
                load_row=BoltLoadRow(shear_mag=25.0),
            ),
            BoltInput(
                bolt_id="B2",
                direct_ptl=500.0,
                ptl_mode="direct",
                load_row=BoltLoadRow(shear_mag=25.0),
                fitting_factor=1.25,
                separation_factor=1.2,
                preload_override=PreloadOverrideInputs(ppi_nom=1500.0),
                geometry_override=BoltGeometryOverrides(tensile_area=25.0),
                material_override=MaterialAllowableOverrides(tensile_ultimate=800.0),
            ),
        ],
    )

    result = calculate_project(project)
    b1 = result.bolt_results[0].margin_result
    b2 = result.bolt_results[1].margin_result

    assert b1.pp_min == pytest.approx(1000.0)
    assert b1.demand == pytest.approx(500.0)
    assert b2.pp_min == pytest.approx(1500.0)
    assert b2.fitting_factor == pytest.approx(1.25)
    assert b2.separation_factor == pytest.approx(1.2)
    assert b2.demand == pytest.approx(750.0)
    assert result.advanced.slip[1].numerator == pytest.approx(0.2 * 1500.0)
    assert result.advanced.combined_load[1].axial_stress == pytest.approx(500.0 / 25.0)
    assert any("row-specific overrides" in warning for warning in result.warnings)


def test_validation_flags_axial_only_caveats() -> None:
    project = ProjectInput(
        seal_or_gasket=True,
        pressure_containment=True,
        combined_loading_expected=True,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0),
        bolts=[BoltInput(bolt_id="B1", direct_ptl=500.0, ptl_mode="direct")],
    )

    result = calculate_project(project)

    assert any("Seal or gasket" in warning for warning in result.warnings)
    assert any("Combined loading" in warning for warning in result.warnings)


def test_recommended_fssep_rules_by_classification() -> None:
    catastrophic = recommended_fssep(
        ProjectInput(joint_classification="catastrophic", program_ultimate_factor=1.5)
    )
    assert catastrophic.recommended_fssep == pytest.approx(1.5)
    assert "FSu" in catastrophic.basis

    critical_minimum = recommended_fssep(
        ProjectInput(joint_classification="critical", program_yield_factor=1.1)
    )
    assert critical_minimum.recommended_fssep == pytest.approx(1.2)
    assert "FSy" in critical_minimum.basis

    assert recommended_fssep(
        ProjectInput(joint_classification="critical", program_yield_factor=1.35)
    ).recommended_fssep == pytest.approx(1.35)

    noncritical = recommended_fssep(
        ProjectInput(joint_classification="non-separation-critical", test_envelope_factor=1.15)
    )
    assert noncritical.recommended_fssep == pytest.approx(1.15)
    assert "program-levied test factor" in noncritical.basis

    assert recommended_fssep(ProjectInput(joint_classification="user-defined")).recommended_fssep is None


def test_fssep_validation_warns_below_recommendation_and_passes_when_met() -> None:
    low = ProjectInput(
        joint_classification="catastrophic",
        program_ultimate_factor=1.4,
        separation_factor=1.2,
        bolts=[BoltInput(bolt_id="B1", direct_ptl=500.0, ptl_mode="direct")],
    )
    low_issues = validate_fssep_against_classification(low)
    assert any(issue.path == "separation_factor" for issue in low_issues)

    ok = ProjectInput(
        joint_classification="catastrophic",
        program_ultimate_factor=1.4,
        separation_factor=1.4,
        bolts=[BoltInput(bolt_id="B1", direct_ptl=500.0, ptl_mode="direct")],
    )
    assert not validate_fssep_against_classification(ok)


def test_fssep_validation_warns_for_user_defined_without_basis_notes() -> None:
    issues = validate_fssep_against_classification(ProjectInput(joint_classification="user-defined"))

    assert any(issue.path == "fssep_basis_notes" for issue in issues)


def test_classification_and_preload_basis_mismatch_warns() -> None:
    project = ProjectInput(
        joint_classification="critical",
        separation_factor=1.2,
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0, separation_critical=False),
        bolts=[BoltInput(bolt_id="B1", direct_ptl=500.0, ptl_mode="direct")],
    )

    result = calculate_project(project)

    assert any("normally pairs with separation-critical preload Eq. 4" in warning for warning in result.warnings)


def test_project_json_round_trip(tmp_path) -> None:
    project = ProjectInput(
        project_name="round trip",
        joint_classification="catastrophic",
        program_yield_factor=1.25,
        program_ultimate_factor=1.5,
        test_envelope_factor=1.1,
        fssep_basis_notes="round-trip basis",
        advanced=AdvancedCheckInputs(
            slip=SlipInputs(
                enabled=True,
                mode="per_fastener",
                friction_coefficient=0.2,
                clean_uncoated_metal=True,
            ),
            evidence_limits=ContactEvidenceLimits(enabled=True, max_gap_allowed=0.05),
            contact_evidence=[
                ContactEvidenceRow(
                    case_id="LC1",
                    set_id="1",
                    bolt_id="B1",
                    region="under_head",
                    max_gap=0.01,
                )
            ],
        ),
        preload=PreloadInputs(ppi_nom=2000.0, gamma=0.1, relaxation_loss=20.0),
        bolts=[
            BoltInput(
                bolt_id="B1",
                direct_ptl=750.0,
                ptl_mode="direct",
                fitting_factor=1.2,
                separation_factor=1.35,
                preload_override=PreloadOverrideInputs(ppi_nom=1800.0, gamma=0.05),
                geometry_override=BoltGeometryOverrides(tensile_area=44.0),
                material_override=MaterialAllowableOverrides(tensile_ultimate=1200.0),
            )
        ],
    )
    path = tmp_path / "project.json"

    save_project_json(project, path)
    loaded = load_project_json(path)

    assert loaded.project_name == "round trip"
    assert loaded.joint_classification == "catastrophic"
    assert loaded.program_yield_factor == pytest.approx(1.25)
    assert loaded.program_ultimate_factor == pytest.approx(1.5)
    assert loaded.test_envelope_factor == pytest.approx(1.1)
    assert loaded.fssep_basis_notes == "round-trip basis"
    assert loaded.advanced.slip.enabled is True
    assert loaded.advanced.slip.friction_coefficient == pytest.approx(0.2)
    assert loaded.advanced.evidence_limits.max_gap_allowed == pytest.approx(0.05)
    assert loaded.advanced.contact_evidence[0].region == "under_head"
    assert loaded.preload.ppi_nom == pytest.approx(2000.0)
    assert loaded.bolts[0].direct_ptl == pytest.approx(750.0)
    assert loaded.bolts[0].fitting_factor == pytest.approx(1.2)
    assert loaded.bolts[0].separation_factor == pytest.approx(1.35)
    assert loaded.bolts[0].preload_override.ppi_nom == pytest.approx(1800.0)
    assert loaded.bolts[0].preload_override.gamma == pytest.approx(0.05)
    assert loaded.bolts[0].geometry_override.tensile_area == pytest.approx(44.0)
    assert loaded.bolts[0].material_override.tensile_ultimate == pytest.approx(1200.0)
    assert project_from_dict(project_to_dict(project)).bolts[0].bolt_id == "B1"


def test_ansys_load_csv_round_trip(tmp_path) -> None:
    rows = [
        BoltLoadRow(
            case_id="LC1",
            set_id="2",
            bolt_id="B7",
            fx=1.0,
            fy=2.0,
            fz=3.0,
            mx=4.0,
            my=5.0,
            mz=6.0,
            axial=7.0,
            shear_mag=8.0,
            units="N|N-mm",
            source_type="beam_probe",
            source_name="B7_BEAM",
            quality_flags="axis checked",
        )
    ]
    path = tmp_path / "ansys.csv"

    export_ansys_loads_csv(rows, path)
    loaded = import_ansys_loads_csv(path)

    assert loaded[0].bolt_id == "B7"
    assert loaded[0].axial == pytest.approx(7.0)
    assert loaded[0].quality_flags == "axis checked"


def test_bolt_table_csv_round_trip(tmp_path) -> None:
    bolts = [
        BoltInput(
            bolt_id="B1",
            ptl_mode="axial_plus_bending",
            direct_ptl=None,
            load_row=BoltLoadRow(bolt_id="B1", axial=100.0, mx=50.0),
            moment_arm=10.0,
            fitting_factor=1.2,
            separation_factor=1.35,
            preload_override=PreloadOverrideInputs(
                ppi_nom=2100.0,
                gamma=0.1,
                cmin=0.95,
                nf=4,
                separation_critical=False,
                relaxation_loss=25.0,
                creep_loss=5.0,
                thermal_loss=15.0,
            ),
            geometry_override=BoltGeometryOverrides(diameter=9.5, tensile_area=40.0, shear_area=55.0),
            material_override=MaterialAllowableOverrides(tensile_yield=850.0, tensile_ultimate=1000.0),
            notes="screening row",
        )
    ]
    path = tmp_path / "bolts.csv"

    export_bolt_table_csv(bolts, path)
    loaded = import_bolt_table_csv(path)

    assert loaded[0].ptl_mode == "axial_plus_bending"
    assert loaded[0].moment_arm == pytest.approx(10.0)
    assert loaded[0].fitting_factor == pytest.approx(1.2)
    assert loaded[0].separation_factor == pytest.approx(1.35)
    assert loaded[0].preload_override.ppi_nom == pytest.approx(2100.0)
    assert loaded[0].preload_override.separation_critical is False
    assert loaded[0].geometry_override.tensile_area == pytest.approx(40.0)
    assert loaded[0].material_override.tensile_ultimate == pytest.approx(1000.0)
    assert loaded[0].notes == "screening row"


def test_nonlinear_evidence_csv_round_trip(tmp_path) -> None:
    rows = [
        ContactEvidenceRow(
            case_id="LC2",
            set_id="5",
            bolt_id="B9",
            region="flange_land",
            max_gap=0.012,
            min_contact_pressure=3.5,
            separated_area_fraction=0.04,
            redistributed_ptl=4100.0,
            quality_flags="contact converged",
        )
    ]
    path = tmp_path / "evidence.csv"

    export_nonlinear_evidence_csv(rows, path)
    loaded = import_nonlinear_evidence_csv(path)

    assert loaded[0].case_id == "LC2"
    assert loaded[0].region == "flange_land"
    assert loaded[0].max_gap == pytest.approx(0.012)
    assert loaded[0].redistributed_ptl == pytest.approx(4100.0)
    assert loaded[0].quality_flags == "contact converged"


def test_report_contains_method_sources_and_caveats() -> None:
    project = ProjectInput(
        project_name="report test",
        seal_or_gasket=True,
        combined_loading_expected=True,
        joint_classification="catastrophic",
        program_ultimate_factor=1.5,
        separation_factor=1.5,
        fssep_basis_notes="program ultimate factor basis",
        preload=PreloadInputs(ppi_nom=1000.0, gamma=0.0, relaxation_loss=0.0),
        bolts=[BoltInput(bolt_id="B1", direct_ptl=500.0, ptl_mode="direct")],
    )
    result = calculate_project(project)

    report = generate_text_report(project, result)

    assert "MSsep = Pp_min / (FF * FSsep * PtL) - 1" in report
    assert "NASA-STD-5020B PDF" in report
    assert "axial-only" in report
    assert "Seal or gasket" in report
    assert "Recommended FSsep: 1.5" in report
    assert "FSsep basis notes: program ultimate factor basis" in report
    assert "Combined Load Strength Screen" in report
    assert "Joint Slip" in report
    assert "Seal / Pressure Residual Compression" in report
    assert "Nonlinear Ansys Evidence" in report


def test_gui_help_text_and_bundled_pdf_are_available() -> None:
    from scripts.nasa_bolt_separation_calculator_ansys.gui import (
        BOLT_CSV_TOOLTIP_HTML,
        HELP_TOPICS,
        LOCAL_NASA_PDF,
        NASA_5020B_REVALIDATED_PDF_URL,
        NOMENCLATURE_HTML,
    )

    combined = "\n".join(text for _, text in HELP_TOPICS.values())

    assert "FF" in combined
    assert "FSsep" in combined
    assert "Ppi_nom" in combined
    assert "Gamma" in combined
    assert "Program yield factor FSy" in combined
    assert "Program ultimate factor FSu" in combined
    assert "program-levied test factor" in combined
    assert "not bolt material yield stress" in combined
    assert "Figure 1" in combined
    assert "NASA-STD-5020B" in combined
    assert NASA_5020B_REVALIDATED_PDF_URL.startswith("https://standards.nasa.gov/")
    assert LOCAL_NASA_PDF.exists()
    assert LOCAL_NASA_PDF.suffix.lower() == ".pdf"
    assert "Nomenclature" in NOMENCLATURE_HTML
    assert "Eq. 19 is rendered in the native equation card" in NOMENCLATURE_HTML
    assert "axial_plus_bending" in NOMENCLATURE_HTML
    assert "NASA Eq. 20" in NOMENCLATURE_HTML
    assert "Eq. 84" in NOMENCLATURE_HTML
    assert "Seal / Pressure Residual Compression" in NOMENCLATURE_HTML
    assert "Nonlinear Ansys Evidence" in NOMENCLATURE_HTML
    assert "FSsep Classification Factor Inputs" in NOMENCLATURE_HTML
    assert "program ultimate factor of safety as FSu" in NOMENCLATURE_HTML
    assert "program yield" in NOMENCLATURE_HTML
    assert "program-levied test factor" in NOMENCLATURE_HTML
    assert "Step 1 Project Flag Checkboxes" in NOMENCLATURE_HTML
    assert "enables Step 4 Seal / Pressure" in NOMENCLATURE_HTML
    assert "<b>Import full bolt table CSV</b>" in BOLT_CSV_TOOLTIP_HTML
    assert "preload_ppi_nom" in BOLT_CSV_TOOLTIP_HTML
    assert "Leave override cells blank" in BOLT_CSV_TOOLTIP_HTML


def test_validate_project_reports_missing_bolts() -> None:
    project = ProjectInput(bolts=[])

    issues = validate_project(project)

    assert any(issue.path == "bolts" and issue.severity == "error" for issue in issues)


def test_gui_fssep_recommendation_apply_smoke(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from scripts.nasa_bolt_separation_calculator_ansys.gui import QApplication, BoltSeparationWindow

    app = QApplication.instance() or QApplication([])
    window = BoltSeparationWindow()
    try:
        window.joint_classification.setCurrentText("catastrophic")
        window.program_ultimate_factor.setValue(1.6)
        window.separation_factor.setValue(1.1)
        window._update_fssep_recommendation()

        assert window.recommended_fssep.text() == "1.6"
        assert "below the recommended" in window.fssep_recommendation_label.text()

        window.apply_recommended_fssep.click()

        assert window.separation_factor.value() == pytest.approx(1.6)
        assert "meets or exceeds" in window.fssep_recommendation_label.text()
    finally:
        window.close()
        app.processEvents()


def test_gui_advanced_tab_and_summary_smoke(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from scripts.nasa_bolt_separation_calculator_ansys.gui import QApplication, BoltSeparationWindow

    app = QApplication.instance() or QApplication([])
    window = BoltSeparationWindow()
    try:
        labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]

        assert labels == [
            "Step 1 - Project",
            "Step 2 - Default Preload",
            "Step 3 - Bolts",
            "Step 4 - Advanced",
            "Step 5 - Results",
            "Step 6 - Report",
            "Nomenclature",
        ]

        window.calculate()
        summary = window.advanced_results_text.toPlainText()

        assert "Combined Load Strength Screen" in summary
        assert "Joint Slip" in summary
        assert "Nonlinear Ansys Evidence" in summary
        assert window.report_text.toPlainText()
    finally:
        window.close()
        app.processEvents()


def test_gui_project_flags_sync_to_advanced_checks(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from scripts.nasa_bolt_separation_calculator_ansys.gui import QApplication, BoltSeparationWindow

    app = QApplication.instance() or QApplication([])
    window = BoltSeparationWindow()
    try:
        window.combined_loading.setChecked(False)
        assert window.combined_enabled.isChecked() is False

        window.combined_loading.setChecked(True)
        assert window.combined_enabled.isChecked() is True

        window.seal_or_gasket.setChecked(False)
        window.pressure_containment.setChecked(False)
        assert window.seal_pressure_enabled.isChecked() is False

        window.seal_or_gasket.setChecked(True)
        assert window.seal_pressure_enabled.isChecked() is True

        window.seal_or_gasket.setChecked(False)
        assert window.seal_pressure_enabled.isChecked() is False

        window.pressure_containment.setChecked(True)
        assert window.seal_pressure_enabled.isChecked() is True
    finally:
        window.close()
        app.processEvents()


def test_gui_bolt_table_pastes_header_mapped_override_rows(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from scripts.nasa_bolt_separation_calculator_ansys.gui import QApplication, BoltSeparationWindow

    app = QApplication.instance() or QApplication([])
    window = BoltSeparationWindow()
    try:
        window.bolt_table.setRowCount(0)
        window.bolt_table.setCurrentCell(0, 0)
        QApplication.clipboard().setText(
            "bolt_id\tptl_mode\tdirect_ptl\tpreload_ppi_nom\tfitting_factor\tseparation_factor\tnotes\n"
            "B9\tdirect\t450\t1800\t1.3\t1.4\tcustom preload"
        )

        window.bolt_table.paste_clipboard()
        bolt = window._row_to_bolt(0)

        assert bolt.bolt_id == "B9"
        assert bolt.direct_ptl == pytest.approx(450.0)
        assert bolt.preload_override.ppi_nom == pytest.approx(1800.0)
        assert bolt.fitting_factor == pytest.approx(1.3)
        assert bolt.separation_factor == pytest.approx(1.4)
        assert bolt.notes == "custom preload"
    finally:
        window.close()
        app.processEvents()
