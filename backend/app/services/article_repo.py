"""Article persistence + querying helpers (used by search, articles, exports)."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Article
from app.schemas.processed_article import ProcessedArticle

SORT_FIELDS = {
    "newest": Article.published_date.desc().nullslast(),
    "oldest": Article.published_date.asc().nullslast(),
    # Explicit date aliases: the frontend (and any stored client params) may
    # send date_desc/date_asc; without these keys they silently fell back to
    # "newest", making "Oldest first" a no-op (QA bug N1, 2026-09-28).
    "date_desc": Article.published_date.desc().nullslast(),
    "date_asc": Article.published_date.asc().nullslast(),
    "category": Article.category.asc(),
    "state": Article.state.asc(),
    "source": Article.source.asc(),
    "title": Article.title.asc(),
}


def upsert_articles(db: Session, processed: Sequence[ProcessedArticle]) -> Tuple[List[Article], int]:
    """Insert new articles (by URL); return all rows and the number created."""
    urls = [pa.url for pa in processed if pa.url]
    existing = {}
    if urls:
        rows = db.scalars(select(Article).where(Article.url.in_(urls))).all()
        existing = {r.url: r for r in rows}

    created_rows: List[Article] = []
    result_rows: List[Article] = []
    new_count = 0
    for pa in processed:
        row = existing.get(pa.url)
        if row is None:
            row = Article.from_processed(pa)
            db.add(row)
            existing[pa.url] = row
            created_rows.append(row)
            new_count += 1
        result_rows.append(row)

    db.flush()  # assign ids to newly added rows
    return result_rows, new_count


def link_search(db: Session, search_id: int, rows: Sequence[Article]) -> None:
    from app.models import Search

    search = db.get(Search, search_id)
    if search is None:
        return
    existing_ids = {a.id for a in search.articles}
    for row in rows:
        if row.id not in existing_ids:
            search.articles.append(row)


def serialize(row: Article) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "url": row.url,
        "source": row.source,
        "provider": row.provider,
        "author": row.author,
        "published_at": row.published_at,
        "published_date": row.published_date.isoformat() if row.published_date else None,
        "keyword_matched": row.keyword_matched,
        "language": row.language,
        "country": row.country,
        "image_url": row.image_url,
        "name_of_exam": row.name_of_exam,
        "exam_category": row.exam_category,
        "board": row.board,
        "conducted_by": row.conducted_by,
        "pbt_cbt": row.pbt_cbt,
        "state": row.state,
        "conducted_in": row.conducted_in,
        "category": row.category,
        "reason": row.reason,
        "exam_year": row.exam_year,
    }


def _apply_filters(stmt, filters: dict):
    if filters.get("provider"):
        stmt = stmt.where(Article.provider == filters["provider"])
    if filters.get("category"):
        stmt = stmt.where(Article.category == filters["category"])
    if filters.get("state"):
        stmt = stmt.where(Article.state == filters["state"])
    if filters.get("source"):
        stmt = stmt.where(Article.source == filters["source"])
    if filters.get("language"):
        lang = filters["language"]
        # Articles are stored with the RSS locale tag (e.g. "en-IN"), while
        # requests/saved searches default to the bare prefix ("en"). Exact
        # equality made that combination return zero rows (QA bug, 2026-09-28);
        # match the exact value OR the "<prefix>-<REGION>" form.
        wildcards = ("%" in lang) or ("_" in lang)
        if wildcards:
            stmt = stmt.where(Article.language == lang)
        else:
            stmt = stmt.where(
                or_(Article.language == lang, Article.language.like(f"{lang}-%"))
            )
    if filters.get("country"):
        stmt = stmt.where(Article.country == filters["country"])
    if filters.get("name_of_exam"):
        stmt = stmt.where(Article.name_of_exam == filters["name_of_exam"])
    if filters.get("q"):
        like = f"%{filters['q']}%"
        stmt = stmt.where(or_(Article.title.ilike(like), Article.description.ilike(like)))
    return stmt


def list_articles(
    db: Session,
    *,
    filters: Optional[dict] = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 20,
    search_id: Optional[int] = None,
) -> Tuple[List[dict], int]:
    filters = filters or {}
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    base = select(Article)
    if search_id is not None:
        from app.models import search_results

        base = base.join(search_results, search_results.c.article_id == Article.id).where(
            search_results.c.search_id == search_id
        )
    base = _apply_filters(base, filters)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    order = SORT_FIELDS.get(sort, SORT_FIELDS["newest"])
    stmt = base.order_by(order).offset((page - 1) * page_size).limit(page_size)
    rows = db.scalars(stmt).all()
    return [serialize(r) for r in rows], total


def get_by_id(db: Session, article_id: int) -> Optional[Article]:
    return db.get(Article, article_id)


def related(
    db: Session, row: Article, *, limit: int = 6
) -> List[dict]:
    """Articles sharing this one's topic or location (excluding itself).

    Uses only genuinely-stored metadata: prefers the same non-placeholder
    category, then the same non-placeholder state, then the same source. Never
    invents a relationship - if nothing matches, a smaller/empty list returns.
    """
    def _meaningful(v: Optional[str]) -> bool:
        return bool(v) and v not in {"Unknown", "Other"}

    def _query(stmt):
        stmt = stmt.where(Article.id != row.id).order_by(SORT_FIELDS["newest"]).limit(limit)
        return [serialize(r) for r in db.scalars(stmt).all()]

    results: List[dict] = []
    seen = set()
    for stmt in (
        select(Article).where(Article.category == row.category) if _meaningful(row.category) else None,
        select(Article).where(Article.state == row.state) if _meaningful(row.state) else None,
        select(Article).where(Article.source == row.source) if _meaningful(row.source) else None,
    ):
        if stmt is None:
            continue
        for item in _query(stmt):
            if item["id"] not in seen:
                seen.add(item["id"])
                results.append(item)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results[:limit]


def all_articles(
    db: Session,
    *,
    filters: Optional[dict] = None,
    sort: str = "newest",
    search_id: Optional[int] = None,
    limit: Optional[int] = 5000,
) -> List[dict]:
    """Return every row matching the filters (for export), capped by ``limit``.

    The cap is a safety rail against unbounded exports, not a data-quality
    heuristic; the route surfaces the effective count to the caller.
    """
    filters = filters or {}
    base = select(Article)
    if search_id is not None:
        from app.models import search_results

        base = base.join(search_results, search_results.c.article_id == Article.id).where(
            search_results.c.search_id == search_id
        )
    base = _apply_filters(base, filters)
    order = SORT_FIELDS.get(sort, SORT_FIELDS["newest"])
    stmt = base.order_by(order)
    if limit is not None:
        stmt = stmt.limit(limit)
    return [serialize(r) for r in db.scalars(stmt).all()]
