from __future__ import annotations

from pathlib import Path

import numpy as np
import plotly.graph_objects as go


OUTPUT_DIR = Path(__file__).resolve().parent
SCENARIO = "Bladeout_Max_REF_LPT1_CF_1_58"

FILES = {
    "main": f"SG_Calculations__{SCENARIO}__von_Mises_MPa__main.html",
    "compared": f"SG_Calculations__{SCENARIO}__von_Mises_MPa__compared_data.html",
    "overlay": f"SG_Calculations__{SCENARIO}__von_Mises_MPa__main_and_compared_data.html",
    "comparison": f"SG_Calculations__{SCENARIO}__von_Mises_MPa__comparison.html",
    "comparison_percent": f"SG_Calculations__{SCENARIO}__von_Mises_MPa__comparison_percent.html",
    "raw": f"SG_Calculations__{SCENARIO}__Raw_Strain_Data__main.html",
    "mixed": f"SG_Calculations__{SCENARIO}__Mixed_Test_Channels__main_and_compared_data.html",
}


COLORS = [
    "#b13a2f",
    "#2f5aa8",
    "#5f9b3a",
    "#8b5aa1",
    "#8b6a3d",
    "#2f9f9f",
    "#a35f9f",
    "#607d8b",
]


def _bladeout_time() -> np.ndarray:
    return np.arange(0.0, 1200.0 + 25.0, 25.0, dtype=np.float64)


def _stepped_bladeout_profile(
    time_s: np.ndarray,
    *,
    peak: float,
    baseline: float,
    start: float,
    peak_start: float,
    peak_end: float,
    settle_end: float,
    phase: float,
) -> np.ndarray:
    ramp = np.interp(
        time_s,
        [0.0, 95.0, start, peak_start, peak_end, settle_end, 1140.0, 1200.0],
        [0.0, 3.0, 3.0, peak * 0.92, peak, baseline * 1.65, baseline, baseline * 1.08],
    )
    step_height = max(2.0, peak * 0.035)
    staircase = np.floor(np.maximum(time_s - start, 0.0) / 45.0) * step_height
    staircase -= np.floor(np.maximum(time_s - peak_end, 0.0) / 45.0) * step_height * 1.85
    ripple = np.sin(time_s / 25.0 + phase) * peak * 0.012
    early_spike = np.exp(-((time_s - 30.0) / 10.0) ** 2) * peak * 0.06
    profile = ramp + staircase + ripple + early_spike
    return np.maximum(profile, -8.0)


def _stress_channels() -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]]:
    time_s = _bladeout_time()
    peaks = {
        "SG57_von_Mises [MPa]": 210.0,
        "SG58_von_Mises [MPa]": 18.0,
        "SG59_von_Mises [MPa]": 205.0,
        "SG60_von_Mises [MPa]": 78.0,
        "SG61_von_Mises [MPa]": 176.0,
        "SG62_von_Mises [MPa]": 58.0,
    }
    main: dict[str, np.ndarray] = {}
    comp: dict[str, np.ndarray] = {}
    for index, (name, peak) in enumerate(peaks.items()):
        main_series = _stepped_bladeout_profile(
            time_s,
            peak=peak,
            baseline=14.0 + index * 1.8,
            start=120.0 + index * 8.0,
            peak_start=575.0 + index * 12.0,
            peak_end=660.0 + index * 17.0,
            settle_end=1010.0 + index * 12.0,
            phase=index * 0.65,
        )
        scale = 0.96 + index * 0.012
        delay = 12.0 + index * 2.0
        comp_series = np.interp(time_s, time_s + delay, main_series, left=main_series[0], right=main_series[-1])
        comp_series = comp_series * scale + np.sin(time_s / 55.0 + index) * (peak * 0.01)
        main[name] = np.round(main_series, 4)
        comp[name] = np.round(comp_series, 4)
    return time_s, main, comp


def _raw_strain_channels(time_s: np.ndarray) -> dict[str, np.ndarray]:
    _, stress_main, _ = _stress_channels()
    channels: dict[str, np.ndarray] = {}
    for index, name in enumerate(["SG57_1", "SG57_2", "SG58_1", "SG59_1", "SG60_1", "SG61_1"]):
        stress_name = list(stress_main)[index]
        scale = 3.8 + index * 0.35
        channels[name] = np.round(stress_main[stress_name] * scale - 22.0 + index * 7.0, 4)
    return channels


