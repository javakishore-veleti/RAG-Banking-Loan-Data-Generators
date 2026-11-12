"""L0 — load one source document into plain text.

One function per format, matching the six Datagen formats. Text
extraction is best-effort and local (no AWS calls): if a file yields no
extractable text, the caller falls back to the manifest ground-truth
description for that document (pipeline.py) — so a PNG, which has no
text layer, still gets indexed from its description instead of being
silently skipped. An OCR engine can replace the PNG path later; the
interface (extract_text(fmt, data) -> str) does not change.

Keep extraction dependency-light: pypdf / python-docx / openpyxl are
already in requirements.txt for this app.
"""

import csv
import io


def extract_text(fmt, data: bytes) -> str:
    """Plain text of a document. `fmt` is one of pdf/docx/xlsx/csv/txt/png.
    Returns '' when nothing extractable is found (caller decides fallback)."""
    fmt = (fmt or "").lower()
    if fmt == "pdf":
        return _extract_pdf(data)
    if fmt == "docx":
        return _extract_docx(data)
    if fmt == "xlsx":
        return _extract_xlsx(data)
    if fmt == "csv":
        return _extract_csv(data)
    if fmt == "txt":
        return data.decode("utf-8", errors="ignore")
    if fmt == "png":
        return ""  # raster image: no text layer; manifest fallback applies
    raise ValueError(f"unsupported format: {fmt!r}")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _extract_docx(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(p for p in parts if p).strip()


def _extract_xlsx(data: bytes) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(f"Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            parts.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(p for p in parts if p).strip()


def _extract_csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="ignore")
    rows = list(csv.reader(io.StringIO(text)))
    return "\n".join(" | ".join(r) for r in rows).strip()
