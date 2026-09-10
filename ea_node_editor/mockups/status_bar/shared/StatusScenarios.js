.pragma library

// Fake telemetry presets that drive every mockup panel at once. Mirrors the data
// the real status bar shows: engine state, job counters (R/Q/D/F), optional
// FPS, CPU/RAM, disk read/write, and warning/error counts. The gallery seeds a
// shared model from one of these, then a single Timer jitters the live metrics.
var RAM_TOTAL = 31.8;

function ids() {
    return ["idle", "running", "heavy", "error"];
}

function label(name) {
    switch (String(name)) {
    case "running": return "Running";
    case "heavy": return "Heavy load";
    case "error": return "Error";
    default: return "Idle";
    }
}

function preset(name) {
    switch (String(name)) {
    case "running":
        return {
            engineState: "running",
            engineDetail: "Executing graph",
            jobsR: 2, jobsQ: 5, jobsD: 12, jobsF: 0,
            fpsEnabled: true,
            fps: 47, cpu: 38, ram: 14.6, ramTotal: RAM_TOTAL,
            diskRead: 18.4, diskWrite: 4.2,
            warnings: 1, errors: 0
        };
    case "heavy":
        return {
            engineState: "running",
            engineDetail: "Solving (HPC)",
            jobsR: 6, jobsQ: 18, jobsD: 40, jobsF: 0,
            fpsEnabled: true,
            fps: 24, cpu: 83, ram: 26.4, ramTotal: RAM_TOTAL,
            diskRead: 146.8, diskWrite: 72.5,
            warnings: 3, errors: 0
        };
    case "error":
        return {
            engineState: "error",
            engineDetail: "Node failed: Solver_03",
            jobsR: 0, jobsQ: 3, jobsD: 8, jobsF: 2,
            fpsEnabled: false,
            fps: 52, cpu: 22, ram: 12.1, ramTotal: RAM_TOTAL,
            diskRead: 7.6, diskWrite: 1.8,
            warnings: 2, errors: 1
        };
    default: // idle
        return {
            engineState: "ready",
            engineDetail: "Idle",
            jobsR: 0, jobsQ: 0, jobsD: 0, jobsF: 0,
            fpsEnabled: false,
            fps: 58, cpu: 8, ram: 9.2, ramTotal: RAM_TOTAL,
            diskRead: 0.5, diskWrite: 0.2,
            warnings: 0, errors: 0
        };
    }
}
