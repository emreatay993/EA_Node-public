# DOCX Rendering Comparison Prototype

This mockup compares Microsoft Word document rendering approaches from Python.
It is intentionally outside production source because several candidates depend
on Microsoft Word, LibreOffice, commercial packages, or native runtime pieces.

## Run

```powershell
.\venv\Scripts\python.exe mockups\docx_rendering_comparison\run.py
```

By default the runner creates a sample `.docx`, tries every renderer, writes
per-renderer PDFs/HTML/PNGs under `_outputs/`, and creates a
`comparison.html` report.

Use a real document instead:

```powershell
.\venv\Scripts\python.exe mockups\docx_rendering_comparison\run.py --input C:\path\to\document.docx
```

Fast smoke check:

```powershell
.\venv\Scripts\python.exe mockups\docx_rendering_comparison\run.py --selftest
```

## Renderer Candidates

- `word_com_pdf`: Microsoft Word through `pywin32`; best baseline when Word is installed.
- `docx2pdf_word`: `docx2pdf`; thin wrapper around Microsoft Word automation on Windows.
- `aspose_words_pdf`: `aspose-words`; commercial renderer, may add evaluation marks without a license.
- `spire_doc_pdf`: `Spire.Doc`; commercial renderer, may add evaluation marks without a license.
- `libreoffice_pdf`: LibreOffice CLI through `soffice`; skipped when LibreOffice is not on `PATH`.
- `pypandoc_html_qt`: `pypandoc`/Pandoc DOCX to HTML, then Qt WebEngine to PDF.
- `mammoth_html_qt`: `mammoth` semantic DOCX to HTML, then Qt WebEngine to PDF.
- `docling_html_qt`: `docling` DOCX to HTML or Markdown-derived HTML, then Qt WebEngine to PDF.
- `markitdown_html_qt`: `markitdown` DOCX to Markdown/HTML, then Qt WebEngine to PDF.
- `python_docx_html_qt`: `python-docx` simple paragraph/table extraction, then Qt WebEngine to PDF.
- `docx2python_html_qt`: `docx2python` extraction, then Qt WebEngine to PDF.

HTML-producing libraries are not full Word layout engines. They are included to
show semantic conversion quality and layout drift against PDF-grade renderers.

## Installed Venv Packages

The current venv has been populated with the comparison candidates:

```powershell
.\venv\Scripts\python.exe -m pip install python-docx docx2pdf mammoth pypandoc_binary docx2python PyMuPDF pypdfium2 pdf2image weasyprint aspose-words Spire.Doc docling markitdown
```

`weasyprint` was installed as another HTML-to-PDF option, but this Windows
environment is missing the native Pango/GLib runtime it needs. The prototype
therefore uses Qt WebEngine for HTML-to-PDF rendering.

LibreOffice is an external application, not a Python library. For this machine
the official MSI was extracted to:

```text
%LOCALAPPDATA%\LibreOfficeAdminImage\program\soffice.exe
```

The runner checks that user-local extraction path, normal `Program Files`
install locations, `PATH`, and the optional `LIBREOFFICE_SOFFICE_PATH`
environment variable.

## Outputs

Each run writes:

- `sample.docx` when no input is supplied.
- `report.json` with renderer status, timing, notes, and artifacts.
- `comparison.html` with first-page thumbnails and links to outputs.
- One subfolder per renderer containing source HTML/Markdown/PDF/PNG artifacts.
