from __future__ import annotations

import sys
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from plotly.colors import qualitative
from plotly.offline import plot as write_plotly_html
from scripts.Sensor_Data_Comparison_Tool.mock_inputs.plotly_html.generate_mock_plotly_html_inputs import (
    generate_mock_plotly_html_inputs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = REPO_ROOT / "scripts" / "Sensor_Data_Comparison_Tool"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import sensor_compare_tool.plots as plots_module  # noqa: E402
from sensor_compare_tool.logic import (  # noqa: E402
    DatasetSpec,
    SensorDataError,
    apply_sample_shift,
    build_overlay_transforms,
    calculate_calibration_diagnostics,
    calculate_data_quality,
    calculate_event_timing_diagnostics,
    calculate_frequency_diagnostics,
    calculate_lag_diagnostics,
    calculate_metric_diagnostics,
    calculate_residual_diagnostics,
    calculate_rolling_diagnostics,
    calculate_sign_agreement,
    calculate_scale_offset,
    calculate_statistical_metrics,
    detect_main_comp_overlay_pairs,
    filter_time_range,
    interpolate_and_align,
    load_dataset,
    prepare_comparison,
    update_metric_tolerances,
    _clipping_candidate_count,
    _flatline_segment_count,
    _local_extrema,
    _spike_count,
    _zero_crossings,
)
from sensor_compare_tool.analysis_tables import build_analysis_table_bundle, write_analysis_workbook  # noqa: E402
from sensor_compare_tool.metric_help import (  # noqa: E402
    METRIC_HELP,
    metric_help_html,
    validate_metric_help_catalog,
)
from sensor_compare_tool.dash_plot_host import LocalResamplerDashHost  # noqa: E402
from sensor_compare_tool.plots import (  # noqa: E402
    ALL_METRIC_KEYS,
    CALIB_SCATTER_POINT_CAP,
    DEFAULT_HOVER_ANNOTATION_STYLE,
    DEFAULT_RESAMPLER_SAMPLES,
    WE_DAVIS_HOVER_ANNOTATION_STYLE,
    build_certification_ranking_figure,
    build_metrics_figure,
    build_calibration_figure,
    build_data_quality_figure,
    build_events_figure,
    build_frequency_figure,
    build_lag_figure,
    build_overlay_figure,
    build_residual_figure,
    build_rolling_metrics_figure,
    build_scale_offset_figure,
    build_sign_agreement_figure,
    build_sign_agreement_plot_data,
    is_resampled_figure,
    next_hover_annotation_style,
    next_legend_position,
)


REFERENCE_CSV = TOOL_ROOT / "mock_inputs" / "mock_sensor_dataset_reference.csv"
CANDIDATE_CSV = TOOL_ROOT / "mock_inputs" / "mock_sensor_dataset_candidate.csv"


@pytest.fixture(scope="module")
def plotly_html_paths(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return generate_mock_plotly_html_inputs(
        tmp_path_factory.mktemp("sensor_plotly_html"),
        include_plotlyjs=False,
    )


def _write_sg_plotly_html(tmp_path: Path, filename: str, *traces: dict) -> Path:
    figure = go.Figure()
    for trace in traces:
        figure.add_trace(go.Scattergl(**trace))
    html_path = tmp_path / filename
    write_plotly_html(
        figure,
        filename=str(html_path),
        output_type="file",
        auto_open=False,
        include_plotlyjs=False,
    )
    return html_path


def test_load_dataset_validates_time_and_summarizes_mock_input() -> None:
    dataset = load_dataset(REFERENCE_CSV, "Reference")

    assert dataset.display_name == "Reference"
    assert dataset.row_count > 0
    assert dataset.channels[:2] == ["SG_Front_Left", "SG_Front_Right"]
    assert dataset.time_min == pytest.approx(0.0)


def test_load_dataset_rejects_missing_time_first_column(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Elapsed,A\n0,1\n1,2\n", encoding="utf-8")

    with pytest.raises(SensorDataError, match="first column"):
        load_dataset(bad_csv)


def test_load_dataset_imports_generated_stress_overlay_fixture(plotly_html_paths: dict[str, Path]) -> None:
    dataset = load_dataset(plotly_html_paths["overlay"], "Stress Overlay")
    pairs = detect_main_comp_overlay_pairs(dataset)
    stress_channels = [f"SG{number}_von_Mises [MPa]" for number in range(57, 63)]

    assert dataset.display_name == "Stress Overlay"
    assert dataset.row_count == 49
    assert dataset.time_min == pytest.approx(0.0)
    assert dataset.time_max == pytest.approx(1200.0)
    assert len(dataset.channels) == 12
    for channel in stress_channels:
        assert f"Main: {channel}" in dataset.channels
        assert f"Comp: {channel}" in dataset.channels
    assert pairs.dataset1_columns[:2] == (
        "Main: SG57_von_Mises [MPa]",
        "Main: SG58_von_Mises [MPa]",
    )
    assert pairs.dataset2_columns[:2] == (
        "Comp: SG57_von_Mises [MPa]",
        "Comp: SG58_von_Mises [MPa]",
    )
    assert pairs.final_names[:2] == ("SG57_von_Mises [MPa]", "SG58_von_Mises [MPa]")

    prepared = prepare_comparison(
        dataset,
        dataset,
        ["Main: SG57_von_Mises [MPa]", "Main: SG58_von_Mises [MPa]"],
        ["Comp: SG57_von_Mises [MPa]", "Comp: SG58_von_Mises [MPa]"],
        ["SG57 von Mises", "SG58 von Mises"],
    )

    assert prepared.channels == ["SG57 von Mises", "SG58 von Mises"]
    assert len(prepared.dataset1_aligned) == dataset.row_count


def test_detect_main_comp_overlay_pairs_ignores_unpaired_columns(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "Time": [0.0, 1.0],
            "Main: A": [1.0, 2.0],
            "Comp: A": [1.1, 2.1],
            "Main: B": [3.0, 4.0],
            "Unrelated": [5.0, 6.0],
        }
    )
    dataset = DatasetSpec(tmp_path / "overlay.csv", "Overlay", frame)

    pairs = detect_main_comp_overlay_pairs(dataset)

    assert pairs.dataset1_columns == ("Main: A",)
    assert pairs.dataset2_columns == ("Comp: A",)
    assert pairs.final_names == ("A",)
    assert pairs.ignored_columns == ("Unrelated", "Main: B")


def test_detect_main_comp_overlay_pairs_rejects_dataset_without_pairs(plotly_html_paths: dict[str, Path]) -> None:
    dataset = load_dataset(plotly_html_paths["main"])

    with pytest.raises(SensorDataError, match="matched Main:/Comp: channels"):
        detect_main_comp_overlay_pairs(dataset)


def test_load_dataset_imports_generated_main_and_compared_html_pair(plotly_html_paths: dict[str, Path]) -> None:
    main = load_dataset(plotly_html_paths["main"], "Main")
    compared = load_dataset(plotly_html_paths["compared"], "Compared")

    assert main.channels[:2] == ["SG57_von_Mises [MPa]", "SG58_von_Mises [MPa]"]
    assert compared.channels[:2] == ["SG57_von_Mises [MPa]", "SG58_von_Mises [MPa]"]
    assert not any(channel.startswith("*") for channel in compared.channels)
    prepared = prepare_comparison(
        main,
        compared,
        ["SG57_von_Mises [MPa]"],
        ["SG57_von_Mises [MPa]"],
        ["SG57 von Mises"],
    )
    assert prepared.channels == ["SG57 von Mises"]
    assert prepared.time_min == pytest.approx(0.0)


def test_load_dataset_imports_generated_delta_and_percent_fixtures(plotly_html_paths: dict[str, Path]) -> None:
    delta = load_dataset(plotly_html_paths["comparison"])
    percent = load_dataset(plotly_html_paths["comparison_percent"])

    assert "DeltaSG57_von_Mises [MPa]" in delta.channels
    assert "%SG57_von_Mises [MPa]" in percent.channels
    assert pd.api.types.is_numeric_dtype(delta.frame["DeltaSG57_von_Mises [MPa]"])
    assert pd.api.types.is_numeric_dtype(percent.frame["%SG57_von_Mises [MPa]"])


def test_load_dataset_imports_generated_mixed_channel_fixture(plotly_html_paths: dict[str, Path]) -> None:
    dataset = load_dataset(plotly_html_paths["mixed"])

    for channel in [
        "Main: Accel_X [g]",
        "Comp: LVDT_Stroke [mm]",
        "Main: SG57_1",
        "Comp: SG57_epsilon_x [ue]",
        "Main: SG57_von_Mises [MPa]",
    ]:
        assert channel in dataset.channels
    assert dataset.row_count == 49


def test_load_dataset_imports_plotly_html_typed_arrays(tmp_path: Path) -> None:
    html_path = _write_sg_plotly_html(
        tmp_path,
        "SG_Calculations__main.html",
        {
            "x": np.array([0.0, 0.5, 1.0], dtype=np.float64),
            "y": np.array([10.0, 11.0, 12.0], dtype=np.float64),
            "name": "SG1_1",
            "meta": "SG1_1",
        },
    )

    dataset = load_dataset(html_path, "HTML")

    assert dataset.display_name == "HTML"
    assert list(dataset.frame.columns) == ["Time", "SG1_1"]
    assert dataset.frame["Time"].tolist() == pytest.approx([0.0, 0.5, 1.0])
    assert dataset.frame["SG1_1"].tolist() == pytest.approx([10.0, 11.0, 12.0])


def test_load_dataset_imports_compared_plotly_html_and_strips_marker(tmp_path: Path) -> None:
    html_path = _write_sg_plotly_html(
        tmp_path,
        "SG_Calculations__compared_data.html",
        {
            "x": [0.0, 1.0],
            "y": [20.0, 21.0],
            "name": "*SG2_1",
            "meta": "*SG2_1",
        },
    )

    dataset = load_dataset(html_path)

    assert list(dataset.frame.columns) == ["Time", "SG2_1"]
    assert dataset.frame["SG2_1"].tolist() == pytest.approx([20.0, 21.0])


def test_load_dataset_imports_overlay_plotly_html_with_role_names(tmp_path: Path) -> None:
    html_path = _write_sg_plotly_html(
        tmp_path,
        "SG_Calculations__main_and_compared_data.html",
        {
            "x": [0.0, 1.0],
            "y": [30.0, 31.0],
            "name": "Main: SG3_1",
            "meta": "Main: SG3_1",
        },
        {
            "x": [0.0, 1.0],
            "y": [29.0, 30.5],
            "name": "Comp: SG3_1",
            "meta": "Comp: SG3_1",
        },
    )

    dataset = load_dataset(html_path)

    assert list(dataset.frame.columns) == ["Time", "Main: SG3_1", "Comp: SG3_1"]
    assert dataset.frame["Main: SG3_1"].tolist() == pytest.approx([30.0, 31.0])
    assert dataset.frame["Comp: SG3_1"].tolist() == pytest.approx([29.0, 30.5])


def test_load_dataset_imports_delta_and_percent_plotly_html_names(tmp_path: Path) -> None:
    html_path = _write_sg_plotly_html(
        tmp_path,
        "SG_Calculations__comparison_percent.html",
        {
            "x": [0.0, 1.0],
            "y": [1.0, -2.0],
            "name": "\u0394SG4_1",
            "meta": "SG4_1",
        },
        {
            "x": [0.0, 1.0],
            "y": [3.5, 4.5],
            "name": "%SG4_1",
            "meta": "%SG4_1",
        },
    )

    dataset = load_dataset(html_path)

    assert list(dataset.frame.columns) == ["Time", "\u0394SG4_1", "%SG4_1"]
    assert dataset.frame["\u0394SG4_1"].tolist() == pytest.approx([1.0, -2.0])
    assert dataset.frame["%SG4_1"].tolist() == pytest.approx([3.5, 4.5])


def test_load_dataset_rejects_plotly_html_without_numeric_traces(tmp_path: Path) -> None:
    html_path = _write_sg_plotly_html(
        tmp_path,
        "SG_Calculations__empty.html",
        {"x": ["zero", "one"], "y": ["low", "high"], "name": "Bad"},
    )

    with pytest.raises(SensorDataError, match="usable Plotly trace data"):
        load_dataset(html_path)


def test_load_dataset_rejects_plotly_html_with_mismatched_time_axes(tmp_path: Path) -> None:
    html_path = _write_sg_plotly_html(
        tmp_path,
        "SG_Calculations__mismatched.html",
        {"x": [0.0, 1.0], "y": [1.0, 2.0], "name": "SG5_1"},
        {"x": [0.0, 2.0], "y": [1.5, 2.5], "name": "SG5_2"},
    )

    with pytest.raises(SensorDataError, match="same Time axis"):
        load_dataset(html_path)


def _write_raw_plotly_html(path: Path, *trace_groups: list[dict]) -> Path:
    import json

    scripts = "".join(
        f'<script>Plotly.newPlot("div{index}", {json.dumps(group)}, {{}}, {{}});</script>'
        for index, group in enumerate(trace_groups)
    )
    path.write_text(f"<html><body>{scripts}</body></html>", encoding="utf-8")
    return path


def test_load_dataset_prefers_valid_overlay_over_secondary_mismatched_figure(tmp_path: Path) -> None:
    # A real SG overlay (shared axis, Main:/Comp: names) plus a small secondary
    # figure with its own, mismatched axis. The bad figure must not mask the good
    # one — regression for the parser aborting on the first candidate it tried.
    overlay = [
        {"x": [0.0, 1.0, 2.0], "y": [10.0, 11.0, 12.0], "name": "Main: SG3_1", "meta": "Main: SG3_1"},
        {"x": [0.0, 1.0, 2.0], "y": [9.0, 10.0, 11.0], "name": "Comp: SG3_1", "meta": "Comp: SG3_1"},
    ]
    secondary = [
        {"x": [0.0, 0.5], "y": [1.0, 2.0], "name": "inset 0"},
        {"x": [0.0, 0.9], "y": [3.0, 4.0], "name": "inset 1"},
    ]
    html_path = _write_raw_plotly_html(
        tmp_path / "SG_Calculations__main_and_compared_data.html", overlay, secondary
    )

    dataset = load_dataset(html_path)

    assert list(dataset.frame.columns) == ["Time", "Main: SG3_1", "Comp: SG3_1"]
    pairs = detect_main_comp_overlay_pairs(dataset)
    assert pairs.final_names == ("SG3_1",)


def test_load_dataset_tolerates_tiny_time_axis_drift(tmp_path: Path) -> None:
    # Axes that are physically identical but differ by floating-point noise
    # (interpolation / float round-trip) must still be accepted.
    base = np.linspace(0.0, 100.0, 64)
    drifted = base + 1e-9
    overlay = [
        {"x": base.tolist(), "y": (base * 2.0).tolist(), "name": "Main: A", "meta": "Main: A"},
        {"x": drifted.tolist(), "y": (base * 1.9).tolist(), "name": "Comp: A", "meta": "Comp: A"},
    ]
    html_path = _write_raw_plotly_html(
        tmp_path / "SG_Calculations__main_and_compared_data.html", overlay
    )

    dataset = load_dataset(html_path)

    assert list(dataset.frame.columns) == ["Time", "Main: A", "Comp: A"]
    assert detect_main_comp_overlay_pairs(dataset).final_names == ("A",)


def _resampler_decorated(name: str, bin_label: str = "~1") -> str:
    # Mirrors plotly_resampler's trace-name rewrite.
    return (
        f'<b style="color:sandybrown">[R]</b> {name} '
        f'<i style="color:#fc9944">{bin_label}</i>'
    )


def test_load_dataset_imports_plotly_resampler_decorated_overlay(tmp_path: Path) -> None:
    # plot_SG_calculations builds overlays with plotly_resampler.FigureResampler:
    # trace names get HTML decoration (clean name only in `meta`) and each channel
    # is LTTB-downsampled to its OWN x sampling — same time range, different points.
    main_x = np.linspace(0.0, 100.0, 40)
    comp_x = np.linspace(0.0, 100.0, 55)
    overlay = [
        {
            "x": main_x.tolist(),
            "y": (main_x * 2.0).tolist(),
            "name": _resampler_decorated("Main: SG7_1"),
            "meta": "Main: SG7_1",
        },
        {
            "x": comp_x.tolist(),
            "y": (comp_x * 1.9).tolist(),
            "name": _resampler_decorated("Comp: SG7_1"),
            "meta": "Comp: SG7_1",
        },
    ]
    html_path = _write_raw_plotly_html(
        tmp_path / "SG_Calculations__main_and_compared_data.html", overlay
    )

    dataset = load_dataset(html_path)

    assert "Main: SG7_1" in dataset.channels
    assert "Comp: SG7_1" in dataset.channels
    assert not any("<" in column for column in dataset.frame.columns)
    pairs = detect_main_comp_overlay_pairs(dataset)
    assert pairs.final_names == ("SG7_1",)
    # Comp was re-aligned onto the shared grid: y = 1.9 * t at every sample.
    interpolated = np.interp(50.0, dataset.frame["Time"], dataset.frame["Comp: SG7_1"])
    assert interpolated == pytest.approx(95.0, abs=0.5)


def test_load_dataset_strips_resampler_decoration_preserving_channel_marker(tmp_path: Path) -> None:
    # Comparison figures set name="Δ"+col but meta=col (no marker). The Δ marker
    # must survive import, so the decoration is stripped from the name rather than
    # falling back to the unmarked meta.
    overlay = [
        {
            "x": [0.0, 1.0, 2.0],
            "y": [1.0, 2.0, 3.0],
            "name": _resampler_decorated("ΔSG9_1", "~2"),
            "meta": "SG9_1",
        },
    ]
    html_path = _write_raw_plotly_html(tmp_path / "SG_Calculations__comparison.html", overlay)

    dataset = load_dataset(html_path)

    assert dataset.channels == ["ΔSG9_1"]


def test_prepare_comparison_aligns_matched_channels_and_rejects_duplicate_final_names() -> None:
    reference = load_dataset(REFERENCE_CSV, "Reference")
    candidate = load_dataset(CANDIDATE_CSV, "Candidate")

    prepared = prepare_comparison(
        reference,
        candidate,
        ["SG_Front_Left", "Accel_Z"],
        ["SG_Front_Left", "Accel_Z"],
        ["Front Left", "Acceleration Z"],
    )

    assert prepared.channels == ["Front Left", "Acceleration Z"]
    assert list(prepared.dataset1_aligned.columns) == ["Time", "Front Left", "Acceleration Z"]
    assert len(prepared.dataset1_aligned) == len(prepared.dataset2_aligned)

    with pytest.raises(SensorDataError, match="unique"):
        prepare_comparison(
            reference,
            candidate,
            ["SG_Front_Left", "Accel_Z"],
            ["SG_Front_Left", "Accel_Z"],
            ["Repeated", "Repeated"],
        )


def test_interpolate_and_align_uses_denser_overlapping_time_axis() -> None:
    left = pd.DataFrame({"Time": [0.0, 1.0, 2.0], "A": [0.0, 10.0, 20.0]})
    right = pd.DataFrame({"Time": [0.0, 0.5, 1.0, 1.5, 2.0], "A": [0.0, 5.0, 10.0, 15.0, 20.0]})

    aligned_left, aligned_right = interpolate_and_align(left, right)

    assert aligned_left["Time"].tolist() == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])
    assert aligned_left["A"].tolist() == pytest.approx(aligned_right["A"].tolist())


