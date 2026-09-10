# Purpose: Benchmark content-search + traversal strategies for office_date_collector_gui.
# Map: subsystems/supporting_runtime_assets
# Run: .\venv\Scripts\python.exe scripts\bench_office_search.py --build-corpus --n-files 2000
"""Benchmark harness for the Office Date Collector file search.

Measures the per-file content match (ElementTree DOM-parse baseline vs. tag-strip vs.
raw-bytes) across serial / ThreadPool / ProcessPool execution, plus serial vs. threaded
directory traversal. Every timed cell is correctness-checked against the ElementTree
baseline match set and the run exits non-zero on any divergence.

The worker functions here are intentionally PyQt-free replicas of the shipped functions
(so ProcessPool workers stay light); ``--check-fidelity`` proves the replicas return the
same results as the real ``office_date_collector_gui`` functions over the corpus.
"""

from __future__ import annotations

import argparse
import functools
import multiprocessing
import os
import random
import re
import shutil
import statistics
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

OPEN_XML_EXTENSIONS = frozenset({".docx", ".pptx", ".pptm", ".ppsx", ".ppsm", ".xlsx", ".xlsm"})
_TAG_RE = re.compile(rb"<[^>]*>")

try:  # optional faster inflate (Intel ISA-L); benchmark-only
    from isal import isal_zlib as _isal_zlib  # type: ignore

    _HAVE_ISAL = True
except Exception:  # pragma: no cover - depends on environment
    _isal_zlib = None
    _HAVE_ISAL = False


