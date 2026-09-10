"""Self-contained engineering HTML report generation."""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path

import matplotlib.pyplot as plt

from .models import BearingCase, CaseResult


def _figure_base64(draw) -> str:
    fig = plt.figure(figsize=(7.2, 3.8), constrained_layout=True)
    ax = fig.add_subplot(111)
    draw(ax)
    stream = io.BytesIO()
    fig.savefig(stream, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _fmt(value: object) -> str:
    if isinstance(value, float):
        if value == float("inf"):
            return "∞"
        magnitude = abs(value)
        if magnitude != 0 and (magnitude >= 1e6 or magnitude < 1e-3):
            return f"{value:.4e}"
        return f"{value:,.4f}"
    return html.escape(str(value))


def generate_html_report(case: BearingCase, result: CaseResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    convergence = _figure_base64(
        lambda ax: (
            ax.plot([r["iteration"] for r in result.history], [r["temperature_c"] for r in result.history], marker="o", label="Iterated"),
            ax.plot([r["iteration"] for r in result.history], [r["target_temperature_c"] for r in result.history], marker="x", label="Thermal target"),
            ax.set_xlabel("Iteration"),
            ax.set_ylabel("Temperature [°C]"),
            ax.set_title("Coupled thermal convergence"),
            ax.grid(True, alpha=0.25),
            ax.legend(),
        )
    )
    torque = _figure_base64(
        lambda ax: (
            ax.bar(
                ["Rolling", "Sliding", "Seal", "Drag"],
                [
                    result.friction.rolling_torque_nmm,
                    result.friction.sliding_torque_nmm,
                    result.friction.seal_torque_nmm,
                    result.friction.drag_torque_nmm,
                ],
            ),
            ax.set_ylabel("Torque [N mm]"),
            ax.set_title("Friction torque breakdown"),
            ax.grid(True, axis="y", alpha=0.25),
        )
    )
    temperatures = _figure_base64(
        lambda ax: (
            ax.bar(
                ["Inner ring", "Rolling element", "Outer ring", "Oil outlet", "Contact"],
                [
                    result.thermal.inner_ring_temperature_c,
                    result.thermal.rolling_element_temperature_c,
                    result.thermal.outer_ring_temperature_c,
                    result.thermal.oil_outlet_temperature_c,
                    result.thermal.contact_temperature_c,
                ],
            ),
            ax.set_ylabel("Temperature [°C]"),
            ax.set_title("Steady thermal state"),
            ax.grid(True, axis="y", alpha=0.25),
        )
    )

    summary_rows = "".join(
        f"<tr><th>{html.escape(key.replace('_', ' ').title())}</th><td>{_fmt(value)}</td></tr>"
        for key, value in result.summary_dict().items()
    )
    bearing_rows = "".join(
        f"<tr><th>{html.escape(key.replace('_', ' ').title())}</th><td>{_fmt(value)}</td></tr>"
        for key, value in case.to_dict()["bearing"].items()
    )
    operating_rows = "".join(
        f"<tr><th>{html.escape(key.replace('_', ' ').title())}</th><td>{_fmt(value)}</td></tr>"
        for key, value in case.to_dict()["operating"].items()
    )
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in result.warnings) or "<li>None</li>"

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(case.case_name)} — SKF Engineering Bearing Suite</title>
<style>
:root {{ --ink:#172033; --muted:#607086; --line:#d8dee8; --panel:#f6f8fb; --accent:#2457a7; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); font:14px/1.45 'Segoe UI', Arial, sans-serif; background:white; }}
header {{ padding:30px 42px 22px; border-bottom:4px solid var(--accent); }}
h1 {{ margin:0; font-size:27px; font-weight:650; letter-spacing:-.3px; }}
.subtitle {{ margin-top:5px; color:var(--muted); }}
main {{ padding:24px 42px 50px; max-width:1200px; margin:auto; }}
.status {{ display:inline-block; padding:5px 10px; border-radius:4px; background:{'#e7f6ec' if result.converged else '#fff1f0'}; color:{'#176b35' if result.converged else '#a12622'}; font-weight:600; }}
h2 {{ margin:28px 0 12px; font-size:18px; border-bottom:1px solid var(--line); padding-bottom:7px; }}
.grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }}
.card {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:white; break-inside:avoid; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; padding:7px 9px; border-bottom:1px solid #edf0f4; vertical-align:top; }}
th {{ width:52%; color:#475569; font-weight:600; }}
img {{ display:block; width:100%; height:auto; }}
ul {{ margin-top:8px; }}
.note {{ padding:12px 14px; background:var(--panel); border-left:4px solid var(--accent); }}
footer {{ margin-top:36px; padding-top:16px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
@media print {{ main {{ max-width:none; }} .grid {{ gap:10px; }} }}
</style>
</head>
<body>
<header>
<h1>SKF Engineering Bearing Calculation Report</h1>
<div class="subtitle">{html.escape(case.case_name)} · {html.escape(case.bearing.designation)}</div>
</header>
<main>
<p><span class="status">{'CONVERGED' if result.converged else 'NOT CONVERGED'} · {result.iterations} iterations</span></p>
<div class="note"><strong>Model status.</strong> SKF friction, seal and drag equations and ISO 281 rating-life equations are separated from installation and multi-node thermal engineering extensions. This report is not an SKF-certified product selection record.</div>
<h2>Principal results</h2>
<div class="card"><table>{summary_rows}</table></div>
<h2>Charts</h2>
<div class="grid">
<div class="card"><img alt="Convergence" src="data:image/png;base64,{convergence}"></div>
<div class="card"><img alt="Torque breakdown" src="data:image/png;base64,{torque}"></div>
<div class="card"><img alt="Temperature state" src="data:image/png;base64,{temperatures}"></div>
</div>
<h2>Inputs</h2>
<div class="grid">
<div class="card"><h3>Bearing</h3><table>{bearing_rows}</table></div>
<div class="card"><h3>Operating point</h3><table>{operating_rows}</table></div>
</div>
<h2>Warnings and assumptions</h2>
<div class="card"><ul>{warnings}</ul></div>
<footer>Generated by SKF Engineering Bearing Suite 1.0. Verify product dimensions, coefficients, equivalent dynamic load, thermal conductances and calibration data before design release.</footer>
</main>
</body>
</html>"""
    target.write_text(document, encoding="utf-8")
    return target
