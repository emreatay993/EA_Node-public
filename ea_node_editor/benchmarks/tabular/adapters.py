from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ea_node_editor.benchmarks.tabular.contracts import (
    DatasetSpec,
    UnsupportedBenchmarkCaseError,
)
from ea_node_editor.benchmarks.tabular.datasets import (
    array_supported,
    iter_table_chunks,
    make_array,
    make_excel_sheets,
    make_table,
    table_supported,
)
from ea_node_editor.benchmarks.tabular.optional_imports import load_module

_MATERIALIZED_TABLE_ROW_LIMIT = 1_000_000
_EXCEL_MAX_ROWS = 1_048_576


class FormatAdapter(ABC):
    format_id: str
    extension: str
    kind: str = "table"

    def path_for(self, root: Path, spec: DatasetSpec) -> Path:
        safe_profile = spec.profile.replace("/", "_")
        return root / f"{safe_profile}_{spec.size}_{spec.rows}x{spec.columns}.{self.extension}"

    @abstractmethod
    def supports(self, spec: DatasetSpec) -> bool:
        raise NotImplementedError

    @abstractmethod
    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def read(self, path: Path, backend_id: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def schema(self, path: Path) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def row_count(self, path: Path) -> int | None:
        raise NotImplementedError


class DelimitedAdapter(FormatAdapter):
    kind = "table"

    def __init__(self, format_id: str, extension: str, separator: str) -> None:
        self.format_id = format_id
        self.extension = extension
        self.separator = separator

    def supports(self, spec: DatasetSpec) -> bool:
        return table_supported(spec.profile)

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        first_chunk = True
        rows_written = 0
        for chunk in iter_table_chunks(spec):
            chunk.to_csv(
                path,
                sep=self.separator,
                index=False,
                mode="w" if first_chunk else "a",
                header=first_chunk,
                lineterminator="\n",
            )
            rows_written += len(chunk)
            first_chunk = False
        return {"rows": rows_written, "columns": spec.columns}

    def read(self, path: Path, backend_id: str) -> Any:
        if backend_id == "pandas":
            pd = load_module("pandas")
            return pd.read_csv(path, sep=self.separator)
        if backend_id == "polars":
            pl = load_module("polars")
            return pl.read_csv(path, separator=self.separator)
        if backend_id == "arrow":
            pa_csv = load_module("pyarrow.csv")
            return pa_csv.read_csv(
                path,
                parse_options=pa_csv.ParseOptions(delimiter=self.separator),
            )
        if backend_id == "duckdb":
            duckdb = load_module("duckdb")
            con = duckdb.connect()
            return con.read_csv(str(path), sep=self.separator, header=True)
        if backend_id == "numpy":
            pd = load_module("pandas")
            return pd.read_csv(path, sep=self.separator).select_dtypes("number").to_numpy()
        raise UnsupportedBenchmarkCaseError(f"{backend_id} cannot read {self.format_id}.")

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        if backend_id == "polars":
            pl = load_module("polars")
            return pl.read_csv(path, separator=self.separator, n_rows=rows)
        if backend_id == "duckdb":
            relation = self.read(path, "duckdb")
            return relation.limit(rows).df()
        pd = load_module("pandas")
        return pd.read_csv(path, sep=self.separator, nrows=rows)

    def schema(self, path: Path) -> dict[str, str]:
        pd = load_module("pandas")
        frame = pd.read_csv(path, sep=self.separator, nrows=200)
        return {str(name): str(dtype) for name, dtype in frame.dtypes.items()}

    def row_count(self, path: Path) -> int | None:
        with path.open("r", encoding="utf-8", newline="") as handle:
            count = sum(1 for _ in handle)
        return max(0, count - 1)


class FixedWidthAdapter(FormatAdapter):
    format_id = "fixed_width_txt"
    extension = "fwf.txt"
    kind = "table"

    def supports(self, spec: DatasetSpec) -> bool:
        return table_supported(spec.profile)

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        rows_written = 0
        first_chunk = True
        for chunk in iter_table_chunks(spec):
            text = chunk.to_string(index=False, col_space=16, justify="left", header=first_chunk)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.write("\n")
            rows_written += len(chunk)
            first_chunk = False
        return {"rows": rows_written, "columns": spec.columns}

    def read(self, path: Path, backend_id: str) -> Any:
        pd = load_module("pandas")
        frame = pd.read_fwf(path)
        return _convert_pandas_frame(frame, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        pd = load_module("pandas")
        frame = pd.read_fwf(path, nrows=rows)
        return _convert_pandas_frame(frame, backend_id)

    def schema(self, path: Path) -> dict[str, str]:
        pd = load_module("pandas")
        frame = pd.read_fwf(path, nrows=200)
        return {str(name): str(dtype) for name, dtype in frame.dtypes.items()}

    def row_count(self, path: Path) -> int | None:
        with path.open("r", encoding="utf-8") as handle:
            return max(0, sum(1 for _ in handle) - 1)


class JsonLinesAdapter(FormatAdapter):
    format_id = "jsonl"
    extension = "jsonl"
    kind = "table"

    def supports(self, spec: DatasetSpec) -> bool:
        return table_supported(spec.profile)

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        rows_written = 0
        for chunk in iter_table_chunks(spec):
            chunk.to_json(path, orient="records", lines=True, mode="a", date_format="iso")
            rows_written += len(chunk)
        return {"rows": rows_written, "columns": spec.columns}

    def read(self, path: Path, backend_id: str) -> Any:
        if backend_id == "polars":
            pl = load_module("polars")
            return pl.read_ndjson(path)
        if backend_id == "arrow":
            pa_json = load_module("pyarrow.json")
            return pa_json.read_json(path)
        if backend_id == "duckdb":
            duckdb = load_module("duckdb")
            con = duckdb.connect()
            return con.sql(f"SELECT * FROM read_json_auto('{_sql_path(path)}')")
        pd = load_module("pandas")
        frame = pd.read_json(path, lines=True)
        return _convert_pandas_frame(frame, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        pd = load_module("pandas")
        lines: list[str] = []
        with path.open("r", encoding="utf-8") as handle:
            for _, line in zip(range(rows), handle):
                lines.append(line)
        from io import StringIO

        frame = pd.read_json(StringIO("".join(lines)), lines=True) if lines else pd.DataFrame()
        return _convert_pandas_frame(frame, backend_id)

    def schema(self, path: Path) -> dict[str, str]:
        frame = self.preview(path, rows=200, backend_id="pandas")
        return {str(name): str(dtype) for name, dtype in frame.dtypes.items()}

    def row_count(self, path: Path) -> int | None:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)


class NpyAdapter(FormatAdapter):
    format_id = "npy"
    extension = "npy"
    kind = "array"

    def supports(self, spec: DatasetSpec) -> bool:
        return array_supported(spec.profile)

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        np = load_module("numpy")
        path.parent.mkdir(parents=True, exist_ok=True)
        array = make_array(spec)
        np.save(path, array, allow_pickle=False)
        return {"rows": int(array.shape[0]), "columns": int(array.shape[-1]), "shape": tuple(array.shape)}

    def read(self, path: Path, backend_id: str) -> Any:
        np = load_module("numpy")
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        return _convert_array(array, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        np = load_module("numpy")
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        sliced = array[:rows]
        return _convert_array(sliced, backend_id)

    def schema(self, path: Path) -> dict[str, str]:
        np = load_module("numpy")
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        return {"shape": str(tuple(array.shape)), "dtype": str(array.dtype)}

    def row_count(self, path: Path) -> int | None:
        np = load_module("numpy")
        array = np.load(path, allow_pickle=False, mmap_mode="r")
        return int(array.shape[0])


class NpzAdapter(NpyAdapter):
    format_id = "npz"
    extension = "npz"

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        np = load_module("numpy")
        path.parent.mkdir(parents=True, exist_ok=True)
        array = make_array(spec)
        np.savez_compressed(path, data=array)
        return {"rows": int(array.shape[0]), "columns": int(array.shape[-1]), "shape": tuple(array.shape)}

    def read(self, path: Path, backend_id: str) -> Any:
        np = load_module("numpy")
        with np.load(path, allow_pickle=False) as archive:
            array = archive["data"]
            return _convert_array(array, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        np = load_module("numpy")
        with np.load(path, allow_pickle=False) as archive:
            return _convert_array(archive["data"][:rows], backend_id)

    def schema(self, path: Path) -> dict[str, str]:
        np = load_module("numpy")
        with np.load(path, allow_pickle=False) as archive:
            array = archive["data"]
            return {"shape": str(tuple(array.shape)), "dtype": str(array.dtype)}


class ParquetAdapter(FormatAdapter):
    format_id = "parquet"
    extension = "parquet"
    kind = "table"

    def supports(self, spec: DatasetSpec) -> bool:
        return table_supported(spec.profile)

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        pq = load_module("pyarrow.parquet")
        pa = load_module("pyarrow")
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = None
        rows_written = 0
        try:
            for chunk in iter_table_chunks(spec):
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema, compression="zstd")
                writer.write_table(table)
                rows_written += len(chunk)
        finally:
            if writer is not None:
                writer.close()
        return {"rows": rows_written, "columns": spec.columns}

    def read(self, path: Path, backend_id: str) -> Any:
        if backend_id == "pandas":
            pd = load_module("pandas")
            return pd.read_parquet(path)
        if backend_id == "polars":
            pl = load_module("polars")
            return pl.read_parquet(path)
        if backend_id == "arrow":
            pq = load_module("pyarrow.parquet")
            return pq.read_table(path)
        if backend_id == "duckdb":
            duckdb = load_module("duckdb")
            con = duckdb.connect()
            return con.read_parquet(str(path))
        if backend_id == "numpy":
            pd = load_module("pandas")
            return pd.read_parquet(path).select_dtypes("number").to_numpy()
        raise UnsupportedBenchmarkCaseError(f"{backend_id} cannot read parquet.")

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        if backend_id == "duckdb":
            return self.read(path, "duckdb").limit(rows).df()
        if backend_id == "polars":
            pl = load_module("polars")
            return pl.scan_parquet(path).head(rows).collect()
        pd = load_module("pandas")
        return pd.read_parquet(path).head(rows)

    def schema(self, path: Path) -> dict[str, str]:
        pq = load_module("pyarrow.parquet")
        schema = pq.read_schema(path)
        return {field.name: str(field.type) for field in schema}

    def row_count(self, path: Path) -> int | None:
        pq = load_module("pyarrow.parquet")
        metadata = pq.ParquetFile(path).metadata
        return None if metadata is None else int(metadata.num_rows)


class FeatherAdapter(ParquetAdapter):
    format_id = "feather"
    extension = "feather"

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        feather = load_module("pyarrow.feather")
        pa = load_module("pyarrow")
        if spec.rows > _MATERIALIZED_TABLE_ROW_LIMIT:
            raise UnsupportedBenchmarkCaseError("Feather generation is materialized in v1; use small/medium tiers.")
        frame = make_table(spec)
        feather.write_feather(pa.Table.from_pandas(frame, preserve_index=False), path)
        return {"rows": len(frame), "columns": len(frame.columns)}

    def read(self, path: Path, backend_id: str) -> Any:
        if backend_id == "pandas":
            pd = load_module("pandas")
            return pd.read_feather(path)
        if backend_id == "polars":
            pl = load_module("polars")
            return pl.read_ipc(path, memory_map=False)
        feather = load_module("pyarrow.feather")
        table = feather.read_table(path)
        return _convert_arrow_table(table, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        return _slice_rows(self.read(path, backend_id), rows)

    def schema(self, path: Path) -> dict[str, str]:
        feather = load_module("pyarrow.feather")
        table = feather.read_table(path)
        return {field.name: str(field.type) for field in table.schema}

    def row_count(self, path: Path) -> int | None:
        feather = load_module("pyarrow.feather")
        return int(feather.read_table(path, columns=[]).num_rows)


class OrcAdapter(ParquetAdapter):
    format_id = "orc"
    extension = "orc"

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        orc = load_module("pyarrow.orc")
        pa = load_module("pyarrow")
        if spec.rows > _MATERIALIZED_TABLE_ROW_LIMIT:
            raise UnsupportedBenchmarkCaseError("ORC generation is materialized in v1; use small/medium tiers.")
        frame = make_table(spec)
        for column in frame.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
            frame[column] = frame[column].astype("string")
        with path.open("wb") as handle:
            orc.write_table(pa.Table.from_pandas(frame, preserve_index=False), handle)
        return {"rows": len(frame), "columns": len(frame.columns)}

    def read(self, path: Path, backend_id: str) -> Any:
        orc = load_module("pyarrow.orc")
        with path.open("rb") as handle:
            table = orc.ORCFile(handle).read()
        return _convert_arrow_table(table, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        return _slice_rows(self.read(path, backend_id), rows)

    def schema(self, path: Path) -> dict[str, str]:
        orc = load_module("pyarrow.orc")
        with path.open("rb") as handle:
            schema = orc.ORCFile(handle).schema
        return {field.name: str(field.type) for field in schema}

    def row_count(self, path: Path) -> int | None:
        orc = load_module("pyarrow.orc")
        with path.open("rb") as handle:
            return int(orc.ORCFile(handle).read().num_rows)


class Hdf5Adapter(FormatAdapter):
    format_id = "hdf5"
    extension = "h5"
    kind = "hybrid"

    def supports(self, spec: DatasetSpec) -> bool:
        return table_supported(spec.profile) or array_supported(spec.profile)

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if array_supported(spec.profile):
            h5py = load_module("h5py")
            array = make_array(spec)
            with h5py.File(path, "w") as handle:
                handle.create_dataset("data", data=array, compression="gzip", chunks=True)
            return {"rows": int(array.shape[0]), "columns": int(array.shape[-1]), "shape": tuple(array.shape)}

        load_module("tables")
        if path.exists():
            path.unlink()
        first_chunk = True
        rows_written = 0
        for chunk in iter_table_chunks(spec):
            chunk.to_hdf(path, key="data", mode="w" if first_chunk else "a", format="table", append=not first_chunk)
            rows_written += len(chunk)
            first_chunk = False
        return {"rows": rows_written, "columns": spec.columns}

    def read(self, path: Path, backend_id: str) -> Any:
        if _hdf5_has_array_dataset(path):
            h5py = load_module("h5py")
            with h5py.File(path, "r") as handle:
                array = handle["data"][...]
            return _convert_array(array, backend_id)
        pd = load_module("pandas")
        frame = pd.read_hdf(path, key="data")
        return _convert_pandas_frame(frame, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        if _hdf5_has_array_dataset(path):
            h5py = load_module("h5py")
            with h5py.File(path, "r") as handle:
                array = handle["data"][:rows]
            return _convert_array(array, backend_id)
        pd = load_module("pandas")
        frame = pd.read_hdf(path, key="data", start=0, stop=rows)
        return _convert_pandas_frame(frame, backend_id)

    def schema(self, path: Path) -> dict[str, str]:
        if _hdf5_has_array_dataset(path):
            h5py = load_module("h5py")
            with h5py.File(path, "r") as handle:
                dataset = handle["data"]
                return {"shape": str(tuple(dataset.shape)), "dtype": str(dataset.dtype)}
        frame = self.preview(path, rows=200, backend_id="pandas")
        return {str(name): str(dtype) for name, dtype in frame.dtypes.items()}

    def row_count(self, path: Path) -> int | None:
        if _hdf5_has_array_dataset(path):
            h5py = load_module("h5py")
            with h5py.File(path, "r") as handle:
                return int(handle["data"].shape[0])
        pd = load_module("pandas")
        with pd.HDFStore(path, mode="r") as store:
            return int(store.get_storer("data").nrows)


class XlsxAdapter(FormatAdapter):
    format_id = "xlsx"
    extension = "xlsx"
    kind = "table"

    def supports(self, spec: DatasetSpec) -> bool:
        return table_supported(spec.profile) and spec.rows <= _EXCEL_MAX_ROWS

    def write(self, spec: DatasetSpec, path: Path) -> dict[str, Any]:
        if spec.rows > _EXCEL_MAX_ROWS:
            raise UnsupportedBenchmarkCaseError("XLSX cannot exceed 1,048,576 rows per sheet.")
        pd = load_module("pandas")
        load_module("openpyxl")
        path.parent.mkdir(parents=True, exist_ok=True)
        sheets = make_excel_sheets(spec)
        engine = "xlsxwriter"
        try:
            load_module("xlsxwriter")
        except Exception:
            engine = "openpyxl"
        with pd.ExcelWriter(path, engine=engine) as writer:
            for sheet_name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        main = sheets["data"]
        return {"rows": len(main), "columns": len(main.columns), "sheets": tuple(sheets)}

    def read(self, path: Path, backend_id: str) -> Any:
        pd = load_module("pandas")
        frame = pd.read_excel(path, sheet_name="data")
        return _convert_pandas_frame(frame, backend_id)

    def preview(self, path: Path, *, rows: int, backend_id: str) -> Any:
        pd = load_module("pandas")
        frame = pd.read_excel(path, sheet_name="data", nrows=rows)
        return _convert_pandas_frame(frame, backend_id)

    def schema(self, path: Path) -> dict[str, str]:
        frame = self.preview(path, rows=200, backend_id="pandas")
        return {str(name): str(dtype) for name, dtype in frame.dtypes.items()}

    def row_count(self, path: Path) -> int | None:
        openpyxl = load_module("openpyxl")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook["data"] if "data" in workbook.sheetnames else workbook.active
            return max(0, int(sheet.max_row) - 1)
        finally:
            workbook.close()


def available_format_adapters() -> dict[str, FormatAdapter]:
    adapters: tuple[FormatAdapter, ...] = (
        DelimitedAdapter("csv", "csv", ","),
        DelimitedAdapter("tsv", "tsv", "\t"),
        DelimitedAdapter("txt", "txt", "|"),
        FixedWidthAdapter(),
        JsonLinesAdapter(),
        NpyAdapter(),
        NpzAdapter(),
        ParquetAdapter(),
        FeatherAdapter(),
        Hdf5Adapter(),
        XlsxAdapter(),
        OrcAdapter(),
    )
    return {adapter.format_id: adapter for adapter in adapters}


def _convert_pandas_frame(frame: Any, backend_id: str) -> Any:
    if backend_id == "pandas":
        return frame
    if backend_id == "numpy":
        return frame.select_dtypes("number").to_numpy()
    if backend_id == "polars":
        pl = load_module("polars")
        return pl.from_pandas(frame)
    if backend_id == "arrow":
        pa = load_module("pyarrow")
        return pa.Table.from_pandas(frame, preserve_index=False)
    if backend_id == "duckdb":
        duckdb = load_module("duckdb")
        con = duckdb.connect()
        return con.from_df(frame)
    raise UnsupportedBenchmarkCaseError(f"Unknown backend: {backend_id}")


def _convert_arrow_table(table: Any, backend_id: str) -> Any:
    if backend_id == "arrow":
        return table
    if backend_id == "pandas":
        return table.to_pandas()
    if backend_id == "polars":
        pl = load_module("polars")
        return pl.from_arrow(table)
    if backend_id == "numpy":
        return table.to_pandas().select_dtypes("number").to_numpy()
    if backend_id == "duckdb":
        duckdb = load_module("duckdb")
        con = duckdb.connect()
        return con.from_arrow(table)
    raise UnsupportedBenchmarkCaseError(f"Unknown backend: {backend_id}")


def _convert_array(array: Any, backend_id: str) -> Any:
    if backend_id == "numpy":
        return array
    np = load_module("numpy")
    flat = np.asarray(array)
    if flat.ndim > 2:
        flat = flat.reshape(flat.shape[0], -1)
    pd = load_module("pandas")
    frame = pd.DataFrame(flat, columns=[f"value_{index}" for index in range(flat.shape[1])])
    return _convert_pandas_frame(frame, backend_id)


def _slice_rows(data: Any, rows: int) -> Any:
    if hasattr(data, "head"):
        return data.head(rows)
    if hasattr(data, "slice") and hasattr(data, "num_rows"):
        return data.slice(0, rows)
    if hasattr(data, "limit"):
        return data.limit(rows)
    return data[:rows]


def _hdf5_has_array_dataset(path: Path) -> bool:
    try:
        h5py = load_module("h5py")
        with h5py.File(path, "r") as handle:
            node = handle.get("data")
            return node is not None and hasattr(node, "shape")
    except Exception:
        return False


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''").replace("\\", "/")
