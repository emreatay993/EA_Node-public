from __future__ import annotations

from collections.abc import Iterator

from ea_node_editor.benchmarks.tabular.contracts import DatasetSpec, UnsupportedBenchmarkCaseError
from ea_node_editor.benchmarks.tabular.optional_imports import load_module

_DEFAULT_CHUNK_ROWS = 100_000


def table_supported(profile: str) -> bool:
    return profile in {"mixed_table", "dense_numeric", "wide_table", "tall_table", "excel_like"}


def array_supported(profile: str) -> bool:
    return profile in {"dense_numeric", "ndarray3d"}


def iter_table_chunks(spec: DatasetSpec, *, chunk_rows: int = _DEFAULT_CHUNK_ROWS) -> Iterator[object]:
    if not table_supported(spec.profile):
        raise UnsupportedBenchmarkCaseError(f"Profile '{spec.profile}' is not tabular.")

    remaining = spec.rows
    offset = 0
    while remaining > 0:
        rows = min(chunk_rows, remaining)
        yield make_table(spec, rows=rows, offset=offset)
        remaining -= rows
        offset += rows


def make_table(spec: DatasetSpec, *, rows: int | None = None, offset: int = 0) -> object:
    pd = load_module("pandas")
    np = load_module("numpy")

    row_count = spec.rows if rows is None else rows
    rng = np.random.default_rng(spec.seed + offset)
    column_count = _resolved_column_count(spec)
    numeric_count = max(2, column_count - 6)
    data = {
        f"numeric_{index}": rng.normal(loc=index, scale=1.0, size=row_count)
        for index in range(numeric_count)
    }

    if spec.profile != "dense_numeric":
        row_indexes = np.arange(offset, offset + row_count)
        data.update(
            {
                "group": np.array([f"G{value % 16:02d}" for value in row_indexes]),
                "category": np.array([f"C{value % 64:02d}" for value in row_indexes]),
                "text": np.array([f"item_{value % 1000:04d}" for value in row_indexes]),
                "flag": (row_indexes % 2) == 0,
                "timestamp": pd.Timestamp("2024-01-01")
                + pd.to_timedelta(row_indexes % 100_000, unit="s"),
            }
        )
        nullable = data["numeric_0"].copy()
        nullable[row_indexes % 10 == 0] = np.nan
        data["nullable"] = nullable

    frame = pd.DataFrame(data)
    if spec.profile == "wide_table":
        for index in range(len(frame.columns), column_count):
            frame[f"wide_{index}"] = rng.integers(0, 1_000_000, size=row_count)
    return frame


def make_array(spec: DatasetSpec) -> object:
    if not array_supported(spec.profile):
        raise UnsupportedBenchmarkCaseError(f"Profile '{spec.profile}' is not an array profile.")

    np = load_module("numpy")
    rng = np.random.default_rng(spec.seed)
    if spec.profile == "ndarray3d":
        depth = max(2, min(32, spec.columns))
        side = max(8, int((spec.rows * max(1, spec.columns) / depth) ** 0.5))
        return rng.normal(size=(depth, side, side)).astype("float64")
    return rng.normal(size=(spec.rows, max(2, spec.columns))).astype("float64")


def make_excel_sheets(spec: DatasetSpec) -> dict[str, object]:
    if spec.profile != "excel_like":
        return {"data": make_table(spec)}
    main = make_table(spec)
    pd = load_module("pandas")
    summary = pd.DataFrame(
        {
            "metric": ["rows", "columns", "seed"],
            "value": [len(main), len(main.columns), spec.seed],
        }
    )
    return {"data": main, "summary": summary}


def _resolved_column_count(spec: DatasetSpec) -> int:
    if spec.profile == "wide_table":
        return max(spec.columns, 128)
    if spec.profile == "dense_numeric":
        return max(spec.columns, 2)
    return max(spec.columns, 8)