def _mixed_channels(time_s: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    _, stress_main, stress_comp = _stress_channels()
    pulse = _stepped_bladeout_profile(
        time_s,
        peak=1.0,
        baseline=0.08,
        start=125.0,
        peak_start=560.0,
        peak_end=670.0,
        settle_end=1040.0,
        phase=1.4,
    )
    main = {
        "Accel_X [g]": np.round(0.08 + pulse * 4.6 + np.sin(time_s / 18.0) * 0.35, 5),
        "Accel_Z [g]": np.round(-0.04 + pulse * 6.2 + np.cos(time_s / 21.0) * 0.28, 5),
        "LVDT_Stroke [mm]": np.round(pulse * 18.0 + np.sin(time_s / 140.0) * 0.6, 5),
        "LVDT_Case_Y [mm]": np.round(pulse * 9.0 + np.cos(time_s / 120.0) * 0.35, 5),
        "SG57_1": _raw_strain_channels(time_s)["SG57_1"],
        "SG57_epsilon_x [ue]": np.round(stress_main["SG57_von_Mises [MPa]"] * 4.4, 5),
        "SG57_von_Mises [MPa]": stress_main["SG57_von_Mises [MPa]"],
    }
    comp = {
        "Accel_X [g]": np.round(main["Accel_X [g]"] * 0.965 + 0.08, 5),
        "Accel_Z [g]": np.round(main["Accel_Z [g]"] * 1.035 - 0.05, 5),
        "LVDT_Stroke [mm]": np.round(main["LVDT_Stroke [mm]"] * 0.955 + 0.35, 5),
        "LVDT_Case_Y [mm]": np.round(main["LVDT_Case_Y [mm]"] * 1.04 - 0.12, 5),
        "SG57_1": np.round(main["SG57_1"] * 0.982 + 3.0, 5),
        "SG57_epsilon_x [ue]": np.round(main["SG57_epsilon_x [ue]"] * 0.975 + 5.0, 5),
        "SG57_von_Mises [MPa]": stress_comp["SG57_von_Mises [MPa]"],
    }
    return main, comp


def _base_figure(title: str, y_title: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title_text=title,
        title_x=0.45,
        title_y=0.95,
        legend_title_text="Result",
        template="plotly_white",
        plot_bgcolor="rgba(0,0,0,0.005)",
        xaxis_title="Time [s]",
        yaxis_title=y_title,
        font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
        xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2, nticks=30),
        yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True, nticks=30),
        hovermode="closest",
        margin=dict(t=55, r=260, b=55, l=75),
        legend=dict(x=1.02, y=1.0),
    )
    return figure


def _add_trace(
    figure: go.Figure,
    time_s: np.ndarray,
    y_values: np.ndarray,
    *,
    name: str,
    color: str,
    dash: str | None = None,
) -> None:
    figure.add_trace(
        go.Scattergl(
            x=time_s,
            y=y_values,
            name=name,
            mode="lines",
            line=dict(color=color, dash=dash) if dash else dict(color=color),
            hovertemplate="%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.2f}<extra></extra>",
            hoverlabel=dict(font_size=14, bgcolor="rgba(255, 255, 255, 0.5)"),
            meta=name,
        )
    )


