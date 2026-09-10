# Release validation checklist

## Input traceability

- Record bearing designation, supplier revision and selected SKF table series.
- Check d, D, B, d1, d2, E, rolling-element count, C, C0, Cu and Y against controlled product data.
- Enter the product-specific equivalent dynamic load P. Do not release a life result based only on the generic fallback.
- Record lubricant batch/type, viscosity at 40 °C and 100 °C, density and heat capacity.
- Record speed, radial/axial load, oil inlet temperature, flow, oil level, shaft orientation and boundary temperatures.

## Model selection

- Confirm the friction-model validity range: steady load/speed, adequate minimum load, applicable viscosity, normal clearance and acceptable alignment.
- Confirm seal-table family, diameter range and counterface dimension.
- Confirm whether oil-bath or oil-jet drag assumptions represent the real reservoir/jet arrangement.
- Treat VM graph interpolation, full-complement CARB proxy, installation corrections and four-node temperatures as calibrated engineering inputs.

## Calibration and verification

- Compare at least three representative operating points spanning low, nominal and high speed/load.
- Use independent reference data: test torque, stabilized temperatures, measured oil flow/temperature rise, or manually exported supplier calculations.
- Retain raw calibration CSV, fitted profile, residual table and acceptance limits.
- Check energy balance and thermal convergence at every validation point.
- Check sensitivity to conductances, bypass fraction, contact thermal resistances, clearance and misalignment.

## Software record

- Save case JSON, calibration-profile JSON, batch input/output, HTML report, application version and test result.
- Run `run_tests.bat` after installation or source changes.
- Review warnings in the HTML report before design release.
