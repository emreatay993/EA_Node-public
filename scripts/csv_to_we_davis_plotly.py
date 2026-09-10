"""Convert a time-history CSV into a WE-DAVIS-style offline Plotly HTML file.

Run without arguments to select a CSV with a PyQt file dialog:

    python scripts/csv_to_we_davis_plotly.py

For automation or testing, pass the file path directly:

    python scripts/csv_to_we_davis_plotly.py --csv path/to/data.csv
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


TRACE_OPACITY = 0.75
COMPONENT_COLORS = {
    "fx": "#636EFA",
    "fy": "#EF553B",
    "fz": "#00CC96",
    "mx": "#AB63FA",
    "my": "#FFA15A",
    "mz": "#19D3F3",
}
COORDINATE_GROUPS = {
    "global": {
        "title": "Global coordinates",
        "dash": "solid",
    },
    "local": {
        "title": "Local coordinates",
        "dash": "dash",
    },
}


def _require_pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required. Install it with: python -m pip install pandas") from exc
    return pd


def _require_plotly():
    try:
        import plotly.graph_objects as go
        from plotly.offline import plot as plot_offline
    except ImportError as exc:
        raise RuntimeError("plotly is required. Install it with: python -m pip install plotly") from exc
    return go, plot_offline


def _qt_file_dialog() -> Path | None:
    try:
        from PyQt6.QtWidgets import QApplication, QFileDialog
    except ImportError:
        try:
            from PyQt5.QtWidgets import QApplication, QFileDialog
        except ImportError as exc:
            raise RuntimeError(
                "PyQt6 or PyQt5 is required for the file picker. "
                "Install one of them or run with --csv path/to/file.csv."
            ) from exc

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv[:1])

    file_name, _selected_filter = QFileDialog.getOpenFileName(
        None,
        "Select CSV file",
        str(Path.home()),
        "CSV Files (*.csv);;All Files (*)",
    )

    if owns_app:
        app.quit()

    return Path(file_name) if file_name else None


def _clean_column_name(name: object) -> str:
    return str(name).strip()


def _numeric_series(series: pd.Series) -> pd.Series:
    pd = _require_pandas()
    if series.dtype == object:
        cleaned = series.astype(str).str.strip().str.replace(",", ".", regex=False)
        return pd.to_numeric(cleaned, errors="coerce")
    return pd.to_numeric(series, errors="coerce")


def _read_time_history_csv(csv_path: Path) -> tuple[pd.Series, dict[str, pd.Series], str]:
    pd = _require_pandas()
    df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"CSV has no rows: {csv_path}")

    df.columns = [_clean_column_name(column) for column in df.columns]
    df = df.dropna(axis=1, how="all")
    df = df.loc[:, ~pd.Index(df.columns).str.match(r"^Unnamed", case=False)]
    if df.empty:
        raise ValueError(f"CSV has no usable columns: {csv_path}")

    x_column = "time_s" if "time_s" in df.columns else str(df.columns[0])
    x_values = _numeric_series(df[x_column])
    if not x_values.notna().any():
        raise ValueError(f"X column is not numeric: {x_column}")

    y_series: dict[str, pd.Series] = {}
    for column in df.columns:
        if column == x_column:
            continue
        values = _numeric_series(df[column])
        if values.notna().any():
            y_series[str(column)] = values

    if not y_series:
        raise ValueError("No numeric Y columns were found after the X column.")

    return x_values, y_series, x_column


def _trace_style(column_name: str, seen_groups: set[str]) -> dict[str, object]:
    base_name, separator, suffix = column_name.rpartition("_")
    if not separator or suffix not in COORDINATE_GROUPS or not base_name:
        return {
            "name": column_name,
            "line": dict(dash="solid"),
        }

    group = COORDINATE_GROUPS[suffix]
    line: dict[str, str] = {"dash": str(group["dash"])}
    component_key = base_name.lower()
    if component_key in COMPONENT_COLORS:
        line["color"] = COMPONENT_COLORS[component_key]

    style: dict[str, object] = {
        "name": base_name,
        "line": line,
        "legendgroup": suffix,
        "legendgrouptitle_text": group["title"] if suffix not in seen_groups else None,
        "hover_title": f"{group['title']}<br>{base_name}",
    }
    seen_groups.add(suffix)
    return style


def _hover_template(x_axis_title: str, hover_title: object) -> str:
    x_label = x_axis_title or "X"
    return f"{hover_title}<br>{x_label}: %{{x}}<br>Value: %{{y:.3f}}<extra></extra>"


def _build_figure(csv_path: Path):
    go, _plot_offline = _require_plotly()
    x_values, y_series, x_column = _read_time_history_csv(csv_path)
    fig = go.Figure()
    seen_groups: set[str] = set()

    for name, values in y_series.items():
        valid = x_values.notna() & values.notna()
        if not valid.any():
            continue
        style = _trace_style(name, seen_groups)
        fig.add_trace(
            go.Scatter(
                x=x_values[valid],
                y=values[valid],
                mode="lines",
                name=style["name"],
                hovertemplate=_hover_template(x_column, style.get("hover_title", style["name"])),
                line=style["line"],
                opacity=TRACE_OPACITY,
                legendgroup=style.get("legendgroup"),
                legendgrouptitle_text=style.get("legendgrouptitle_text"),
            )
        )

    if not fig.data:
        raise ValueError("No plottable numeric data remained after filtering blank values.")

    fig.update_layout(
        title=csv_path.stem,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(
            font=dict(family="Open Sans", size=10, color="black"),
            x=1.02,
            y=1,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255, 255, 255, 0.6)",
            groupclick="toggleitem",
            itemclick="toggle",
            itemdoubleclick="toggleothers",
        ),
        hoverlabel=dict(bgcolor="rgba(240, 240, 240, 0.9)", font_size=15),
        hovermode="closest",
        font=dict(family="Open Sans", size=12, color="black"),
        showlegend=True,
        legend_tracegroupgap=12,
        xaxis_title=x_column,
        yaxis_title="Value",
    )
    return fig


def _timestamped_html_path(csv_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = csv_path.with_name(f"{csv_path.stem}_{timestamp}.html")
    counter = 1
    while output_path.exists():
        output_path = csv_path.with_name(f"{csv_path.stem}_{timestamp}_{counter:02d}.html")
        counter += 1
    return output_path


def convert_csv_to_html(csv_path: Path) -> Path:
    _go, plot_offline = _require_plotly()
    csv_path = csv_path.expanduser().resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")

    fig = _build_figure(csv_path)
    output_path = _timestamped_html_path(csv_path)
    plot_offline(
        fig,
        filename=str(output_path),
        auto_open=False,
        include_plotlyjs=True,
        config={"responsive": True},
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a WE-DAVIS-style offline Plotly HTML plot from a CSV file."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="CSV file to convert. If omitted, a PyQt file picker is shown.",
    )
    args = parser.parse_args(argv)

    csv_path = args.csv
    if csv_path is None:
        csv_path = _qt_file_dialog()
        if csv_path is None:
            print("No CSV selected.")
            return 0

    try:
        output_path = convert_csv_to_html(csv_path)
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1

    print(f"Saved Plotly HTML: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
