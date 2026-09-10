"""Field-level help for the GUI: what each input does, the equation it feeds and
the published source it comes from.

Every entry is written against the implementation in this package, and every
citation is one of the four sources listed in ``docs/model_traceability.md``.
Inputs that drive an engineering extension rather than a published SKF equation
are tagged with :data:`REF_EXTENSION` so the distinction stays visible in the UI,
exactly as it is in the calculation warnings and the HTML report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- sources

REF_FRICTION = "SKF, <i>The SKF model for calculating the frictional moment</i>"
REF_SELECTION = "SKF rolling-bearing selection principles and rating-life documentation"
REF_ISO281 = "ISO 281:2007, <i>Rolling bearings — Dynamic load ratings and rating life</i>"
REF_ASTM = "ASTM D341, viscosity–temperature equations"
REF_EXTENSION = (
    "Engineering extension — not an SKF catalogue equation. "
    "Calibrate against internal load analysis or test."
)
REF_DIGITIZED = (
    "Digitized from an SKF diagram, not tabular data. "
    "Override it when product-specific values are available."
)
REF_NONE = ""

#: Width, in visible characters, that tooltip prose is wrapped to.
WRAP_WIDTH = 76


@dataclass(frozen=True, slots=True)
class FieldHelp:
    """One field's documentation."""

    title: str
    body: str
    formula: str = ""
    reference: str = REF_NONE


_TAG = re.compile(r"<[^>]+>")


def _visible_length(word: str) -> int:
    """Length of a word ignoring markup, so wrapping measures what is drawn."""
    return len(_TAG.sub("", word))


def wrap_html(text: str, width: int = WRAP_WIDTH) -> str:
    """Word-wrap prose into ``<br>``-separated lines.

    Qt sizes a rich-text tooltip to its longest unbroken line and ignores CSS
    ``width`` on the wrapper, so the wrapping has to be done here to get a
    predictable tooltip shape.
    """
    lines: list[str] = []
    line: list[str] = []
    length = 0
    for word in text.split():
        visible = _visible_length(word)
        if line and length + 1 + visible > width:
            lines.append(" ".join(line))
            line, length = [word], visible
        else:
            length += visible + (1 if line else 0)
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return "<br>".join(lines)


def tooltip_html(help_entry: FieldHelp) -> str:
    """Render one :class:`FieldHelp` as a Qt rich-text tooltip."""
    parts = [
        "<div>",
        f"<b style='color:#0F172A'>{help_entry.title}</b><br>",
        f"<span style='color:#334155'>{wrap_html(help_entry.body)}</span>",
    ]
    if help_entry.formula:
        parts.append(
            "<br><br><span style='color:#1D4ED8'>"
            f"{wrap_html(help_entry.formula, WRAP_WIDTH + 8)}</span>"
        )
    if help_entry.reference:
        parts.append(
            "<br><br><span style='color:#64748B; font-size:8pt'>"
            f"{wrap_html(help_entry.reference)}</span>"
        )
    parts.append("</div>")
    return "".join(parts)


# --------------------------------------------------------------------------- catalogue
#
# Keys are the ``MainWindow`` attribute names of the input widgets.

