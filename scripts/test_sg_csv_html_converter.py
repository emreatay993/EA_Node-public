"""Headless round-trip tests for ``sg_csv_html_converter``.

Covers every SG label family and all five HTML export suffixes, asserting that:

* HTML -> CSV -> HTML preserves the value columns and y-data within tolerance.
* CSV -> HTML -> CSV preserves Time, every column header (incl. ``µ``/``Δ``/``°``/``%``),
  and every value.

The real exported fixtures under
``Sensor_Data_Comparison_Tool/mock_inputs/plotly_html`` are used as ground truth
where available, plus a synthetic full ``SG_calculations.csv`` spanning every family.

Run::

    python scripts/test_sg_csv_html_converter.py        # standalone
    pytest scripts/test_sg_csv_html_converter.py        # under pytest
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import sg_csv_html_converter as conv  # noqa: E402

FIXTURE_DIR = SCRIPT_DIR / "Sensor_Data_Comparison_Tool" / "mock_inputs" / "plotly_html"


# --------------------------------------------------------------------------- #
# Synthetic full SG_calculations.csv covering every label family
# --------------------------------------------------------------------------- #

def _make_full_frame(n: int = 40) -> pd.DataFrame:
    t = np.round(np.linspace(0.0, 120.0, n), 4)
    rng = np.linspace(-1.0, 1.0, n)
    data = {conv.TIME_COLUMN: t}
    for sg in (57, 58):
        # raw strain channels
        for ch in (1, 2, 3):
            data[f"SG{sg}_{ch}"] = np.round(100.0 * rng + sg + ch, 5)
        # global strains (microstrain)
        data[f"SG{sg}_epsilon_x [µe]"] = np.round(250.0 * rng + sg, 5)
        data[f"SG{sg}_epsilon_y [µe]"] = np.round(-180.0 * rng - sg, 5)
        data[f"SG{sg}_gamma_xy [µe]"] = np.round(60.0 * rng, 5)
        # stresses
        data[f"SG{sg}_sigma_1 [MPa]"] = np.round(420.0 * rng + sg * 2, 5)
        data[f"SG{sg}_sigma_2 [MPa]"] = np.round(120.0 * rng - sg, 5)
        data[f"SG{sg}_theta_p [°]"] = np.round(45.0 + 10.0 * rng, 5)
        data[f"SG{sg}_Biaxiality_Ratio"] = np.round(0.3 * rng, 5)
        data[f"SG{sg}_von_Mises [MPa]"] = np.round(np.abs(380.0 * rng) + sg, 5)
    # mixed channels
    data["Accel_Z [g]"] = np.round(9.81 + rng, 5)
    data["LVDT_Stroke [mm]"] = np.round(5.0 * rng, 5)
    return pd.DataFrame(data)


def _make_comparison_frame(n: int = 40) -> pd.DataFrame:
    """A frame whose columns already carry Δ and % markers (as the full CSV does)."""
    base = _make_full_frame(n)
    out = {conv.TIME_COLUMN: base[conv.TIME_COLUMN].to_numpy()}
    for col in base.columns:
        if col == conv.TIME_COLUMN:
            continue
        out[f"Δ{col}"] = np.round(base[col].to_numpy() * 0.05, 5)
        out[f"%{col}"] = np.round(base[col].to_numpy() * 0.5, 5)
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_csv_to_html_roundtrip_all_families(tmp_path):
    frame = _make_full_frame()
    csv_path = tmp_path / "SG_Calculations__Demo_Scn__All__main.csv"
    conv.dataframe_to_csv(frame, csv_path)

    result = conv.convert_csv_to_html(csv_path, tmp_path)
    assert result.ok, result.error
    assert result.output is not None and result.output.exists()

    # Re-import the HTML and confirm every family survived.
    reloaded = conv.html_to_dataframe(result.output)
    assert list(reloaded.columns) == list(frame.columns)
    for col in frame.columns:
        np.testing.assert_allclose(
            reloaded[col].to_numpy(float), frame[col].to_numpy(float),
            rtol=1e-6, atol=1e-6, err_msg=f"family column {col!r} drifted")

    # Unicode headers must survive byte-for-byte.
    for needle in ("[µe]", "[MPa]", "[°]", "Biaxiality_Ratio"):
        assert any(needle in c for c in reloaded.columns), needle


def test_csv_to_html_comparison_markers(tmp_path):
    frame = _make_comparison_frame()
    csv_path = tmp_path / "SG_Calculations__Demo_Scn__All__comparison.csv"
    conv.dataframe_to_csv(frame, csv_path)
    # Columns already carry Δ/% markers; the comparison suffix must NOT double them.
    result = conv.convert_csv_to_html(csv_path, tmp_path, suffix=conv.SUFFIX_COMPARISON)
    assert result.ok, result.error
    reloaded = conv.html_to_dataframe(result.output)
    assert list(reloaded.columns) == list(frame.columns)
    assert not any(c.startswith("ΔΔ") for c in reloaded.columns)


def test_each_suffix_styles_apply(tmp_path):
    """Each suffix sets its own title/hover/yaxis; only compared_data adds '*'."""
    frame = _make_full_frame(12)
    value_cols = [c for c in frame.columns if c != conv.TIME_COLUMN]
    for suffix, style in conv.SUFFIX_STYLES.items():
        fig = conv.build_figure(frame, scenario="Scn", group="grp", suffix=suffix)
        names = [tr.name for tr in fig.data]
        expected = [conv.header_to_trace_name(c, suffix) for c in value_cols]
        assert names == expected, suffix
        if suffix == conv.SUFFIX_COMPARED:
            assert all(n.startswith("*") for n in names)
        # hovertemplate matches the suffix family (percent has a trailing %)
        assert all(tr.hovertemplate == style.hovertemplate for tr in fig.data)
        # title carries the right prefix and yaxis the right label
        assert fig.layout.title.text.startswith(style.title_prefix)
        assert fig.layout.yaxis.title.text == style.yaxis_title


def test_overlay_pairs_main_comp(tmp_path):
    base = _make_full_frame(10)
    cols = [c for c in base.columns if c != conv.TIME_COLUMN][:3]
    data = {conv.TIME_COLUMN: base[conv.TIME_COLUMN].to_numpy()}
    for c in cols:
        data[f"Main: {c}"] = base[c].to_numpy()
        data[f"Comp: {c}"] = base[c].to_numpy() * 0.9
    frame = pd.DataFrame(data)
    csv_path = tmp_path / "SG_Calculations__Scn__grp__main_and_compared_data.csv"
    conv.dataframe_to_csv(frame, csv_path)
    result = conv.convert_csv_to_html(csv_path, tmp_path)
    assert result.ok, result.error
    reloaded = conv.html_to_dataframe(result.output)
    assert list(reloaded.columns) == list(frame.columns)
    # Comp: traces are dashed
    fig = conv.build_figure(frame, scenario="Scn", group="grp",
                            suffix=conv.SUFFIX_OVERLAY)
    for tr in fig.data:
        if tr.name.startswith("Comp:"):
            assert tr.line.dash == "dash"


def test_overlay_percentage_full_csv(tmp_path):
    """do_percentage on an overlay HTML -> a third comparison_full CSV
    (Time | main | Δ | %) whose headers parse under SG-annotations v0.74."""
    base = _make_full_frame(10)
    paired = ["SG57_sigma_1 [MPa]", "SG57_von_Mises [MPa]", "SG58_epsilon_x [µe]"]
    main_only = "SG58_von_Mises [MPa]"
    data = {conv.TIME_COLUMN: base[conv.TIME_COLUMN].to_numpy()}
    for c in paired:
        data[f"Main: {c}"] = base[c].to_numpy()
        data[f"Comp: {c}"] = base[c].to_numpy() * 0.9
    data[f"Main: {main_only}"] = base[main_only].to_numpy()  # no Comp counterpart
    overlay = pd.DataFrame(data)

    # Round-trip through a real overlay HTML so we exercise the import path.
    csv_path = tmp_path / "SG_Calculations__Scn__grp__main_and_compared_data.csv"
    conv.dataframe_to_csv(overlay, csv_path)
    html = conv.convert_csv_to_html(csv_path, tmp_path)
    assert html.ok, html.error

    result = conv.convert_html_to_csv(html.output, tmp_path, do_percentage=True)
    assert result.ok, result.error

    # main + compared_data splits, plus the new comparison_full CSV.
    pct_paths = [p for p in result.outputs if "comparison_full" in p.name]
    assert len(pct_paths) == 1, result.outputs
    pct = conv.csv_to_dataframe(pct_paths[0])

    main_cols = paired + [main_only]
    expected_cols = (
        [conv.TIME_COLUMN]
        + main_cols                       # all Main: cols, marker stripped
        + ["Δ" + c for c in paired]       # Δ block (common only)
        + ["%" + c for c in paired]       # % block (common only)
    )
    assert list(pct.columns) == expected_cols

    for c in paired:
        m = base[c].to_numpy(float)
        comp = m * 0.9
        np.testing.assert_allclose(pct["Δ" + c].to_numpy(float), m - comp,
                                   rtol=1e-6, atol=1e-6, equal_nan=True)
        np.testing.assert_allclose(pct["%" + c].to_numpy(float),
                                   (m / comp - 1.0) * 100.0,
                                   rtol=1e-6, atol=1e-6, equal_nan=True)

    # Every value-column header must satisfy the SG-annotations v0.74 contract.
    annot = re.compile(r"^[%Δ]?SG\d+_.+$")
    for c in pct.columns:
        if c == conv.TIME_COLUMN:
            continue
        assert annot.match(str(c)), c


def test_overlay_percentage_off_by_default(tmp_path):
    """Without do_percentage an overlay still yields exactly the two splits."""
    base = _make_full_frame(8)
    data = {conv.TIME_COLUMN: base[conv.TIME_COLUMN].to_numpy()}
    for c in ["SG57_von_Mises [MPa]"]:
        data[f"Main: {c}"] = base[c].to_numpy()
        data[f"Comp: {c}"] = base[c].to_numpy() * 0.8
    overlay = pd.DataFrame(data)
    csv_path = tmp_path / "SG_Calculations__Scn__grp__main_and_compared_data.csv"
    conv.dataframe_to_csv(overlay, csv_path)
    html = conv.convert_csv_to_html(csv_path, tmp_path)
    assert html.ok, html.error
    result = conv.convert_html_to_csv(html.output, tmp_path)
    assert result.ok, result.error
    assert not any("comparison_full" in p.name for p in result.outputs)
    assert len(result.outputs) == 2


def test_fixture_html_to_csv_to_html_roundtrip(tmp_path):
    if not FIXTURE_DIR.exists():
        return  # fixtures optional
    fixtures = sorted(FIXTURE_DIR.glob("SG_Calculations__*.html"))
    assert fixtures, "no fixtures found"
    for html in fixtures:
        original = conv.html_to_dataframe(html)          # verbatim trace names
        suffix = conv.parse_export_filename(html).suffix
        value_cols = [c for c in original.columns if c != conv.TIME_COLUMN]
        has_main = any(str(c).startswith("Main: ") for c in value_cols)
        has_comp = any(str(c).startswith("Comp: ") for c in value_cols)

        r1 = conv.convert_html_to_csv(html, tmp_path)
        assert r1.ok, f"{html.name}: {r1.error}"

        if has_main and has_comp:
            # Overlay -> two standalone CSVs (main + compared_data), base headers.
            assert len(r1.outputs) == 2, html.name
            by_suffix = {conv.parse_export_filename(p).suffix: p for p in r1.outputs}
            assert set(by_suffix) == {conv.SUFFIX_MAIN, conv.SUFFIX_COMPARED}, html.name
            for marker, out_suffix in (("Main: ", conv.SUFFIX_MAIN),
                                       ("Comp: ", conv.SUFFIX_COMPARED)):
                sub = conv.csv_to_dataframe(by_suffix[out_suffix])
                # base headers, no lingering Main:/Comp:/* markers
                assert not any(str(c).startswith(("Main:", "Comp:", "*"))
                               for c in sub.columns), html.name
                for c in value_cols:
                    if str(c).startswith(marker):
                        base = str(c)[len(marker):]
                        np.testing.assert_allclose(
                            sub[base].to_numpy(float), original[c].to_numpy(float),
                            rtol=1e-6, atol=1e-6, err_msg=f"{html.name}:{c}")
            continue

        # Single-dataset figure: one CSV with base SG headers; values unchanged.
        from_csv = conv.csv_to_dataframe(r1.output)
        expected_csv_cols = [conv.trace_name_to_header(c, suffix) for c in original.columns]
        assert list(from_csv.columns) == expected_csv_cols, html.name
        for orig_col, csv_col in zip(original.columns, from_csv.columns):
            np.testing.assert_allclose(
                from_csv[csv_col].to_numpy(float), original[orig_col].to_numpy(float),
                rtol=1e-6, atol=1e-6, err_msg=f"{html.name}:{orig_col}")

        # CSV -> HTML must reproduce the ORIGINAL figure exactly (markers re-applied).
        r2 = conv.convert_csv_to_html(r1.output, tmp_path)
        assert r2.ok, f"{html.name}: {r2.error}"
        round_html = conv.html_to_dataframe(r2.output)
        assert list(round_html.columns) == list(original.columns), html.name
        for col in original.columns:
            np.testing.assert_allclose(
                round_html[col].to_numpy(float), original[col].to_numpy(float),
                rtol=1e-6, atol=1e-6, err_msg=f"roundtrip {html.name}:{col}")


def test_non_finite_values_preserved(tmp_path):
    """NaN/inf (e.g. Biaxiality_Ratio = σ2/σ1) must survive the round trip."""
    frame = pd.DataFrame({
        conv.TIME_COLUMN: [0.0, 1.0, 2.0, 3.0],
        "SG1_Biaxiality_Ratio": [0.5, np.nan, np.inf, -0.3],
        "SG1_von_Mises [MPa]": [10.0, 20.0, 30.0, 40.0],
    })
    csv_path = tmp_path / "SG_Calculations__S__g__main.csv"
    conv.dataframe_to_csv(frame, csv_path)
    result = conv.convert_csv_to_html(csv_path, tmp_path)
    assert result.ok, result.error
    back = conv.html_to_dataframe(result.output)
    assert list(back.columns) == list(frame.columns)
    col = back["SG1_Biaxiality_Ratio"].to_numpy()
    assert np.isnan(col[1]) and np.isinf(col[2])


def test_filename_metadata_roundtrip():
    for suffix in conv.KNOWN_SUFFIXES:
        stem = f"SG_Calculations__Bladeout_Max_REF__von_Mises_MPa__{suffix}"
        meta = conv.parse_export_filename(stem + ".html")
        assert meta.matched
        assert meta.suffix == suffix
        assert meta.scenario == "Bladeout_Max_REF"
        assert meta.group == "von_Mises_MPa"
        assert conv.build_export_stem(meta) == stem


def test_filename_scenario_with_double_underscore():
    """The group is the token before the suffix; scenario may contain '__'."""
    meta = conv.parse_export_filename(
        "SG_Calculations__Run__A__von_Mises_MPa__comparison.html")
    assert meta.matched
    assert meta.suffix == "comparison"
    assert meta.group == "von_Mises_MPa"
    assert meta.scenario == "Run__A"


def test_unnamed_handling(tmp_path):
    """A stray index column is dropped, but a real trace named 'Unnamed: N' is kept."""
    import sg_csv_html_converter as c
    # Real value column literally named 'Unnamed: 7' must survive a CSV read.
    df = pd.DataFrame({conv.TIME_COLUMN: [0.0, 1.0, 2.0],
                       "Unnamed: 7": [10.0, 11.0, 12.0]})
    p = tmp_path / "keep.csv"
    conv.dataframe_to_csv(df, p)
    back = conv.csv_to_dataframe(p)
    assert "Unnamed: 7" in back.columns
    # A genuine 0..n-1 index artifact is dropped.
    raw = pd.DataFrame({"Unnamed: 0": [0, 1, 2],
                        conv.TIME_COLUMN: [0.0, 1.0, 2.0],
                        "SG1_x": [5.0, 6.0, 7.0]})
    raw_path = tmp_path / "with_index.csv"
    raw.to_csv(raw_path, index=False, encoding=conv.CSV_ENCODING)
    cleaned = conv.csv_to_dataframe(raw_path)
    assert "Unnamed: 0" not in cleaned.columns
    assert list(cleaned.columns) == [conv.TIME_COLUMN, "SG1_x"]


def test_nan_time_self_check_passes(tmp_path):
    """A NaN in the Time column must not trip a false-negative self-check."""
    frame = pd.DataFrame({conv.TIME_COLUMN: [0.0, np.nan, 2.0],
                          "SG1_von_Mises [MPa]": [1.0, 2.0, 3.0]})
    csv_path = tmp_path / "SG_Calculations__S__g__main.csv"
    conv.dataframe_to_csv(frame, csv_path)
    result = conv.convert_csv_to_html(csv_path, tmp_path)
    assert result.ok, result.error


# --------------------------------------------------------------------------- #
# Compatibility with the SG-annotations script (show_SG_annotations_*.py)
# --------------------------------------------------------------------------- #
# Faithful replica of that script's pure CSV-reading contract: HEADER_PATTERN,
# split_header_prefix and the group-detection in read_csv_file. The real script
# runs under IronPython, whose .NET StreamReader auto-strips the UTF-8 BOM, so
# we read utf-8-sig here to mirror it.

_ANN_HEADER_PATTERN = re.compile(r"^SG(\d+)_(.+)$")


def _ann_split_prefix(text):
    text = text.strip()
    if text.startswith("%"):
        return "percent", text[1:]
    if text.startswith("Δ"):
        return "delta", text[1:]
    if text.lower().startswith("delta"):
        return "delta", text[5:]
    return "base", text


def _ann_read_groups(path):
    """Return the SG result groups the annotations script would detect, or raise."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    if "Time" not in header:
        raise AssertionError("annotations script needs a 'Time' column")
    groups = {}
    for col in header:
        if col == "Time":
            continue
        prefix, body = _ann_split_prefix(col)
        m = _ANN_HEADER_PATTERN.match(body)
        if not m or not m.group(2).strip():
            continue
        groups.setdefault("%s|%s" % (prefix, m.group(2).strip()), 0)
        groups["%s|%s" % (prefix, m.group(2).strip())] += 1
    if not groups:
        raise AssertionError("no supported SG result columns for annotations script")
    return groups


