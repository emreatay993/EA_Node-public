from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class MetricHelpEntry:
    key: str
    group: str
    title: str
    fallback: str
    formula: str
    practice: str
    example: str
    interpretation: str
    related_tab: str


def _entry(
    key: str,
    group: str,
    title: str,
    fallback: str,
    formula: str,
    practice: str,
    example: str,
    interpretation: str,
    related_tab: str,
) -> MetricHelpEntry:
    return MetricHelpEntry(
        key=key,
        group=group,
        title=title,
        fallback=fallback,
        formula=formula,
        practice=practice,
        example=example,
        interpretation=interpretation,
        related_tab=related_tab,
    )


METRIC_HELP: dict[str, MetricHelpEntry] = {
    "RMSE": _entry(
        "RMSE",
        "Error",
        "Root Mean Squared Error",
        "Typical point error in signal units, with larger misses weighted strongly.",
        "RMSE = sqrt(mean((reference_i - candidate_i)^2))",
        "Use RMSE when large excursions matter. It stays in the same units as the channel, but the squaring step makes rare large differences more visible than MAE.",
        "Reference pressure [50, 51, 52] and candidate [50, 50, 54] give errors [0, -1, 2], MSE = (0 + 1 + 4) / 3 = 1.667, so RMSE = 1.291 pressure units.",
        "Lower is better. A high RMSE with moderate MAE usually means a few short periods have large disagreement.",
        "Statistical Metrics",
    ),
    "MAE": _entry(
        "MAE",
        "Error",
        "Mean Absolute Error",
        "Average absolute residual in signal units.",
        "MAE = mean(abs(candidate_i - reference_i))",
        "Use MAE for a direct average miss size. It is easier to explain than MSE and is less dominated by a single outlier than RMSE.",
        "Reference strain [100, 110, 120] and candidate [102, 107, 124] give absolute errors [2, 3, 4], so MAE = 3 microstrain.",
        "Lower is better. Compare it to engineering tolerance for the channel; MAE below tolerance means the average miss is acceptable.",
        "Residuals",
    ),
    "Mean Bias": _entry(
        "Mean Bias",
        "Error",
        "Mean Bias",
        "Average signed residual, candidate minus reference.",
        "Mean Bias = mean(candidate_i - reference_i)",
        "Use bias to detect a systematic offset. It preserves sign, so positive values mean the candidate is generally above the reference.",
        "Residuals [0.2, -0.1, 0.1] have Mean Bias = 0.067. The candidate is slightly high on average.",
        "Near zero is usually preferred. A low MAE with high bias points to a consistent calibration offset.",
        "Residuals",
    ),
    "Max Abs Error": _entry(
        "Max Abs Error",
        "Error",
        "Maximum Absolute Error",
        "Largest absolute point-by-point residual.",
        "Max Abs Error = max(abs(candidate_i - reference_i))",
        "Use this when a single limit exceedance matters, such as peak strain, peak pressure, or a transient sensor spike.",
        "Absolute errors [1, 3, 8, 2] give Max Abs Error = 8. One point is much worse than the others.",
        "Lower is better. If this is high while P95/P99 are low, inspect the Overlay and Data Quality tabs for a spike or isolated event.",
        "Residuals",
    ),
    "P95 Abs Error": _entry(
        "P95 Abs Error",
        "Error",
        "95th Percentile Absolute Error",
        "High-percentile residual that ignores the worst 5 percent of samples.",
        "P95 Abs Error = percentile(abs(candidate_i - reference_i), 95)",
        "Use P95 to understand near-worst normal behavior without letting one bad point define the whole comparison.",
        "For 1000 samples, P95 is the error level below which about 950 absolute residuals fall.",
        "Lower is better. If P95 is close to Max Abs Error, disagreement is sustained; if it is much lower, the worst errors are isolated.",
        "Residuals",
    ),
    "P99 Abs Error": _entry(
        "P99 Abs Error",
        "Error",
        "99th Percentile Absolute Error",
        "Very high-percentile residual that keeps most outliers visible.",
        "P99 Abs Error = percentile(abs(candidate_i - reference_i), 99)",
        "Use P99 when rare peaks still matter but a single noisy sample should not dominate the assessment.",
        "For 10,000 vibration samples, P99 reports the threshold exceeded by roughly the worst 100 samples.",
        "Lower is better. P99 much higher than P95 indicates rare but important bursts of error.",
        "Residuals",
    ),
    "MSE": _entry(
        "MSE",
        "Error",
        "Mean Squared Error",
        "Average squared point-by-point error.",
        "MSE = mean((reference_i - candidate_i)^2)",
        "Use MSE when optimization or model scoring should heavily penalize larger misses. Its units are squared channel units, so it is less intuitive than RMSE.",
        "Errors [0, -1, 2] give squared errors [0, 1, 4], so MSE = 1.667.",
        "Lower is better. Use RMSE for day-to-day interpretation because RMSE returns to signal units.",
        "Statistical Metrics",
    ),
    "Absolute Error": _entry(
        "Absolute Error",
        "Error",
        "Average Absolute Error",
        "Average magnitude of point-by-point error.",
        "Absolute Error = mean(abs(reference_i - candidate_i))",
        "This is the legacy aggregate absolute-error metric. It is equivalent in meaning to MAE in this tool and is retained for continuity with older reports.",
        "Reference [10, 12, 14] and candidate [11, 10, 15] give absolute errors [1, 2, 1], so Absolute Error = 1.333.",
        "Lower is better. Prefer MAE for new reviews because the name is standard and clearer.",
        "Statistical Metrics",
    ),
    "Percentage Error": _entry(
        "Percentage Error",
        "Error",
        "Mean Percentage Error",
        "Average absolute error as a percent of the reference value.",
        "Percentage Error = mean(abs(reference_i - candidate_i) / abs(reference_i) * 100), excluding zero reference samples",
        "Use percentage error to compare channels with different scales. Avoid relying on it near zero because small denominators inflate the result.",
        "Reference [100, 200] and candidate [110, 180] give percentage errors [10%, 10%], so the mean is 10%.",
        "Lower is better. If this is high while MAE is small, check whether the reference passes near zero.",
        "Statistical Metrics",
    ),
    "SMAPE": _entry(
        "SMAPE",
        "Error",
        "Symmetric Mean Absolute Percentage Error",
        "Scale-normalized error using both reference and candidate magnitudes.",
        "SMAPE = mean(2 * abs(reference_i - candidate_i) / (abs(reference_i) + abs(candidate_i)) * 100)",
        "Use SMAPE when both signals can be treated symmetrically and normal percentage error is too sensitive to which dataset is selected as reference.",
        "Reference 100 and candidate 110 gives 2 * 10 / 210 * 100 = 9.52%.",
        "Lower is better. It is still unstable when both values are near zero; pair it with Sign Deadband and residual plots.",
        "Statistical Metrics",
    ),
    "WMAPE": _entry(
        "WMAPE",
        "Error",
        "Weighted Mean Absolute Percentage Error",
        "Total absolute error divided by total absolute reference magnitude.",
        "WMAPE = sum(abs(reference_i - candidate_i)) / sum(abs(reference_i)) * 100",
        "Use WMAPE when larger reference magnitudes should naturally carry more weight than small near-zero samples.",
        "Reference [100, 200] and candidate [110, 180] give total absolute error 30 and total reference magnitude 300, so WMAPE = 10%.",
        "Lower is better. It is more stable than pointwise percentage error when individual reference samples are small.",
        "Statistical Metrics",
    ),
    "Within Tolerance Abs (%)": _entry(
        "Within Tolerance Abs (%)",
        "Error",
        "Within Tolerance (Absolute)",
        "Percent of samples whose absolute residual fits the absolute tolerance band, or whose channels are both below the noise floor.",
        "Within tolerance when abs(candidate_i - reference_i) <= abs_tol, OR (abs(reference_i) <= noise_floor AND abs(candidate_i) <= noise_floor)",
        "Use this as the practical agreement indicator after entering an absolute engineering tolerance. It answers whether the miss is small enough in real units, even when percentage error looks large. The noise-floor term lets near-zero samples on both channels count as agreeing instead of being penalized.",
        "Reference 120 microns and candidate 100 microns have a 20 micron miss. With Abs tol = 20, the sample is within tolerance, so a channel that holds this gap reports 100%.",
        "Higher is better. Blank means both the absolute tolerance and the noise floor are zero, so the tool has no acceptance band to apply.",
        "Statistical Metrics",
    ),
    "Within Tolerance Rel (%)": _entry(
        "Within Tolerance Rel (%)",
        "Error",
        "Within Tolerance (Relative)",
        "Percent of samples whose absolute residual fits a tolerance band scaled to the reference magnitude, or whose channels are both below the noise floor.",
        "Within tolerance when abs(candidate_i - reference_i) <= abs(reference_i) * rel_tol_pct / 100, OR (abs(reference_i) <= noise_floor AND abs(candidate_i) <= noise_floor)",
        "Use this when the acceptable miss should grow with signal size rather than stay fixed. The band is a percent of the reference (main) value; the noise-floor term keeps tiny near-zero samples from failing a percentage test that has almost no band.",
        "Reference 120 microns and candidate 100 microns miss by 20 microns, which is 16.7% of 120. With Rel tol = 16.7% the sample is within tolerance, so the channel reports 100%.",
        "Higher is better. Blank means both the relative tolerance and the noise floor are zero, so the tool has no acceptance band to apply.",
        "Statistical Metrics",
    ),
    "Robust NMAE (%)": _entry(
        "Robust NMAE (%)",
        "Error",
        "Robust Normalized Mean Absolute Error",
        "MAE normalized by a robust reference scale, reported as a percent.",
        "Robust NMAE = 100 * MAE / max(P95(reference) - P5(reference), median(abs(reference)))",
        "Use this to rank channels with different magnitudes without depending on each point's reference value as the denominator.",
        "If MAE is 2 and the robust reference scale is 20, Robust NMAE is 10%.",
        "Lower is better. Use it for ranking and screening, then use the Within Tolerance Abs/Rel metrics with an entered tolerance for pass/fail-style agreement.",
        "Statistical Metrics",
    ),
    "Max Correlation": _entry(
        "Max Correlation",
        "Correlation",
        "Maximum Cross-Correlation",
        "Best normalized cross-correlation found across sample shifts.",
        "Max Correlation = max(crosscorr(zscore(reference), zscore(candidate)))",
        "Use this to detect whether two signals have the same shape even if they are shifted in time.",
        "Two identical waveforms shifted by one sample can have low zero-lag Pearson R but high Max Correlation at lag 1.",
        "Closer to 1 is better. A high value with a non-zero lag means the shape matches but timing is off.",
        "Statistical Metrics",
    ),
    "Pearson Correlation": _entry(
        "Pearson Correlation",
        "Correlation",
        "Pearson Correlation",
        "Zero-lag linear correlation between reference and candidate.",
        "Pearson R = cov(reference, candidate) / (std(reference) * std(candidate))",
        "Use Pearson R to check whether the two signals rise and fall together without applying a time shift.",
        "If reference [1, 2, 3] and candidate [2, 4, 6], Pearson R = 1.0 even though the magnitude scale is different.",
        "Closer to 1 is better for same-direction signals. Values near -1 indicate strong opposite polarity.",
        "Statistical Metrics",
    ),
    "Coefficient of Determination": _entry(
        "Coefficient of Determination",
        "Correlation",
        "Coefficient of Determination",
        "Fraction of reference variance explained by the candidate residual model.",
        "Coefficient of Determination = 1 - sum((reference_i - candidate_i)^2) / sum((reference_i - mean(reference))^2)",
        "Use coefficient of determination as a goodness-of-fit score when the reference variance is meaningful.",
        "If residual sum of squares is 5 and reference total sum of squares is 100, coefficient of determination = 0.95.",
        "Closer to 1 is better. Negative values can occur when the candidate is worse than using the reference mean.",
        "Statistical Metrics",
    ),
    "Lag at Max Correlation (samples)": _entry(
        "Lag at Max Correlation (samples)",
        "Correlation",
        "Lag at Max Correlation",
        "Sample offset where the legacy cross-correlation reaches its maximum.",
        "Lag at Max Correlation = argmax(crosscorr(zscore(reference), zscore(candidate))) - (n - 1)",
        "Use this legacy lag value with Max Correlation to identify rough sample-level timing shift.",
        "If the best correlation occurs one index after the zero-lag position, the lag is +1 sample.",
        "Near zero is expected for synchronized data. Confirm timing issues in the Lag tab with Best Lag and Max Lag Correlation.",
        "Statistical Metrics",
    ),
    "Time Shift (s)": _entry(
        "Time Shift (s)",
        "Correlation",
        "Time Shift",
        "Legacy cross-correlation lag converted from samples to seconds.",
        "Time Shift (s) = Lag at Max Correlation (samples) * median sample step",
        "Use this to express the legacy lag estimate in physical time instead of sample count.",
        "A lag of 3 samples with 0.02 s sampling gives Time Shift = 0.06 s.",
        "Near zero is expected after synchronization. Non-zero values suggest a trigger, logging, or interpolation alignment issue.",
        "Statistical Metrics",
    ),
    "Sign Agreement (%)": _entry(
        "Sign Agreement (%)",
        "Polarity",
        "Sign Agreement",
        "Percent of samples where both non-deadband signals have the same sign.",
        "Sign Agreement = count(sign_eps(reference_i) == sign_eps(candidate_i) and both non-zero) / n * 100",
        "Use this when direction matters, such as tensile versus compressive strain or positive versus negative acceleration.",
        "Reference signs [-, +, +] and candidate signs [-, -, +] have two same-sign samples out of three, so agreement is 66.7%.",
        "Higher is better. Low sign agreement with acceptable RMSE means the magnitude may be close but the physical direction is often wrong.",
        "Sign Agreement",
    ),
    "Sign Mismatch (%)": _entry(
        "Sign Mismatch (%)",
        "Polarity",
        "Sign Mismatch",
        "Percent of samples where the two non-deadband signals have opposite signs.",
        "Sign Mismatch = count(sign_eps(reference_i) == -sign_eps(candidate_i) and both non-zero) / n * 100",
        "Use this to highlight polarity reversals that can be hidden by aggregate magnitude metrics.",
        "If 40 of 200 aligned samples have opposite signs, Sign Mismatch = 20%.",
        "Lower is better. Inspect long red bands in the Sign Agreement tab for sustained polarity errors.",
        "Sign Agreement",
    ),
    "Sign Deadband (%)": _entry(
        "Sign Deadband (%)",
        "Polarity",
        "Sign Deadband Share",
        "Percent of samples ignored for polarity because at least one value is near zero.",
        "Sign Deadband = count(abs(reference_i) <= eps or abs(candidate_i) <= eps) / n * 100",
        "Use this to separate real polarity disagreements from sensor noise around zero.",
        "With eps = 0.1, values reference 0.03 or candidate -0.04 are neutral and count toward deadband.",
        "Moderate values are normal for zero crossings. Very high values mean polarity metrics are based on little decisive data.",
        "Sign Agreement",
    ),
    "Polarity Score": _entry(
        "Polarity Score",
        "Polarity",
        "Polarity Score",
        "Average signed polarity product after deadbanding.",
        "Polarity Score = mean(sign_eps(reference_i) * sign_eps(candidate_i))",
        "Use this as a compact direction score: +1 for consistently same sign, -1 for consistently opposite sign.",
        "Products [1, 1, -1, 0] average to 0.25, meaning mostly correct signs with one mismatch and one neutral point.",
        "Closer to +1 is better. Negative values indicate systematic sign inversion.",
        "Sign Agreement",
    ),
    "Longest Sign Mismatch (s)": _entry(
        "Longest Sign Mismatch (s)",
        "Polarity",
        "Longest Sign Mismatch Duration",
        "Longest continuous time span where signs are opposite.",
        "Longest Sign Mismatch = max(run_length_of_opposite_sign_samples) * median sample step",
        "Use this when sustained polarity reversal is more important than scattered individual mismatches.",
        "Five consecutive opposite-sign samples at 0.02 s spacing give a longest mismatch duration of 0.10 s.",
        "Lower is better. A long duration points to a phase, sign convention, or reference-axis problem.",
        "Sign Agreement",
    ),
    "Best Lag (samples)": _entry(
        "Best Lag (samples)",
        "Lag",
        "Best Lag in Samples",
        "Sample shift with the highest normalized lag correlation in the Lag tab.",
        "Best Lag = argmax_lag(corr(reference shifted by lag, candidate))",
        "Use this newer lag diagnostic for a bounded, channel-specific timing estimate.",
        "If the best correlation occurs when the candidate is shifted back two samples, Best Lag = -2.",
        "Near zero is expected after alignment. Consistent non-zero lag across channels suggests synchronization offset.",
        "Lag",
    ),
    "Best Lag (s)": _entry(
        "Best Lag (s)",
        "Lag",
        "Best Lag in Seconds",
        "Best lag converted from sample count to time.",
        "Best Lag (s) = Best Lag (samples) * median sample step",
        "Use this to compare timing offset against engineering time tolerances or acquisition trigger delays.",
        "A best lag of -4 samples with 0.005 s sampling gives -0.020 s.",
        "Near zero is expected. A stable non-zero value can guide manual synchronization in Configure Alignment.",
        "Lag",
    ),
    "Max Lag Correlation": _entry(
        "Max Lag Correlation",
        "Lag",
        "Maximum Lag Correlation",
        "Correlation value achieved at the best lag.",
        "Max Lag Correlation = max_lag(corr(reference shifted by lag, candidate))",
        "Use this with Best Lag to determine whether the lag estimate is trustworthy.",
        "A best lag of 3 samples with Max Lag Correlation 0.98 is strong evidence of a 3-sample timing offset.",
        "Closer to 1 is better. Low values mean no tested lag aligns the channel well.",
        "Lag",
    ),
    "Mean Event Timing Error (s)": _entry(
        "Mean Event Timing Error (s)",
        "Event",
        "Mean Event Timing Error",
        "Average absolute timing difference between paired detected events.",
        "Mean Event Timing Error = mean(abs(candidate_event_time_j - reference_event_time_j))",
        "Use this to compare physical event timing, such as zero crossings, peaks, valleys, or threshold crossings.",
        "If paired peak errors are [0.01, 0.03, 0.02] s, the mean event timing error is 0.02 s.",
        "Lower is better. If this is high while Best Lag is stable, try synchronization before judging amplitude fit.",
        "Events",
    ),
    "Max Event Timing Error (s)": _entry(
        "Max Event Timing Error (s)",
        "Event",
        "Maximum Event Timing Error",
        "Largest paired event timing difference.",
        "Max Event Timing Error = max(abs(candidate_event_time_j - reference_event_time_j))",
        "Use this to find the worst delayed peak, crossing, or threshold event.",
        "Paired zero-crossing errors [0.01, 0.04, 0.02] s give Max Event Timing Error = 0.04 s.",
        "Lower is better. A large value may indicate missed or extra events; check Event Count Delta and the Overlay tab.",
        "Events",
    ),
    "Event Count Delta": _entry(
        "Event Count Delta",
        "Event",
        "Event Count Delta",
        "Difference between detected candidate and reference event counts.",
        "Event Count Delta = abs(count(candidate_events) - count(reference_events))",
        "Use this to detect missing peaks, extra oscillations, or threshold chatter.",
        "If the reference has 6 peaks and the candidate has 8 peaks, Event Count Delta = 2.",
        "Lower is better. Non-zero values mean timing error summaries may be based on partial event pairing.",
        "Events",
    ),
    "Data Quality Warnings": _entry(
        "Data Quality Warnings",
        "Quality",
        "Data Quality Warning Count",
        "Total warning count from timestamp and channel-quality checks.",
        "Warning Count = flags(NaN, Inf, duplicate timestamps, jitter, flatlines, clipping, spikes)",
        "Use this before interpreting fit metrics. Bad input quality can produce misleading error, event, and frequency diagnostics.",
        "A channel with duplicate timestamps and spike candidates can have Warning Count = 2 even if its RMSE looks acceptable.",
        "Lower is better. Open the Data Quality tab to see which specific check triggered the count.",
        "Data Quality",
    ),
    "Calibration Slope": _entry(
        "Calibration Slope",
        "Calibration",
        "Calibration Slope",
        "Fitted gain mapping reference to candidate.",
        "candidate = slope * reference + offset",
        "Use slope to detect scale or gain mismatch between datasets.",
        "If candidate strain is approximately 1.08 times reference plus a small offset, Calibration Slope is about 1.08.",
        "Closer to 1 is usually better. Values above 1 mean the candidate changes more strongly than the reference.",
        "Calibration",
    ),
    "Calibration Offset": _entry(
        "Calibration Offset",
        "Calibration",
        "Calibration Offset",
        "Fitted constant bias after scale is considered.",
        "candidate = slope * reference + offset",
        "Use offset to detect zero-shift or tare mismatch between datasets.",
        "If candidate pressure is consistently 0.2 MPa high after scale correction, Calibration Offset is about +0.2 MPa.",
        "Closer to 0 is usually better. A large offset points to bias correction or sensor zeroing issues.",
        "Calibration",
    ),
    "Calibration R^2": _entry(
        "Calibration R^2",
        "Calibration",
        "Calibration Fit R^2",
        "Goodness of the fitted candidate-versus-reference calibration line.",
        "Calibration R^2 = 1 - sum(residual_fit^2) / sum((candidate_i - mean(candidate))^2)",
        "Use this to see whether a simple scale and offset can explain the candidate signal.",
        "If the fitted line residual sum is 2 and candidate total sum of squares is 100, Calibration R^2 = 0.98.",
        "Closer to 1 is better. Low values mean disagreement is not just a simple gain or offset problem.",
        "Calibration",
    ),
    "Residual Std": _entry(
        "Residual Std",
        "Calibration",
        "Calibration Residual Standard Deviation",
        "Scatter remaining after fitting scale and offset.",
        "Residual Std = std(candidate_i - (slope * reference_i + offset))",
        "Use this to judge how much unexplained variation remains after simple calibration.",
        "If calibrated residuals are [-0.1, 0.0, 0.1], Residual Std is small, so the linear correction explains most disagreement.",
        "Lower is better. High residual scatter means nonlinear behavior, timing mismatch, or noise remains.",
        "Calibration",
    ),
    "Dominant Freq Delta": _entry(
        "Dominant Freq Delta",
        "Frequency",
        "Dominant Frequency Delta",
        "Difference between each dataset's dominant FFT frequency.",
        "Dominant Freq Delta = candidate_dominant_frequency - reference_dominant_frequency",
        "Use this for cyclic or vibration-like signals when frequency content matters.",
        "If the reference peak is 12 Hz and candidate peak is 13 Hz, Dominant Freq Delta = +1 Hz.",
        "Near zero is expected for matching dynamics. Non-zero values suggest changed oscillation rate or sampling issues.",
        "Frequency",
    ),
    "Spectral Energy Ratio": _entry(
        "Spectral Energy Ratio",
        "Frequency",
        "Spectral Energy Ratio",
        "Candidate spectral energy divided by reference spectral energy.",
        "Spectral Energy Ratio = sum(abs(FFT(candidate))^2) / sum(abs(FFT(reference))^2)",
        "Use this to compare vibration or oscillation energy across datasets.",
        "If candidate spectral energy is 120 and reference energy is 100, Spectral Energy Ratio = 1.2.",
        "Near 1 is expected for similar energy. Values above 1 indicate stronger candidate oscillation energy; values below 1 indicate weaker energy.",
        "Frequency",
    ),
    "Certification Score": _entry(
        "Certification Score",
        "Certification",
        "Certification Screening Score",
        "Engineering screening score from 0 to 100 for ranking candidate validation channels.",
        "Score = weighted shape, peak-error, slope-error, sign-agreement, and data-quality terms",
        "Use this to sort channels for review. It is a screening aid, not an authority-approved pass/fail criterion.",
        "A channel with strong Pearson correlation, low peak error, near-unity slope, matching sign, and no data-quality warnings scores near 100.",
        "Higher is better. Review the Evidence Grade and Exclusion Reason columns before using a channel as certification evidence.",
        "Certification Ranking",
    ),
    "Peak Error (%)": _entry(
        "Peak Error (%)",
        "Certification",
        "Peak Error",
        "Absolute difference between test and FEA signed peak response, normalized by test peak magnitude.",
        "Peak Error = abs(FEA_peak - test_peak) / abs(test_peak) * 100",
        "Use this for static strain/load cases where peak response drives substantiation.",
        "If the test peak is 1000 microstrain and FEA peak is 920 microstrain, Peak Error is 8%.",
        "Lower is better. Large peak error can screen out a channel even when the trace shape looks similar.",
        "Certification Ranking",
    ),
    "Slope Error (%)": _entry(
        "Slope Error (%)",
        "Certification",
        "Slope Error",
        "Percent deviation of the calibration slope from one-to-one agreement.",
        "Slope Error = abs(Calibration Slope - 1) * 100",
        "Use this to catch scale-factor mismatch between the FEA and test response.",
        "A calibration slope of 0.92 gives Slope Error = 8%.",
        "Lower is better. A large value suggests amplitude scaling or load-path mismatch.",
        "Certification Ranking",
    ),
    "Envelope NMAE (%)": _entry(
        "Envelope NMAE (%)",
        "Certification",
        "Envelope Normalized Mean Absolute Error",
        "The robust normalized MAE reused as the channel-wide static-test envelope error.",
        "Envelope NMAE = Robust NMAE",
        "Use this as the broad agreement term when comparing channels with different strain magnitudes.",
        "If MAE is 15 microstrain and the robust channel envelope is 300 microstrain, Envelope NMAE is 5%.",
        "Lower is better. Pair it with Peak Error and the residual plot before selecting certification channels.",
        "Certification Ranking",
    ),
}


