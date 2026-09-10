from __future__ import annotations

import math

import numpy as np
import pytest

from ea_node_editor.execution.plot_series_decimation import (
    DECIMATION_METHOD_MINMAX,
    DECIMATION_METHOD_NONE,
    DECIMATION_METHOD_STRIDE,
    decimate_xy,
    stride_sample_indices,
    stride_sample_rows,
)


def test_small_series_pass_through_unchanged() -> None:
    x = [0.0, 1.0, 2.0]
    y = [5.0, -1.0, 3.0]
    out_x, out_y, meta = decimate_xy(x, y, 4000)
    assert out_x == x
    assert out_y == y
    assert meta == {"method": DECIMATION_METHOD_NONE, "original_rows": 3, "points": 3}


def test_budget_is_respected_and_extremes_preserved() -> None:
    rng = np.random.default_rng(7)
    y = rng.normal(size=400_000)
    spike_high = 1e6
    spike_low = -1e6
    y[123_456] = spike_high
    y[321_000] = spike_low
    x = np.arange(y.size, dtype=np.float64)

    out_x, out_y, meta = decimate_xy(x, y, 4000)

    assert meta["method"] == DECIMATION_METHOD_MINMAX
    assert meta["original_rows"] == 400_000
    assert meta["points"] == len(out_y) == len(out_x)
    assert len(out_y) <= 4000
    assert max(out_y) == spike_high
    assert min(out_y) == spike_low
    # x stays monotonically non-decreasing (row order preserved)
    assert all(b >= a for a, b in zip(out_x, out_x[1:]))
    # first/last samples always survive
    assert out_x[0] == 0.0
    assert out_x[-1] == float(y.size - 1)


def test_non_finite_rows_are_dropped_like_legacy_row_filtering() -> None:
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [1.0, math.nan, 3.0, math.inf, 5.0]
    out_x, out_y, meta = decimate_xy(x, y, 4000)
    assert out_x == [0.0, 2.0, 4.0]
    assert out_y == [1.0, 3.0, 5.0]
    assert meta["original_rows"] == 5
    assert meta["points"] == 3


def test_all_nan_series_returns_empty() -> None:
    out_x, out_y, meta = decimate_xy([0.0, 1.0], [math.nan, math.nan], 10)
    assert out_x == []
    assert out_y == []
    assert meta["points"] == 0


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        decimate_xy([0.0, 1.0], [1.0], 100)


def test_envelope_is_visually_faithful_per_bucket() -> None:
    # A sine sweep decimated to 1% must keep the full amplitude envelope.
    x = np.linspace(0.0, 100.0 * np.pi, 200_000)
    y = np.sin(x)
    _out_x, out_y, meta = decimate_xy(x, y, 2000)
    assert meta["points"] <= 2000
    assert max(out_y) == pytest.approx(1.0, abs=1e-3)
    assert min(out_y) == pytest.approx(-1.0, abs=1e-3)


def test_stride_sample_indices_bounds_and_endpoints() -> None:
    indices = stride_sample_indices(1_000_000, 4000)
    assert len(indices) <= 4000
    assert indices[0] == 0
    assert indices[-1] == 999_999
    small = stride_sample_indices(10, 4000)
    assert list(small) == list(range(10))


def test_gap_preserving_envelope_keeps_each_run_extrema_and_source_order() -> None:
    x = np.arange(1000, dtype=float)
    y = np.sin(x)
    y[100:200] = np.nan
    x[500:520] = np.nan
    out_x, out_y, meta = decimate_xy(x, y, 40, preserve_gaps=True)
    finite = np.isfinite(out_x) & np.isfinite(out_y)
    assert len(out_y) == meta["points"] <= 40
    assert np.count_nonzero(finite[1:] != finite[:-1]) == 4
    assert out_x[0] == 0 and out_x[-1] == 999
    assert np.all(np.diff(np.asarray(out_x)[np.isfinite(out_x)]) > 0)
    for start, stop in ((0, 100), (200, 500), (520, 1000)):
        assert float(y[start:stop].min()) in out_y
        assert float(y[start:stop].max()) in out_y
    assert np.isnan(y[100:200]).all() and np.isnan(x[500:520]).all()
    with pytest.raises(ValueError, match="gap topology"):
        decimate_xy(x, y, 3, preserve_gaps=True)
    full_x, full_y, meta = decimate_xy(x, y, 0, preserve_gaps=True)
    np.testing.assert_equal(full_x, x)
    np.testing.assert_equal(full_y, y)
    assert meta["method"] == DECIMATION_METHOD_NONE


def test_stride_sample_rows_meta() -> None:
    rows = [[float(i), float(i)] for i in range(10_000)]
    sampled, meta = stride_sample_rows(rows, 100)
    assert meta["method"] == DECIMATION_METHOD_STRIDE
    assert meta["original_rows"] == 10_000
    assert len(sampled) == meta["points"] <= 100
    assert sampled[0] == [0.0, 0.0]
    assert sampled[-1] == [9999.0, 9999.0]

    passthrough, meta_none = stride_sample_rows(rows[:5], 100)
    assert meta_none["method"] == DECIMATION_METHOD_NONE
    assert passthrough == rows[:5]
