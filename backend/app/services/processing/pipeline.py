"""End-to-end processing pipeline (Phase 3).

Chains the refactored notebook logic into one deterministic pass:

    normalize -> deduplicate (by URL) -> classify/extract (rule-based, with an
    optional supervised topic-model fallback for general news) -> sort (newest first)

Input: raw provider ``Article`` objects (from ``app.services.news``).
Output: structured ``ProcessedArticle`` objects ready for storage/export.

Articles that cannot be classified keep safe "Unknown"/"Other" values; nothing
is silently dropped except empty-URL duplicates.
"""
from __future__ import annotations

from typing import List, Optional

from app.schemas.article import Article
from app.schemas.processed_article import ProcessedArticle
from app.services.processing import classifier, extractor
from app.services.processing.deduplicator import deduplicate
from app.services.processing.news_topics import predict_topic
from app.services.processing.domain_config import (
    DEFAULT_CONFIG,
    ClassificationConfig,
)
from app.services.processing.normalizer import (
    normalize_article,
    normalize_datetime,
    to_iso,
)


def enrich(article: Article, config: ClassificationConfig) -> ProcessedArticle:
    full_text = f"{article.title} {article.description or ''}"

    exam = classifier.detect_exam(full_text, config)
    state = classifier.detect_state(full_text, config)
    category = classifier.detect_category(full_text, config)

    # The rule set is domain-specific (exam/NEET). When it cannot assign a
    # specific category, optionally fall back to the supervised general-news
    # topic model so real headlines stop landing in the "Other" bucket. This is
    # disabled for the deterministic default config and only enabled for live
    # collection runs (see Settings.enable_topic_model).
    if category == "Other" and getattr(config, "topic_model_enabled", False):
        topic, _confidence = predict_topic(full_text, config.topic_min_confidence)
        if topic != "Other":
            category = topic

    reason = extractor.extract_reason(article.description)
    year = extractor.extract_year(article.title, article.published_at)
    published_dt = normalize_datetime(article.published_at)

    return ProcessedArticle(
        **article.model_dump(),
        name_of_exam=exam["Name of Exam"],
        exam_category=exam["Exam Category"],
        board=exam["Board"],
        conducted_by=exam["Conducted By"],
        pbt_cbt=exam["PBT/CBT"],
        state=state,
        conducted_in="India" if state == "Unknown" else state,
        category=category,
        reason=reason,
        exam_year=year,
        published_date=to_iso(published_dt),
    )


def _sort_key(article: ProcessedArticle):
    dt = normalize_datetime(article.published_date)
    # Undated articles sort last (oldest) without being discarded.
    return (dt is not None, dt.timestamp() if dt else 0.0)


def process(
    articles: List[Article],
    config: Optional[ClassificationConfig] = None,
) -> List[ProcessedArticle]:
    config = config or DEFAULT_CONFIG

    normalized = [normalize_article(a) for a in articles]
    unique = deduplicate(normalized)
    processed = [enrich(a, config) for a in unique]
    processed.sort(key=_sort_key, reverse=True)
    return processed
