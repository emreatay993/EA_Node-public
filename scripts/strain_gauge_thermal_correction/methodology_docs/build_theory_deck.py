# Purpose: Reproducibly build the strain-gauge thermal-correction theory deck (.pptx).
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Generate ``strain_gauge_thermal_correction_methodology_and_theory.pptx``.

House style: navy #1F4E79 / orange #C55A11, 16:9. Equations are rendered to PNGs
via matplotlib mathtext and embedded through the shared
``ea_node_editor.ui.pptx_export.create_project_review_pptx`` helper. Worked-example
and mismatch-trap figures are produced by running the REAL tool functions.

Run::

    python scripts/strain_gauge_thermal_correction/methodology_docs/build_theory_deck.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ea_node_editor.ui.pptx_export import ProjectReviewPptxSlide, create_project_review_pptx  # noqa: E402
from scripts.strain_gauge_thermal_correction import config, core  # noqa: E402

NAVY, ORANGE, RED, GREEN = "#1F4E79", "#C55A11", "#b3261e", "#2e7d32"
FOOTER = "COREX · Strain-Gauge Thermal Correction · BAB350 (STC 16, copper) on titanium"
DECK_NAME = "strain_gauge_thermal_correction_methodology_and_theory.pptx"


def _equation_png(lines: list[str], path: Path, *, fontsize: int = 26) -> Path:
    fig = plt.figure(figsize=(11.5, 0.95 * len(lines) + 0.5))
    for i, line in enumerate(lines):
        y = 1.0 - (i + 0.65) / (len(lines) + 0.3)
        fig.text(0.04, y, line, fontsize=fontsize, color=NAVY, va="center")
    fig.savefig(path, dpi=160, transparent=True, bbox_inches="tight")
    plt.close(fig)
    return path