def test_statistical_metrics_and_time_filter_are_qt_free() -> None:
    reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [1.0, 2.0, 3.0, 4.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [1.0, 2.0, 3.0, 4.0]})

    filtered_reference = filter_time_range(reference, 1.0, 3.0, ["A"])
    filtered_target = filter_time_range(target, 1.0, 3.0, ["A"])
    metrics = calculate_statistical_metrics(filtered_reference, filtered_target)

    assert metrics[0]["Channel"] == "A"
    assert metrics[0]["MSE"] == pytest.approx(0.0)
    assert metrics[0]["Max Correlation"] == pytest.approx(1.0)
    assert metrics[0]["Sign Agreement (%)"] == pytest.approx(100.0)
    assert metrics[0]["MAE"] == pytest.approx(0.0)
    assert np.isnan(metrics[0]["Within Tolerance Abs (%)"])
    assert np.isnan(metrics[0]["Within Tolerance Rel (%)"])
    assert metrics[0]["Robust NMAE (%)"] == pytest.approx(0.0)
    assert metrics[0]["Best Lag (s)"] == pytest.approx(0.0)
    assert metrics[0]["Calibration Slope"] == pytest.approx(1.0)
    assert metrics[0]["Certification Eligible"] == "Yes"
    assert metrics[0]["Evidence Grade"] == "A"
    assert metrics[0]["Certification Score"] == pytest.approx(100.0)
    assert metrics[0]["Peak Error (%)"] == pytest.approx(0.0)
    assert metrics[0]["Slope Error (%)"] == pytest.approx(0.0)
    assert metrics[0]["Envelope NMAE (%)"] == pytest.approx(0.0)

    # A sign-flipped channel misses every agreement threshold, but a threshold miss is a
    # graduated score penalty -- not a hard exclusion. The channel stays eligible with a low
    # score / poor grade, and the failed checks are surfaced as penalty notes for review.
    reversed_target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [-1.0, -2.0, -3.0, -4.0]})
    penalized_metrics = calculate_statistical_metrics(reference, reversed_target)
    assert penalized_metrics[0]["Certification Eligible"] == "Yes"
    assert penalized_metrics[0]["Evidence Grade"] == "C"
    assert penalized_metrics[0]["Certification Score"] < 75.0
    assert "Sign agreement < 90%" in penalized_metrics[0]["Exclusion Reason"]
    assert "Pearson correlation < 0.90" in penalized_metrics[0]["Exclusion Reason"]

    practical_reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [10.0, 10.0, 10.0, 10.0]})
    practical_target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [12.0, 12.0, 12.0, 12.0]})
    passing_metrics = calculate_statistical_metrics(
        practical_reference,
        practical_target,
        absolute_tolerance=2.0,
        relative_tolerance_pct=0.0,
    )
    failing_metrics = calculate_statistical_metrics(
        practical_reference,
        practical_target,
        absolute_tolerance=1.9,
        relative_tolerance_pct=0.0,
    )

    assert passing_metrics[0]["Percentage Error"] == pytest.approx(20.0)
    assert passing_metrics[0]["MAE"] == pytest.approx(2.0)
    assert passing_metrics[0]["Within Tolerance Abs (%)"] == pytest.approx(100.0)
    # Relative tolerance and noise floor are both zero, so the relative metric has no band.
    assert np.isnan(passing_metrics[0]["Within Tolerance Rel (%)"])
    assert passing_metrics[0]["Robust NMAE (%)"] == pytest.approx(20.0)
    assert failing_metrics[0]["Within Tolerance Abs (%)"] == pytest.approx(0.0)

    # The noise floor lets near-zero samples on both channels count as agreeing even when the
    # absolute difference exceeds the band. main 20 / comp -20 differ by 40 but both sit at 20.
    floor_reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [20.0, 20.0, 20.0, 20.0]})
    floor_target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [-20.0, -20.0, -20.0, -20.0]})
    floor_metrics = calculate_statistical_metrics(
        floor_reference,
        floor_target,
        absolute_tolerance=20.0,
        relative_tolerance_pct=10.0,
        noise_floor=20.0,
    )
    assert floor_metrics[0]["Within Tolerance Abs (%)"] == pytest.approx(100.0)
    assert floor_metrics[0]["Within Tolerance Rel (%)"] == pytest.approx(100.0)
    no_floor_metrics = calculate_statistical_metrics(
        floor_reference,
        floor_target,
        absolute_tolerance=20.0,
        relative_tolerance_pct=10.0,
        noise_floor=0.0,
    )
    assert no_floor_metrics[0]["Within Tolerance Abs (%)"] == pytest.approx(0.0)
    assert no_floor_metrics[0]["Within Tolerance Rel (%)"] == pytest.approx(0.0)


