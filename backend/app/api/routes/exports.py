"""Export endpoint (Phase 9).

Streams the current result set (optionally scoped to a saved search or the
active filters) as CSV / XLSX / PDF / DOCX. A GET is used so the frontend can
trigger a browser download directly; every number in the report comes from the
rows actually selected.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.models import Search, User
from app.services import article_repo
from app.services.exports import SUPPORTED_FORMATS, build_export
from app.services.exports.common import FORMAT_MEDIA_TYPES

router = APIRouter(tags=["exports"])


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else "-" for c in (text or "export")).strip("-")
    return (cleaned[:40] or "export").lower()


@router.get("/export", summary="Export stored articles as csv/xlsx/pdf/docx")
def export_articles(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    format: str = Query("csv", description="|".join(SUPPORTED_FORMATS)),
    search_id: Optional[int] = Query(None, ge=1),
    provider: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    name_of_exam: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: str = Query("newest"),
):
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported format '{format}'. choose one of: {', '.join(SUPPORTED_FORMATS)}",
        )

    filters = {
        "provider": provider,
        "category": category,
        "state": state,
        "source": source,
        "language": language,
        "country": country,
        "name_of_exam": name_of_exam,
        "q": q,
    }

    query_label = q or ""
    from_date = to_date = None
    sources = None
    if search_id is not None:
        s = db.get(Search, search_id)
        if s is None:
            raise HTTPException(status_code=404, detail="search not found")
        query_label = s.query
        from_date, to_date = s.from_date, s.to_date
        # Merge the stored search's own filters (without overriding explicit params).
        s_filters = s.filters or {}
        sources = s_filters.get("sources")
        for key in ("country", "language", "category", "state"):
            if not filters.get(key) and s_filters.get(key):
                filters[key] = s_filters[key]

    rows = article_repo.all_articles(db, filters=filters, sort=sort, search_id=search_id)

    meta = {
        "query": query_label,
        "from_date": from_date,
        "to_date": to_date,
        "sources": sources,
        "country": filters.get("country") or "",
        "language": filters.get("language") or "",
        "total": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    try:
        content = build_export(fmt, rows, meta)
    except ValueError as exc:  # pragma: no cover - guarded by the check above
        raise HTTPException(status_code=422, detail=str(exc))

    media_type, ext = FORMAT_MEDIA_TYPES[fmt]
    filename = f"newslens-{_slug(query_label)}.{ext}"
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
