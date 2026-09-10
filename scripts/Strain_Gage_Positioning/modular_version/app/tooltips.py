# =====================================================================================
# TOOLTIPS.PY
# Central repository for all UI tooltips in the Strain Gage Positioning Tool.
# This file contains detailed, user-friendly explanations for every feature.
# =====================================================================================

# =====================================================================================
# File Loading and Main Actions
# =====================================================================================

LOAD_STRAIN_DATA = """
<b>Load Strain Data File (.txt, .dat)</b><br/>
<br/>
Select a whitespace-delimited text file containing node coordinates and strain tensors.
<br/><br/>
<b><u>Format:</u></b>
<ul style="margin: 0 0 0 6px;">
  <li><b>Delimiter:</b> One or more spaces (whitespace). CSV commas are not supported.</li>
  <li><b>Header:</b> The first line is treated as a header and skipped.</li>
  <li><b>Columns (per node):</b>
    <ol style="margin: 6px 0 0 14px;">
      <li>Node ID (int)</li>
      <li>X (float)</li>
      <li>Y (float)</li>
      <li>Z (float)</li>
      <li>Exx (strain, mm/mm)</li>
      <li>Eyy (strain, mm/mm)</li>
      <li>Ezz (strain, mm/mm) — parsed for compatibility</li>
      <li>Exy (engineering shear strain γ<sub>xy</sub>, mm/mm)</li>
    </ol>
    <div style="margin-top: 4px;">
      <i>Optional:</i> Columns <b>9</b> and <b>10</b> may be <b>Eyz</b> and <b>Exz</b> (mm/mm).
      If present, they are read but <b>ignored</b> by the analysis.
    </div>
  </li>
</ul>
<br/>
<b><u>Units:</u></b><br/>
Provide strains in <b>strain (mm/mm)</b>. The tool converts to microstrain internally; display units can be toggled/changed later.
<br/>
<i>Unit detection from header:</i> If the first line contains <b>"X Location (m)"</b>, coordinates are treated as meters and converted to <b>mm</b> internally. If it contains <b>"X Location (mm)"</b>, they are used as mm. If unspecified, mm is assumed. All distance inputs in the UI (Min Distance, Uniformity Search Radius, ROI) are always specified in <b>millimeters</b>.
<br/><br/>
<b><u>Multiple Load Cases:</u></b><br/>
Provide multiple cases in either of two ways:
<ol style="margin: 6px 0 0 14px;">
  <li><b>Single file, multiple cases:</b> Append extra <b>4-column</b> blocks
      (Exx, Eyy, Ezz, Exy) for each load case. The tool auto-detects and analyzes all cases.<br/>
      This method is not recommended as it can be confusing and error-prone.<br/>
           Please use the multiple files method instead.<br/></li>
  <li><b>Multiple files:</b> Select more than one file when loading.
      Files are stacked as separate load cases as long as they share the same Node and XYZ coordinates.</li>

</ol>
"""
FILE_LABEL = """
<b>Current Data File</b><br><br>
Displays the name of the file that is currently loaded into the application. If no file is loaded,
it will show "No file loaded".
"""
LOAD_RST_DPF = """
<b>Load from .rst (DPF)</b><br/>
<br/>
Read nodal elastic strain straight from an Ansys result file (<b>.rst</b>) using
DPF &mdash; no manual text export needed.
<br/><br/>
After picking a file you choose:
<ul style="margin: 0 0 0 6px;">
  <li><b>Named selection:</b> scope to a component (e.g. a surface), or the whole model.</li>
  <li><b>Result sets:</b> each set becomes one load case (e.g. <i>all</i>, <i>last</i>, <i>1,3</i>, <i>1-4</i>).</li>
  <li><b>Rotate to global:</b> express strains in the global frame (recommended).</li>
</ul>
<br/>
Coordinates are converted to <b>mm</b> automatically from the mesh unit, and strains
are converted to <b>microstrain</b>, exactly like the text-file loader. Requires
<b>ansys-dpf-core</b> and an Ansys/DPF server on this machine.
"""
RUN_ANALYSIS = """
<b>Run Analysis / Update</b><br><br>
This is the main action button that triggers the entire calculation and point selection process
based on all the settings you have configured in the control panel.<br><br>
<b><u>Workflow:</u></b>
<ol>
  <li>Computes the strain metric (von Mises or Uniaxial) for all nodes.</li>
  <li>Calculates the local standard deviation (strain gradient) for all nodes.</li>
  <li>Calculates the final 'Quality' score for all nodes using the selected formula.</li>
  <li>Applies the chosen 'Selection Strategy' to pick the best candidate points.</li>
  <li>Updates the 3D visualization and the candidate table with the results.</li>
</ol>
<b><u>Note on K-Means:</u></b><br>
When using the "Max Coverage (K-Means)" strategy, this button will first show a preview of the
spatial clusters. Its text will then change to <i>"Continue with K-Means"</i>, requiring a
second click to finalize the selection.
"""
# =====================================================================================
# Core Settings
# =====================================================================================