def test_statistical_metrics_reuse_precomputed_diagnostics() -> None:
    reference = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0, 3.0, 4.0],
            "A": [0.0, 1.0, 0.0, -1.0, 0.0],
            "B": [2.0, 3.0, 4.0, 3.0, 2.0],
        }
    )
    target = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0, 3.0, 4.0],
            "A": [0.1, 1.1, 0.1, -0.9, 0.1],
            "B": [1.9, 2.9, 4.1, 3.1, 2.1],
        }
    )

    diagnostics = calculate_metric_diagnostics(reference, target, sign_deadband=0.05)
    direct = calculate_statistical_metrics(reference, target, sign_deadband=0.05, absolute_tolerance=0.2)
    reused = calculate_statistical_metrics(
        reference,
        target,
        sign_deadband=0.05,
        absolute_tolerance=0.2,
        diagnostics=diagnostics,
    )

    assert reused == direct
    assert diagnostics.sign.metrics[0]["Channel"] == "A"


def test_update_metric_tolerances_changes_only_tolerance_field() -> None:
    reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0], "A": [10.0, 20.0, 30.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0, 2.0], "A": [11.0, 18.0, 35.0]})
    metrics = calculate_statistical_metrics(reference, target)

    updated = update_metric_tolerances(
        metrics,
        reference,
        target,
        absolute_tolerance=2.0,
        relative_tolerance_pct=0.0,
    )

    tolerance_keys = {"Within Tolerance Abs (%)", "Within Tolerance Rel (%)"}
    assert updated[0]["Within Tolerance Abs (%)"] == pytest.approx(2 / 3 * 100.0)
    # Relative tolerance stays zero with no noise floor, so the relative metric remains blank.
    assert pd.isna(updated[0]["Within Tolerance Rel (%)"])
    assert pd.isna(metrics[0]["Within Tolerance Abs (%)"])
    assert pd.isna(metrics[0]["Within Tolerance Rel (%)"])
    for key, value in metrics[0].items():
        if key not in tolerance_keys:
            if pd.isna(value):
                assert pd.isna(updated[0][key])
            else:
                assert updated[0][key] == value


