# Purpose: Head-to-head benchmark of office_date_collector_gui search vs native Windows tools.
# Map: subsystems/supporting_runtime_assets
# Run: .\venv\Scripts\python.exe scripts\bench_vs_windows.py --n-files 3000
"""Compare this program's file/string search against native Windows mechanisms.

File (name/date) search is compared against robocopy /L /MT (native multithreaded
matcher), `where /r`, PowerShell Get-ChildItem -Recurse, and `dir /s`. String search
(text *inside* Office files) is compared against `findstr /s` -- which cannot read OOXML
zips at all -- to show the capability gap, not just the speed gap.

Times are medians; speedup = native_median / ours_median (higher = we are faster).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

# Reuse the corpus builder from the sibling benchmark.
_spec = importlib.util.spec_from_file_location("bench_office_search", SCRIPTS_DIR / "bench_office_search.py")
_bench = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _bench
_spec.loader.exec_module(_bench)

OFFICE_MASKS = ["*.docx", "*.pptx", "*.pptm", "*.ppsx", "*.ppsm", "*.xlsx", "*.xlsm"]


def _load_odc():
    spec = importlib.util.spec_from_file_location(
        "office_date_collector_gui", SCRIPTS_DIR / "office_date_collector_gui.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _median_time(fn, repeat):
    times, result = [], None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), result


# --------------------------------------------------------------------------------------
# Ours
# --------------------------------------------------------------------------------------
def ours_file_search(odc, source: Path, output: Path):
    cfg = odc.JobConfig(source, output, date(1990, 1, 1), date(2100, 1, 1), odc.DEFAULT_FILE_TYPES, "")
    matches, _stats = odc.scan_office_files(cfg)
    return len(matches)


def ours_content_search(odc, source: Path, output: Path, needle: str):
    cfg = odc.JobConfig(source, output, date(1990, 1, 1), date(2100, 1, 1), odc.DEFAULT_FILE_TYPES, needle)
    matches, _stats = odc.scan_office_files(cfg)
    return len(matches)


# --------------------------------------------------------------------------------------
# Native Windows
# --------------------------------------------------------------------------------------
def _run(cmd, shell=False):
    proc = subprocess.run(cmd, shell=shell, capture_output=True, text=True, errors="ignore")
    return proc


def native_robocopy(source: Path):
    # robocopy /L (list only, no copy) /S (recurse) /MT (multithreaded) with office masks.
    empty = source.parent / "robocopy_null"
    empty.mkdir(exist_ok=True)
    cmd = ["robocopy", str(source), str(empty), *OFFICE_MASKS,
           "/S", "/L", "/NJH", "/NJS", "/NDL", "/NC", "/NS", "/NP", "/FP", "/MT:16"]
    proc = _run(cmd)
    count = sum(1 for ln in proc.stdout.splitlines() if ln.strip())
    return count


def native_where(source: Path):
    # `where /r <dir> *.docx ...` recursive filename search (no date filter).
    cmd = ["where", "/r", str(source), *OFFICE_MASKS]
    proc = _run(cmd)
    count = sum(1 for ln in proc.stdout.splitlines() if ln.strip())
    return count


def native_get_childitem(source: Path):
    exts = ",".join(f"'{m}'" for m in OFFICE_MASKS)
    ps = (
        f"$ErrorActionPreference='SilentlyContinue';"
        f"(Get-ChildItem -LiteralPath '{source}' -Recurse -File -Include {exts} | Measure-Object).Count"
    )
    proc = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps])
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def native_dir(source: Path):
    # `dir /s /b *.docx ...` -- raw filename enumeration, lower bound for native (no date).
    masks = " ".join(OFFICE_MASKS)
    proc = _run(f'dir /s /b {masks}', shell=True)
    # dir runs relative to cwd; run it inside the source dir instead.
    proc = subprocess.run(f'cmd /c "cd /d {source} && dir /s /b {masks}"',
                          shell=True, capture_output=True, text=True, errors="ignore")
    count = sum(1 for ln in proc.stdout.splitlines() if ln.strip())
    return count


def native_findstr_content(source: Path, needle: str):
    # findstr searches RAW bytes; OOXML text is deflated, so this finds ~nothing -> proves
    # native CLI cannot search inside Office files (capability gap, not just speed).
    masks = " ".join(OFFICE_MASKS)
    cmd = f'cmd /c "cd /d {source} && findstr /s /m /c:\\"{needle}\\" {masks}"'
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors="ignore")
    count = sum(1 for ln in proc.stdout.splitlines() if ln.strip())
    return count


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark this program's search vs native Windows.")
    parser.add_argument("--corpus-dir", type=Path, default=None)
    parser.add_argument("--n-files", type=int, default=3000)
    parser.add_argument("--match-fraction", type=float, default=0.2)
    parser.add_argument("--needle", default="rotor margin")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--keep-corpus", action="store_true")
    args = parser.parse_args(argv)

    import shutil

    tmp_root = None
    if args.corpus_dir is not None:
        source = args.corpus_dir
        print(f"Using existing corpus: {source}")
    else:
        tmp_root = Path(tempfile.mkdtemp(prefix="office_vswin_"))
        source = tmp_root / "corpus"
        print(f"Building corpus: {args.n_files} files -> {source}")
        _bench.build_corpus(source, args.n_files, args.match_fraction, args.needle, args.seed)

    output = (tmp_root or source.parent) / "vswin_output"
    output.mkdir(parents=True, exist_ok=True)
    odc = _load_odc()

    try:
        # Warm OS cache so nobody is unfairly cold.
        ours_file_search(odc, source, output)

        print(f"\n================ FILE SEARCH (find all Office files; cpu={os.cpu_count()}) ================")
        ours_ms, ours_n = _median_time(lambda: ours_file_search(odc, source, output), args.repeat)
        rows = [("THIS PROGRAM (scandir)", ours_ms, ours_n)]
        for label, fn in [
            ("robocopy /L /MT:16", lambda: native_robocopy(source)),
            ("where /r", lambda: native_where(source)),
            ("Get-ChildItem -Recurse", lambda: native_get_childitem(source)),
            ("dir /s /b", lambda: native_dir(source)),
        ]:
            ms, n = _median_time(fn, args.repeat)
            rows.append((label, ms, n))
        _print_table(rows, ours_ms)

        print(f"\n================ STRING SEARCH (find text inside Office files: {args.needle!r}) ================")
        # Warm the zip *contents* (the file-search warmup only touched directory entries).
        ours_content_search(odc, source, output, args.needle)
        ours_ms2, ours_n2 = _median_time(lambda: ours_content_search(odc, source, output, args.needle), args.repeat)
        fs_ms, fs_n = _median_time(lambda: native_findstr_content(source, args.needle), args.repeat)
        files_per_sec = ours_n / ours_ms2 if ours_ms2 > 0 else 0
        print(f"  {'tool':26s} {'median ms':>11s} {'found':>8s}  {'verdict':>22s}")
        print("  " + "-" * 72)
        print(f"  {'THIS PROGRAM (OOXML)':26s} {ours_ms2 * 1000:11.1f} {ours_n2:8d}  "
              f"{f'{files_per_sec:,.0f} files/sec':>22s}")
        capable = fs_n >= max(1, ours_n2 // 2)
        verdict = "(correct)" if capable else "INCAPABLE: 0 hits in zips"
        print(f"  {'findstr /s (raw bytes)':26s} {fs_ms * 1000:11.1f} {fs_n:8d}  {verdict:>22s}")
        print(f"\n  findstr found {fs_n} of {ours_n2} -> native CLI tools (findstr/where/Select-String)")
        print("  CANNOT read deflated OOXML text at any speed: a capability native lacks, not just")
        print("  a speed gap. Windows Explorer/Search can, but only via iFilter *indexing* that must")
        print("  be pre-built and is stale or absent for arbitrary, just-modified, or network folders.")
    finally:
        if tmp_root is not None and not args.keep_corpus:
            shutil.rmtree(tmp_root, ignore_errors=True)
        elif tmp_root is not None:
            print(f"\nCorpus kept at: {tmp_root}")
    return 0


def _print_table(rows, ours_ms):
    print(f"  {'tool':26s} {'median ms':>11s} {'files':>8s}  {'vs us':>8s}")
    print("  " + "-" * 58)
    for label, ms, n in rows:
        if "THIS PROGRAM" in label:
            tag = "  (baseline)"
        elif ms <= 0:
            tag = "    n/a"
        else:
            ratio = ms / ours_ms
            tag = f"{ratio:6.1f}x slower" if ratio >= 1 else f"{1 / ratio:6.1f}x FASTER"
        print(f"  {label:26s} {ms * 1000:11.1f} {n:8d}  {tag}")


if __name__ == "__main__":
    raise SystemExit(main())