def _workflow_png(path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    ax.axis("off")
    boxes = [
        ("Measured strain\n(Time × channels)", NAVY),
        ("− apparent(T)\ncurve + mismatch", ORANGE),
        ("× F_ref/F(T)\ngauge factor", ORANGE),
        ("Mechanical strain\n(corrected CSV)", GREEN),
        ("FE elastic strain\nSensor Comparison", NAVY),
    ]
    x = 0.02
    w, h, gap = 0.175, 0.42, 0.025
    for i, (label, color) in enumerate(boxes):
        ax.add_patch(mpatches.FancyBboxPatch((x, 0.3), w, h, boxstyle="round,pad=0.012",
                                             linewidth=2, edgecolor=color, facecolor="white"))
        ax.text(x + w / 2, 0.3 + h / 2, label, ha="center", va="center", fontsize=12.5, color=color)
        if i < len(boxes) - 1:
            ax.annotate("", xy=(x + w + gap, 0.51), xytext=(x + w, 0.51),
                        arrowprops=dict(arrowstyle="-|>", color="#444", lw=2))
        x += w + gap
    ax.text(0.5, 0.86, "Temperatures (thermocouple per gauge)  →  apparent strain  →  corrected mechanical strain",
            ha="center", fontsize=12, color="#444")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.savefig(path, dpi=150, transparent=False, bbox_inches="tight")
    plt.close(fig)
    return path


def _scenario():
    t_ref, m_cu, alpha_part, alpha_curve, gf = 20.0, 1.1, 9.0, 16.0, 0.008
    time = np.linspace(0, 100, 240)
    T = t_ref + (170 - t_ref) * np.sin(np.pi * time / time[-1])
    truth = 250 * np.sin(2 * np.pi * time / 30) + 0.8 * time
    eps_app = m_cu * (T - t_ref) + (alpha_part - alpha_curve) * (T - t_ref)
    measured = truth * (1 + gf * (T - t_ref) / 100) + eps_app
    fit = core.load_curve_from_coeffs([m_cu, -m_cu * t_ref], t_min=-20, t_max=260)
    cfg = config.CorrectionConfig(t_ref_celsius=t_ref, mismatch_enabled=True,
                                  alpha_part_ppm=alpha_part, alpha_curve_substrate_ppm=alpha_curve,
                                  gauge_factor_delta_pct=gf)
    return time, T, truth, measured, fit, cfg


def _worked_png(path: Path) -> Path:
    import pandas as pd

    time, T, truth, measured, fit, cfg = _scenario()
    corrected = core.correct_dataset(pd.DataFrame({"Time": time, "SG01": measured}),
                                     pd.DataFrame({"Time": time, "SG01": T}), fit, cfg)[0]["SG01"].to_numpy()
    fig, ax = plt.subplots(figsize=(11.0, 4.6))
    ax.plot(time, measured, color=NAVY, lw=1.2, label="measured (raw, thermally contaminated)")
    ax.plot(time, truth, color=GREEN, lw=2.4, label="true mechanical strain")
    ax.plot(time, corrected, "--", color=ORANGE, lw=1.8, label="recovered (corrected)")
    ax.set(xlabel="time [s]", ylabel="strain [µε]",
           title=f"Ground-truth round trip — recovery error {np.max(np.abs(corrected-truth)):.2f} µε")
    ax.grid(alpha=0.3); ax.legend(loc="upper right", fontsize=10)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _trap_png(path: Path) -> Path:
    import pandas as pd

    time, T, truth, measured, fit, _cfg = _scenario()
    cfg_off = config.CorrectionConfig(t_ref_celsius=20.0, mismatch_enabled=False, gauge_factor_delta_pct=0.008)
    rec_off = core.correct_dataset(pd.DataFrame({"Time": time, "SG01": measured}),
                                   pd.DataFrame({"Time": time, "SG01": T}), fit, cfg_off)[0]["SG01"].to_numpy()
    residual = rec_off - truth
    fig, ax = plt.subplots(figsize=(11.0, 4.6))
    ax.plot(time, residual, color=RED, lw=2.0)
    ax.axhline(0, color="k", lw=0.6)
    ax.set(xlabel="time [s]", ylabel="recovered − true [µε]",
           title=f"Silent trap: omitting the mismatch term leaves {np.max(np.abs(residual)):.0f} µε of error")
    ax.grid(alpha=0.3)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def build() -> Path:
    from PyQt6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    assets = Path(tempfile.mkdtemp(prefix="sgtc_deck_"))
    eq_gov = _equation_png(
        [r"$\varepsilon_{\mathrm{mech}}(t) = \left[\,\varepsilon_{\mathrm{meas}}(t) - \varepsilon_{\mathrm{app}}(T(t))\,\right]\; F_{\mathrm{ref}}/F(T(t))$"],
        assets / "eq_gov.png",
    )
    eq_mis = _equation_png(
        [
            r"$\varepsilon_{\mathrm{app}}(T) = \mathrm{curve}(T) + (\alpha_{\mathrm{part}} - \alpha_{\mathrm{curve}})\,(T - T_{\mathrm{ref}})$",
            r"$(\alpha_{\mathrm{Ti}} - \alpha_{\mathrm{Cu}}) \approx 9 - 16 = -7\ \mathrm{ppm/^{\circ}C}\;\Rightarrow\; \sim\!-1000\,\mu\varepsilon\ \mathrm{at}\ \Delta T = 150^{\circ}\mathrm{C}$",
        ],
        assets / "eq_mis.png",
        fontsize=22,
    )
    eq_gf = _equation_png(
        [r"$F(T) = F_{\mathrm{ref}}\left(1 + \Delta F(T)/100\right),\qquad \mathrm{scale} = F_{\mathrm{ref}}/F(T)$"],
        assets / "eq_gf.png",
    )
    workflow = _workflow_png(assets / "workflow.png")
    worked = _worked_png(assets / "worked.png")
    trap = _trap_png(assets / "trap.png")

    slides = [
        ProjectReviewPptxSlide(
            title="Thermal Correction of Strain-Gauge Test Data",
            subtitle="Recovering mechanical strain for FE validation — BAB350 (STC 16, copper) on a titanium part",
            body_lines=(
                "Goal: validate engine-test strain gauges against an FE model's elastic strain.",
                "Problem: a heated gauge reads thermal output (apparent strain) even with no load.",
                "Method: subtract apparent(T), rescale for gauge-factor drift, then overlay vs FE.",
                "Key risk resolved: the manufacturer curve is the copper STC reference → mismatch term ON.",
            ),
            footer=FOOTER,
        ),
        ProjectReviewPptxSlide(
            title="The problem — raw strain ≠ mechanical strain",
            body_lines=(
                "Measured = mechanical strain (what FE predicts) + thermal output (apparent strain).",
                "Apparent strain comes from grid resistance drift + differential grid/substrate expansion.",
                "On titanium it can reach ~1000 µε — larger than the strains being validated.",
                "FE gives elastic (mechanical) strain only, so the apparent part must be removed first.",
            ),
            footer=FOOTER,
        ),
        ProjectReviewPptxSlide(title="Governing equation", image_path=eq_gov, footer=FOOTER),
        ProjectReviewPptxSlide(
            title="Self-temperature compensation (the “(16)”)",
            body_lines=(
                "STC number = substrate α the gauge is tuned to null thermal output on.",
                "“(16)” → self-compensated for α ≈ 16 ppm/°C (copper); near-flat curve on copper.",
                "A curve from the gauge maker is that copper-reference curve — NOT your titanium part.",
                "So on titanium the gauge is uncompensated and a large mismatch term appears.",
            ),
            footer=FOOTER,
        ),
        ProjectReviewPptxSlide(title="Substrate α-mismatch term", image_path=eq_mis, footer=FOOTER),
        ProjectReviewPptxSlide(title="Gauge-factor variation with temperature", image_path=eq_gf, footer=FOOTER),
        ProjectReviewPptxSlide(title="Workflow — from measured strain to FE overlay", image_path=workflow, footer=FOOTER),
        ProjectReviewPptxSlide(title="Worked example — recovered ≈ ground truth", image_path=worked, footer=FOOTER),
        ProjectReviewPptxSlide(title="The silent trap — omitting the mismatch term", image_path=trap, footer=FOOTER),
        ProjectReviewPptxSlide(
            title="Diagnostics, assumptions & what to confirm",
            body_lines=(
                "Every run emits diagnostics JSON: fit R²/coeffs, α's, units, per-channel max |apparent|.",
                "Confirm with the gauge maker: curve substrate, exact α_curve, and curve reference temperature.",
                "Use α(T) for the specific Ti alloy; set output units to match SG_FEA_strain_data.csv.",
                "Compare against FE elastic strain projected onto the gauge axis, not total strain.",
            ),
            footer=FOOTER,
        ),
    ]

    deck_path = Path(__file__).resolve().parent / DECK_NAME
    return create_project_review_pptx(slides=slides, output_path=deck_path, slide_size="16:9 landscape")


if __name__ == "__main__":
    print("wrote", build())