def test_engineering_diagnostics_are_qt_free() -> None:
    reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [0.0, 1.0, 0.0, -1.0, 0.0, 1.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [0.1, 1.2, 0.1, -1.0, 0.1, 1.2]})

    residuals = calculate_residual_diagnostics(reference, target)
    rolling = calculate_rolling_diagnostics(reference, target, window_size=3)
    lag = calculate_lag_diagnostics(reference, target, max_lag_samples=2)
    events = calculate_event_timing_diagnostics(reference, target)
    quality = calculate_data_quality(reference, target)
    calibration = calculate_calibration_diagnostics(reference, target)
    frequency = calculate_frequency_diagnostics(reference, target)

    assert residuals.metrics[0]["MAE"] == pytest.approx(0.1166666667)
    assert rolling.window_size == 3
    assert "A Rolling RMSE" in rolling.frame.columns
    assert lag.metrics[0]["Best Lag (samples)"] == 0
    assert any(row["Event"] == "Zero Crossing" for row in events.metrics)
    assert all("Warning Count" in row for row in quality.rows)
    assert calibration.metrics[0]["Calibration Slope"] == pytest.approx(1.1)
    assert frequency.available
    assert frequency.metrics[0]["Spectral Energy Ratio"] > 0


def test_lag_diagnostics_match_explicit_slice_correlations() -> None:
    time_values = np.arange(7, dtype=float)
    base = np.array([0.0, 2.0, -1.0, 5.0, 1.0, -3.0, 4.0])
    reference = pd.DataFrame(
        {
            "Time": time_values,
            "Positive": base,
            "Negative": base,
            "Zero": base,
            "Const": np.ones_like(base),
            "WithNan": np.array([0.0, 1.0, np.nan, 3.0, 5.0, 8.0, 13.0]),
        }
    )
    target = pd.DataFrame(
        {
            "Time": time_values,
            "Positive": np.concatenate(([99.0], base[:-1])),
            "Negative": np.concatenate((base[1:], [99.0])),
            "Zero": base * 2.0 + 3.0,
            "Const": np.ones_like(base) * 2.0,
            "WithNan": np.array([0.0, 1.0, 2.0, np.nan, 5.0, 8.0, 13.0]),
        }
    )
    lags = np.arange(-2, 3)

    def explicit(reference_values: np.ndarray, target_values: np.ndarray, lag: int) -> float:
        if lag > 0:
            left = reference_values[:-lag]
            right = target_values[lag:]
        elif lag < 0:
            left = reference_values[-lag:]
            right = target_values[:lag]
        else:
            left = reference_values
            right = target_values
        if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
            return np.nan
        return float(np.corrcoef(left, right)[0, 1])

    result = calculate_lag_diagnostics(reference, target, max_lag_samples=2)

    for channel in ("Positive", "Negative", "Zero", "Const", "WithNan"):
        expected = np.array(
            [explicit(reference[channel].to_numpy(dtype=float), target[channel].to_numpy(dtype=float), int(lag)) for lag in lags]
        )
        np.testing.assert_allclose(result.correlations[channel].to_numpy(dtype=float), expected, equal_nan=True)

    metrics = {str(row["Channel"]): row for row in result.metrics}
    assert metrics["Positive"]["Best Lag (samples)"] == 1
    assert metrics["Negative"]["Best Lag (samples)"] == -1
    assert metrics["Zero"]["Best Lag (samples)"] == 0
    assert metrics["Const"]["Best Lag (samples)"] == 0
    assert pd.isna(metrics["Const"]["Max Lag Correlation"])


def test_event_helpers_preserve_crossings_plateaus_and_extrema() -> None:
    time_values = np.arange(6, dtype=float)

    assert _zero_crossings(time_values, np.array([-1.0, 1.0, 0.0, 0.0, 2.0, -2.0])) == pytest.approx(
        [0.5, 2.0, 3.0, 3.0, 4.5]
    )
    assert _local_extrema(time_values, np.array([0.0, 2.0, 1.0, 3.0, 3.0, 0.0]), find_max=True) == pytest.approx(
        [1.0, 3.0, 4.0]
    )
    assert _local_extrema(time_values, np.array([2.0, 0.0, 1.0, -1.0, -1.0, 3.0]), find_max=False) == pytest.approx(
        [1.0, 3.0, 4.0]
    )


def test_event_timing_diagnostics_preserve_shifted_threshold_timing() -> None:
    reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [0.0, 1.0, 2.0, 3.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [0.0, 0.0, 1.0, 2.0]})

    result = calculate_event_timing_diagnostics(reference, target)
    threshold_row = next(row for row in result.metrics if row["Channel"] == "A" and row["Event"] == "50% Threshold")

    assert threshold_row["Reference Count"] == 1
    assert threshold_row["Target Count"] == 1
    assert threshold_row["Mean Timing Error (s)"] == pytest.approx(1.0)
    assert threshold_row["Max Timing Error (s)"] == pytest.approx(1.0)


def test_data_quality_reports_progress_by_dataset_channel_and_check() -> None:
    reference = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0, 3.0],
            "A": [1.0, 1.0, 1.0, 2.0],
            "B": [0.0, 2.0, 4.0, 8.0],
        }
    )
    target = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0, 3.0],
            "A": [1.1, 1.1, 1.1, 2.1],
            "B": [0.0, 2.1, 4.1, 8.1],
        }
    )
    messages: list[str] = []

    quality = calculate_data_quality(reference, target, progress=messages.append)

    expected: list[str] = []
    for dataset_name in ("Reference", "Target"):
        expected.append(f"Checking {dataset_name} timestamps...")
        for channel_index, channel in enumerate(("A", "B"), start=1):
            label = f"{dataset_name} channel {channel_index}/2: {channel}"
            expected.extend(
                [
                    f"Checking {label} - NaN/Inf...",
                    f"Checking {label} - flatlines...",
                    f"Checking {label} - clipping...",
                    f"Checking {label} - spikes...",
                ]
            )

    assert len(quality.rows) == 4
    assert messages == expected


def test_data_quality_flatline_and_clipping_counts_edge_cases() -> None:
    assert _flatline_segment_count(np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0])) == 2
    assert (
        _flatline_segment_count(np.array([1.0, 1.0, np.nan, np.nan, np.nan, 3.0, 3.0, 3.0]))
        == 1
    )
    assert _flatline_segment_count(np.array([1.0, 1.0])) == 0

    assert (
        _clipping_candidate_count(np.array([0.0, 0.0, 0.0, 5.0, 1.0, 1.0, 1.0, 10.0, 10.0, 10.0]))
        == 2
    )
    assert _clipping_candidate_count(np.array([0.0, 10.0, 0.0, 10.0, 0.0])) == 0
    assert _clipping_candidate_count(np.array([4.0, 4.0, 4.0, 4.0])) == 1
    assert _clipping_candidate_count(np.array([np.nan, np.nan, np.nan])) == 0


