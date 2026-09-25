"""Honest offline evaluation for the general-news topic classifier.

This module exists to *measure* the model, never to change how it behaves in
production. The live pipeline still uses :func:`news_topics.predict_topic`
(rule-first, ML-fallback, 0.30 abstention). Nothing here is imported by the
collection pipeline.

What it adds over the old ``evaluate()`` (cross-validated accuracy only):

- a stratified train / validation / untouched-holdout split (fixed seed so the
  numbers are reproducible and the holdout is never trained or tuned on);
- a full metric suite - accuracy, macro & weighted precision/recall/F1,
  per-class precision/recall/F1/support and a confusion matrix;
- a confidence + abstention analysis measured *with the production threshold*
  (we do not lower the threshold to inflate coverage);
- a separate, manually labelled *real-world* validation set of unseen
  short queries / headlines, ambiguous + multi-topic text and items that
  should legitimately stay ``Other``.

scikit-learn is imported lazily inside the functions so this module is safe to
import even where the dependency is absent (mirrors ``news_topics.py``).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.services.processing.news_topics_data import (
    FALLBACK_LABEL,
    SEED_CORPUS,
    TAXONOMY,
)

# Keep the split reproducible. This is *not* a tuning knob - it only fixes the
# random_state so the reported holdout metrics are stable across runs.
RANDOM_STATE = 42
HOLDOUT_SIZE = 0.25
VAL_SIZE_WITHIN_TRAINVAL = 0.15

# Same hyper-parameters as the production pipeline (see news_topics._build_model).
# Kept here so the evaluation measures the model that actually ships.
VECTIZER_KWARGS = dict(
    sublinear_tf=True,
    ngram_range=(1, 2),
    min_df=1,
    stop_words="english",
    lowercase=True,
)
NB_ALPHA = 0.1
PRODUCTION_THRESHOLD = 0.30


# --------------------------------------------------------------------------- #
# Dataset inspection
# --------------------------------------------------------------------------- #
def dataset_stats() -> Dict[str, object]:
    """Return corpus size, per-class counts and basic imbalance facts."""
    counts: Dict[str, int] = {label: 0 for label in TAXONOMY}
    seen: set = set()
    dupes = 0
    for text, label in SEED_CORPUS:
        key = text.strip().lower()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        counts[label] = counts.get(label, 0) + 1
    total = sum(counts.values())
    sizes = [c for c in counts.values()]
    return {
        "total_examples": total,
        "per_class": counts,
        "duplicate_entries_removed": dupes,
        "min_class_count": min(sizes) if sizes else 0,
        "max_class_count": max(sizes) if sizes else 0,
        "imbalance_ratio": (max(sizes) / min(sizes)) if sizes and min(sizes) else 0.0,
    }


def _deduped_corpus() -> Tuple[List[str], List[str]]:
    """Exact-duplicate-free (texts, labels). Prevents trivial train/test leak."""
    seen: set = set()
    texts: List[str] = []
    labels: List[str] = []
    for text, label in SEED_CORPUS:
        key = text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        texts.append(text)
        labels.append(label)
    return texts, labels


# --------------------------------------------------------------------------- #
# Model factory (identical configuration to production)
# --------------------------------------------------------------------------- #
def _make_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import ComplementNB
    from sklearn.pipeline import Pipeline

    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(**VECTIZER_KWARGS)),
            ("clf", ComplementNB(alpha=NB_ALPHA)),
        ]
    )


def split_corpus() -> Dict[str, List]:
    """Stratified train / validation / untouched-holdout split.

    The holdout (25%) is set aside first and is only ever used for the final
    measurement. The remaining pool is split into train + validation; validation
    is where any threshold inspection happens so the holdout stays clean.
    """
    from sklearn.model_selection import train_test_split

    texts, labels = _deduped_corpus()
    trainval_t, hold_t, trainval_l, hold_l = train_test_split(
        texts,
        labels,
        test_size=HOLDOUT_SIZE,
        stratify=labels,
        random_state=RANDOM_STATE,
    )
    train_t, val_t, train_l, val_l = train_test_split(
        trainval_t,
        trainval_l,
        test_size=VAL_SIZE_WITHIN_TRAINVAL,
        stratify=trainval_l,
        random_state=RANDOM_STATE,
    )
    return {
        "train": (train_t, train_l),
        "validation": (val_t, val_l),
        "holdout": (hold_t, hold_l),
    }


# --------------------------------------------------------------------------- #
# Holdout evaluation
# --------------------------------------------------------------------------- #
def run_holdout_evaluation(threshold: float = PRODUCTION_THRESHOLD) -> Dict[str, object]:
    """Train on train+val, measure on the untouched holdout.

    Returns a structured metrics dict (accuracy, macro/weighted + per-class
    precision/recall/f1/support, confusion matrix) plus confidence/abstention
    statistics measured at ``threshold``. Returns ``None`` if sklearn is absent.
    """
    try:
        from sklearn.metrics import (
            classification_report,
            confusion_matrix,
            f1_score,
            precision_recall_fscore_support,
        )

        splits = split_corpus()
        train_t, train_l = splits["train"]
        val_t, val_l = splits["validation"]
        hold_t, hold_l = splits["holdout"]

        # Fit on train+val (still never the holdout).
        fit_texts = train_t + val_t
        fit_labels = train_l + val_l
        pipe = _make_pipeline()
        pipe.fit(fit_texts, fit_labels)

        vectorizer = pipe.named_steps["tfidf"]
        classes = list(pipe.classes_)

        # Raw argmax predictions (ignore abstention) for "before" accuracy.
        proba = pipe.predict_proba(hold_t)
        idx = proba.argmax(axis=1)
        conf = proba.max(axis=1)
        raw_pred = [classes[i] for i in idx]

        # OOV guard, mirroring predict_topic: an all-zero row cannot be classified.
        features = vectorizer.transform(hold_t)
        row_nnz = features.getnnz(axis=1)  # per-row non-zero feature count

        final_pred: List[str] = []
        confident_mask: List[bool] = []
        for k in range(len(hold_t)):
            if row_nnz[k] == 0 or conf[k] < threshold:
                final_pred.append(FALLBACK_LABEL)
                confident_mask.append(False)
            else:
                final_pred.append(raw_pred[k])
                confident_mask.append(True)

        from sklearn.metrics import accuracy_score

        accuracy_before = float(accuracy_score(hold_l, raw_pred))
        accuracy_after = float(accuracy_score(hold_l, final_pred))

        macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
            hold_l, raw_pred, average="macro", zero_division=0
        )
        w_p, w_r, w_f1, _ = precision_recall_fscore_support(
            hold_l, raw_pred, average="weighted", zero_division=0
        )
        report = classification_report(
            hold_l, raw_pred, output_dict=True, zero_division=0, labels=TAXONOMY
        )
        per_class = {
            label: {
                "precision": report[label]["precision"],
                "recall": report[label]["recall"],
                "f1-score": report[label]["f1-score"],
                "support": report[label]["support"],
            }
            for label in TAXONOMY
            if label in report
        }
        cm = confusion_matrix(hold_l, raw_pred, labels=TAXONOMY)

        # Confidence / abstention analysis.
        total = len(hold_t)
        confident = sum(confident_mask)
        abstained = total - confident
        correct_confident = sum(
            1 for k in range(total) if confident_mask[k] and final_pred[k] == hold_l[k]
        )
        precision_on_confident = (
            correct_confident / confident if confident else 0.0
        )
        conf_list = [float(c) for c in conf]
        conf_by_class: Dict[str, float] = {}
        conf_support_by_class: Dict[str, int] = {}
        for k in range(total):
            truth = hold_l[k]
            conf_by_class[truth] = conf_by_class.get(truth, 0.0) + conf_list[k]
            conf_support_by_class[truth] = conf_support_by_class.get(truth, 0) + 1
        mean_conf_by_class = {
            label: (conf_by_class[label] / conf_support_by_class[label])
            for label in conf_by_class
        }

        return {
            "sklearn": True,
            "split_sizes": {
                "train": len(train_t),
                "validation": len(val_t),
                "holdout": len(hold_t),
            },
            "threshold": threshold,
            "metrics": {
                "accuracy_before_abstention": accuracy_before,
                "accuracy_after_abstention": accuracy_after,
                "macro_precision": float(macro_p),
                "macro_recall": float(macro_r),
                "macro_f1": float(macro_f1),
                "weighted_precision": float(w_p),
                "weighted_recall": float(w_r),
                "weighted_f1": float(w_f1),
            },
            "per_class": per_class,
            "confusion_matrix": cm.tolist(),
            "confusion_labels": TAXONOMY,
            "abstention": {
                "total_predictions": total,
                "confident_predictions": confident,
                "abstentions": abstained,
                "abstention_rate": abstained / total if total else 0.0,
                "precision_on_confident_subset": precision_on_confident,
                "mean_confidence": sum(conf_list) / total if total else 0.0,
                "min_confidence": min(conf_list) if conf_list else 0.0,
                "max_confidence": max(conf_list) if conf_list else 0.0,
                "mean_confidence_by_class": mean_conf_by_class,
            },
        }
    except ImportError:  # pragma: no cover - sklearn unavailable
        return {"sklearn": False}


# --------------------------------------------------------------------------- #
# Real-world validation (separate, unseen, manually labelled)
# --------------------------------------------------------------------------- #
# These are deliberately NOT drawn from SEED_CORPUS. They mix short queries,
# headline-style text, ambiguous + multi-topic items and genuine noises that
# should stay Other, exercising the model the way live search text does.
REAL_WORLD_VALIDATION: List[Tuple[str, str]] = [
    # ---- short keyword queries -------------------------------------------
    ("sensex nifty close", "Business"),
    ("t20 world cup final score", "Sports"),
    ("new iphone launch 5g", "Technology"),
    ("monsoon flood relief camps", "Climate"),
    ("cbse class 10 result date", "Education"),
    ("covid vaccine booster dose", "Health"),
    ("mars rover water discovery", "Science"),
    ("box office collection day one", "Entertainment"),
    ("parliament winter session", "Politics"),
    ("ceasefire border talks un", "World"),
    ("stock market crash", "Business"),
    ("ai chatbot update", "Technology"),
    ("cricket test centurion", "Sports"),
    # ---- headline-style ---------------------------------------------------
    ("Central bank raises repo rate to fight rising inflation", "Business"),
    ("Hackers leak customer database of major e-commerce site", "Technology"),
    ("Cyclone warning issued as coastal districts evacuate", "Climate"),
    ("Entrance exam admit card released for engineering aspirants", "Education"),
    ("Health ministry approves new malaria vaccine for children", "Health"),
    ("ISRO successfully test fires indigenously built cryogenic engine", "Science"),
    ("Streaming giant renews hit series for a third season", "Entertainment"),
    ("Opposition demands floor test after mass defections", "Politics"),
    ("Foreign troops withdrawn under the peace accord", "World"),
    ("Arrest made in the museum painting theft", "Crime"),
    # ---- ambiguous / multi-topic (model may abstain - both are acceptable) --
    ("Company lays off staff citing poor quarterly earnings", "Business"),
    ("City shuts schools and offices on hazardous air quality", "Climate"),
    ("Government unveils funding for hospital research labs", "Health"),
    # ---- should remain Other (no confident general-news signal) ------------
    ("wibbly frobnicate zzz quux", FALLBACK_LABEL),
    ("the quick brown fox jumps over", FALLBACK_LABEL),
    ("hello there how are you doing today", FALLBACK_LABEL),
]

# Items where abstention (Other) is an acceptable outcome, not a failure.
_AMBIGUOUS_OK_OTHER = {
    "Company lays off staff citing poor quarterly earnings",
    "City shuts schools and offices on hazardous air quality",
    "Government unveils funding for hospital research labs",
}


def run_real_world_validation() -> Optional[Dict[str, object]]:
    """Score the *production* ``predict_topic`` on the unseen real-world set.

    Uses the live code path (full-corpus model + 0.30 threshold), which is what
    users actually hit. Returns a summary + a per-item failure list, or ``None``
    when sklearn is unavailable.
    """
    try:
        from app.services.processing.news_topics import predict_topic
    except Exception:  # pragma: no cover
        return None

    total = 0
    exact = 0
    acceptable = 0
    failures: List[Dict[str, object]] = []
    for text, expected in REAL_WORLD_VALIDATION:
        total += 1
        label, conf = predict_topic(text, min_confidence=PRODUCTION_THRESHOLD)
        if label == expected:
            exact += 1
            acceptable += 1
        elif expected in _AMBIGUOUS_OK_OTHER and label == FALLBACK_LABEL:
            # Ambiguous text that honestly abstains is not counted a failure.
            acceptable += 1
        else:
            failures.append(
                {"text": text, "expected": expected, "predicted": label, "confidence": round(conf, 3)}
            )
    return {
        "total": total,
        "exact_match": exact,
        "exact_accuracy": exact / total if total else 0.0,
        "acceptable_accuracy": acceptable / total if total else 0.0,
        "failures": failures,
    }


# --------------------------------------------------------------------------- #
# Human-readable report (run: python -m app.services.processing.news_topics_eval)
# --------------------------------------------------------------------------- #
def _print_report() -> None:  # pragma: no cover - manual inspection helper
    stats = dataset_stats()
    print("=== Dataset ===")
    print(f"total_examples={stats['total_examples']} "
          f"per_class={stats['min_class_count']}..{stats['max_class_count']} "
          f"(imbalance_ratio={stats['imbalance_ratio']:.2f}, dupes={stats['duplicate_entries_removed']})")
    for label in TAXONOMY:
        print(f"  {label:<14} {stats['per_class'].get(label, 0)}")

    ev = run_holdout_evaluation()
    if not ev or not ev.get("sklearn"):
        print("\nscikit-learn unavailable - cannot run holdout evaluation.")
        return
    m = ev["metrics"]
    print("\n=== Holdout (untouched) ===")
    print(f"split: {ev['split_sizes']}  threshold={ev['threshold']}")
    print(f"accuracy_before_abstention={m['accuracy_before_abstention']:.3f}  "
          f"accuracy_after_abstention={m['accuracy_after_abstention']:.3f}")
    print(f"macro  P/R/F1 = {m['macro_precision']:.3f}/{m['macro_recall']:.3f}/{m['macro_f1']:.3f}")
    print(f"wtd    P/R/F1 = {m['weighted_precision']:.3f}/{m['weighted_recall']:.3f}/{m['weighted_f1']:.3f}")
    print("\nper-class F1:")
    for label, vals in ev["per_class"].items():
        print(f"  {label:<14} P={vals['precision']:.2f} R={vals['recall']:.2f} "
              f"F1={vals['f1-score']:.2f} n={int(vals['support'])}")
    a = ev["abstention"]
    print(f"\nabstention_rate={a['abstention_rate']:.3f} "
          f"(confident={a['confident_predictions']}, abstained={a['abstentions']}) "
          f"precision_on_confident={a['precision_on_confident_subset']:.3f}")

    print("\n=== Real-world (unseen) ===")
    rw = run_real_world_validation()
    if rw:
        print(f"exact_accuracy={rw['exact_accuracy']:.3f}  acceptable_accuracy={rw['acceptable_accuracy']:.3f}")
        for f in rw["failures"]:
            print(f"  MISS exp={f['expected']:<12} got={f['predicted']:<12} conf={f['confidence']}  {f['text']!r}")


if __name__ == "__main__":  # pragma: no cover
    _print_report()
