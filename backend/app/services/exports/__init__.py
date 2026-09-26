"""Report / export generation (Phase 9): CSV, XLSX, PDF, DOCX.

`build_export` is the single dispatch point used by the /export route.
"""
from __future__ import annotations

from typing import List

from app.services.exports.common import FORMAT_MEDIA_TYPES
from app.services.exports.csv_export import build_csv
from app.services.exports.docx_export import build_docx
from app.services.exports.excel_export import build_xlsx
from app.services.exports.pdf_export import build_pdf

_BUILDERS = {
    "csv": build_csv,
    "xlsx": build_xlsx,
    "pdf": build_pdf,
    "docx": build_docx,
}

SUPPORTED_FORMATS = tuple(_BUILDERS.keys())


def build_export(fmt: str, rows: List[dict], meta: dict) -> bytes:
    """Render ``rows`` into the requested format, returning raw bytes."""
    builder = _BUILDERS.get(fmt)
    if builder is None:
        raise ValueError(f"unsupported export format: {fmt}")
    return builder(rows, meta)


__all__ = [
    "build_export",
    "build_csv",
    "build_xlsx",
    "build_pdf",
    "build_docx",
    "SUPPORTED_FORMATS",
    "FORMAT_MEDIA_TYPES",
]
