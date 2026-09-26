"""CSV export (UTF-8 with BOM so Excel opens it correctly)."""
from __future__ import annotations

import csv
import io
from typing import List

from app.services.exports.common import HEADERS, KEYS


def build_csv(rows: List[dict], meta: dict) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    for r in rows:
        writer.writerow([r.get(k, "") for k in KEYS])
    return buf.getvalue().encode("utf-8-sig")
