"""Tests for the supervised general-news topic model (news_topics) and its
optional integration into the processing pipeline.

These do NOT hit the network: the model trains from the bundled seed corpus at
import/first-use. scikit-learn is deterministic, so predictions are stable.
"""
from __future__ import annotations

import pytest

from app.schemas.article import Article
from app.services.processing import news_topics
from app.services.processing.domain_config import ClassificationConfig, DEFAULT_CONFIG
from app.services.processing.news_topics_data import TAXONOMY
from app.services.processing.normalizer import normalize_article
from app.services.processing.pipeline import enrich

sklearn = pytest.importorskip("sklearn", reason="scikit-learn required for the topic model")


# --------------------------------------------------------------------------- #
# predict_topic
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Apple unveils new AI chip for the iPhone", "Technology"),
        ("Heavy monsoon rains trigger floods across Maharashtra villages", "Climate"),
        ("Police recover stolen cars in a multi-city crackdown", "Crime"),
        ("New research finds a link between sleep and heart health", "Health"),
    ],
)
def test_predict_topic_labels_clear_headlines(text, expected):
    label, conf = news_topics.predict_topic(text)
    assert label == expected
    assert conf >= 0.30
    assert label in TAXONOMY


@pytest.mark.parametrize("text", ["zzx qqq wibble frobnicate", "", "   "])
def test_predict_topic_abstains_on_unknown_text(text):
    label, conf = news_topics.predict_topic(text)
    assert label == "Other"
    assert conf == 0.0


def test_predict_topic_is_deterministic():
    text = "Sensex and Nifty rally as banking shares gain"
    first = news_topics.predict_topic(text)
    for _ in range(3):
        assert news_topics.predict_topic(text) == first


def test_high_confidence_beats_low_for_on_topic_text():
    on_topic = "Team chased down the target to win the cricket match"
    off_topic = "A thing happened with several unrelated words"
    _, conf_on = news_topics.predict_topic(on_topic)
    _, conf_off = news_topics.predict_topic(off_topic)
    assert conf_on > conf_off


# --------------------------------------------------------------------------- #
# evaluate: honest quality metric on the seed corpus
# --------------------------------------------------------------------------- #
def test_cross_validated_accuracy_beats_random():
    # 11 classes -> random baseline ~0.09. The model should clearly beat that.
    acc = news_topics.evaluate(cv=4)
    assert isinstance(acc, float)
    assert acc >= 0.40


# --------------------------------------------------------------------------- #
# Pipeline integration + gating
# --------------------------------------------------------------------------- #
def _art(**kw) -> Article:
    kw.setdefault("provider", "google_news")
    return Article(**kw)


def test_enrich_uses_topic_model_when_enabled():
    config = ClassificationConfig(topic_model_enabled=True)
    a = normalize_article(
        _art(
            title="Apple unveils new AI chip for the iPhone",
            description="The tech giant announced a next-generation processor.",
            url="https://ex/1",
        )
    )
    p = enrich(a, config)
    assert p.category == "Technology"


def test_enrich_leaves_other_when_model_disabled():
    # Default config keeps the model off: general news stays "Other" so the
    # low-level pipeline remains deterministic.
    assert DEFAULT_CONFIG.topic_model_enabled is False
    a = normalize_article(
        _art(
            title="Apple unveils new AI chip for the iPhone",
            description="The tech giant announced a next-generation processor.",
            url="https://ex/2",
        )
    )
    p = enrich(a, DEFAULT_CONFIG)
    assert p.category == "Other"


def test_enrich_domain_rules_still_win_over_model():
    # A NEET "paper leak" headline must keep the rule-based domain category,
    # even with the topic model enabled - the model is only a fallback.
    config = ClassificationConfig(topic_model_enabled=True)
    a = normalize_article(
        _art(
            title="NEET 2026 paper leak sparks protest",
            description="Students demand a CBI probe into the question paper leak.",
            url="https://ex/3",
        )
    )
    p = enrich(a, config)
    assert p.category == "Paper Leak"