def test_spike_count_floors_threshold_on_smooth_signals() -> None:
    # A smooth ramp has tiny first-difference variation; the MAD-based threshold collapses,
    # but the amplitude-relative floor keeps it from being flagged as spikes.
    smooth = np.linspace(0.0, 100.0, 500)
    assert _spike_count(smooth) == 0
    # A genuine single-step impulse (large relative to the signal range) is still caught.
    spiky = smooth.copy()
    spiky[250] += 80.0
    assert _spike_count(spiky) >= 1


def test_soft_quality_warning_does_not_reject_well_agreeing_channel() -> None:
    # Identical reference/target with a held zero baseline + plateau: the flatline/clipping
    # detectors fire (a normal feature of deterministic FEA traces), but the agreement is
    # perfect, so the channel must stay certification eligible -- not auto-rejected.
    samples = np.arange(12, dtype=float)
    shape = np.array([0.0, 0.0, 0.0, 0.0, 25.0, 50.0, 75.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    reference = pd.DataFrame({"Time": samples, "A": shape})
    target = pd.DataFrame({"Time": samples, "A": shape})

    metrics = calculate_statistical_metrics(reference, target)
    row = metrics[0]

    assert row["Data Quality Warnings"] > 0.0
    assert row["Certification Eligible"] == "Yes"
    assert row["Evidence Grade"] != "Reject"
    assert "Invalid samples (NaN/Inf)" not in str(row["Exclusion Reason"])


def test_invalid_samples_hard_reject_certification() -> None:
    samples = np.arange(6, dtype=float)
    reference = pd.DataFrame({"Time": samples, "A": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    target = pd.DataFrame({"Time": samples, "A": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0]})

    metrics = calculate_statistical_metrics(reference, target)
    row = metrics[0]

    assert row["Certification Eligible"] == "No"
    assert row["Evidence Grade"] == "Reject"
    assert "Invalid samples (NaN/Inf)" in str(row["Exclusion Reason"])


def test_low_reference_signal_hard_rejects_certification() -> None:
    samples = np.arange(6, dtype=float)
    reference = pd.DataFrame({"Time": samples, "A": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]})
    target = pd.DataFrame({"Time": samples, "A": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]})

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        metrics = calculate_statistical_metrics(reference, target)
    row = metrics[0]

    assert row["Certification Eligible"] == "No"
    assert row["Evidence Grade"] == "Reject"
    assert "Low reference signal" in str(row["Exclusion Reason"])


def test_sign_agreement_metrics_track_per_time_point_polarity() -> None:
    reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0], "A": [-2.0, -1.0, 0.0, 1.0, 2.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0], "A": [-3.0, 2.0, 0.05, -1.0, 2.0]})

    result = calculate_sign_agreement(reference, target, deadband=0.1)

    assert result.status_frame["A"].tolist() == [1, -1, 0, -1, 1]
    assert result.metrics[0]["Sign Agreement (%)"] == pytest.approx(40.0)
    assert result.metrics[0]["Sign Mismatch (%)"] == pytest.approx(40.0)
    assert result.metrics[0]["Sign Deadband (%)"] == pytest.approx(20.0)
    assert result.metrics[0]["Polarity Score"] == pytest.approx(0.0)
    assert result.metrics[0]["Longest Sign Mismatch (s)"] == pytest.approx(1.0)


def test_scale_offset_shift_and_overlay_transform_helpers() -> None:
    predictor = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [1.0, 2.0, 3.0, 4.0]})
    response = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0], "A": [3.0, 5.0, 7.0, 9.0]})

    scale_offset = calculate_scale_offset(predictor, response)
    assert scale_offset[0]["Scale"] == pytest.approx(2.0)
    assert scale_offset[0]["Offset"] == pytest.approx(1.0)

    shifted_right, samples_right = apply_sample_shift(predictor, 1.0)
    shifted_left, samples_left = apply_sample_shift(predictor, -1.0)
    assert samples_right == 1
    assert samples_left == -1
    assert shifted_right["A"].tolist() == pytest.approx([1e-8, 1.0, 2.0, 3.0])
    assert shifted_left["A"].tolist() == pytest.approx([2.0, 3.0, 4.0, 1e-8])

    scaled_only, offset_only, scaled_offset_df = build_overlay_transforms(predictor, response)
    assert list(scaled_only.columns) == ["Time", "A"]
    assert list(offset_only.columns) == ["Time", "A"]
    assert list(scaled_offset_df.columns) == ["Time", "A"]


def test_analysis_table_bundle_and_excel_export_include_master_tables(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    reference = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0, 3.0],
            "A": [1.0, 2.0, 3.0, 4.0],
            "B": [2.0, 4.0, 6.0, 8.0],
        }
    )
    target = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0, 3.0],
            "A": [1.1, 2.1, 3.1, 4.1],
            "B": [2.2, 4.2, 6.2, 8.2],
        }
    )

    def bundle_for(scope: str, columns: list[str]):
        reference_filtered = filter_time_range(reference, 1.0, 3.0, columns)
        target_filtered = filter_time_range(target, 1.0, 3.0, columns)
        metrics = calculate_statistical_metrics(reference_filtered, target_filtered)
        residuals = calculate_residual_diagnostics(reference_filtered, target_filtered)
        rolling = calculate_rolling_diagnostics(reference_filtered, target_filtered)
        lag = calculate_lag_diagnostics(reference_filtered, target_filtered)
        events = calculate_event_timing_diagnostics(reference_filtered, target_filtered)
        quality = calculate_data_quality(reference_filtered, target_filtered)
        calibration = calculate_calibration_diagnostics(reference_filtered, target_filtered)
        frequency = calculate_frequency_diagnostics(reference_filtered, target_filtered)
        sign_agreement = calculate_sign_agreement(reference_filtered, target_filtered)
        scale_offset = calculate_scale_offset(target_filtered, reference_filtered)
        scaled_only, offset_only, scaled_offset = build_overlay_transforms(reference_filtered, target_filtered)
        return build_analysis_table_bundle(
            scope=scope,
            summary={"Reference": "Main", "Candidate": "Comp", "Channel Count": len(columns)},
            metrics=metrics,
            scale_offset_metrics=scale_offset,
            sign_metrics=sign_agreement.metrics,
            sign_status_frame=sign_agreement.status_frame,
            residual_metrics=residuals.metrics,
            residual_frame=residuals.residual_frame,
            rolling_frame=rolling.frame,
            lag_metrics=lag.metrics,
            lag_correlations=lag.correlations,
            event_metrics=events.metrics,
            quality_rows=quality.rows,
            calibration_metrics=calibration.metrics,
            frequency_metrics=frequency.metrics,
            frequency_spectrum=frequency.spectrum_frame,
            overlay_frames={
                "overlay_reference": reference_filtered,
                "overlay_candidate_original": target_filtered,
                "overlay_candidate_scaled": scaled_only,
                "overlay_candidate_offset": offset_only,
                "overlay_candidate_scaled_offset": scaled_offset,
            },
        )

    current_bundle = bundle_for("Current analysis view", ["A"])
    full_bundle = bundle_for("Full aligned data", ["A", "B"])

    assert current_bundle.table("metrics").frame["Channel"].tolist() == ["A"]
    assert full_bundle.table("metrics").frame["Channel"].tolist() == ["A", "B"]
    assert current_bundle.table("certification_ranking").title == "Certification Ranking"
    assert current_bundle.table("certification_ranking").frame["Channel"].tolist() == ["A"]
    assert "Certification Score" in current_bundle.table("certification_ranking").frame.columns
    assert "Within Tolerance Abs (%)" in current_bundle.table("metrics").frame.columns
    assert "Within Tolerance Rel (%)" in current_bundle.table("metrics").frame.columns
    assert "Robust NMAE (%)" in current_bundle.table("metrics").frame.columns
    assert list(current_bundle.table("overlay_reference").frame.columns) == ["Time", "A"]
    assert list(full_bundle.table("overlay_reference").frame.columns) == ["Time", "A", "B"]
    assert current_bundle.table("events").frame.shape[0] > 0
    assert current_bundle.table("data_quality").frame.shape[0] > 0

    workbook_path = write_analysis_workbook(tmp_path / "analysis.xlsx", current_bundle)
    workbook = openpyxl.load_workbook(workbook_path, data_only=True)
    try:
        assert "Summary" in workbook.sheetnames
        assert "Statistical Metrics" in workbook.sheetnames
        assert "Certification Ranking" in workbook.sheetnames
        assert "Overlay Reference" in workbook.sheetnames
        assert workbook["Summary"]["A1"].value == "Property"
        assert workbook["Statistical Metrics"]["A1"].value == "Channel"
        assert workbook["Statistical Metrics"]["A2"].value == "A"
        assert workbook["Certification Ranking"]["A1"].value == "Channel"
        header_values = [cell.value for cell in workbook["Statistical Metrics"][1]]
        assert "Within Tolerance Abs (%)" in header_values
        assert "Within Tolerance Rel (%)" in header_values
        assert "Robust NMAE (%)" in [cell.value for cell in workbook["Statistical Metrics"][1]]
        assert workbook["Overlay Reference"]["B1"].value == "A"
    finally:
        workbook.close()


