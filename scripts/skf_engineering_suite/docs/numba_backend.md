# Numba backend scope

The full solver prioritizes model coverage and traceability. The Numba backend prioritizes throughput for repeated deep-groove-ball-bearing operating maps.

## Supported

- deep-groove ball bearing SKF `Grr/Gsl` equations;
- inlet shear and replenishment factors;
- mixed-lubrication sliding coefficient;
- contact-seal torque;
- ball-bearing oil-bath/oil-jet drag;
- one-node oil/housing thermal balance;
- calibration scale factors;
- varying speed, loads, inlet/ambient temperature, flow and housing conductance.

## Not supported in fast path

- other bearing families;
- four-node temperatures;
- clearance/preload/misalignment correction;
- element load distribution;
- rating life.

The GUI prevents silent substitution by identifying the backend in the output table and adding a scope warning.
