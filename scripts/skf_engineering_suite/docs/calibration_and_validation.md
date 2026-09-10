# Calibration and validation workflow

## 1. Freeze the published-input layer

Before fitting any scale factors, verify:

- exact bearing family and friction-table series;
- `d`, `D`, `B`, `C`, `C0`, `Cu`, `Y`, seal dimensions and seal code;
- lubricant `nu40`, `nu100`, density and heat capacity;
- actual oil level/equivalent jet immersion and oil flow;
- equivalent dynamic load `P`.

Do not use calibration factors to conceal incorrect product data.

## 2. Prepare reference points

Use `examples/calibration_template.csv`. Each row can contain:

- speed and radial/axial loads;
- inlet and ambient temperatures;
- oil flow;
- measured torque and/or measured contact/bulk temperature.

SKF Bearing Select points can be manually transcribed into the same format. Keep the source calculation file or screenshots as validation evidence.

## 3. Fit only identifiable parameters

Recommended sequence:

1. Fit rolling/sliding scales from low-drag or grease/oil-air torque points.
2. Fit drag scale from oil-bath/oil-jet speed sweeps.
3. Fit seal scale from sealed/open comparisons where available.
4. Fit heat-transfer scale from temperature points after torque is stable.
5. Fit installation scale only when clearance/preload/misalignment are known.

Avoid fitting many correlated parameters to a small dataset.

## 4. Use separate calibration and validation sets

A minimum useful matrix spans:

- low, medium and high speed;
- radial-dominant and axial-dominant loading;
- at least two oil inlet temperatures or viscosities;
- multiple oil flows for a thermal model;
- both steady and repeat measurements if test scatter is material.

Fit on one subset and assess errors on the withheld subset.

## 5. Acceptance outputs

Retain:

- program version;
- case JSON;
- calibration profile JSON;
- raw reference CSV;
- predicted-versus-measured CSV;
- residual statistics;
- HTML report for representative points;
- rationale for every enabled engineering extension.

## 6. Design-use guardrails

Do not release a design using:

- automatic equivalent-load defaults without review;
- uncalibrated four-node conductances presented as measured temperatures;
- a digitized `VM` value without checking sensitivity when drag dominates;
- Explorer axis scaling without product-class evidence;
- clearance/misalignment multipliers outside the calibrated range.