MEASUREMENT_MODE = """
<b>Measurement Mode</b><br><br>
This setting defines the fundamental engineering quantity that the tool will optimize for.
Your choice depends on the type of strain gage you intend to use and what you want to measure.<br><br>
<ul>
  <li><b>Rosette:</b> This mode calculates the equivalent <b>von Mises strain</b>. This is a single
    scalar value that represents the total strain energy or "intensity" at a point, regardless of
    direction.
    <br><b>Use Case:</b> Excellent for general-purpose analysis or when you plan to use a triaxial
    (0-45-90 or 0-60-120 degree) rosette gage. It's the best choice when you don't know much aboutthe
    principal strain direction beforehand.</li>
  <br>
  <li><b>Uniaxial:</b> This mode calculates the normal strain (direct stretching or compression)
    across a full range of angles (0-180 degrees) for each node. It then identifies the single angle
    that produces the highest absolute strain value (principal strain).
    <br><b>Analogy:</b> This is like rotating a single, straight ruler at a point on the rubber
    sheet and finding the orientation where the ruler measures the most stretch.
    <br><b>Use Case:</b> The ideal choice when you plan to use a simple, single-element (uniaxial)
    strain gage and want to orient it to capture the absolute maximum strain possible at that location.</li>
</ul>
"""
CANDIDATE_COUNT = """
<b>Candidate Points Requested</b><br><br>
This value directly sets the number of final candidate points the selection algorithm will
attempt to find and display. For example, if you set this to 10, the software will return the
top 10 locations that best satisfy your chosen strategy.
"""
UNIFORMITY_RADIUS = """
<b>Uniformity Search Radius [mm]</b><br><br>
This is one of the most important parameters as it defines the "local neighborhood" for
calculating the strain gradient (represented by 'Local Standard Deviation', σ).<br><br>
<b><u>How it Works:</u></b><br>
For every single point in your model, the tool draws an imaginary sphere of this radius around it.
It then looks at the 'Best Strain' values of all other points that fall inside this sphere and
calculates the standard deviation of those values.
<ul>
  <li>A <b>low</b> standard deviation means the strain is uniform or "flat" in that area.</li>
  <li>A <b>high</b> standard deviation means the strain is changing rapidly, indicating a
    high strain gradient or stress concentration.</li>
</ul>
<b><u>Practical Advice:</u></b>
<ul>
  <li><b>Too Small:</b> If the radius is too small, it might not enclose any other points,
    resulting in a gradient of zero. This can lead to inaccurate quality scores.</li>
  <li><b>Too Large:</b> If the radius is too large, it might average the gradient over too wide
    an area, "smoothing out" and hiding important local hot spots.</li>
</ul>
<b>Pro Tip:</b> A good starting value is often 2-3 times the average distance between nodes in your area of interest.
<br><br>
<b>Stability safeguards:</b><br>
When very few neighbors fall inside the radius (e.g., at edges or sparse regions), the tool
computes the local gradient using the <b>k nearest neighbors</b> (k≥4) to stabilize the estimate.
After each run, it reports how often this fallback was used. If more than ~<b>5%</b> of points rely
on the fallback, consider increasing the radius or refining the mesh.
"""
# =====================================================================================
# Quality Metrics
# =====================================================================================

