"""Phase 3 tests: normalization, dedup, rule-based classification/extraction,
and the end-to-end processing pipeline. No network access."""
from __future__ import annotations

import pytest

from app.schemas.article import Article
from app.services.processing import classifier, extractor
from app.services.processing.deduplicator import deduplicate
from app.services.processing.domain_config import DEFAULT_CONFIG
from app.services.processing.normalizer import (
    normalize_article,
    normalize_datetime,
    to_iso,
)
from app.services.processing.pipeline import enrich, process


def _art(**kw) -> Article:
    kw.setdefault("provider", "gnews")
    return Article(**kw)


# --------------------------------------------------------------------------- #
# Normalizer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Mon, 18 Aug 2026 10:00:00 GMT", "2026-08-18T10:00:00+00:00"),
        ("2026-08-18T00:00:00Z", "2026-08-18T00:00:00+00:00"),
        ("not a real date", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_datetime(raw, expected):
    assert to_iso(normalize_datetime(raw)) == expected


def test_normalize_article_cleans_fields():
    a = _art(
        title="  NEET   protest  ",
        description="<b>Students</b> protest\n against leaks.",
        url="  https://ex/1  ",
    )
    clean = normalize_article(a)
    assert clean.title == "NEET protest"
    assert clean.description == "Students protest against leaks."
    assert clean.url == "https://ex/1"


# --------------------------------------------------------------------------- #
# Dedup
# --------------------------------------------------------------------------- #
def test_dedup_removes_duplicates_and_empty_urls():
    arts = [
        _art(url="https://ex/1"),
        _art(url="https://ex/1"),   # dup
        _art(url="   "),            # empty -> dropped
        _art(url="https://ex/2"),
    ]
    out = deduplicate(arts)
    assert [a.url for a in out] == ["https://ex/1", "https://ex/2"]


# --------------------------------------------------------------------------- #
# Classifier (rule-based)
# --------------------------------------------------------------------------- #
def test_detect_exam_known_and_unknown():
    assert classifier.detect_exam("NEET UG result", DEFAULT_CONFIG)["Name of Exam"] == "NEET UG"
    assert classifier.detect_exam("unrelated text", DEFAULT_CONFIG)["Name of Exam"] == "Unknown"


def test_detect_category_first_match_wins():
    assert classifier.detect_category("students protest outside", DEFAULT_CONFIG) == "Protest"
    assert classifier.detect_category("high court hearing today", DEFAULT_CONFIG) == "Court Case"
    assert classifier.detect_category("nothing relevant", DEFAULT_CONFIG) == "Other"


def test_detect_state():
    assert classifier.detect_state("protest in Delhi today", DEFAULT_CONFIG) == "Delhi"
    assert classifier.detect_state("no location here", DEFAULT_CONFIG) == "Unknown"


# --------------------------------------------------------------------------- #
# Extractor (rule-based)
# --------------------------------------------------------------------------- #
def test_extract_reason_first_sentence_html_stripped():
    assert extractor.extract_reason("<p>Students protest.</p> More text here.") == "Students protest."
    assert extractor.extract_reason(None) == ""
    assert extractor.extract_reason("") == ""


def test_extract_reason_length_capped():
    long = "a" * 300
    assert len(extractor.extract_reason(long)) == 250


def test_extract_year():
    assert extractor.extract_year("NEET 2026 result", None) == "2026"
    assert extractor.extract_year("no year here", "Mon, 18 Aug 2026 10:00:00 GMT") == "2026"
    assert extractor.extract_year("no year", "bad-date") == ""


# --------------------------------------------------------------------------- #
# enrich (single article)
# --------------------------------------------------------------------------- #
def test_enrich_maps_domain_fields():
    a = _art(
        title="NEET 2026 paper leak",
        description="Court orders probe into the NEET paper leak in Delhi.",
        url="https://ex/1",
        published_at="Mon, 18 Aug 2026 10:00:00 GMT",
    )
    p = enrich(normalize_article(a), DEFAULT_CONFIG)
    assert p.name_of_exam == "NEET UG"
    # 'paper leak' is the first category in the rule set -> Paper Leak wins
    assert p.category == "Paper Leak"
    assert p.state == "Delhi"
    assert p.conducted_in == "Delhi"
    assert p.exam_year == "2026"
    assert p.published_date == "2026-08-18T10:00:00+00:00"


def test_enrich_non_domain_article_gets_safe_defaults():
    a = _art(title="Apple launches new AI chip", description="Tech news today.", url="https://ex/9")
    p = enrich(normalize_article(a), DEFAULT_CONFIG)
    assert p.name_of_exam == "Unknown"
    assert p.category == "Other"
    assert p.state == "Unknown"
    assert p.conducted_in == "India"   # unknown state maps conducted_in to India


# --------------------------------------------------------------------------- #
# Pipeline end-to-end
# --------------------------------------------------------------------------- #
def test_process_pipeline_dedup_classify_sort():
    raw = [
        _art(title="NEET protest in Delhi", description="Students protest. Details.",
             url="https://ex/1", published_at="Mon, 17 Aug 2026 09:00:00 GMT"),
        _art(title="NEET protest in Delhi", description="dupe",
             url="https://ex/1", published_at="Mon, 17 Aug 2026 09:00:00 GMT"),  # dup
        _art(title="Later article", description="A court hearing happened.",
             url="https://ex/2", published_at="Wed, 19 Aug 2026 09:00:00 GMT"),
        _art(title="Undated", description="no date", url="https://ex/3", published_at=None),
    ]
    result = process(raw, DEFAULT_CONFIG)

    urls = [r.url for r in result]
    assert urls.count("https://ex/1") == 1          # deduped
    assert len(result) == 3                          # empty url none here; 3 unique
    # newest first, undated last
    assert urls[0] == "https://ex/2"
    assert urls[-1] == "https://ex/3"
    assert result[0].category == "Court Case"