FIELD_HELP: dict[str, FieldHelp] = {
    # ------------------------------------------------------------- 01 Bearing
    "case_name": FieldHelp(
        "Case name",
        "Free-text label for this calculation. It is stored in the saved case "
        "file and printed in the exported HTML report. It does not affect any "
        "result.",
    ),
    "designation": FieldHelp(
        "Bearing designation",
        "Catalogue designation for the record you are transcribing, for example "
        "6208. It is documentation only: the friction constants are selected by "
        "the family and table series below, not by this string.",
    ),
    "family": FieldHelp(
        "Bearing family",
        "Selects which published SKF load-factor formula is evaluated. Each "
        "family has its own algebraic form for G<sub>rr</sub> and G<sub>sl</sub> "
        "— deep-groove ball, angular contact, self-aligning, cylindrical, "
        "tapered, spherical, CARB and the thrust variants all differ.",
        "M = M<sub>rr</sub> + M<sub>sl</sub> + M<sub>seal</sub> + M<sub>drag</sub>",
        REF_FRICTION,
    ),
    "series": FieldHelp(
        "SKF table series",
        "Selects the table row that supplies the R and S coefficients used in "
        "G<sub>rr</sub> and G<sub>sl</sub>, together with the geometry constants "
        "K<sub>z</sub> and (for roller bearings) K<sub>L</sub> used by the drag "
        "model. Pick the series that matches the catalogue record.",
        "G<sub>rr</sub> = f(R₁, R₂, d<sub>m</sub>, F<sub>r</sub>, F<sub>a</sub>)"
        " · G<sub>sl</sub> = f(S₁, S₂, d<sub>m</sub>, F<sub>r</sub>, F<sub>a</sub>)",
        REF_FRICTION,
    ),
    "quality": FieldHelp(
        "Performance class",
        "Standard leaves the ISO 281 life-modification factor unchanged. SKF "
        "Explorer applies a more favourable effective fatigue-limit axis when "
        "a<sub>SKF</sub> is evaluated, set by the Explorer axis scale on the "
        "Rating Life page.",
        "a<sub>SKF</sub> = f(κ, e<sub>C</sub> · C<sub>u</sub> / P)",
        REF_SELECTION,
    ),
    "d": FieldHelp(
        "Bore diameter d",
        "Bearing bore. With the outside diameter it sets the mean diameter "
        "d<sub>m</sub>, which appears in every friction term, and it also enters "
        "the replenishment factor and the drag geometry factors directly.",
        "d<sub>m</sub> = 0.5 (d + D)",
        REF_FRICTION,
    ),
    "D": FieldHelp(
        "Outside diameter D",
        "Bearing outside diameter. Sets d<sub>m</sub> together with the bore, "
        "drives the (D − d) terms in the drag geometry factors, and selects "
        "the applicable contact-seal table row.",
        "φ<sub>rs</sub> = exp[−K<sub>rs</sub> ν n (d + D) "
        "√(K<sub>z</sub> / (2 (D − d)))]",
        REF_FRICTION,
    ),
    "B": FieldHelp(
        "Width B",
        "Total bearing width. Used by the roller-bearing drag model through the "
        "relative length l<sub>D</sub> and the churning-torque term, and by the "
        "load-zone extension when converting ring tilt into a radial approach.",
        "l<sub>D</sub> = 5 K<sub>L</sub> B / d<sub>m</sub>",
        REF_FRICTION,
    ),
    "d1": FieldHelp(
        "Seal counterface diameter d₁",
        "Seal counterface diameter taken from the catalogue record. It is only "
        "read when the selected contact-seal table row is defined against "
        "d<sub>1</sub> — currently the angular-contact RS1 row. Leave it at "
        "zero for open bearings.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "d2": FieldHelp(
        "Seal counterface diameter d₂",
        "Seal counterface diameter for the table rows defined against "
        "d<sub>2</sub>, which covers the deep-groove RSL, RSH and RS1 seals and "
        "the self-aligning RS1 seal. Leave it at zero for open bearings.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "E": FieldHelp(
        "Raceway diameter E",
        "Outer-raceway diameter from the catalogue record. It is the seal "
        "diameter used by the cylindrical-roller LS seal row. Leave it at zero "
        "unless that row applies.",
        "M<sub>seal</sub> = K<sub>s1</sub> E<sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "element_d": FieldHelp(
        "Rolling-element diameter",
        "Ball or roller diameter. It is not used by the published friction "
        "equations. The oil-jet path uses half of it as the equivalent immersion "
        "depth H when you leave H at zero.",
        "H ≈ 0.5 D<sub>w</sub>  (oil-jet fallback only)",
        REF_FRICTION,
    ),
    "element_count": FieldHelp(
        "Rolling-element count Z",
        "Number of rolling elements per row. It does not enter the SKF friction "
        "equations; it sets the number of contacts in the rolling-element "
        "load-zone solver on the Installation page.",
        "Q<sub>j</sub> = K (δ cosψ<sub>j</sub> − P<sub>d</sub>/2)<sup>p</sup>,"
        " ψ<sub>j</sub> = 2πj / Z",
        REF_EXTENSION,
    ),
    "row_count": FieldHelp(
        "Row count",
        "Number of rolling-element rows. It enters the ball-bearing drag "
        "geometry factor as the row multiplier i<sub>rw</sub>; the larger of this "
        "value and the series-table row count is used.",
        "K<sub>ball</sub> = i<sub>rw</sub> K<sub>z</sub> (d + D) / (D − d) · 10<sup>−12</sup>",
        REF_FRICTION,
    ),
    "C": FieldHelp(
        "Basic dynamic load rating C",
        "Catalogue dynamic load rating. It sets the basic rating life directly. "
        "The exponent p is 3 for ball bearings and 10/3 for roller bearings.",
        "L<sub>10</sub> = (C / P)<sup>p</sup>  ·  "
        "L<sub>10h</sub> = 10<sup>6</sup> L<sub>10</sub> / (60 n)",
        REF_ISO281,
    ),
    "C0": FieldHelp(
        "Basic static load rating C₀",
        "Catalogue static load rating. For deep-groove ball bearings under axial "
        "load it sets the load-dependent contact angle used inside "
        "G<sub>rr</sub> and G<sub>sl</sub>, so it changes friction as well as "
        "static safety.",
        "α = 24.6 (F<sub>a</sub> / C₀)<sup>0.24</sup>  [°]",
        REF_FRICTION,
    ),
    "Cu": FieldHelp(
        "Fatigue load limit C<sub>u</sub>",
        "Load below which fatigue does not occur under clean lubrication. It "
        "enters the life-modification factor through the contamination-scaled "
        "load ratio. For thrust bearings the denominator carries an extra factor "
        "of 3 (ball) or 2.5 (roller).",
        "x = e<sub>C</sub> C<sub>u</sub> / P  →  a<sub>SKF</sub> = f(κ, x)",
        REF_ISO281,
    ),
    "Y": FieldHelp(
        "Axial load factor Y",
        "Tapered-roller axial factor from the catalogue record. It appears "
        "inside the tapered G<sub>rr</sub> and G<sub>sl</sub> forms, and in the "
        "program's default equivalent dynamic load when you leave P at zero.",
        "G<sub>rr</sub> = R₁ d<sub>m</sub><sup>2.38</sup> "
        "(F<sub>r</sub> + R₂ Y F<sub>a</sub>)<sup>0.31</sup>",
        REF_FRICTION,
    ),
    # -------------------------------------------------------- 02 Operating & oil
    "speed": FieldHelp(
        "Rotational speed n",
        "Relative speed between the rings. It is the strongest single variable "
        "in the model: it drives the rolling term, both starvation factors, the "
        "sliding-regime weighting, the drag terms (which go with n<sup>2</sup>) "
        "and the conversion of life from revolutions to hours.",
        "M<sub>rr</sub> = φ<sub>ish</sub> φ<sub>rs</sub> G<sub>rr</sub> "
        "(ν n)<sup>0.6</sup>",
        REF_FRICTION,
    ),
    "Fr": FieldHelp(
        "Radial load F<sub>r</sub>",
        "Radial bearing load at this operating point. It feeds the load factors "
        "G<sub>rr</sub> and G<sub>sl</sub>, and the load-zone solver. If the "
        "installation extension is enabled, the effective radial load is "
        "combined with any radial preload before the friction step.",
        "G<sub>rr</sub>, G<sub>sl</sub> = f(d<sub>m</sub>, F<sub>r</sub>, F<sub>a</sub>)",
        REF_FRICTION,
    ),
    "Fa": FieldHelp(
        "Axial load F<sub>a</sub>",
        "Axial bearing load at this operating point. It enters the family load "
        "factors, sets the deep-groove contact angle through C₀, and is "
        "added to any axial preload when the installation extension is enabled.",
        "G<sub>rr</sub>, G<sub>sl</sub> = f(d<sub>m</sub>, F<sub>r</sub>, F<sub>a</sub>)",
        REF_FRICTION,
    ),
    "P": FieldHelp(
        "Equivalent dynamic load P",
        "Equivalent dynamic bearing load used by the rating-life calculation. "
        "Enter the value computed with the bearing-specific X and Y factors. "
        "Leaving it at zero makes the program substitute a clearly reported "
        "default — F<sub>a</sub> for thrust bearings, F<sub>r</sub> + Y "
        "F<sub>a</sub> for tapered, otherwise √(F<sub>r</sub>² + "
        "F<sub>a</sub>²) — which is not a substitute for the catalogue "
        "method.",
        "L<sub>10</sub> = (C / P)<sup>p</sup>",
        REF_ISO281,
    ),
    "oil_name": FieldHelp(
        "Lubricant name",
        "Free-text label for the oil or grease. Documentation only; it appears "
        "in the saved case and the report.",
    ),
    "nu40": FieldHelp(
        "Kinematic viscosity ν₄₀",
        "Kinematic viscosity at 40 °C from the lubricant data sheet. With "
        "ν₁₀₀ it fixes the two-point viscosity–temperature "
        "fit that the solver iterates on, so it must be greater than "
        "ν₁₀₀.",
        "log₁₀ log₁₀(ν + 0.7) = A − B log₁₀ T",
        REF_ASTM,
    ),
    "nu100": FieldHelp(
        "Kinematic viscosity ν₁₀₀",
        "Kinematic viscosity at 100 °C from the lubricant data sheet. It "
        "sets the slope of the viscosity–temperature fit, which controls how "
        "strongly friction falls as the bearing heats up.",
        "log₁₀ log₁₀(ν + 0.7) = A − B log₁₀ T",
        REF_ASTM,
    ),
    "oil_kind": FieldHelp(
        "Lubricant category",
        "Selects the full-film sliding friction coefficient "
        "μ<sub>EHL</sub> used in the mixed-lubrication blend. Cylindrical "
        "and tapered roller bearings use their own published values instead of "
        "this category.",
        "μ<sub>sl</sub> = φ<sub>bl</sub> μ<sub>bl</sub> + "
        "(1 − φ<sub>bl</sub>) μ<sub>EHL</sub>",
        REF_FRICTION,
    ),
    "density": FieldHelp(
        "Lubricant density ρ",
        "Oil density at operating temperature. It converts the volumetric oil "
        "flow into the mass flow that carries heat out of the bearing, so it "
        "only matters when oil flow is non-zero.",
        "ṁ = Q · 10<sup>−3</sup> / 60 · ρ  [kg/s]",
        REF_EXTENSION,
    ),
    "cp": FieldHelp(
        "Specific heat c<sub>p</sub>",
        "Oil specific heat capacity. With the mass flow it sets the convective "
        "conductance of the oil stream in both thermal models.",
        "G<sub>oil</sub> = ṁ c<sub>p</sub> (1 − bypass)",
        REF_EXTENSION,
    ),
    "ep_additives": FieldHelp(
        "Proven EP additive performance",
        "Tick this only when the additive package has demonstrated its "
        "effectiveness in the actual application. It enables the ISO 281 "
        "treatment that lifts a<sub>SKF</sub> towards the κ = 1 value, "
        "capped at 3, and only when κ &lt; 1 and e<sub>C</sub> ≥ 0.2.",
        "a<sub>SKF</sub> ← min(a<sub>SKF</sub>(κ = 1), 3)",
        REF_ISO281,
    ),
    # ------------------------------------------------ 03 Lubrication, drag, seals
    "lub_mode": FieldHelp(
        "Lubrication mode",
        "Sets the replenishment/starvation constant K<sub>rs</sub> and decides "
        "whether churning drag is evaluated at all. Grease and oil-air return "
        "only the fixed drag torque; oil-jet additionally doubles the drag "
        "result as published.",
        "φ<sub>rs</sub> = exp[−K<sub>rs</sub> ν n (d + D) "
        "√(K<sub>z</sub> / (2 (D − d)))]",
        REF_FRICTION,
    ),
    "oil_level": FieldHelp(
        "Oil immersion depth H",
        "Height of the oil level above the lowest point of the outer-ring "
        "raceway, measured with the bearing at rest. It is normalised by "
        "d<sub>m</sub> to read the drag volume factor, and it sets the immersion "
        "angle and submerged area. For oil-jet it is an equivalent immersion "
        "depth. It is clamped to 1.2 d<sub>m</sub>.",
        "x = H / d<sub>m</sub>  →  V<sub>M</sub>(x)",
        REF_FRICTION,
    ),
    "orientation": FieldHelp(
        "Shaft orientation",
        "Horizontal matches the published drag model directly. Vertical applies "
        "the submerged-width correction below, because the published relation "
        "assumes a horizontal shaft, a large reservoir, a rotating inner ring "
        "and constant speed.",
        reference=REF_FRICTION,
    ),
    "vertical_fraction": FieldHelp(
        "Vertical submerged fraction",
        "Fraction of the bearing width actually submerged on a vertical shaft. "
        "It multiplies the drag torque directly. Use 1.0 for a fully submerged "
        "bearing.",
        "M<sub>drag</sub> ← M<sub>drag</sub> · f<sub>submerged</sub>",
        REF_FRICTION,
    ),
    "drag_enabled": FieldHelp(
        "Evaluate SKF oil drag",
        "Turns the churning/drag model on. With it off, only the fixed drag "
        "torque below is added. Drag is also skipped automatically for grease "
        "and oil-air, and whenever the speed is zero.",
        "M = M<sub>rr</sub> + M<sub>sl</sub> + M<sub>seal</sub> + M<sub>drag</sub>",
        REF_FRICTION,
    ),
    "fixed_drag": FieldHelp(
        "Added fixed drag torque",
        "A constant torque added to the drag component, for losses the model "
        "does not represent — for example a flinger, a labyrinth or a known "
        "measured offset. It is added whether or not the drag model is enabled.",
        "M<sub>drag</sub> ← M<sub>drag,model</sub> + M<sub>fixed</sub>",
        REF_EXTENSION,
    ),
    "vm_override": FieldHelp(
        "Manual V<sub>M</sub> override",
        "Drag volume factor. SKF publishes V<sub>M</sub> as a diagram, so with "
        "this left at zero the program interpolates a digitized curve and says "
        "so in the warnings. Enter a value read from the diagram yourself to "
        "remove that approximation.",
        "M<sub>drag,hydro</sub> ∝ V<sub>M</sub>",
        REF_DIGITIZED,
    ),
    "seal_type": FieldHelp(
        "Seal type",
        "Selects the published contact-seal coefficient row for this family and "
        "outside diameter. Only seal designations that have a table row for the "
        "selected family are offered. Manual lets you enter coefficients "
        "directly.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "seal_count": FieldHelp(
        "Seal count",
        "Number of contact seals. The published relation gives the torque for "
        "two seals, so one seal takes half of it. The deep-groove RSL row with "
        "D &gt; 25 mm is the published exception and is not halved. Zero "
        "disables the seal term.",
        "1 seal: M<sub>seal</sub> = 0.5 · M<sub>seal,2</sub>  (RSL, D &gt; 25 mm excepted)",
        REF_FRICTION,
    ),
    "seal_diameter": FieldHelp(
        "Manual seal counterface diameter",
        "Overrides the seal counterface diameter that the selected table row "
        "would otherwise read from d<sub>1</sub>, d<sub>2</sub> or E. Required "
        "for the Manual seal type. Leave at zero to use the bearing dimensions.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "Ks1": FieldHelp(
        "Manual K<sub>s1</sub>",
        "Seal coefficient used only by the Manual seal type. Take it from "
        "product data for the specific seal; verify it before relying on the "
        "result.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "Ks2": FieldHelp(
        "Manual K<sub>s2</sub>",
        "Constant seal-torque offset used only by the Manual seal type.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    "beta": FieldHelp(
        "Manual exponent β",
        "Diameter exponent used only by the Manual seal type. Published rows use "
        "2.0 or 2.25 depending on family and seal designation.",
        "M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>β</sup> + K<sub>s2</sub>",
        REF_FRICTION,
    ),
    # --------------------------------------------------------- 04 Installation
    "install_enabled": FieldHelp(
        "Enable installation correction",
        "Applies the clearance/preload and misalignment torque multipliers to "
        "the rolling and sliding terms, and adds preload into the effective "
        "loads. These are engineering extensions: SKF's published model assumes "
        "normal operating clearance and aligned rings.",
        "M<sub>rr</sub>, M<sub>sl</sub> ← M · f<sub>clearance</sub> · f<sub>misalign</sub>",
        REF_EXTENSION,
    ),
    "clearance": FieldHelp(
        "Operating clearance",
        "Radial internal clearance under operating conditions, after fits and "
        "thermal effects. A negative value is interpreted as preload and, with a "
        "non-zero clearance stiffness, is converted into an induced radial "
        "preload force.",
        "f<sub>clearance</sub> = 1 + k<sub>c</sub> · max(1 − P<sub>d</sub>/P<sub>d,ref</sub>, 0)²",
        REF_EXTENSION,
    ),
    "reference_clearance": FieldHelp(
        "Reference clearance",
        "Clearance at which no torque penalty is applied — normally the "
        "nominal operating clearance the published model assumes. At or above "
        "this value the clearance multiplier is exactly 1.",
        "tightness = max(1 − P<sub>d</sub> / P<sub>d,ref</sub>, 0)",
        REF_EXTENSION,
    ),
    "radial_preload": FieldHelp(
        "Radial preload",
        "Externally applied radial preload force. It is combined with the "
        "applied radial load as a vector sum to give the effective radial load "
        "used by the friction and load-zone calculations.",
        "F<sub>r,eff</sub> = √(F<sub>r</sub>² + F<sub>preload</sub>²)",
        REF_EXTENSION,
    ),
    "axial_preload": FieldHelp(
        "Axial preload",
        "Externally applied axial preload force, added directly to the applied "
        "axial load before the friction calculation.",
        "F<sub>a,eff</sub> = F<sub>a</sub> + F<sub>a,preload</sub>",
        REF_EXTENSION,
    ),
    "clearance_stiffness": FieldHelp(
        "Clearance stiffness",
        "Radial force generated per micrometre of negative clearance. It "
        "converts interference into an induced radial preload. Leave at zero to "
        "skip that conversion; it should come from an internal load model or "
        "test, not from a catalogue.",
        "F<sub>induced</sub> = k · max(−P<sub>d</sub>, 0)",
        REF_EXTENSION,
    ),
    "clearance_coeff": FieldHelp(
        "Clearance torque coefficient",
        "Strength of the clearance torque penalty. Zero disables it. This is the "
        "coefficient to fit on the Calibration page against measured torque; it "
        "has no published value.",
        "f<sub>clearance</sub> = 1 + k<sub>c</sub> · tightness²",
        REF_EXTENSION,
    ),
    "misalignment": FieldHelp(
        "Ring misalignment",
        "Relative angular misalignment between the rings. It drives the "
        "misalignment torque penalty and, in the load-zone solver, a tilt-induced "
        "radial approach around the circumference.",
        "f<sub>misalign</sub> = 1 + k<sub>m</sub> (θ / θ<sub>perm</sub>)²",
        REF_EXTENSION,
    ),
    "permissible_misalignment": FieldHelp(
        "Permissible misalignment",
        "Misalignment the bearing tolerates, from the catalogue. For "
        "self-aligning types only the excess beyond this value is penalised; for "
        "rigid types the full ratio is used.",
        "self-aligning: θ<sub>eff</sub> = max(θ/θ<sub>perm</sub> − 1, 0)",
        REF_EXTENSION,
    ),
    "misalignment_coeff": FieldHelp(
        "Misalignment torque coefficient",
        "Strength of the misalignment torque penalty. Zero disables it. Fit it "
        "on the Calibration page or from a bearing-specific analysis.",
        "f<sub>misalign</sub> = 1 + k<sub>m</sub> · ratio²",
        REF_EXTENSION,
    ),
    "contact_stiffness": FieldHelp(
        "Contact stiffness K",
        "Load–deflection constant of one rolling-element contact, used by the "
        "load-zone solver. The solver finds the ring displacement at which the "
        "element forces balance the applied radial load.",
        "Q = K δ<sup>p</sup>,  Σ Q<sub>j</sub> cosψ<sub>j</sub> = F<sub>r</sub>",
        REF_EXTENSION,
    ),
    "deflection_exponent": FieldHelp(
        "Load-deflection exponent p",
        "Exponent of the contact load–deflection law. Hertzian theory gives "
        "1.5 for ball (point) contact and about 1.1 for line contact.",
        "Q = K δ<sup>p</sup>",
        REF_EXTENSION,
    ),
    # -------------------------------------------------------- 05 Thermal network
    "thermal_model": FieldHelp(
        "Thermal model",
        "One-node solves a single energy balance for the whole bearing and is "
        "fast and robust. Four-node resolves inner ring, rolling elements, outer "
        "ring and oil, and needs the seven conductances below. Both are "
        "engineering models, not SKF catalogue equations.",
        "one-node: T = (Q + G<sub>h</sub>T<sub>amb</sub> + G<sub>oil</sub>T<sub>in</sub>) "
        "/ (G<sub>h</sub> + G<sub>oil</sub>)",
        REF_EXTENSION,
    ),
    "inlet_temp": FieldHelp(
        "Oil inlet temperature",
        "Temperature of the oil entering the bearing. It is the sink temperature "
        "for the oil-flow conductance in both models, and it sets the oil node "
        "boundary in the four-node network.",
        "Q<sub>oil</sub> = G<sub>oil</sub> (T<sub>oil</sub> − T<sub>in</sub>)",
        REF_EXTENSION,
    ),
    "ambient_temp": FieldHelp(
        "Ambient temperature",
        "Surroundings temperature used by the one-node model as the sink for "
        "the housing conductance. The four-node model uses the housing boundary "
        "temperature instead.",
        "Q<sub>housing</sub> = G<sub>h</sub> (T − T<sub>amb</sub>)",
        REF_EXTENSION,
    ),
    "shaft_temp": FieldHelp(
        "Shaft boundary temperature",
        "Fixed shaft temperature behind the inner-ring-to-shaft conductance. "
        "Four-node model only.",
        "Q<sub>shaft</sub> = G<sub>is</sub> (T<sub>inner</sub> − T<sub>shaft</sub>)",
        REF_EXTENSION,
    ),
    "housing_temp": FieldHelp(
        "Housing boundary temperature",
        "Fixed housing temperature behind the outer-ring-to-housing conductance. "
        "Four-node model only.",
        "Q<sub>housing</sub> = G<sub>oh</sub> (T<sub>outer</sub> − T<sub>housing</sub>)",
        REF_EXTENSION,
    ),
    "oil_flow": FieldHelp(
        "Oil flow rate",
        "Volumetric flow through the bearing. With density and specific heat it "
        "sets the convective conductance of the oil stream, which is usually the "
        "dominant heat path in a circulating system. Zero means no through-flow "
        "cooling.",
        "G<sub>oil</sub> = ṁ c<sub>p</sub> (1 − bypass)",
        REF_EXTENSION,
    ),
    "one_g": FieldHelp(
        "One-node housing conductance",
        "Lumped conductance from the bearing to ambient through the housing, "
        "used only by the one-node model. It is the single calibration knob of "
        "that model and should be fitted to measured temperatures.",
        "T = (Q + G<sub>h</sub>T<sub>amb</sub> + G<sub>oil</sub>T<sub>in</sub>) "
        "/ (G<sub>h</sub> + G<sub>oil</sub>)",
        REF_EXTENSION,
    ),
    "heat_fraction": FieldHelp(
        "Heat fraction modelled",
        "Fraction of the calculated friction power treated as heat entering the "
        "thermal model. Use 1.0 unless a known share is carried away by a path "
        "outside the model.",
        "Q = f<sub>heat</sub> · P<sub>friction</sub>",
        REF_EXTENSION,
    ),
    "relaxation": FieldHelp(
        "Relaxation factor",
        "Under-relaxation of the outer temperature–viscosity loop. Viscosity "
        "falls as temperature rises and friction falls with viscosity, so the "
        "loop can oscillate. Lower values converge more slowly but more safely.",
        "T<sub>k+1</sub> = T<sub>k</sub> + ω (T<sub>target</sub> − T<sub>k</sub>)",
        REF_EXTENSION,
    ),
    "tolerance": FieldHelp(
        "Temperature tolerance",
        "Convergence threshold on the temperature change between successive "
        "outer iterations. The solve stops once the step is smaller than this.",
        "|T<sub>k+1</sub> − T<sub>k</sub>| ≤ tol",
        REF_EXTENSION,
    ),
    "max_iterations": FieldHelp(
        "Maximum iterations",
        "Iteration cap for the coupled temperature–viscosity loop. Reaching "
        "it is reported as a non-converged result rather than an error.",
        reference=REF_EXTENSION,
    ),
    "Gis": FieldHelp(
        "Inner ring → shaft conductance",
        "Thermal conductance from the inner ring into the shaft boundary. It is "
        "installation-specific: it depends on the interference fit, contact area "
        "and shaft geometry.",
        "Q = G<sub>is</sub> (T<sub>inner</sub> − T<sub>shaft</sub>)",
        REF_EXTENSION,
    ),
    "Goh": FieldHelp(
        "Outer ring → housing conductance",
        "Thermal conductance from the outer ring into the housing boundary. "
        "Usually the main solid heat path out of the bearing.",
        "Q = G<sub>oh</sub> (T<sub>outer</sub> − T<sub>housing</sub>)",
        REF_EXTENSION,
    ),
    "Gie": FieldHelp(
        "Inner ring ↔ elements conductance",
        "Conductance between the inner raceway and the rolling elements, across "
        "the contacts and the film.",
        "Q = G<sub>ie</sub> (T<sub>inner</sub> − T<sub>element</sub>)",
        REF_EXTENSION,
    ),
    "Goe": FieldHelp(
        "Outer ring ↔ elements conductance",
        "Conductance between the outer raceway and the rolling elements.",
        "Q = G<sub>oe</sub> (T<sub>outer</sub> − T<sub>element</sub>)",
        REF_EXTENSION,
    ),
    "Gio": FieldHelp(
        "Inner ring ↔ oil conductance",
        "Convective conductance between the inner ring and the lubricant node.",
        "Q = G<sub>io</sub> (T<sub>inner</sub> − T<sub>oil</sub>)",
        REF_EXTENSION,
    ),
    "Goo": FieldHelp(
        "Outer ring ↔ oil conductance",
        "Convective conductance between the outer ring and the lubricant node.",
        "Q = G<sub>oo</sub> (T<sub>outer</sub> − T<sub>oil</sub>)",
        REF_EXTENSION,
    ),
    "Geo": FieldHelp(
        "Elements ↔ oil conductance",
        "Convective conductance between the rolling elements and the lubricant "
        "node.",
        "Q = G<sub>eo</sub> (T<sub>element</sub> − T<sub>oil</sub>)",
        REF_EXTENSION,
    ),
    "bypass": FieldHelp(
        "Oil bypass fraction",
        "Fraction of the supplied oil that passes the bearing without picking up "
        "heat. It reduces the effective oil conductance, so raising it raises "
        "the solved temperature.",
        "G<sub>oil</sub> = ṁ c<sub>p</sub> (1 − bypass)",
        REF_EXTENSION,
    ),
    "q_element": FieldHelp(
        "Element heat share",
        "Share of the rolling plus sliding heat deposited in the rolling "
        "elements. This share and the two race shares are normalised to sum to "
        "one, so only their ratio matters.",
        "Q<sub>element</sub> = share · (P<sub>rr</sub> + P<sub>sl</sub>)",
        REF_EXTENSION,
    ),
    "q_inner": FieldHelp(
        "Inner-race heat share",
        "Share of the rolling plus sliding heat deposited at the inner raceway. "
        "Normalised together with the element and outer shares.",
        "Q<sub>inner</sub> = share · (P<sub>rr</sub> + P<sub>sl</sub>)",
        REF_EXTENSION,
    ),
    "q_outer": FieldHelp(
        "Outer-race heat share",
        "Share of the rolling plus sliding heat deposited at the outer raceway. "
        "Normalised together with the element and inner shares.",
        "Q<sub>outer</sub> = share · (P<sub>rr</sub> + P<sub>sl</sub>)",
        REF_EXTENSION,
    ),
    "seal_outer": FieldHelp(
        "Seal heat to outer ring",
        "Fraction of the seal friction power deposited on the outer ring; the "
        "remainder goes to the inner ring. Seals normally rub on the outer-ring "
        "counterface, so the default is high.",
        "Q<sub>outer</sub> += f · P<sub>seal</sub>,  Q<sub>inner</sub> += (1 − f) P<sub>seal</sub>",
        REF_EXTENSION,
    ),
    "drag_oil": FieldHelp(
        "Drag heat to oil",
        "Fraction of the churning/drag power deposited directly in the "
        "lubricant; the remainder goes to the rolling elements. Drag is a bulk "
        "fluid loss, so the default is high.",
        "Q<sub>oil</sub> += f · P<sub>drag</sub>,  Q<sub>element</sub> += (1 − f) P<sub>drag</sub>",
        REF_EXTENSION,
    ),
    "rth_inner": FieldHelp(
        "Inner contact thermal resistance",
        "Local constriction/flash resistance at the inner contact. It raises the "
        "reported contact temperature above the mean of the inner-ring and "
        "element node temperatures, and that contact temperature is what the "
        "viscosity loop iterates on.",
        "T<sub>c,i</sub> = ½(T<sub>inner</sub> + T<sub>element</sub>) + Q<sub>i</sub> R<sub>th,i</sub>",
        REF_EXTENSION,
    ),
    "rth_outer": FieldHelp(
        "Outer contact thermal resistance",
        "Local constriction/flash resistance at the outer contact, used the same "
        "way as the inner value. The reported contact temperature is the mean of "
        "the two.",
        "T<sub>c,o</sub> = ½(T<sub>outer</sub> + T<sub>element</sub>) + Q<sub>o</sub> R<sub>th,o</sub>",
        REF_EXTENSION,
    ),
    # ----------------------------------------------------------- 06 Rating life
    "life_enabled": FieldHelp(
        "Calculate rating life",
        "Runs the basic and modified rating-life calculation after the friction "
        "and thermal solution, using the converged operating viscosity.",
        "L<sub>nm</sub> = a₁ a<sub>SKF</sub> L<sub>10</sub>",
        REF_ISO281,
    ),
    "reliability": FieldHelp(
        "Reliability",
        "Survival probability the modified life is quoted at. 90 % gives "
        "a₁ = 1 and L<sub>10</sub>. Higher reliability reduces a₁ and so "
        "shortens the quoted life; values between the tabulated points are "
        "interpolated.",
        "L<sub>nm</sub> = a₁ a<sub>SKF</sub> L<sub>10</sub>",
        REF_ISO281,
    ),
    "contamination_preset": FieldHelp(
        "Cleanliness preset",
        "Convenience selector that writes a typical contamination factor into "
        "the field below. The presets are indicative; for release work use a "
        "value justified by the actual filtration and cleanliness level.",
        reference=REF_ISO281,
    ),
    "ec": FieldHelp(
        "Contamination factor e<sub>C</sub>",
        "Lubricant cleanliness factor, from 0 for heavy contamination to 1 for "
        "extreme cleanliness. It scales the fatigue load limit in the "
        "life-modification factor, so it has a strong effect on modified life.",
        "x = e<sub>C</sub> C<sub>u</sub> / P  →  a<sub>SKF</sub> = f(κ, x)",
        REF_ISO281,
    ),
    "explorer_scale": FieldHelp(
        "SKF Explorer axis scale",
        "Multiplier on the effective fatigue-limit axis when the performance "
        "class is SKF Explorer. SKF publishes the Explorer improvement as a more "
        "favourable diagram rather than one universal multiplier, so leaving "
        "this at zero uses a flagged default of 1.20 for ball and 1.44 for roller "
        "bearings. Replace it with a product-specific calibrated value where you "
        "have one.",
        "a<sub>SKF</sub> = f(κ, x · scale)",
        REF_SELECTION,
    ),
}