QUALITY_MODE = """
<b>Quality Metrics Mode</b><br><br>
This formula defines what the tool considers a "good" location for a strain gage. All formulas
are a trade-off between two competing factors:
<ol>
  <li><b>High Strain Magnitude (|ε|):</b> You want to place gages where the signal is strong.</li>
  <li><b>Low Strain Gradient (σ):</b> The strain across the physical area of the gage should be as
    uniform as possible. Placing a gage on a sharp gradient can lead to inaccurate, averaged readings.</li>
</ol>
Your choice of formula depends on how strongly you want to penalize high-gradient areas.<br><br>
<ul>
  <li><b>Signal-Noise Ratio: |ε|/(σ+1e-12)</b> (Default): This is a standard in signal processing.
    Think of the strain magnitude (|ε|) as the "signal" you want to measure and the gradient (σ) as the
    "noise" that can corrupt the measurement. This formula aggressively favors a strong signal over
    low noise and is extremely effective at finding peak strain locations that are reasonably stable.<br>
    <i>Auto-calibration:</i> ε<sub>0</sub> is set from the data as <b>max(1 μɛ, 1% of σ<sub>75</sub>)</b>,
    where σ<sub>75</sub> is the 75th percentile of the local gradient. This prevents blow-ups when σ≈0
    and keeps the scale consistent across different models.</li>
  <br>
  <li><b>Default: |ε|/(1+σ):</b> A balanced and intuitive approach. The quality score decreases
    linearly as the local gradient increases. It's a reliable, general-purpose choice.</li>
  <br>
  <li><b>Squared: |ε|/(1+σ²):</b> This formula strongly penalizes high-gradient areas. Because the
    gradient term (σ) is squared, even a moderately high gradient will cause the quality score to
    drop dramatically.
    <br><b>Use Case:</b> Select this if measurement accuracy and strain field uniformity are far more
    important to you than simply finding the absolute highest peak strain.</li>
  <br>
  <li><b>Exponential: |ε|·exp(–kσ):</b> This is the most aggressive penalty against gradients.
    The exponential function means that the quality score decays with the local gradient.
    In this tool, <b>k auto‑calibrates</b> per dataset so that at the 75th percentile of σ the
    exponential factor is ~<b>0.5</b> (i.e., <b>k = ln(2)/σ<sub>75</sub></b>). This keeps behavior
    consistent across meshes and load cases without manual tuning.
    <br><b>Use Case:</b> Use this for applications requiring extreme measurement fidelity, where you
    must find and place gages only in the most stable, flat, and uniform strain fields.</li>
</ul>
"""

# =====================================================================================
# Aggregation Method
# =====================================================================================

AGGREGATION_METHOD = """
<b>Aggregation Method (for multiple load cases)</b><br><br>
This setting is crucial when your input file contains data from more than one analysis or load case.
It specifies how to combine the 'Quality' scores from these different scenarios to get a single, final
score for each node, which is then used by the selection strategy.
"""
AGGREGATION_MAX = """
<b>Max Aggregation</b><br><br>
For each node, the final Quality score will be the <b>highest</b> score it achieved
across all load cases.<br><br>
<b>Use Case:</b> This is the best choice for "worst-case scenario" or fatigue analysis.
You want to find locations that experience high strain in <i>at least one</i> of the scenarios,
even if they are quiet in others. It's designed to find the absolute critical points.
"""
AGGREGATION_AVERAGE = """
<b>Average Aggregation</b><br><br>
For each node, the final Quality score will be the <b>average</b> of its scores
from all load cases.<br><br>
<b>Use Case:</b> This is ideal for finding locations that are consistently good performers
across all expected operating conditions. It avoids points that are extreme in only one
scenario and favors locations with overall stability and reliability.
"""

# =====================================================================================
# Selection Strategies
# =====================================================================================

