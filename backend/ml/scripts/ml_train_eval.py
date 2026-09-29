"""PHASE 8-13: Train 5 candidate models, evaluate, calibrate, error-analyse,
learning curve, and save reproducible DEVELOPMENT artifacts.

Candidates (TF-IDF -> classifier), all deterministic (fixed seed):
  A  unigram        + ComplementNB
  B  unigram        + LogisticRegression
  C  unigram        + LinearSVC          (evaluated for comparison only - no
                                          native probabilities, so never deployed)
  D  unigram+bigram + ComplementNB
  E  unigram+bigram + LogisticRegression

The deployed artifact is chosen only from the probability-capable candidates
(A/B/D/E) so it exposes ``named_steps['tfidf']`` + ``predict_proba`` and is
loadable by ``news_topics._load_artifact`` / ``predict_topic`` at inference time.

CRITICAL HONESTY NOTE carried into every report:
  The provisional labels and the TF-IDF features are BOTH derived from the same
  title+description surface text. This evaluation is therefore an OPTIMISTIC
  UPPER BOUND and does NOT measure real-world accuracy. The labels are
  single-annotator, rule-assisted, unverified, and the corpus rights are
  UNVERIFIED_GOOGLE_NEWS. No production claim is made.

Run:  python backend/ml/scripts/ml_train_eval.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    COMPARISON_REPORT,
    DATASET_ID,
    DEDUPED_JSONL,
    FALLBACK_LABEL,
    MODEL_ARTIFACT,
    MODEL_METADATA,
    MODEL_SERIES,
    PREPROCESSING_VERSION,
    RANDOM_SEED,
    REPORTS_DIR,
    RIGHTS_STATUS,
    SPLITS_MANIFEST,
    TAXONOMY,
    TRAINING_CONFIG,
    MODEL_CARD,
)

LABELS = TAXONOMY + [FALLBACK_LABEL]


def _vectorizer(ngram):
    from sklearn.feature_extraction.text import TfidfVectorizer

    return TfidfVectorizer(
        sublinear_tf=True,
        ngram_range=ngram,
        min_df=1,
        stop_words="english",
        lowercase=True,
    )


def _candidates():
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import ComplementNB
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC

    def pipe(ng, clf):
        return Pipeline([("tfidf", _vectorizer(ng)), ("clf", clf)])

    cnb = lambda: ComplementNB(alpha=0.1)  # noqa: E731
    lr = lambda: LogisticRegression(  # noqa: E731
        max_iter=2000, C=1.0, random_state=RANDOM_SEED
    )
    svc = lambda: LinearSVC(  # noqa: E731
        max_iter=5000, C=1.0, random_state=RANDOM_SEED
    )
    return {
        "A_unigram_CNB": pipe((1, 1), cnb()),
        "B_unigram_LR": pipe((1, 1), lr()),
        "C_unigram_SVC": pipe((1, 1), svc()),
        "D_bigram_CNB": pipe((1, 2), cnb()),
        "E_bigram_LR": pipe((1, 2), lr()),
    }


def _metrics(y_true, y_pred):
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
        precision_score,
        recall_score,
    )

    p, r, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, zero_division=0
    )
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_precision": round(float(precision_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)), 4),
        "macro_recall": round(float(recall_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)), 4),
        "weighted_f1": round(float(f1_score(y_true, y_pred, labels=LABELS, average="weighted", zero_division=0)), 4),
        "per_class": {
            lab: {
                "precision": round(float(p[i]), 4),
                "recall": round(float(r[i]), 4),
                "f1": round(float(f1[i]), 4),
                "support": int(sup[i]),
            }
            for i, lab in enumerate(LABELS)
        },
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
        "confusion_labels": LABELS,
    }


def main() -> None:
    import joblib
    import numpy as np

    if not os.path.exists(DEDUPED_JSONL):
        raise SystemExit(f"missing deduped dataset: {DEDUPED_JSONL} (run ml_dedupe_split.py)")

    records = [json.loads(line) for line in open(DEDUPED_JSONL, encoding="utf-8")]
    rec_by_id = {r["id"]: r for r in records}
    tr = [r for r in records if r["split"] == "train"]
    va = [r for r in records if r["split"] == "val"]
    te = [r for r in records if r["split"] == "test"]

    Xtr, ytr = [r["model_text"] for r in tr], [r["label"] for r in tr]
    Xva, yva = [r["model_text"] for r in va], [r["label"] for r in va]
    Xte, yte = [r["model_text"] for r in te], [r["label"] for r in te]

    train_dist = dict(Counter(ytr))
    print(f"train={len(tr)} val={len(va)} test={len(te)} | train class dist={train_dist}")

    # ---- Phase 8/9: train + evaluate every candidate ----
    comparison = {}
    fitted = {}
    for name, model in _candidates().items():
        model.fit(Xtr, ytr)
        fitted[name] = model
        val_m = _metrics(yva, model.predict(Xva))
        test_m = _metrics(yte, model.predict(Xte))
        comparison[name] = {"validation": val_m, "test": test_m, "deployable": name != "C_unigram_SVC"}
        print(f"[{name}] val macroF1={val_m['macro_f1']} acc={val_m['accuracy']} "
              f"| test macroF1={test_m['macro_f1']} acc={test_m['accuracy']}")

    # ---- select best among DEPLOYABLE (proba-capable) by val macro-F1 ----
    deployable = {k: v for k, v in comparison.items() if v["deployable"]}
    best_name = max(deployable, key=lambda k: (deployable[k]["validation"]["macro_f1"],
                                               deployable[k]["validation"]["weighted_f1"]))
    best = fitted[best_name]
    print(f"\nSELECTED (deployable) = {best_name}")

    # ---- Phase 10: threshold / calibration on VALIDATION only ----
    from sklearn.metrics import f1_score

    proba_val = best.predict_proba(Xva)
    top = proba_val.max(axis=1)
    pred_idx = proba_val.argmax(axis=1)
    val_true_idx = [LABELS.index(y) for y in yva]

    thr_table = []
    chosen_thr, chosen_obj = 0.30, -1.0
    for thr in [round(x * 0.05, 2) for x in range(2, 19)]:  # 0.10 .. 0.90
        covered = [i for i in range(len(top)) if top[i] >= thr]
        cov = len(covered) / len(top) if len(top) else 0
        if covered:
            acc_cov = sum(1 for i in covered if pred_idx[i] == val_true_idx[i]) / len(covered)
            preds_cov = [LABELS[pred_idx[i]] for i in covered]
            true_cov = [yva[i] for i in covered]
            present = sorted(set(preds_cov) | set(true_cov))
            mf1_cov = f1_score(true_cov, preds_cov, labels=present, average="macro", zero_division=0) if present else 0.0
        else:
            acc_cov, mf1_cov = 0.0, 0.0
        obj = acc_cov * cov  # balance precision-among-confident vs coverage
        thr_table.append({
            "threshold": thr, "coverage": round(cov, 3), "abstain_rate": round(1 - cov, 3),
            "accuracy_on_covered": round(acc_cov, 4), "macro_f1_on_covered": round(float(mf1_cov), 4),
        })
        if obj > chosen_obj:
            chosen_obj, chosen_thr = obj, thr
    print(f"chosen threshold={chosen_thr} (objective=accuracy_on_covered*coverage); "
          f"tuned on VALIDATION only, never on frozen 99 / dev test")

    # ---- Phase 11: error analysis on DEV TEST (selected model) ----
    proba_te = best.predict_proba(Xte)
    pred_te = [LABELS[i] for i in proba_te.argmax(axis=1)]
    conf_te = _metrics(yte, pred_te)
    pairs = Counter()
    for t, p in zip(yte, pred_te):
        if t != p:
            pairs[f"{t} -> {p}"] += 1
    test_top = [r for r in te if r["annotation_confidence"] < 0.5]
    errs = {
        "confusion_matrix": conf_te["confusion_matrix"],
        "labels": LABELS,
        "top_confusion_pairs": pairs.most_common(15),
        "false_negative_examples": [
            {"id": r["id"], "true": r["label"], "pred": pred_te[i], "title": (r["title"] or "")[:90]}
            for i, r in enumerate(te) if pred_te[i] != r["label"]
        ][:20],
        "low_conf_label_examples": [
            {"id": r["id"], "label": r["label"], "ann_conf": r["annotation_confidence"]}
            for r in test_top
        ][:20],
    }

    # ---- Phase 12: learning curve (selected config, fractions of TRAIN -> VAL) ----
    curve = []
    rng = np.random.default_rng(RANDOM_SEED)
    for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
        k = max(20, int(len(tr) * frac))
        idx = rng.choice(len(tr), size=k, replace=False)
        sub = fitted[best_name].__class__  # build a fresh pipeline of same shape
        fresh = _candidates()[best_name]
        fresh.fit([Xtr[i] for i in idx], [ytr[i] for i in idx])
        m = _metrics(yva, fresh.predict(Xva))
        curve.append({"train_fraction": frac, "train_n": int(k),
                      "val_macro_f1": m["macro_f1"], "val_accuracy": m["accuracy"]})
    print("learning curve (val macroF1):", [c["val_macro_f1"] for c in curve])

    # ---- Phase 13: save artifacts ----
    os.makedirs(os.path.dirname(MODEL_ARTIFACT), exist_ok=True)
    joblib.dump(best, MODEL_ARTIFACT)
    assert set(best.classes_) <= set(LABELS), "artifact learned an unexpected class"

    meta = {
        "model_name": "NewsLens Topic Classifier - Development v0.1",
        "model_series": MODEL_SERIES,
        "model_version": "dev_v0.1",
        "dataset_id": DATASET_ID,
        "dataset_version": "v0.1",
        "preprocessing_version": PREPROCESSING_VERSION,
        "model_text_builder": "app.services.processing.model_text.build_model_text (SHARED train+inference)",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "training_seed": RANDOM_SEED,
        "class_list": list(best.classes_),
        "full_taxonomy": LABELS,
        "selected_candidate": best_name,
        "hyperparameters": {
            "vectorizer": {"sublinear_tf": True, "ngram_range": (1, 2) if best_name in ("D_bigram_CNB", "E_bigram_LR") else (1, 1),
                           "min_df": 1, "stop_words": "english", "lowercase": True},
            "classifier": str(best.named_steps["clf"]),
        },
        "deployment_threshold": chosen_thr,
        "rights_status": RIGHTS_STATUS,
        "status": "DEVELOPMENT / EXPERIMENTAL - rights UNVERIFIED - NOT production",
        "training_counts": train_dist,
        "split_counts": {"train": len(tr), "val": len(va), "test": len(te)},
        "validation_metrics": comparison[best_name]["validation"],
        "test_metrics": comparison[best_name]["test"],
        "candidate_comparison": {k: {"val_macro_f1": v["validation"]["macro_f1"],
                                     "test_macro_f1": v["test"]["macro_f1"]}
                                 for k, v in comparison.items()},
        "threshold_calibration_val": thr_table,
        "learning_curve": curve,
        "evaluation_caveat": (
            "Optimistic upper bound: provisional single-annotator rule-assisted labels "
            "share surface-text features with the TF-IDF model; metrics do not represent "
            "real-world accuracy. 396 records is insufficient for production."
        ),
    }
    with open(MODEL_METADATA, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    with open(COMPARISON_REPORT, "w", encoding="utf-8") as f:
        json.dump({
            "selected": best_name, "chosen_threshold": chosen_thr,
            "candidates": comparison, "error_analysis_test": errs,
            "threshold_calibration_val": thr_table, "learning_curve": curve,
        }, f, indent=2, ensure_ascii=False)

    cfg = {
        "random_seed": RANDOM_SEED, "labels": LABELS,
        "candidates": list(_candidates().keys()),
        "threshold_tuned_on": "validation", "frozen_99_used_for_tuning": False,
        "vectors": "see ml_config / news_topics_eval for shared defaults",
    }
    with open(TRAINING_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    _write_model_card(meta, errs)
    np  # noqa: B018 (referenced for clarity)
    print(f"\nSaved artifact -> {MODEL_ARTIFACT}")
    print(f"Saved metadata -> {MODEL_METADATA}")
    print("DONE")


def _write_model_card(meta, errs):
    lines = [
        "# NewsLens Topic Classifier - Development v0.1 (MODEL CARD)",
        "",
        f"- **Status:** {meta['status']}",
        f"- **Rights:** {meta['rights_status']} (Google News collected; publisher/ML-training rights UNVERIFIED)",
        f"- **Dataset:** {meta['dataset_id']} ({meta['dataset_version']}), single-annotator rule-assisted PROVISIONAL labels",
        f"- **Selected model:** {meta['selected_candidate']}  | seed={meta['training_seed']}",
        f"- **Model text:** {meta['model_text_builder']} (shared train+inference, prevents train/serve skew)",
        f"- **Deployed abstain threshold:** {meta['deployment_threshold']} (tuned on VALIDATION only)",
        "",
        "## Headline metrics (optimistic upper bound - see caveat)",
        f"- Validation: acc={meta['validation_metrics']['accuracy']} macroF1={meta['validation_metrics']['macro_f1']} weightedF1={meta['validation_metrics']['weighted_f1']}",
        f"- Dev test:   acc={meta['test_metrics']['accuracy']} macroF1={meta['test_metrics']['macro_f1']} weightedF1={meta['test_metrics']['weighted_f1']}",
        "",
        "## Candidate comparison (validation macro-F1)",
    ]
    for k, v in meta["candidate_comparison"].items():
        lines.append(f"- {k}: val={v['val_macro_f1']} test={v['test_macro_f1']}")
    lines += ["", "## Top confusion pairs (dev test)"]
    for pair, c in errs["top_confusion_pairs"][:10]:
        lines.append(f"- {pair}: {c}")
    lines += ["", "## Learning curve (val macro-F1)",
              *[f"- {int(c['train_fraction']*100)}% ({c['train_n']}): {c['val_macro_f1']}" for c in meta["learning_curve"]],
              "",
              "## Caveats / limitations",
              "- Metrics are an OPTIMISTIC UPPER BOUND: labels + TF-IDF share surface-text features.",
              "- Health/Entertainment classes have <=2 training examples -> near-unlearnable; per-class scores unreliable.",
              "- 396 records is NOT sufficient for production. This is a plumbing/validation build only.",
              "- Model is an OFF-BY-DEFAULT artifact: runtime only loads it when NLENS_ML_MODEL_PATH is set; production keeps the rule-first + SEED-model behaviour and the frozen-99 tests unchanged.",
              "- Do not publish / redistribute / claim commercial training rights on this corpus or model.",
              ""]
    with open(MODEL_CARD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