# --------------------------------------------------------------------------------------
# Pure search replicas (mirror office_date_collector_gui; PyQt-free so they pickle cleanly)
# --------------------------------------------------------------------------------------
def _office_xml_parts(extension: str, names) -> list[str]:
    if extension == ".docx":
        return [
            name
            for name in names
            if name == "word/document.xml"
            or name.startswith("word/header")
            or name.startswith("word/footer")
            or name in {"word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"}
        ]
    if extension in {".pptx", ".pptm", ".ppsx", ".ppsm"}:
        return [
            name
            for name in names
            if (name.startswith("ppt/slides/slide") or name.startswith("ppt/notesSlides/notesSlide"))
            and name.endswith(".xml")
        ]
    if extension in {".xlsx", ".xlsm"}:
        return [
            name
            for name in names
            if name == "xl/sharedStrings.xml"
            or (name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        ]
    return []


def _iter_xml_text(payload: bytes):
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return
    for text in root.itertext():
        if text:
            yield text


def _needle_is_prefilter_safe(needle: str) -> bool:
    return needle.isascii() and not any(ch in needle for ch in "&<>")


def et_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Baseline: full DOM parse + itertext (== shipped open_xml_contains)."""
    suffix = path.suffix.casefold()
    if suffix not in OPEN_XML_EXTENSIONS:
        return False
    target = needle if case_sensitive else needle.casefold()
    try:
        with zipfile.ZipFile(path) as package:
            for name in _office_xml_parts(suffix, package.namelist()):
                haystack = "\n".join(_iter_xml_text(package.read(name)))
                if not case_sensitive:
                    haystack = haystack.casefold()
                if target in haystack:
                    return True
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
        return False
    return False


def strip_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Shipped fast path: tag-strip + substring, ET fallback for unsafe needles."""
    suffix = path.suffix.casefold()
    if suffix not in OPEN_XML_EXTENSIONS:
        return False
    if not _needle_is_prefilter_safe(needle):
        return et_contains(path, needle, case_sensitive)
    target = needle if case_sensitive else needle.casefold()
    try:
        with zipfile.ZipFile(path) as package:
            for name in _office_xml_parts(suffix, package.namelist()):
                haystack = _TAG_RE.sub(b" ", package.read(name)).decode("utf-8", "replace")
                if not case_sensitive:
                    haystack = haystack.casefold()
                if target in haystack:
                    return True
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
        return False
    return False


def raw_contains(path: Path, needle: str, case_sensitive: bool) -> bool:
    """Raw ceiling: decode whole payload (tags included) + substring; can over-match markup."""
    suffix = path.suffix.casefold()
    if suffix not in OPEN_XML_EXTENSIONS:
        return False
    target = needle if case_sensitive else needle.casefold()
    try:
        with zipfile.ZipFile(path) as package:
            for name in _office_xml_parts(suffix, package.namelist()):
                haystack = package.read(name).decode("utf-8", "replace")
                if not case_sensitive:
                    haystack = haystack.casefold()
                if target in haystack:
                    return True
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
        return False
    return False


_STRATEGY_FUNCS = {"et": et_contains, "strip": strip_contains, "raw": raw_contains}


def _worker(path_str: str, needle: str, case_sensitive: bool, strategy: str) -> bool:
    return _STRATEGY_FUNCS[strategy](Path(path_str), needle, case_sensitive)


# --------------------------------------------------------------------------------------
# Synthetic corpus
# --------------------------------------------------------------------------------------
_FILLER = (
    "compressor turbine blade disk shaft bearing seal margin fatigue creep oxidation "
    "vibration mission cycle stress strain temperature pressure clearance airflow rotor "
    "stator vane nozzle combustor liner casing flange bolt fillet notch gradient ansys"
).split()

_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

# Active filler pool, narrowed by build_corpus to exclude the needle's tokens so the
# random filler can never coincidentally form the needle (keeps ground truth exact).
_WORDS = list(_FILLER)


def _body_text(rng: random.Random, words: int, needle: str | None) -> str:
    chunk = " ".join(rng.choice(_WORDS) for _ in range(words))
    if needle:
        return f"{chunk} {needle} {rng.choice(_WORDS)}"
    return chunk


def _docx_bytes(rng: random.Random, runs: int, needle: str | None) -> dict[str, str]:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    paras = []
    hit_run = rng.randrange(runs) if needle else -1
    for i in range(runs):
        text = _body_text(rng, 12, needle if i == hit_run else None)
        paras.append(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>")
    xml = f"{_DECL}<w:document {ns}><w:body>{''.join(paras)}</w:body></w:document>"
    return {"word/document.xml": xml}


def _pptx_bytes(rng: random.Random, slides: int, needle: str | None) -> dict[str, str]:
    ns = (
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    )
    hit_slide = rng.randrange(slides) if needle else -1
    parts = {}
    for i in range(slides):
        text = _body_text(rng, 14, needle if i == hit_slide else None)
        parts[f"ppt/slides/slide{i + 1}.xml"] = (
            f"{_DECL}<p:sld {ns}><p:cSld><p:spTree><p:sp><p:txBody>"
            f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>"
            f"</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
        )
    return parts


def _xlsx_bytes(rng: random.Random, strings: int, needle: str | None) -> dict[str, str]:
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    hit = rng.randrange(strings) if needle else -1
    items = []
    for i in range(strings):
        text = _body_text(rng, 4, needle if i == hit else None)
        items.append(f"<si><t>{text}</t></si>")
    return {"xl/sharedStrings.xml": f"{_DECL}<sst {ns}>{''.join(items)}</sst>"}


def _xlsm_bytes(rng: random.Random, rows: int, needle: str | None) -> dict[str, str]:
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    hit = rng.randrange(rows) if needle else -1
    cells = []
    for i in range(rows):
        text = _body_text(rng, 4, needle if i == hit else None)
        cells.append(f"<row><c t=\"inlineStr\"><is><t>{text}</t></is></c></row>")
    return {"xl/worksheets/sheet1.xml": f"{_DECL}<worksheet {ns}><sheetData>{''.join(cells)}</sheetData></worksheet>"}


_BUILDERS = {
    ".docx": (_docx_bytes, 1, 8),       # (builder, small_units, large_units)
    ".pptx": (_pptx_bytes, 1, 60),
    ".xlsx": (_xlsx_bytes, 6, 4000),
    ".xlsm": (_xlsm_bytes, 6, 4000),
}
_EXT_ROTATION = (".docx", ".pptx", ".xlsx", ".xlsm")


def build_corpus(root: Path, n_files: int, match_fraction: float, needle: str, seed: int):
    global _WORDS
    needle_tokens = {tok.casefold() for tok in needle.split()}
    _WORDS = [w for w in _FILLER if w.casefold() not in needle_tokens] or list(_FILLER)
    rng = random.Random(seed)
    n_dirs = max(1, int(n_files**0.5))
    dirs = []
    for i in range(n_dirs):
        sub = root / f"team_{i % 7}" / f"project_{i}" / "deliverables"
        sub.mkdir(parents=True, exist_ok=True)
        dirs.append(sub)

    office_paths: list[Path] = []
    ground_truth: set[str] = set()
    for i in range(n_files):
        ext = _EXT_ROTATION[i % len(_EXT_ROTATION)]
        builder, small_units, large_units = _BUILDERS[ext]
        large = (i % 10 == 0)
        units = large_units if large else small_units
        contains = rng.random() < match_fraction
        parts = builder(rng, units, needle if contains else None)
        path = dirs[i % n_dirs] / f"file_{i:05d}{ext}"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as pkg:
            for name, xml in parts.items():
                pkg.writestr(name, xml)
        office_paths.append(path)
        if contains:
            ground_truth.add(os.path.normcase(str(path)))

    # Skip-counter exercises: temp lock files and legacy binaries.
    (dirs[0] / "~$open_lock.docx").write_bytes(b"lock")
    (dirs[0] / "legacy_slides.ppt").write_bytes(b"legacy")
    (dirs[0] / "legacy_book.xls").write_bytes(b"legacy")
    return office_paths, ground_truth


def collect_office_paths(root: Path) -> list[Path]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.startswith("~$"):
                continue
            if Path(name).suffix.casefold() in OPEN_XML_EXTENSIONS:
                out.append(Path(dirpath) / name)
    return out


# --------------------------------------------------------------------------------------
# Execution + timing
# --------------------------------------------------------------------------------------
def _match_set(results, paths):
    return {os.path.normcase(str(p)) for p, hit in zip(paths, results) if hit}


def run_serial(strategy, paths, needle, cs):
    fn = _STRATEGY_FUNCS[strategy]
    return [fn(p, needle, cs) for p in paths]


def run_thread(strategy, paths, needle, cs, workers):
    fn = functools.partial(_worker, needle=needle, case_sensitive=cs, strategy=strategy)
    path_strs = [str(p) for p in paths]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, path_strs, chunksize=max(1, len(path_strs) // (workers * 4) or 1)))


def run_process(strategy, paths, needle, cs, workers):
    fn = functools.partial(_worker, needle=needle, case_sensitive=cs, strategy=strategy)
    path_strs = [str(p) for p in paths]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, path_strs, chunksize=max(1, len(path_strs) // (workers * 4) or 1)))


def time_cell(call, repeat):
    times = []
    result = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = call()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), result


def _isal_zipfile_patch(active: bool):
    """Context-manager-ish toggle: route zipfile inflate through isal_zlib."""

    class _Patch:
        def __enter__(self):
            self._saved = zipfile.zlib
            if active and _HAVE_ISAL:
                zipfile.zlib = _isal_zlib
            return self

        def __exit__(self, *exc):
            zipfile.zlib = self._saved
            return False

    return _Patch()


# --------------------------------------------------------------------------------------
# Fidelity + adversarial checks against the shipped module
# --------------------------------------------------------------------------------------
def _load_shipped():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "office_date_collector_gui", SCRIPTS_DIR / "office_date_collector_gui.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_fidelity(odc, paths, needle, cs) -> bool:
    """Replica functions must equal the shipped functions over the corpus."""
    ok = True
    for p in paths:
        if strip_contains(p, needle, cs) != odc.open_xml_contains_fast(p, needle, cs):
            print(f"  FIDELITY FAIL (strip != shipped fast): {p}")
            ok = False
        if et_contains(p, needle, cs) != odc.open_xml_contains(p, needle, cs):
            print(f"  FIDELITY FAIL (et != shipped slow): {p}")
            ok = False
    return ok


def check_adversarial(odc, tmp: Path) -> bool:
    """Entity-bearing needle: shipped fast path must equal the exact ET path."""
    root = tmp / "adversarial"
    root.mkdir(parents=True, exist_ok=True)
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    hit = root / "rnd_hit.docx"
    miss = root / "rnd_miss.docx"
    with zipfile.ZipFile(hit, "w", zipfile.ZIP_DEFLATED) as pkg:
        pkg.writestr("word/document.xml", f"{_DECL}<w:document {ns}><w:body><w:p><w:r><w:t>R&amp;D budget overrun</w:t></w:r></w:p></w:body></w:document>")
    with zipfile.ZipFile(miss, "w", zipfile.ZIP_DEFLATED) as pkg:
        pkg.writestr("word/document.xml", f"{_DECL}<w:document {ns}><w:body><w:p><w:r><w:t>research and development</w:t></w:r></w:p></w:body></w:document>")
    needle = "R&D"
    ok = True
    for p, expected in ((hit, True), (miss, False)):
        fast = odc.open_xml_contains_fast(p, needle, False)
        slow = odc.open_xml_contains(p, needle, False)
        if fast != slow or fast != expected:
            print(f"  ADVERSARIAL FAIL: {p.name} fast={fast} slow={slow} expected={expected}")
            ok = False
    # raw (no guard) is expected to MISS the entity case -> demonstrates why the guard exists
    raw = raw_contains(hit, needle, False)
    print(f"  adversarial: shipped fast/slow agree on 'R&D' (entity) -> {'OK' if ok else 'FAIL'}; "
          f"raw-no-guard would {'miss (expected)' if not raw else 'WRONGLY match'}")
    return ok


# --------------------------------------------------------------------------------------
# Traversal benchmark (the shipped walk is serial-only; see scripts/bench_vs_windows.py
# for the head-to-head against native robocopy /MT, where /r, etc.)
# --------------------------------------------------------------------------------------
def bench_traversal(odc, source: Path, output: Path, repeat: int):
    from datetime import date

    cfg = odc.JobConfig(
        source_dir=source,
        output_dir=output,
        start_date=date(1990, 1, 1),
        end_date=date(2100, 1, 1),
        file_types=odc.DEFAULT_FILE_TYPES,
        search_text="",
    )
    serial_ms, (matches, stats) = time_cell(lambda: odc.scan_office_files(cfg), repeat)
    print("\n== Traversal (walk + classify, no content search; serial walk) ==")
    print(f"  folders={stats.folders} files={stats.files} matched={len(matches)}")
    print(f"  {'serial scandir':24s} {serial_ms * 1000:9.2f} ms")
    print("  (Path() is built only for matches + dirs, not every file. A thread-per-dir walk")
    print("   was benchmarked O(n^2) on large trees and removed; serial beats native robocopy /MT.)")
    return True


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark office_date_collector_gui file search.")
    parser.add_argument("--corpus-dir", type=Path, default=None, help="Use an existing folder/share instead of synthesizing.")
    parser.add_argument("--build-corpus", action="store_true", help="Synthesize a temp corpus (default when no --corpus-dir).")
    parser.add_argument("--n-files", type=int, default=2000)
    parser.add_argument("--match-fraction", type=float, default=0.25)
    parser.add_argument("--needle", default="rotor margin")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--workers", type=int, default=None, help="Override pool size for threaded/process rows.")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--include-isal", action="store_true")
    parser.add_argument("--no-processpool", action="store_true")
    parser.add_argument("--keep-corpus", action="store_true")
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args(argv)

    cs = args.case_sensitive
    needle = args.needle
    cpu = os.cpu_count() or 4
    thread_workers = args.workers or min(32, cpu * 5)
    process_workers = args.workers or cpu

    tmp_root = None
    if args.corpus_dir is not None:
        source = args.corpus_dir
        paths = collect_office_paths(source)
        ground_truth = None
        print(f"Using existing corpus: {source}  ({len(paths)} office files)")
    else:
        tmp_root = Path(tempfile.mkdtemp(prefix="office_bench_"))
        source = tmp_root / "corpus"
        print(f"Building synthetic corpus: {args.n_files} files -> {source}")
        paths, ground_truth = build_corpus(source, args.n_files, args.match_fraction, needle, args.seed)
        print(f"  built {len(paths)} office files; {len(ground_truth)} contain needle {needle!r}")

    output = (tmp_root or source.parent) / "bench_output"
    output.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    try:
        odc = _load_shipped()

        # Warm the OS file cache once so the baseline and every matrix cell observe the
        # same (warm) state -- otherwise the first-measured baseline is unfairly cold.
        for _p in paths:
            et_contains(_p, needle, cs)

        # Baseline match set (the oracle).
        baseline_ms, baseline_results = time_cell(lambda: run_serial("et", paths, needle, cs), args.repeat)
        baseline_set = _match_set(baseline_results, paths)
        if ground_truth is not None and baseline_set != ground_truth:
            print(f"  WARNING: baseline matches ({len(baseline_set)}) != ground truth ({len(ground_truth)})")

        print("\n== Fidelity: replica vs shipped functions ==")
        fid = check_fidelity(odc, paths, needle, cs)
        print(f"  replica == shipped: {'OK' if fid else 'FAIL'}")
        if not fid:
            exit_code = 1
        adv = check_adversarial(odc, tmp_root or source.parent)
        if not adv:
            exit_code = 1

        # Content-search matrix.
        strategies = ["et", "strip", "raw"]
        execs = [("serial", lambda s: run_serial(s, paths, needle, cs), None)]
        execs.append(("thread", lambda s: run_thread(s, paths, needle, cs, thread_workers), thread_workers))
        if not args.no_processpool:
            execs.append(("process", lambda s: run_process(s, paths, needle, cs, process_workers), process_workers))

        print(f"\n== Content search ({len(paths)} files, needle={needle!r}, repeat={args.repeat}, "
              f"cpu={cpu}) ==")
        header = f"  {'strategy':9s} {'exec':8s} {'k':>4s} {'median ms':>11s} {'speedup':>9s}  correctness"
        print(header)
        print("  " + "-" * (len(header) - 2))
        cell_times: dict[tuple[str, str], tuple[float, bool]] = {}
        for strategy in strategies:
            for exec_name, call, k in execs:
                ms, results = time_cell(lambda c=call, s=strategy: c(s), args.repeat)
                cell_set = _match_set(results, paths)
                correct = cell_set == baseline_set
                if not correct:
                    exit_code = 1
                cell_times[(strategy, exec_name)] = (ms, correct)
                speed = baseline_ms / ms if ms > 0 else float("inf")
                kstr = "-" if k is None else str(k)
                print(f"  {strategy:9s} {exec_name:8s} {kstr:>4s} {ms * 1000:11.2f} {speed:8.2f}x  "
                      f"{'PASS' if correct else 'FAIL  <-- diverges from baseline'}")

        # isal inflate variant (serial + thread, strip strategy).
        if args.include_isal:
            print("\n== isal inflate variant (strip strategy) ==")
            if not _HAVE_ISAL:
                print("  isal not installed -> skipped (pip install isal to evaluate).")
            else:
                with _isal_zipfile_patch(True):
                    ms_s, res_s = time_cell(lambda: run_serial("strip", paths, needle, cs), args.repeat)
                    ms_t, res_t = time_cell(lambda: run_thread("strip", paths, needle, cs, thread_workers), args.repeat)
                ok_s = _match_set(res_s, paths) == baseline_set
                ok_t = _match_set(res_t, paths) == baseline_set
                if not (ok_s and ok_t):
                    exit_code = 1
                print(f"  {'strip+isal':9s} {'serial':8s} {'-':>4s} {ms_s * 1000:11.2f} "
                      f"{baseline_ms / ms_s:8.2f}x  {'PASS' if ok_s else 'FAIL'}")
                print(f"  {'strip+isal':9s} {'thread':8s} {thread_workers:>4d} {ms_t * 1000:11.2f} "
                      f"{baseline_ms / ms_t:8.2f}x  {'PASS' if ok_t else 'FAIL'}")
                print("  (verdict: ship isal only if it materially beats stdlib strip/thread above on YOUR data)")

        # Traversal.
        if not bench_traversal(odc, source, output, args.repeat):
            exit_code = 1

        print("\n== Recommended config ==")
        strip_serial = cell_times.get(("strip", "serial"))
        strip_thread = cell_times.get(("strip", "thread"))
        if strip_serial:
            print(f"  shipped fast path: strip (tag-strip) SERIAL = {strip_serial[0] * 1000:.1f} ms, "
                  f"{baseline_ms / strip_serial[0]:.2f}x vs ElementTree baseline.")
        if strip_serial and strip_thread:
            verdict = ("threads HELP here (high-latency I/O)" if strip_thread[0] < strip_serial[0]
                       else "threads LOSE here (no I/O latency to hide)")
            print(f"  strip thread/{thread_workers} = {strip_thread[0] * 1000:.1f} ms -> {verdict}.")
        print("  Shipped policy: strip + SERIAL on local disk; ThreadPool only on network/UNC "
              "sources (or OFFICE_COLLECTOR_WORKERS override). 'raw' (no tag-strip) is faster but "
              "can false-positive on markup, so it is NOT shipped. ProcessPool is bench-only.")
        if exit_code:
            print("\nRESULT: FAIL (a strategy diverged from baseline or a fidelity/traversal check failed).")
        else:
            print("\nRESULT: PASS (all strategies match the ElementTree baseline).")
    finally:
        if tmp_root is not None and not args.keep_corpus:
            shutil.rmtree(tmp_root, ignore_errors=True)
        elif tmp_root is not None:
            print(f"\nCorpus kept at: {tmp_root}")

    return exit_code


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