SELECTION_STRATEGY = """
<b>Selection Strategy</b><br><br>
This is the final step in the process. This setting chooses the algorithm used to select the
final candidate points from the entire population of nodes, each of which now has a final 'Quality' score.
The best strategy depends on your primary goal.
"""
STRATEGY_QUALITY_GREEDY = """
<b>Max Quality (Greedy Search)</b><br><br>
<b>Goal:</b> Find the absolute best points, period.<br><br>
This strategy prioritizes the 'Quality' score above all else. It works by first finding the single
node with the highest quality score in the entire model. It selects this as the first candidate.
Then, it eliminates all other nodes within the 'Min Distance' radius and repeats the process,
finding the next-highest quality point from the remaining nodes. It continues until the requested
number of candidates is found.<br><br>
<b>Analogy:</b> Like planting flags on a mountain range. You plant the first flag on the highest peak.
Then you find the next highest peak that is a safe distance away from the first, and so on.
"""
STRATEGY_KMEANS = """
<b>Max Coverage (K-Means)</b><br><br>
<b>Goal:</b> Ensure the candidate points are spread out across the entire model.<br><br>
This strategy prioritizes spatial coverage. It uses the K-Means clustering algorithm to partition
all the nodes into a specified number of groups (clusters). The algorithm's goal is to make these
clusters as compact and separated as possible. Once the clusters are defined, the tool simply
selects the single point with the highest 'Quality' score from within each cluster.<br><br>
<b>Use Case:</b> Perfect for exploratory analysis where you want a good overview of interesting
locations across your entire part, rather than just focusing on one hot-spot.
"""
STRATEGY_FILTERED_KMEANS = """
<b>Quality-Filtered K-Means</b><br><br>
<b>Goal:</b> Get good spatial coverage, but only among high-quality points.<br><br>
This is a powerful hybrid strategy. It first performs a "pre-filtering" step, throwing away
all nodes that don't meet a certain quality threshold (defined by the 'Quality Filter [%ile]').
It then runs the K-Means clustering algorithm on this much smaller, elite subset of high-quality
points. This prevents clusters from being formed in low-strain, uninteresting areas and gives you
the best of both worlds: quality and coverage.
"""
STRATEGY_GRADIENT_GREEDY = """
<b>Greedy Gradient Search</b><br><br>
<b>Goal:</b> Specifically find stress concentrations and high-gradient zones.<br><br>
This strategy works just like the 'Max Quality (Greedy Search)', but with one critical difference:
instead of prioritizing the 'Quality' score, it greedily selects points with the highest
<b>'Local Std'</b> (strain gradient) value. This is a specialized tool designed to ignore uniform
strain fields and home in directly on the areas where strain is changing most rapidly.<br><br>
<b>Use Case:</b> Ideal for fracture mechanics, durability analysis, or any situation where you
need to place gages specifically to monitor a known stress concentration (like a fillet or a hole).
"""
STRATEGY_ROI = """
<b>Region of Interest (ROI) Search</b><br><br>
<b>Goal:</b> Find the best points, but only within a specific, user-defined area.<br><br>
This strategy allows you to focus the search. It first discards all nodes outside the spherical
'Region of Interest' that you define. It then performs a standard 'Max Quality (Greedy Search)'
on only the points remaining inside the ROI.<br><br>
<b>Use Case:</b> Extremely useful for large, complex models where you only care about a specific
component, feature, or known problem area.
"""

# =====================================================================================
# Strategy-Specific Parameters
# =====================================================================================

MIN_DISTANCE = """
<b>Minimum Distance [mm]</b><br><br>
This parameter is used by all 'Greedy' and 'ROI' search strategies.<br><br>
It defines a "personal space" or "exclusion zone" around each candidate point after it has been
selected. Once a point is chosen, no other point within this radius can be selected as a candidate.
This is essential for preventing the algorithm from picking a tight cluster of points all in the
same hot-spot, which would be redundant for physical measurement.
"""
QUALITY_PERCENTILE = """
<b>Quality Filter [%ile]</b><br><br>
This parameter is used only by the 'Quality-Filtered K-Means' strategy.<br><br>
It sets the quality threshold for the initial filtering step. A percentile is a measure indicating
the value below which a given percentage of observations in a group of observations falls.<br><br>
For example, a value of <b>75</b> means that the algorithm will only consider points whose 'Quality'
score is in the top <b>25%</b> of all points. The remaining 75% of lower-quality points are discarded
before the K-Means clustering begins.
"""
GRADIENT_MODE = """
<b>Gradient Mode</b><br><br>
Controls how 'Greedy Gradient Search' ranks candidates:<br>
<ul>
  <li><b>Max Local Std:</b> Prioritize the steepest strain gradients (typical use).</li>
  <li><b>Min Local Std:</b> Prioritize the flattest, most uniform regions (e.g., for highly stable measurements).</li>
<ul>
"""
ROI_GROUP = "Define a spherical Region of Interest (ROI) by specifying its center coordinates (X, Y, Z) and its radius in millimeters."

# =====================================================================================
# Menu and Display Controls
# =====================================================================================

SET_PROJECT_DIR = "Sets the default directory that will open when you use the 'Load Strain Data' or other file-saving dialogs."
SHOW_TABLE = """
<b>Show/Hide Candidate Table</b><br><br>
Toggles the visibility of the dockable table at the side of the window. This table contains
detailed numerical data for the final selected candidate points, including their coordinates,
best strain, best angle, local standard deviation, and quality score.
"""
DISPLAY_STRAIN = """
<b>Display Results in Strain (mm/mm) vs. Microstrain (με)</b><br><br>
This toggle changes the units used for displaying all strain values in the application,
including the color bar legend and the candidate table.<br><br>
- <b>Unchecked (Default):</b> Results are shown in <b>microstrain (με)</b>.
  (e.g., 1500 με). This is a common industry standard as it avoids dealing with many decimal places.
  (1 με = 1 x 10<sup>-6</sup> strain).<br>
- <b>Checked:</b> Results are shown in dimensionless <b>strain</b> (e.g., 0.0015).
"""

