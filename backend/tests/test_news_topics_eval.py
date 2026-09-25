"""Tests for the offline topic-model evaluation harness (news_topics_eval).

These guard the *measurement* machinery: dataset integrity, leakage-free
splits, the presence and range of every reported metric, reproducibility, the
production-threshold abstention accounting and graceful behaviour when the ML
dependency is missing. They do NOT assert a cosmetic accuracy target - the
floors below are deliberately conservative and reflect the model's honest
baseline quality.

Fully offline and deterministic (fixed split seed). No network calls.
"""
from __future__ import annotations

import pytest

from app.services.processing import news_topics_eval as ev
from app.services.processing.news_topics_data import FALLBACK_LABEL, TAXONOMY

pytest.importorskip("sklearn", reason="scikit-learn required for the evaluation harness")


# --------------------------------------------------------------------------- #
# Dataset integrity
# --------------------------------------------------------------------------- #
def test_dataset_is_expanded_and_balanced():
    stats = ev.dataset_stats()
    # Substantially larger than the original 176-example seed.
    assert stats["total_examples"] >= 350
    # Every taxonomy class is represented.
    assert set(stats["per_class"].keys()) == set(TAXONOMY)
    assert all(c >= 25 for c in stats["per_class"].values())
    # Balanced: no class more than 1.5x another, and no duplicate entries.
    assert stats["imbalance_ratio"] <= 1.5
    assert stats["duplicate_entries_removed"] == 0


def test_all_labels_are_valid_taxonomy():
    texts, labels = ev._deduped_corpus()
    assert len(texts) == len(set(t.strip().lower() for t in texts))  # exact-unique
    assert set(labels).issubset(set(TAXONOMY))


# --------------------------------------------------------------------------- #
# Split correctness (no leakage)
# --------------------------------------------------------------------------- #
def test_splits_are_disjoint_and_cover_corpus():
    splits = ev.split_corpus()
    train, val, hold = splits["train"], splits["validation"], splits["holdout"]

    train_set = {t.strip().lower() for t in train[0]}
    val_set = {t.strip().lower() for t in val[0]}
    hold_set = {t.strip().lower() for t in hold[0]}

    # Untouched holdout must not intersect the fitted data.
    assert train_set.isdisjoint(hold_set)
    assert val_set.isdisjoint(hold_set)
    assert train_set.isdisjoint(val_set)

    # Every split label is a real taxonomy class.
    for _, labels in (train, val, hold):
        assert set(labels).issubset(set(TAXONOMY))

    # Splits are large enough to be meaningful.
    assert len(hold[0]) >= 40
    assert len(train[0]) >= 150


# --------------------------------------------------------------------------- #
# Holdout metrics
# --------------------------------------------------------------------------- #
def _metrics():
    result = ev.run_holdout_evaluation()
    assert result and result.get("sklearn") is True
    return result


def test_holdout_reports_full_metric_suite():
    result = _metrics()
    m = result["metrics"]
    for key in (
        "accuracy_before_abstention",
        "accuracy_after_abstention",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
    ):
        assert key in m
        assert 0.0 <= m[key] <= 1.0

    # Accuracy clearly beats the 11-class random baseline (~0.09) without
    # pretending to a high target - a conservative honest floor.
    assert m["accuracy_before_abstention"] >= 0.40


def test_per_class_and_confusion_matrix_shapes():
    result = _metrics()
    per_class = result["per_class"]
    assert set(per_class.keys()) == set(TAXONOMY)
    for vals in per_class.values():
        for key in ("precision", "recall", "f1-score", "support"):
            assert key in vals

    cm = result["confusion_matrix"]
    n = len(TAXONOMY)
    assert len(cm) == n and all(len(row) == n for row in cm)
    assert result["confusion_labels"] == TAXONOMY
    # Diagonal + off-diagonal cells sum to the holdout size.
    total = sum(sum(row) for row in cm)
    assert total == result["split_sizes"]["holdout"]


def test_abstention_uses_production_threshold_and_is_accounted():
    result = _metrics()
    assert result["threshold"] == ev.PRODUCTION_THRESHOLD == 0.30
    a = result["abstention"]
    assert a["total_predictions"] == a["confident_predictions"] + a["abstentions"]
    assert 0.0 <= a["abstention_rate"] <= 1.0
    # Confidence statistics are present and sane.
    assert 0.0 <= a["min_confidence"] <= a["mean_confidence"] <= a["max_confidence"] <= 1.0
    assert set(a["mean_confidence_by_class"].keys()) == set(TAXONOMY)


def test_evaluation_is_deterministic():
    first = _metrics()["metrics"]
    for _ in range(2):
        assert ev.run_holdout_evaluation()["metrics"] == first


# --------------------------------------------------------------------------- #
# Real-world (unseen) validation
# --------------------------------------------------------------------------- #
def test_real_world_validation_structure():
    result = ev.run_real_world_validation()
    assert result is not None
    assert result["total"] == len(ev.REAL_WORLD_VALIDATION)
    assert 0.0 <= result["exact_accuracy"] <= 1.0
    # Acceptable accuracy can never be below strict exact accuracy.
    assert result["acceptable_accuracy"] >= result["exact_accuracy"]
    assert isinstance(result["failures"], list)
    for f in result["failures"]:
        assert {"text", "expected", "predicted", "confidence"} <= set(f)


def test_real_world_set_includes_other_expectations():
    # The set must exercise genuine no-signal text that should stay Other.
    expected = {lbl for _, lbl in ev.REAL_WORLD_VALIDATION}
    assert FALLBACK_LABEL in expected
    assert expected.issubset(set(TAXONOMY) | {FALLBACK_LABEL})


# --------------------------------------------------------------------------- #
# Graceful dependency failure
# --------------------------------------------------------------------------- #
def test_holdout_eval_degrades_gracefully_without_sklearn(monkeypatch):
    def _boom():
        raise ImportError("no sklearn")

    monkeypatch.setattr(ev, "_make_pipeline", _boom)
    assert ev.run_holdout_evaluation() == {"sklearn": False}