def test_annotations_script_can_read_converter_csvs(tmp_path):
    """Every family the converter writes (including overlay Main: channels) must
    be parseable by the SG-annotations script."""
    if not FIXTURE_DIR.exists():
        return
    seen = set()
    for html in sorted(FIXTURE_DIR.glob("SG_Calculations__*.html")):
        seen.add(conv.parse_export_filename(html).suffix)
        r = conv.convert_html_to_csv(html, tmp_path)
        assert r.ok, f"{html.name}: {r.error}"
        # Every output CSV (an overlay yields two) must be annotation-readable
        # and free of display-only markers the annotator can't parse.
        for out in r.outputs:
            groups = _ann_read_groups(out)           # raises if incompatible
            assert groups, f"{html.name} -> {out.name}"
            with open(out, "r", encoding="utf-8-sig", newline="") as fh:
                header = next(csv.reader(fh))
            assert not any(c.startswith(("*", "Main:", "Comp:")) for c in header), out.name
    assert set(conv.KNOWN_SUFFIXES) <= seen, f"missing coverage: {set(conv.KNOWN_SUFFIXES) - seen}"


def test_overlay_splits_into_two_csvs(tmp_path):
    """An overlay export splits into main + compared_data CSVs, each a clean,
    annotation-readable SG_calculations table; values map to Main:/Comp:."""
    base = _make_full_frame(10)
    cols = [c for c in base.columns if c != conv.TIME_COLUMN and c.startswith("SG")][:3]
    data = {conv.TIME_COLUMN: base[conv.TIME_COLUMN].to_numpy()}
    for c in cols:
        data[f"Main: {c}"] = base[c].to_numpy()
        data[f"Comp: {c}"] = base[c].to_numpy() * 0.9
    overlay_frame = pd.DataFrame(data)
    # Write as an overlay HTML, then convert that HTML to CSV (the real workflow).
    html_path = tmp_path / "SG_Calculations__Scn__grp__main_and_compared_data.html"
    conv.dataframe_to_html(overlay_frame, html_path,
                           scenario="Scn", group="grp", suffix=conv.SUFFIX_OVERLAY)
    r = conv.convert_html_to_csv(html_path, tmp_path)
    assert r.ok, r.error

    # Two outputs: a main CSV and a compared_data CSV.
    assert len(r.outputs) == 2
    by_suffix = {conv.parse_export_filename(p).suffix: p for p in r.outputs}
    assert set(by_suffix) == {conv.SUFFIX_MAIN, conv.SUFFIX_COMPARED}

    for out_suffix, factor in ((conv.SUFFIX_MAIN, 1.0), (conv.SUFFIX_COMPARED, 0.9)):
        path = by_suffix[out_suffix]
        groups = _ann_read_groups(path)               # raises if not annotation-readable
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            header = next(csv.reader(fh))
        # No lingering Main:/Comp:/* markers in either file.
        assert not any(h.startswith(("Main:", "Comp:", "*")) for h in header)
        sub = conv.csv_to_dataframe(path)
        for c in cols:
            token = c.split("_", 1)[1]
            assert f"base|{token}" in groups, (out_suffix, c)
            np.testing.assert_allclose(
                sub[c].to_numpy(float), base[c].to_numpy(float) * factor,
                rtol=1e-6, atol=1e-6, err_msg=f"{out_suffix}:{c}")


def test_synthetic_full_csv_is_annotations_readable(tmp_path):
    """A synthetic SG_calculations.csv (all families, Δ/% columns) parses, and
    every base measurement token is recognised by the annotator."""
    frame = _make_full_frame()
    csv_path = tmp_path / "SG_Calculations__Scn__All__main.csv"
    conv.dataframe_to_csv(frame, csv_path)
    groups = _ann_read_groups(csv_path)
    for token in ("epsilon_x [µe]", "gamma_xy [µe]", "sigma_1 [MPa]",
                  "von_Mises [MPa]", "theta_p [°]", "Biaxiality_Ratio"):
        assert f"base|{token}" in groups, token


def _run_standalone() -> int:
    import tempfile
    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        with tempfile.TemporaryDirectory() as td:
            try:
                test(Path(td))
            except TypeError:
                test()  # tests without a tmp_path parameter
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {test.__name__}: {exc}")
            else:
                print(f"ok   {test.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