# =====================================================================================
# Threshold Filter Controls
# =====================================================================================

STRAIN_THRESHOLD_GROUP = """
<b>Strain Threshold Filter</b><br><br>
Exclude nodes whose strain signal is too small across all load cases.<br>
When enabled, nodes whose selected metric (Average or Max across load cases)
is below the specified microstrain threshold are removed from consideration
before candidate-point selection strategies run.
"""

STRAIN_THRESHOLD_VALUE = """
<b>Threshold (με)</b><br><br>
The microstrain value used to filter out low-signal nodes. Typical values are
10–50 με, but this depends on your material, loads, and measurement fidelity.
"""

STRAIN_THRESHOLD_AGG = """
<b>Across load cases</b><br><br>
Select how the per-node strain metric is computed across multiple load cases for the threshold check.<br>
<ul>
  <li><b>Average:</b> Mean microstrain across load cases. Favors nodes that are consistently above the threshold.<br>
      <i>Example:</i> strains [5, 12, 7] με → avg = 8 με. With a 10 με threshold this node is filtered out.</li>
  <li><b>Max:</b> Maximum microstrain across load cases. Keeps nodes that exceed the threshold in at least one case.<br>
      <i>Example:</i> strains [5, 12, 7] με → max = 12 με. With a 10 με threshold this node is kept.</li>
</ul>
<b>Tip:</b> Use <b>Average</b> for robustness across loads; use <b>Max</b> to retain peak responders.<br>
<b>Note:</b> This filter runs before selection and is independent of the Quality aggregation. The threshold is always specified in microstrain (με).
"""

# =====================================================================================
# Visualization Controls
# =====================================================================================

CLOUD_POINT_SIZE = "Controls the rendered size of the individual points in the main data cloud."
CANDIDATE_POINT_SIZE = "Controls the rendered size of the highlighted magenta points, making the final candidates easier to see."
LABEL_FONT_SIZE = ("Font size of the candidate callouts ('P1  Q 100%'). These are drawn in the "
                   "Ansys Mechanical style: a small pale box joined to its point by a leader line, "
                   "which you can drag to a clearer spot.")
LEGEND_BAND_COUNT = """
<b>Contour Bands</b><br><br>
Number of discrete colour bands, matching Mechanical's contour band count
(default <b>9</b>). This drives both the legend and the shading on the model,
so the geometry shows sharp banded contours rather than a smooth gradient.<br><br>
The legend prints one value per band <i>boundary</i>, so N bands carry N+1
numbers. Labels thin out automatically when the bands get shorter than the text.
"""
CONTOUR_SELECTION = """
<b>Contour Sets / Time Points</b><br/><br/>
Choose independently which loaded result sets feed the contour and hover value.
Use <b>all</b>, <b>last</b>, one set such as <b>2</b>, a list such as
<b>1,3,5</b>, or a range such as <b>2-6</b>. Max/Average applies only to the
chosen contour sets and does not change strain-gage candidate selection.
"""
LEGEND_CONTROLS = """
<b>Legend Color and Range Controls</b><br><br>
These controls allow you to manually adjust the color mapping for the 3D visualization.
This can be very useful for highlighting specific data ranges or improving visual clarity.<br><br>
- <b>Upper/Lower Limit:</b> Sets the data values that map to the top (red) and bottom (blue)
  of the 'jet' color scale. Any value above the upper limit or below the lower limit will be
  clamped to the specified color.<br>
- <b>Above/Below Color:</b> Sets the color to be used where values fall outside
  the defined upper and lower limits.
"""

SHOW_SURFACE_EDGES = "Shows element edges over the filled .rst result contour without hiding the contour itself."
SURFACE_OPACITY = "Controls how solid the .rst surface contour appears. Lower values are more transparent."
SHOW_SURFACE_NORMALS = "Shows the local surface normal at each selected gage placement."
SHOW_GAGE_AXES = "Shows the computed local X/Y axes for each selected gage placement."
OVERRIDE_GAGE_DIRECTION = "Enables two-click gage direction override: click the origin, then click the local X direction point."
CLEAR_GAGE_OVERRIDES = "Clears manual gage direction overrides and returns placements to candidate-based angles."
EXPORT_GAGE_PLACEMENTS = "Writes strain_gage_surface_placements.csv with origins, normals, local axes, and angles."