def _write_figure(
    figure: go.Figure,
    filename: str,
    *,
    output_dir: Path,
    include_plotlyjs: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    figure.write_html(output_path, include_plotlyjs=include_plotlyjs, full_html=True, auto_open=False)
    text = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        "\n".join(line.rstrip() for line in text.splitlines()) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path


def _write_stress_variants(*, output_dir: Path, include_plotlyjs: bool) -> dict[str, Path]:
    time_s, main, comp = _stress_channels()
    title = f"SG Calculations : {SCENARIO.replace('_', ' ')} (von_Mises [MPa])"

    main_fig = _base_figure(title, "Data")
    comp_fig = _base_figure(f"Compared Data : {SCENARIO.replace('_', ' ')} (von_Mises [MPa])", "Data")
    overlay_fig = _base_figure(
        f"Overlay Plot : {SCENARIO.replace('_', ' ')} (FEA vs Test Data) (von_Mises [MPa])",
        "Data",
    )
    comparison_fig = _base_figure(f"Comparison : {SCENARIO.replace('_', ' ')} (von_Mises [MPa])", "Data")
    percent_fig = _base_figure(f"Comparison Percent : {SCENARIO.replace('_', ' ')} (von_Mises [MPa])", "Data [%]")

    for index, name in enumerate(main):
        color = COLORS[index % len(COLORS)]
        _add_trace(main_fig, time_s, main[name], name=name, color=color)
        _add_trace(comp_fig, time_s, comp[name], name=f"*{name}", color=color)
        _add_trace(overlay_fig, time_s, main[name], name=f"Main: {name}", color=color)
        _add_trace(overlay_fig, time_s, comp[name], name=f"Comp: {name}", color=color, dash="dash")
        delta = np.round(main[name] - comp[name], 5)
        percent = np.round(((main[name] / np.maximum(comp[name], 1e-6)) - 1.0) * 100.0, 5)
        _add_trace(comparison_fig, time_s, delta, name=f"Delta{name}", color=color)
        _add_trace(percent_fig, time_s, percent, name=f"%{name}", color=color)

    return {
        "main": _write_figure(main_fig, FILES["main"], output_dir=output_dir, include_plotlyjs=include_plotlyjs),
        "compared": _write_figure(
            comp_fig, FILES["compared"], output_dir=output_dir, include_plotlyjs=include_plotlyjs
        ),
        "overlay": _write_figure(
            overlay_fig, FILES["overlay"], output_dir=output_dir, include_plotlyjs=include_plotlyjs
        ),
        "comparison": _write_figure(
            comparison_fig, FILES["comparison"], output_dir=output_dir, include_plotlyjs=include_plotlyjs
        ),
        "comparison_percent": _write_figure(
            percent_fig,
            FILES["comparison_percent"],
            output_dir=output_dir,
            include_plotlyjs=include_plotlyjs,
        ),
    }


def _write_raw_strain_variant(*, output_dir: Path, include_plotlyjs: bool) -> Path:
    time_s = _bladeout_time()
    raw = _raw_strain_channels(time_s)
    figure = _base_figure(f"SG Calculations : {SCENARIO.replace('_', ' ')} (Raw Strain Data)", "Data")
    for index, (name, values) in enumerate(raw.items()):
        _add_trace(figure, time_s, values, name=name, color=COLORS[index % len(COLORS)])
    return _write_figure(figure, FILES["raw"], output_dir=output_dir, include_plotlyjs=include_plotlyjs)


def _write_mixed_variant(*, output_dir: Path, include_plotlyjs: bool) -> Path:
    time_s = _bladeout_time()
    main, comp = _mixed_channels(time_s)
    figure = _base_figure(f"Overlay Plot : {SCENARIO.replace('_', ' ')} (Mixed Test Channels)", "Data")
    for index, name in enumerate(main):
        color = COLORS[index % len(COLORS)]
        _add_trace(figure, time_s, main[name], name=f"Main: {name}", color=color)
        _add_trace(figure, time_s, comp[name], name=f"Comp: {name}", color=color, dash="dash")
    return _write_figure(figure, FILES["mixed"], output_dir=output_dir, include_plotlyjs=include_plotlyjs)


def generate_mock_plotly_html_inputs(
    output_dir: Path = OUTPUT_DIR,
    *,
    include_plotlyjs: bool = True,
) -> dict[str, Path]:
    paths = _write_stress_variants(output_dir=output_dir, include_plotlyjs=include_plotlyjs)
    paths["raw"] = _write_raw_strain_variant(output_dir=output_dir, include_plotlyjs=include_plotlyjs)
    paths["mixed"] = _write_mixed_variant(output_dir=output_dir, include_plotlyjs=include_plotlyjs)
    return paths


def main() -> None:
    paths = generate_mock_plotly_html_inputs()
    for key in FILES:
        print(paths[key])


if __name__ == "__main__":
    main()