def metric_help_entry(metric_key: str) -> MetricHelpEntry:
    try:
        return METRIC_HELP[metric_key]
    except KeyError as exc:
        raise KeyError(f"No metric help entry exists for {metric_key!r}.") from exc


def metric_fallback_tooltip(metric_key: str) -> str:
    return metric_help_entry(metric_key).fallback


def metric_help_html(metric_key: str) -> str:
    entry = metric_help_entry(metric_key)
    return f"""
    <html>
    <head>
      <style>
        body {{
          margin: 0;
          font-family: "Segoe UI", Arial, sans-serif;
          color: #1e2a36;
          background: #ffffff;
          font-size: 10pt;
        }}
        h2 {{
          margin: 0 0 4px 0;
          color: #173f69;
          font-size: 14pt;
        }}
        .meta {{
          color: #647386;
          font-size: 9pt;
          margin-bottom: 10px;
        }}
        h3 {{
          margin: 12px 0 4px 0;
          color: #1c2a38;
          font-size: 10.5pt;
        }}
        p {{
          margin: 0 0 8px 0;
          line-height: 1.38;
        }}
        .formula {{
          background: #eef5fd;
          border: 1px solid #c8daef;
          border-radius: 4px;
          padding: 7px 8px;
          color: #173f69;
          font-family: Consolas, "Courier New", monospace;
          white-space: pre-wrap;
        }}
      </style>
    </head>
    <body>
      <h2>{escape(entry.title)}</h2>
      <div class="meta">{escape(entry.group)} metric | Related tab: {escape(entry.related_tab)}</div>
      <h3>Formula</h3>
      <p class="formula">{escape(entry.formula)}</p>
      <h3>What It Does In Practice</h3>
      <p>{escape(entry.practice)}</p>
      <h3>Example Problem</h3>
      <p>{escape(entry.example)}</p>
      <h3>How To Interpret It</h3>
      <p>{escape(entry.interpretation)}</p>
    </body>
    </html>
    """


def validate_metric_help_catalog(metric_keys: list[str] | tuple[str, ...]) -> list[str]:
    expected = set(metric_keys)
    actual = set(METRIC_HELP)
    errors: list[str] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"Missing metric help entries: {', '.join(missing)}")
    if extra:
        errors.append(f"Unexpected metric help entries: {', '.join(extra)}")
    for key in sorted(expected & actual):
        entry = METRIC_HELP[key]
        for field_name in (
            "title",
            "fallback",
            "formula",
            "practice",
            "example",
            "interpretation",
            "related_tab",
        ):
            if not getattr(entry, field_name).strip():
                errors.append(f"{key} has empty {field_name}.")
    return errors
