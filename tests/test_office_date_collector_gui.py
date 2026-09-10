from __future__ import annotations

import importlib.util
import os
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "office_date_collector_gui.py"


def load_tool_module():
    spec = importlib.util.spec_from_file_location("office_date_collector_gui", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def touch(path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"office")
    timestamp = when.timestamp()
    os.utime(path, (timestamp, timestamp))


def office_zip(path: Path, when: datetime, parts: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as package:
        for name, xml in parts.items():
            package.writestr(name, xml)
    timestamp = when.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_collect_filters_modified_dates_suffixes_duplicate_names_and_collects_office_types(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    touch(source / "alpha" / "review.pptx", now)
    touch(source / "beta" / "review.pptx", now)
    touch(source / "book.xlsx", now)
    touch(source / "macro.xlsm", now)
    touch(source / "doc.docx", now)
    touch(source / "~$lock.docx", now)
    touch(source / "old" / "old.pptx", now - timedelta(days=10))
    touch(source / "template.potx", now)

    config = tool.JobConfig(source, output, (now - timedelta(days=1)).date(), now.date())
    summary = tool.collect_office_files(config)

    assert summary.matched_files == 5
    assert summary.copied_files == 5
    copied = sorted(path.name for path in output.iterdir() if path.name != tool.MANIFEST_FILENAME)
    assert copied == [
        "book.xlsx",
        "doc.docx",
        "macro.xlsm",
        "review.pptx",
        "review_1.pptx",
    ]
    assert sorted(Path(name).suffix for name in copied) == [".docx", ".pptx", ".pptx", ".xlsm", ".xlsx"]


def test_scan_skips_output_folder_when_output_is_under_source(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = source / "collected"

    touch(source / "fresh.xlsx", now)
    touch(output / "already_copied.pptx", now)

    config = tool.JobConfig(source, output, (now - timedelta(days=1)).date(), now.date(), ("Excel",))
    matches, stats = tool.scan_office_files(config)

    assert stats.matched == 1
    assert [match.source_path.name for match in matches] == ["fresh.xlsx"]


def test_search_filters_docx_xlsx_xlsm_and_pptx_text_case_insensitive(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    office_zip(source / "doc.docx", now, {"word/document.xml": "<root><t>Rotor Margin</t></root>"})
    office_zip(source / "book.xlsx", now, {"xl/sharedStrings.xml": "<sst><si><t>rotor margin</t></si></sst>"})
    office_zip(source / "macro.xlsm", now, {"xl/worksheets/sheet1.xml": "<worksheet><t>ROTOR MARGIN</t></worksheet>"})
    office_zip(source / "deck.pptx", now, {"ppt/slides/slide1.xml": "<p><t>Rotor margin</t></p>"})
    office_zip(source / "miss.docx", now, {"word/document.xml": "<root><t>No match</t></root>"})

    config = tool.JobConfig(source, output, now.date(), now.date(), search_text="rotor margin")
    summary = tool.collect_office_files(config)

    assert summary.matched_files == 4
    assert summary.copied_files == 4
    assert summary.skipped_text == 1
    copied = sorted(path.name for path in output.iterdir() if path.name != tool.MANIFEST_FILENAME)
    assert copied == ["book.xlsx", "deck.pptx", "doc.docx", "macro.xlsm"]


def test_search_case_sensitive_and_legacy_binary_skip(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    office_zip(source / "exact.docx", now, {"word/document.xml": "<root><t>Exact Needle</t></root>"})
    office_zip(source / "wrong_case.docx", now, {"word/document.xml": "<root><t>exact needle</t></root>"})
    touch(source / "legacy.ppt", now)

    config = tool.JobConfig(
        source,
        output,
        now.date(),
        now.date(),
        search_text="Exact Needle",
        case_sensitive=True,
    )
    summary = tool.collect_office_files(config)

    assert summary.matched_files == 1
    assert summary.copied_files == 1
    assert summary.skipped_text == 1
    assert summary.skipped_unsupported_search == 1
    copied = [path.name for path in output.iterdir() if path.name != tool.MANIFEST_FILENAME]
    assert copied == ["exact.docx"]


def write_html(path: Path, when: datetime, markup: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(markup.encode("utf-8"))
    timestamp = when.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_html_file_type_collects_html_and_skips_office(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    write_html(source / "page.html", now, "<html><body><h1>Report</h1></body></html>")
    write_html(source / "notes.htm", now, "<p>Notes</p>")
    touch(source / "deck.pptx", now)  # not selected -> ignored

    config = tool.JobConfig(source, output, now.date(), now.date(), ("HTML",))
    summary = tool.collect_office_files(config)

    assert summary.matched_files == 2
    assert summary.copied_files == 2
    copied = sorted(path.name for path in output.iterdir() if path.name != tool.MANIFEST_FILENAME)
    assert copied == ["notes.htm", "page.html"]


def test_html_content_search_strips_tags_and_decodes_entities(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    write_html(source / "hit.html", now, "<html><body><h1>Rotor Margin</h1></body></html>")
    write_html(source / "miss.htm", now, "<html><body>No relevant text</body></html>")
    # 'Rotor' and 'Margin' split across tags -> not a phrase match (tags are separators)
    write_html(source / "split.html", now, "<p>Rotor</p><p>Margin</p>")

    config = tool.JobConfig(source, output, now.date(), now.date(), ("HTML",), search_text="rotor margin")
    matches, stats = tool.scan_office_files(config)

    assert [match.source_path.name for match in matches] == ["hit.html"]
    assert stats.matched == 1
    assert stats.skipped_text == 2
    assert stats.skipped_unsupported_search == 0


def test_html_content_search_entity_needle(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    write_html(source / "rnd.html", now, "<p>The R&amp;D budget grew</p>")
    write_html(source / "other.html", now, "<p>research and development</p>")

    config = tool.JobConfig(source, output, now.date(), now.date(), ("HTML",), search_text="R&D")
    matches, stats = tool.scan_office_files(config)

    assert [match.source_path.name for match in matches] == ["rnd.html"]
    assert stats.skipped_text == 1


def test_csv_file_type_collects_csv_by_date(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    touch(source / "fresh.csv", now)
    touch(source / "old.csv", now - timedelta(days=10))
    touch(source / "deck.pptx", now)  # not selected -> ignored

    config = tool.JobConfig(source, output, (now - timedelta(days=1)).date(), now.date(), ("CSV",))
    summary = tool.collect_office_files(config)

    assert summary.matched_files == 1
    assert summary.copied_files == 1
    copied = sorted(path.name for path in output.iterdir() if path.name != tool.MANIFEST_FILENAME)
    assert copied == ["fresh.csv"]


def test_pdf_file_type_collects_pdf_by_date(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    touch(source / "fresh.pdf", now)
    touch(source / "old.pdf", now - timedelta(days=10))
    touch(source / "deck.pptx", now)  # not selected -> ignored

    config = tool.JobConfig(source, output, (now - timedelta(days=1)).date(), now.date(), ("PDF",))
    summary = tool.collect_office_files(config)

    assert summary.matched_files == 1
    assert summary.copied_files == 1
    copied = sorted(path.name for path in output.iterdir() if path.name != tool.MANIFEST_FILENAME)
    assert copied == ["fresh.pdf"]


def test_csv_content_search_matches_plain_text(tmp_path: Path) -> None:
    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    write_html(source / "hit.csv", now, "name,note\nrotor,Rotor Margin OK\n")
    write_html(source / "miss.csv", now, "name,note\nstator,nothing relevant\n")

    config = tool.JobConfig(source, output, now.date(), now.date(), ("CSV",), search_text="rotor margin")
    matches, stats = tool.scan_office_files(config)

    assert [match.source_path.name for match in matches] == ["hit.csv"]
    assert stats.matched == 1
    assert stats.skipped_text == 1
    assert stats.skipped_unsupported_search == 0


def test_manifest_csv_lists_collected_files_with_absolute_and_relative_paths(tmp_path: Path) -> None:
    import csv

    tool = load_tool_module()
    now = datetime.now()
    source = tmp_path / "source"
    output = tmp_path / "output"

    touch(source / "alpha" / "review.pptx", now)  # collides with beta/review.pptx
    touch(source / "beta" / "review.pptx", now)
    touch(source / "book.xlsx", now)

    config = tool.JobConfig(source, output, (now - timedelta(days=1)).date(), now.date())
    summary = tool.collect_office_files(config)

    manifest_path = output / tool.MANIFEST_FILENAME
    assert summary.manifest_path == manifest_path
    assert manifest_path.exists()

    with manifest_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == ["File Name", "Absolute Path", "Relative Path", "Copied As"]
    data = rows[1:]
    assert len(data) == summary.copied_files == 3

    by_relative = {row[2]: row for row in data}
    # Paths use the OS separator; build the expected relative paths the same way.
    rel_alpha = os.path.join("alpha", "review.pptx")
    rel_beta = os.path.join("beta", "review.pptx")
    assert set(by_relative) == {rel_alpha, rel_beta, "book.xlsx"}

    alpha_row = by_relative[rel_alpha]
    assert alpha_row[0] == "review.pptx"
    assert alpha_row[1] == os.path.abspath(source / "alpha" / "review.pptx")

    # The two review.pptx files collide; one keeps its name, the other is renamed.
    copied_as = sorted(row[3] for row in data if row[0] == "review.pptx")
    assert copied_as == ["review.pptx", "review_1.pptx"]
