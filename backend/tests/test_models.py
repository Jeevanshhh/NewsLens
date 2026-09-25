"""Phase 4 tests: database schema + model mapping."""
from __future__ import annotations

from sqlalchemy import inspect

from app.models import Article, Bookmark, Report, Search, User
from app.schemas.processed_article import ProcessedArticle


def test_all_tables_created(engine):
    tables = set(inspect(engine).get_table_names())
    assert {"users", "articles", "searches", "search_results", "bookmarks", "reports"} <= tables


def test_article_from_processed_maps_fields():
    pa = ProcessedArticle(
        title="NEET 2026 protest",
        description="Students protest in Delhi.",
        url="https://ex/1",
        provider="gnews",
        published_at="Mon, 18 Aug 2026 10:00:00 GMT",
        published_date="2026-08-18T10:00:00+00:00",
        name_of_exam="NEET UG",
        category="Protest",
        state="Delhi",
        exam_year="2026",
    )
    row = Article.from_processed(pa)
    assert row.url == "https://ex/1"
    assert row.name_of_exam == "NEET UG"
    assert row.category == "Protest"
    assert row.published_date is not None
    assert row.published_date.year == 2026


def test_persist_and_unique_url(session):
    session.add(User(name="A", email="a@example.com", password_hash="x"))
    session.add(Article(url="https://ex/1", title="one", provider="gnews"))
    session.commit()

    session.add(Search(query="NEET", filters={"sources": ["gnews"]}, result_count=1))
    session.add(Bookmark(article_id=1))
    session.add(Report(name="r", type="csv", parameters={}))
    session.commit()

    assert session.query(Article).count() == 1
    # unique URL enforced
    session.add(Article(url="https://ex/1", title="dup", provider="gnews"))
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