def test_plot_builders_return_expected_trace_families() -> None:
    metrics = [
        {
            "Channel": "A",
            "Max Correlation": 1.0,
            "Lag at Max Correlation (samples)": 0,
            "Time Shift (s)": 0.0,
            "MSE": 0.0,
            "RMSE": 0.0,
            "Coefficient of Determination": 1.0,
            "Pearson Correlation": 1.0,
            "Absolute Error": 0.0,
            "Percentage Error": 0.0,
            "SMAPE": 0.0,
            "WMAPE": 0.0,
            "Within Tolerance Abs (%)": 100.0,
            "Within Tolerance Rel (%)": 100.0,
            "Robust NMAE (%)": 0.0,
            "Sign Agreement (%)": 100.0,
            "Sign Mismatch (%)": 0.0,
            "Sign Deadband (%)": 0.0,
            "Polarity Score": 1.0,
            "Longest Sign Mismatch (s)": 0.0,
            "Mean Bias": 0.0,
            "MAE": 0.0,
            "Max Abs Error": 0.0,
            "P95 Abs Error": 0.0,
            "P99 Abs Error": 0.0,
            "Best Lag (samples)": 0.0,
            "Best Lag (s)": 0.0,
            "Max Lag Correlation": 1.0,
            "Calibration Slope": 1.0,
            "Calibration Offset": 0.0,
            "Calibration R^2": 1.0,
            "Residual Std": 0.0,
            "Mean Event Timing Error (s)": 0.0,
            "Max Event Timing Error (s)": 0.0,
            "Event Count Delta": 0.0,
            "Data Quality Warnings": 0.0,
            "Dominant Freq Delta": 0.0,
            "Spectral Energy Ratio": 1.0,
            "Validation Role": "Unassigned",
            "Certification Eligible": "Yes",
            "Exclusion Reason": "Eligible",
            "Peak Strain Test": 2.0,
            "Peak Strain FEA": 2.2,
            "Peak Error (%)": 10.0,
            "Slope Error (%)": 0.0,
            "Offset (signal units)": 0.0,
            "Envelope NMAE (%)": 0.0,
            "Structural Relevance": "Unassigned",
            "Certification Score": 90.0,
            "Evidence Grade": "A",
        }
    ]
    scale_offset = [{"Channel": "A", "Scale": 1.0, "Offset": 0.0}]
    reference = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [1.0, 2.0, 1.0, 0.0, 1.0, 2.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [1.2, 2.2, 1.2, 0.2, 1.2, 2.2]})
    scaled_only = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [1.1, 2.1, 1.1, 0.1, 1.1, 2.1]})
    offset_only = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [1.0, 2.0, 1.0, 0.0, 1.0, 2.0]})
    scaled_offset = pd.DataFrame({"Time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], "A": [0.9, 1.9, 0.9, -0.1, 0.9, 1.9]})

    metrics_fig = build_metrics_figure(metrics, "Reference", "Candidate")
    we_davis_metrics_fig = build_metrics_figure(
        metrics,
        "Reference",
        "Candidate",
        hover_annotation_style=WE_DAVIS_HOVER_ANNOTATION_STYLE,
    )
    all_metrics_fig = build_metrics_figure(metrics, "Reference", "Candidate", selected_metric_keys=ALL_METRIC_KEYS)
    empty_metrics_fig = build_metrics_figure(metrics, "Reference", "Candidate", selected_metric_keys=[])
    certification_fig = build_certification_ranking_figure(metrics, "Reference", "Candidate")
    scale_fig = build_scale_offset_figure(scale_offset, "Reference")
    residuals = calculate_residual_diagnostics(reference, target)
    rolling = calculate_rolling_diagnostics(reference, target, window_size=2)
    lag = calculate_lag_diagnostics(reference, target, max_lag_samples=1)
    events = calculate_event_timing_diagnostics(reference, target)
    quality = calculate_data_quality(reference, target)
    calibration = calculate_calibration_diagnostics(reference, target)
    frequency = calculate_frequency_diagnostics(reference, target)
    residual_fig = build_residual_figure(residuals.residual_frame, residuals.metrics, "Reference", "Candidate")
    tolerance_residual_fig = build_residual_figure(
        residuals.residual_frame,
        residuals.metrics,
        "Reference",
        "Candidate",
        reference_frame=reference,
        absolute_tolerance=0.15,
    )
    rolling_fig = build_rolling_metrics_figure(rolling.frame, rolling.window_size)
    lag_fig = build_lag_figure(lag.correlations, lag.metrics)
    events_fig = build_events_figure(events.metrics)
    quality_fig = build_data_quality_figure(quality.rows)
    calibration_fig = build_calibration_figure(reference, target, calibration.metrics, "Reference", "Candidate")
    frequency_fig = build_frequency_figure(frequency)
    overlay_fig = build_overlay_figure(
        reference,
        target,
        scaled_only,
        offset_only,
        scaled_offset,
        "Reference",
        "Candidate",
    )
    sign_result = calculate_sign_agreement(reference, target)
    sign_fig = build_sign_agreement_figure(sign_result.status_frame, sign_result.metrics, "Reference", "Candidate")
    sign_data = build_sign_agreement_plot_data(sign_result.status_frame, sign_result.metrics, "Reference", "Candidate", deadband=0.02)
    overlay_hidden_fig = build_overlay_figure(
        reference,
        target,
        scaled_only,
        offset_only,
        scaled_offset,
        "Reference",
        "Candidate",
        hide_transforms=True,
    )
    long_reference_name = "SG_Calculations__Bladeout_Max_REF_LPT1_CF_1_58__Mixed_Test_Channels__main_and_compared_data - Main"
    long_target_name = "SG_Calculations__Bladeout_Max_REF_LPT1_CF_1_58__Mixed_Test_Channels__main_and_compared_data - Comp"
    long_name_overlay_fig = build_overlay_figure(
        reference,
        target,
        scaled_only,
        offset_only,
        scaled_offset,
        long_reference_name,
        long_target_name,
    )
    dense_time = np.arange(DEFAULT_RESAMPLER_SAMPLES + 1, dtype=float)
    dense_residual = pd.DataFrame({"Time": dense_time, "A": np.sin(dense_time / 10.0)})
    dense_residual_fig = build_residual_figure(
        dense_residual,
        [
            {
                "Channel": "A",
                "Mean Bias": 0.0,
                "MAE": 0.0,
                "Max Abs Error": 0.0,
                "P95 Abs Error": 0.0,
                "P99 Abs Error": 0.0,
            }
        ],
        "Reference",
        "Candidate",
    )

    assert len(metrics_fig.data) == 9
    assert len(all_metrics_fig.data) == len(ALL_METRIC_KEYS)
    assert len(empty_metrics_fig.layout.annotations) == 1
    assert certification_fig.data[0].type == "bar"
    assert certification_fig.data[0].text[0] == "A"
    assert any(trace.name == "Peak parity" for trace in certification_fig.data)
    assert len(scale_fig.data) == 2
    assert any(shape.y0 == 1 and shape.y1 == 1 for shape in scale_fig.layout.shapes)
    assert len(sign_fig.data) == 5
    assert len(residual_fig.data) == 1
    assert [trace.name for trace in tolerance_residual_fig.data] == [
        "A residual",
        "A upper tolerance",
        "A lower tolerance",
        "A outside tolerance",
    ]
    assert len(tolerance_residual_fig.data[-1].x) == len(reference)
    assert len(rolling_fig.data) == 4
    assert len(lag_fig.data) == 1
    assert events_fig.data[0].type == "table"
    assert quality_fig.data[0].type == "table"
    assert len(calibration_fig.data) >= 2
    assert len(frequency_fig.data) == 2
    assert len(overlay_fig.data) == 5
    assert len(overlay_hidden_fig.data) == 2
    assert [trace.name for trace in overlay_fig.data] == [
        "Reference - A",
        "Candidate Original - A",
        "Candidate Scaled - A",
        "Candidate Offset - A",
        "Candidate Scaled + Offset - A",
    ]
    assert [trace.legendgroup for trace in overlay_fig.data] == ["A"] * 5
    assert [trace.meta["overlay_channel"] for trace in overlay_fig.data] == ["A"] * 5
    assert [trace.name for trace in overlay_hidden_fig.data] == ["Reference - A", "Candidate - A"]
    assert overlay_hidden_fig.data[0].line.color == qualitative.Light24[0]
    assert overlay_hidden_fig.data[1].line.color == qualitative.Light24[0]
    assert overlay_hidden_fig.data[1].line.dash == "dash"
    assert [trace.name for trace in long_name_overlay_fig.data[:2]] == ["Reference - A", "Checked Original - A"]
    assert "SG_Calculations" not in str(long_name_overlay_fig.layout.title.text)
    assert all("SG_Calculations" not in str(trace.name) for trace in long_name_overlay_fig.data)
    assert not is_resampled_figure(residual_fig)
    assert not is_resampled_figure(rolling_fig)
    assert not is_resampled_figure(lag_fig)
    assert not is_resampled_figure(calibration_fig)
    assert not is_resampled_figure(frequency_fig)
    assert not is_resampled_figure(overlay_fig)
    assert not is_resampled_figure(overlay_hidden_fig)
    assert is_resampled_figure(dense_residual_fig)
    assert np.isfinite(metrics_fig.data[0].y[0])
    assert sign_fig.data[0].type == "heatmap"
    assert sign_fig.data[0].showscale is False
    assert sign_fig.data[-1].type == "table"
    assert sign_fig.layout.showlegend is True
    assert sign_data.deadband == pytest.approx(0.02)
    assert sign_data.status_frame.equals(sign_result.status_frame)
    assert sign_data.metrics[0]["Channel"] == "A"
    assert metrics_fig.layout.legend.orientation == "v"
    assert metrics_fig.layout.legend.x == pytest.approx(1.02)
    assert metrics_fig.layout.legend.maxheight == pytest.approx(0.92)
    assert metrics_fig.layout.margin.r >= 240
    assert metrics_fig.layout.hovermode == "x unified"
    assert metrics_fig.layout.hoverlabel.bgcolor == "rgba(255, 255, 255, 0.78)"
    assert metrics_fig.data[0].hovertemplate is None
    assert we_davis_metrics_fig.layout.hovermode == "closest"
    assert we_davis_metrics_fig.layout.hoverlabel.bgcolor == "rgba(240, 240, 240, 0.9)"
    assert we_davis_metrics_fig.layout.hoverlabel.font.size == 15
    assert (
        we_davis_metrics_fig.data[0].hovertemplate
        == "%{fullData.name}<br>Channel: %{x}<br>Metric Value: %{y:.3f}<extra></extra>"
    )
    assert next_hover_annotation_style(DEFAULT_HOVER_ANNOTATION_STYLE) == WE_DAVIS_HOVER_ANNOTATION_STYLE
    assert next_hover_annotation_style(WE_DAVIS_HOVER_ANNOTATION_STYLE) == DEFAULT_HOVER_ANNOTATION_STYLE

    top_left_fig = build_metrics_figure(metrics, "Reference", "Candidate", legend_position="top left")
    assert top_left_fig.layout.legend.x == pytest.approx(0.01)
    assert top_left_fig.layout.legend.y == pytest.approx(0.99)
    assert top_left_fig.layout.margin.r < metrics_fig.layout.margin.r
    assert next_legend_position("bottom left") == "default"


def test_certification_ranking_figure_declutters_dense_channels() -> None:
    metrics = []
    for index in range(108):
        channel = f"SG{index:03d}"
        rejected = index % 17 == 0
        metrics.append(
            {
                "Channel": channel,
                "Certification Eligible": "No" if rejected else "Yes",
                "Exclusion Reason": "Peak error > 25%" if rejected else "Eligible",
                "Peak Strain Test": float(index + 1),
                "Peak Strain FEA": float(index + 1) * (1.4 if rejected else 1.02),
                "Peak Error (%)": 40.0 if rejected else float(index % 20),
                "Envelope NMAE (%)": 30.0 if rejected else float(index % 18),
                "Certification Score": 35.0 if rejected else 95.0 - float(index % 40),
                "Evidence Grade": "Reject" if rejected else ("B" if index % 13 == 0 else "A"),
                "Data Quality Warnings": 1.0 if index % 13 == 0 else 0.0,
            }
        )

    figure = build_certification_ranking_figure(
        metrics,
        "Reference",
        "Candidate",
        highlighted_channels=("SG050",),
        label_mode="auto",
        max_labels=12,
    )
    peak_trace = next(trace for trace in figure.data if trace.name == "Peak parity")
    error_trace = next(trace for trace in figure.data if trace.name == "Error screen")

    assert len(peak_trace.x) == 108
    assert len(error_trace.x) == 108
    assert sum(1 for label in peak_trace.text if label) <= 12
    assert "SG050" in peak_trace.text
    assert max(peak_trace.marker.line.width) > min(peak_trace.marker.line.width)
    assert any("Channels: 108" in annotation.text for annotation in figure.layout.annotations)
    assert any(shape.fillcolor == "#3a8f5a" for shape in figure.layout.shapes)
    # A labeling mode also renders the grade letters on the evidence bars.
    assert figure.data[0].type == "bar"
    assert figure.data[0].textposition == "auto"

    selected_only = build_certification_ranking_figure(
        metrics,
        "Reference",
        "Candidate",
        highlighted_channels=("SG050", "SG051"),
        label_mode="selected",
        max_labels=12,
    )
    selected_peak = next(trace for trace in selected_only.data if trace.name == "Peak parity")
    assert {label for label in selected_peak.text if label} == {"SG050", "SG051"}

    no_labels = build_certification_ranking_figure(metrics, "Reference", "Candidate", label_mode="none")
    assert next(trace for trace in no_labels.data if trace.name == "Peak parity").mode == "markers"
    assert next(trace for trace in no_labels.data if trace.name == "Error screen").mode == "markers"
    # "No labels" (the default) hides the permanent grade letters on the evidence bars so the
    # figure is fully hover-only, while keeping the grade in the trace data for the tooltip.
    no_label_bar = no_labels.data[0]
    assert no_label_bar.type == "bar"
    assert no_label_bar.textposition == "none"
    assert any(no_label_bar.text)

    # The figure default is hover-only as well, so a bare call mirrors label_mode="none".
    default_fig = build_certification_ranking_figure(metrics, "Reference", "Candidate")
    assert default_fig.data[0].textposition == "none"
    assert next(trace for trace in default_fig.data if trace.name == "Peak parity").mode == "markers"


def test_overlay_figure_filters_requested_channels() -> None:
    reference = pd.DataFrame({"Time": [0.0, 1.0], "A": [1.0, 2.0], "B": [3.0, 4.0]})
    target = pd.DataFrame({"Time": [0.0, 1.0], "A": [1.1, 2.1], "B": [3.1, 4.1]})
    scaled_only, offset_only, scaled_offset = build_overlay_transforms(reference, target)

    figure = build_overlay_figure(
        reference,
        target,
        scaled_only,
        offset_only,
        scaled_offset,
        "Reference",
        "Candidate",
        channels=("B",),
    )
    assert [trace.name for trace in figure.data] == [
        "Reference - B",
        "Candidate Original - B",
        "Candidate Scaled - B",
        "Candidate Offset - B",
        "Candidate Scaled + Offset - B",
    ]
    assert {trace.type for trace in figure.data} == {"scatter"}
    assert all(trace.visible is not False for trace in figure.data)
    assert [trace.meta["overlay_channel"] for trace in figure.data] == ["B"] * 5

    hidden_figure = build_overlay_figure(
        reference,
        target,
        scaled_only,
        offset_only,
        scaled_offset,
        "Reference",
        "Candidate",
        hide_transforms=True,
        channels=(),
    )
    assert len(hidden_figure.data) == 0
    np.testing.assert_allclose(figure.data[0].y, [3.0, 4.0])
    np.testing.assert_allclose(figure.data[1].y, [3.1, 4.1])


def test_overlay_figure_uses_direct_resampler_for_dense_overlay(monkeypatch) -> None:
    samples = np.arange(DEFAULT_RESAMPLER_SAMPLES * 3, dtype=float)
    reference = pd.DataFrame(
        {
            "Time": samples,
            "A": np.sin(samples / 10.0),
            "B": np.cos(samples / 12.0),
        }
    )
    target = pd.DataFrame(
        {
            "Time": samples,
            "A": np.sin(samples / 10.0) + 0.25,
            "B": np.cos(samples / 12.0) - 0.1,
        }
    )
    scaled_only, offset_only, scaled_offset = build_overlay_transforms(reference, target)
    monkeypatch.setattr(plots_module, "_as_resampled_figure", lambda _figure: pytest.fail("dense overlay should register hf data directly"))

    figure = build_overlay_figure(
        reference,
        target,
        scaled_only,
        offset_only,
        scaled_offset,
        "Reference",
        "Candidate",
        channels=("B",),
    )

    assert {trace.type for trace in figure.data} == {"scattergl"}
    assert is_resampled_figure(figure)
    assert len(figure.data) == 5
    assert len(getattr(figure, "_hf_data", {})) == 5
    assert [trace.meta["overlay_channel"] for trace in figure.data] == ["B"] * 5


def test_overlay_figure_with_non_monotonic_time_uses_plain_figure() -> None:
    samples = np.arange(DEFAULT_RESAMPLER_SAMPLES + 1, dtype=float)
    samples[-1] = 1.0
    reference = pd.DataFrame({"Time": samples, "A": np.sin(samples / 10.0)})
    target = pd.DataFrame({"Time": samples, "A": np.sin(samples / 10.0) + 0.25})
    scaled_only, offset_only, scaled_offset = build_overlay_transforms(reference, target)

    figure = build_overlay_figure(reference, target, scaled_only, offset_only, scaled_offset, "Reference", "Candidate")

    assert not is_resampled_figure(figure)
    assert len(figure.data) == 5
    assert len(figure.data[0].x) == len(samples)


def test_sign_agreement_figure_heatmap_orientation_and_customdata() -> None:
    status_frame = pd.DataFrame(
        {
            "Time": [0.0, 1.0, 2.0],
            "A": [1, 0, -1],
            "B": [-1, 1, 0],
        }
    )
    metrics = [
        {
            "Channel": "A",
            "Sign Agreement (%)": 80.0,
            "Sign Mismatch (%)": 10.0,
            "Sign Deadband (%)": 10.0,
            "Longest Sign Mismatch (s)": 0.5,
        },
        {
            "Channel": "B",
            "Sign Agreement (%)": 70.0,
            "Sign Mismatch (%)": 20.0,
            "Sign Deadband (%)": 10.0,
            "Longest Sign Mismatch (s)": 1.5,
        },
    ]

    figure = build_sign_agreement_figure(status_frame, metrics, "Reference", "Candidate")
    heatmap = figure.data[0]
    customdata = np.asarray(heatmap.customdata, dtype=object)

    assert np.asarray(heatmap.z).tolist() == [[2, 1, 0], [0, 2, 1]]
    assert customdata.shape == (2, 3, 5)
    assert customdata[0, 0, 0] == "Same sign"
    assert customdata[0, 2, 0] == "Opposite sign"
    assert customdata[1, 2, 0] == "Deadband or zero"
    assert customdata[0, 0, 1] == pytest.approx(80.0)
    assert customdata[1, 0, 4] == pytest.approx(1.5)
    assert "customdata[0]" in heatmap.hovertemplate


def test_residual_figure_tolerance_handles_nan_and_mismatched_reference() -> None:
    residual_frame = pd.DataFrame({"Time": [0.0, 1.0, 2.0], "A": [0.2, 999.0, 0.2]})
    metrics = [
        {
            "Channel": "A",
            "Mean Bias": 0.0,
            "MAE": 0.0,
            "Max Abs Error": 0.0,
            "P95 Abs Error": 0.0,
            "P99 Abs Error": 0.0,
        }
    ]

    mismatched = build_residual_figure(
        residual_frame,
        metrics,
        "Reference",
        "Candidate",
        reference_frame=pd.DataFrame({"Time": [0.0, 1.0], "A": [1.0, 1.0]}),
        absolute_tolerance=0.5,
    )
    with_nan = build_residual_figure(
        residual_frame,
        metrics,
        "Reference",
        "Candidate",
        reference_frame=pd.DataFrame({"Time": [0.0, 1.0, 2.0], "A": [1.0, np.nan, 1.0]}),
        absolute_tolerance=0.5,
    )

    assert [trace.name for trace in mismatched.data] == ["A residual"]
    assert [trace.name for trace in with_nan.data] == [
        "A residual",
        "A upper tolerance",
        "A lower tolerance",
        "A outside tolerance",
    ]
    assert np.isnan(np.asarray(with_nan.data[1].y, dtype=float)[1])
    assert len(with_nan.data[-1].x) == 0


def test_local_resampler_dash_host_serves_without_external_assets() -> None:
    samples = np.arange(DEFAULT_RESAMPLER_SAMPLES + 1, dtype=float)
    reference = pd.DataFrame({"Time": samples, "A": np.sin(samples / 10.0)})
    target = pd.DataFrame({"Time": samples, "A": np.sin(samples / 10.0) + 0.25})
    scaled_only, offset_only, scaled_offset = build_overlay_transforms(reference, target)
    figure = build_overlay_figure(reference, target, scaled_only, offset_only, scaled_offset, "Reference", "Candidate")
    assert is_resampled_figure(figure)

    host = LocalResamplerDashHost()
    try:
        url = host.set_figure(figure)
        assert url.startswith("http://127.0.0.1:")
        page_html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8", errors="replace")
        host.set_trace_visibility(tuple(False for _trace in figure.data))
        assert all(trace.visible is False for trace in figure.data)
        second_url = host.set_figure(figure)
        assert second_url != url
    finally:
        host.stop()

    assert "Sensor Data Plot" in page_html
    assert "https://" not in page_html
    assert "cdn" not in page_html.lower()


def test_dense_calibration_scatter_skips_time_series_resampler() -> None:
    samples = np.arange(DEFAULT_RESAMPLER_SAMPLES + 1, dtype=float)
    reference = pd.DataFrame({"Time": samples, "A": np.sin(samples / 10.0)})
    target = pd.DataFrame({"Time": samples, "A": reference["A"] * 1.02 + 0.1})
    calibration = calculate_calibration_diagnostics(reference, target)

    figure = build_calibration_figure(reference, target, calibration.metrics, "Reference", "Candidate")

    # Non-monotonic X bars the time-series resampler; the dense cloud is instead thinned
    # by the calibration decimation cap (an exact subset, envelope preserved).
    assert not is_resampled_figure(figure)
    assert len(samples) > CALIB_SCATTER_POINT_CAP
    assert len(figure.data[0].x) <= CALIB_SCATTER_POINT_CAP
    reference_values = reference["A"].to_numpy()
    cloud_x = np.asarray(figure.data[0].x, dtype=float)
    assert np.isin(cloud_x, reference_values).all()  # only original samples, nothing interpolated
    assert cloud_x.min() == reference_values.min()  # envelope (extent) preserved
    assert cloud_x.max() == reference_values.max()


def test_metric_help_catalog_covers_every_selectable_metric() -> None:
    assert validate_metric_help_catalog(ALL_METRIC_KEYS) == []
    assert set(METRIC_HELP) == set(ALL_METRIC_KEYS)
    assert "Within Tolerance Abs (%)" in METRIC_HELP
    assert "Within Tolerance Rel (%)" in METRIC_HELP
    assert "Robust NMAE (%)" in METRIC_HELP
    assert "Certification Score" in METRIC_HELP

    for metric_key, entry in METRIC_HELP.items():
        html = metric_help_html(metric_key)
        assert entry.key == metric_key
        assert entry.group
        assert entry.fallback
        assert "<h3>Formula</h3>" in html
        assert "<h3>What It Does In Practice</h3>" in html
        assert "<h3>Example Problem</h3>" in html
        assert "<h3>How To Interpret It</h3>" in html
        assert entry.title in html
