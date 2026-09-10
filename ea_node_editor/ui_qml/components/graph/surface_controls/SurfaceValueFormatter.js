.pragma library

function precisionForStep(step, continuousPrecision) {
    var numeric = Math.abs(Number(step));
    if (!isFinite(numeric) || numeric <= 0)
        return Math.max(0, Math.min(6, Math.round(Number(continuousPrecision) || 3)));
    if (numeric < 0.000001)
        return 6;
    var fixed = numeric.toFixed(6).replace(/0+$/, "");
    var decimal = fixed.indexOf(".");
    return decimal < 0 ? 0 : Math.min(6, fixed.length - decimal - 1);
}

function format(value, valueType, step, continuousPrecision) {
    var numeric = Number(value);
    if (!isFinite(numeric))
        return "\u2014";
    if (String(valueType || "").toLowerCase() === "int")
        return String(Math.round(numeric));
    return numeric.toFixed(precisionForStep(step, continuousPrecision));
}
