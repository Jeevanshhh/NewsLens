"""Lightweight supervised news-topic classifier.

A real (small) machine-learning model: a TF-IDF vectoriser feeding a Complement
Naive-Bayes classifier, trained once on the bundled labelled corpus in
``news_topics_data``. scikit-learn is already a dependency of this environment;
if it is ever unavailable, ``predict_topic`` degrades gracefully to the
``Other`` fallback rather than raising, so the collection pipeline never breaks.

Design notes / honesty:
- The corpus is modest (a few hundred short headlines), so this is a *topic
  signal*, not a high-accuracy production model. ``evaluate()`` reports an
  honest cross-validated accuracy on the seed corpus.
- Out-of-vocabulary / empty-feature text returns ``Other`` (we never guess a
  topic from a bag of unknown words).
- Deterministic: ComplementNB + TfidfVectorizer have no randomness, so the same
  input always yields the same prediction.

The pipeline only calls this as a *fallback* when the existing rule-based
domain classifier cannot assign a specific category, so NEET/exam categories
are unaffected.
"""
from __future__ import annotations

import threading
from typing import Optional, Tuple

from app.services.processing.news_topics_data import (
    FALLBACK_LABEL,
    SEED_CORPUS,
    TAXONOMY,
)

_lock = threading.Lock()
_model = None  # cached sklearn Pipeline once trained
_ModelType = Optional[object]


def _build_model():
    """Construct and train the sklearn pipeline on the bundled corpus."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import ComplementNB
    from sklearn.pipeline import Pipeline

    texts = [t for t, _ in SEED_CORPUS]
    labels = [lbl for _, lbl in SEED_CORPUS]

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    sublinear_tf=True,
                    ngram_range=(1, 2),
                    min_df=1,
                    stop_words="english",
                    lowercase=True,
                ),
            ),
            ("clf", ComplementNB(alpha=0.1)),
        ]
    )
    pipeline.fit(texts, labels)
    return pipeline


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = _build_model()
    return _model


def _max_probability(model, docs) -> Tuple[int, float]:
    """Return (predicted index, max probability) from the pipeline on raw docs."""
    proba = model.predict_proba(docs)[0]
    idx = int(proba.argmax())
    return idx, float(proba[idx])


def predict_topic(text: str, min_confidence: float = 0.30) -> Tuple[str, float]:
    """Predict a general news topic for ``text``.

    Returns ``(label, confidence)``. ``label`` is ``"Other"`` when the model is
    unavailable, the text produces no known features, or the top probability is
    below ``min_confidence``.
    """
    if not text or not text.strip():
        return FALLBACK_LABEL, 0.0

    try:
        model = _get_model()
        # Out-of-vocabulary guard: if none of the text's terms are in the
        # training vocabulary, the transformed row is all-zero - refuse to guess.
        features = model.named_steps["tfidf"].transform([text])
        if features.getnnz() == 0:
            return FALLBACK_LABEL, 0.0
        classes = list(model.classes_)
        idx, conf = _max_probability(model, [text])
    except Exception:  # pragma: no cover - sklearn missing / model failure
        return FALLBACK_LABEL, 0.0

    if conf < min_confidence:
        return FALLBACK_LABEL, conf
    label = classes[idx] if 0 <= idx < len(classes) else FALLBACK_LABEL
    return str(label), conf


def evaluate(cv: int = 4) -> float:
    """Honest 4-fold stratified cross-validated accuracy on the seed corpus.

    Used by tests/metrics to report a real number rather than a claim. Returns
    ``0.0`` if scikit-learn is unavailable.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.model_selection import cross_val_score
        from sklearn.naive_bayes import ComplementNB
        from sklearn.pipeline import Pipeline

        texts = [t for t, _ in SEED_CORPUS]
        labels = [lbl for _, lbl in SEED_CORPUS]
        pipe = Pipeline(
            [
                ("tfidf", TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2),
                                          min_df=1, stop_words="english")),
                ("clf", ComplementNB(alpha=0.1)),
            ]
        )
        scores = cross_val_score(pipe, texts, labels, cv=cv, scoring="accuracy")
        return float(scores.mean())
    except Exception:  # pragma: no cover
        return 0.0


__all__ = ["predict_topic", "evaluate", "TAXONOMY", "FALLBACK_LABEL"]
