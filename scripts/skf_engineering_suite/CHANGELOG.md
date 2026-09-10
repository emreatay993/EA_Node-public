# Changelog

## Unreleased — 2026-08-20

- Fixed the GUI rendering unusably on Windows systems set to dark mode. Qt hands
  the application a dark palette there, and the old style sheet set backgrounds
  without matching foregrounds, so form labels and spin-box values were white on
  white and unstyled containers filled with the dark window brush. The app now
  pins an explicit light colour scheme and palette, and every style-sheet rule
  that sets a background also sets a colour.
- Moved all colours into a single token table in `skfcalc/theme.py`, replacing
  the scattered literals (and four near-identical greys) in `skfcalc/gui.py`.
- Restyled the interface: card-style groups with inside headers, a sectioned
  navigation rail, underline tabs, slim scroll bars, a filled primary
  `Run calculation` action, a semantic result chip in the status bar, and KPI
  tiles that show the unit beside the value.
- Replaced the squashed native spin-box and combo-box arrows with generated
  chevrons; Qt drops the native ones as soon as a sub-control is styled.
- Themed the matplotlib canvases to match the surrounding cards and share the
  application colour cycle.
- Left-aligned form labels, added placeholder text and tooltips, and rebuilt the
  batch and calibration control panels as proper cards.
- Metric titles and card headers now upper-case Latin letters only, so symbols
  such as the viscosity ratio κ are no longer mangled.
- Added field-level help to every input. Hovering an input or its label shows a
  rich-text tooltip with what the field does, the equation it feeds and the
  published source it comes from, in `skfcalc/help_text.py`. Inputs that drive an
  engineering extension rather than a published SKF equation say so in the
  tooltip, matching the separation in the warnings and the report.
- Rewrote Help ▸ Methodology as a full reference: the coupled solution sequence,
  the friction, viscosity and rating-life equations, the engineering-extension
  list with the validation each needs, and the four source documents.
- Removed the prebuilt wheel, `SHA256SUMS.txt` and `RELEASE_MANIFEST.json`. They
  described the pre-restyle build and no longer matched the source; the package
  is built on demand instead. The benchmark table they carried is unchanged in
  `results/benchmark.csv`.

## 1.0.0 — 2026-08-19

- Added all radial and thrust bearing families represented in SKF's published friction-model tables.
- Added inlet shear heating, lubricant replenishment/starvation, mixed-lubrication sliding friction, contact-seal tables and oil-bath/oil-jet drag.
- Added one-node and four-node steady thermal solvers, oil-flow partitioning and local contact-temperature estimates.
- Added optional clearance, preload, misalignment and rolling-element load-zone extensions with explicit engineering-model warnings.
- Added ISO 281 basic/modified rating-life calculations and configurable SKF Explorer chart approximation.
- Added CSV batch calculations, a Numba deep-groove-ball-bearing fast path, least-squares calibration and self-contained HTML reports.
- Added a nine-workspace PyQt6 desktop GUI with case persistence, plots, tables and threaded calculations.
- Added 43 automated numerical/source tests, examples and Windows launch scripts.