# --------------------------------------------------------------- non-field help

#: Help for labelled controls that are not form fields, keyed by an explicit id.
CONTROL_HELP: dict[str, FieldHelp] = {
    "batch_path": FieldHelp(
        "Batch input CSV",
        "Each row overrides fields of the current base case, so only the columns "
        "you vary need to be present. Use it for speed/load maps, duty cycles, "
        "sensitivity studies and design-of-experiments tables. Create template "
        "writes a file with the accepted column names.",
    ),
    "batch_backend": FieldHelp(
        "Batch backend",
        "The full engineering solver runs the complete coupled friction, thermal "
        "and life model for every row. The Numba fast path solves a one-node "
        "deep-groove ball case only, and trades model scope for throughput.",
    ),
    "batch_workers": FieldHelp(
        "Worker processes",
        "Number of parallel processes used by the full solver. More processes "
        "help on large tables; the fast path is already vectorised and gains "
        "little.",
    ),
    "cal_path": FieldHelp(
        "Calibration CSV",
        "Measured torque and/or temperature reference points, or points exported "
        "by hand from SKF Bearing Select. Each row supplies an operating point "
        "and the measured value to fit against.",
    ),
    "cal_checks": FieldHelp(
        "Fitted scale parameters",
        "Which multiplicative scale factors the least-squares fit is free to "
        "adjust. Fitting fewer parameters against few reference points gives a "
        "better-conditioned result; every fitted scale is a departure from the "
        "published model and is stored with the case.",
        reference=REF_EXTENSION,
    ),
}


# --------------------------------------------------------------- methodology

def methodology_html(version: str) -> str:
    """Full methodology reference shown by Help ▸ Methodology / About.

    Mirrors ``docs/model_traceability.md``: published equations first, then the
    engineering extensions, then the sources.
    """
    return f"""
<h2 style="margin-bottom:2px">SKF Engineering Bearing Suite</h2>
<p style="color:#475569; margin-top:0">Version {version} · engineering prototype</p>

<h3>How a case is solved</h3>
<p>The friction and thermal models are coupled through viscosity. Each outer
iteration evaluates viscosity at the current contact temperature, calculates the
friction torque and power, solves the thermal model for a new contact
temperature, and under-relaxes towards it until the temperature step falls below
the tolerance. Rating life is calculated afterwards from the converged
viscosity.</p>

<h3>1 · Total frictional moment</h3>
<p><code>M = M<sub>rr</sub> + M<sub>sl</sub> + M<sub>seal</sub> +
M<sub>drag</sub></code></p>

<p><b>Rolling</b><br>
<code>M<sub>rr</sub> = &#966;<sub>ish</sub> &#966;<sub>rs</sub> G<sub>rr</sub>
(&#957; n)<sup>0.6</sup></code><br>
<code>&#966;<sub>ish</sub> = 1 / [1 + 1.84&#215;10<sup>&#8722;9</sup>
(n d<sub>m</sub>)<sup>1.28</sup> &#957;<sup>0.64</sup>]</code><br>
<code>&#966;<sub>rs</sub> = exp[&#8722;K<sub>rs</sub> &#957; n (d + D)
&#8730;(K<sub>z</sub> / (2(D &#8722; d)))]</code></p>

<p><b>Sliding</b><br>
<code>M<sub>sl</sub> = G<sub>sl</sub> &#956;<sub>sl</sub></code><br>
<code>&#956;<sub>sl</sub> = &#966;<sub>bl</sub> &#956;<sub>bl</sub> +
(1 &#8722; &#966;<sub>bl</sub>) &#956;<sub>EHL</sub></code><br>
<code>&#966;<sub>bl</sub> = exp[&#8722;2.6&#215;10<sup>&#8722;8</sup>
(n &#957;)<sup>1.4</sup> d<sub>m</sub>]</code></p>

<p><b>Seals</b><br>
<code>M<sub>seal</sub> = K<sub>s1</sub> d<sub>s</sub><sup>&#946;</sup> +
K<sub>s2</sub></code> — the published relation represents two seals; one seal
takes half, with the deep-groove RSL row above 25&nbsp;mm as the published
exception.</p>

<p><b>Drag</b> — ball and roller forms with the geometry factors
K<sub>ball</sub>/K<sub>roll</sub>, C<sub>w</sub>, l<sub>D</sub>, f<sub>t</sub>,
R<sub>s</sub> and the immersion angle. The volume factor V<sub>M</sub> is
published as a diagram, so the built-in curve is a digitization and can be
overridden. Oil-jet doubles the result; a vertical shaft applies the
submerged-width fraction.</p>

<p><i>G<sub>rr</sub> and G<sub>sl</sub> are family-specific. The coefficients,
K<sub>z</sub> and K<sub>L</sub> come from the selected table series.</i></p>

<h3>2 · Viscosity</h3>
<p><code>log<sub>10</sub> log<sub>10</sub>(&#957; + 0.7) = A &#8722; B
log<sub>10</sub> T</code> — a two-point fit through &#957;<sub>40</sub> and
&#957;<sub>100</sub>.</p>

<h3>3 · Rating life</h3>
<p><code>L<sub>10</sub> = (C / P)<sup>p</sup></code>, with p = 3 for ball and
10/3 for roller bearings, and
<code>L<sub>10h</sub> = 10<sup>6</sup> L<sub>10</sub> / (60 n)</code>.</p>
<p><code>L<sub>nm</sub> = a<sub>1</sub> a<sub>SKF</sub> L<sub>10</sub></code>,
with a<sub>SKF</sub> from the ISO 281 life-modification equations in
&#954; = &#957; / &#957;<sub>1</sub> and
e<sub>C</sub> C<sub>u</sub> / P.</p>
<p>SKF Explorer performance is exposed as a configurable diagram-axis scale
because the publication does not define one universal multiplier valid for all
bearing classes.</p>

<h3>4 · Engineering extensions</h3>
<p>These are <b>not</b> SKF catalogue equations. They are separated here, in the
input pages, in the calculation warnings and in the exported report, and each
needs its own validation:</p>
<ul>
<li>Clearance / preload and misalignment torque multipliers — internal load
model or test</li>
<li>Generic rolling-element load-zone solver — ISO/TS 16281 or a detailed
contact model</li>
<li>Four-node ring / element / oil temperatures and local contact resistances —
thermal network or test calibration</li>
<li>Oil bypass and heat partition — flow/thermal test or CFD</li>
<li>Full-complement CARB G-factor proxy — supplier calculation or test</li>
<li>Calibration scale factors — an independent validation set</li>
</ul>

<h3>5 · Sources</h3>
<ul>
<li>SKF, <i>The SKF model for calculating the frictional moment</i></li>
<li>SKF rolling-bearing selection principles and rating-life documentation</li>
<li>ISO 281:2007, <i>Rolling bearings — Dynamic load ratings and rating
life</i></li>
<li>ASTM D341, viscosity–temperature equations</li>
</ul>
<p style="color:#475569">The ISO standard itself is not bundled with the
software. This program is not an SKF-certified selector and does not replace
product-specific internal geometry, ISO/TS 16281, supplier review or validation
testing.</p>
"""
