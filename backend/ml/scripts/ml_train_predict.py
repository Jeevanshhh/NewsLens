"""PHASE E-H + R + S + U - train ALL candidates, emit prediction artifacts,
per-class + error analysis, learning curves, documented model selection,
retrain the selected DEVELOPMENT CANDIDATE, and write the complete model card.

Training data = the FINAL adjudicated labels (``topic_dev_final_v0.1``). The 15
``unresolved`` records are EXCLUDED from training (``usable_for_training=False``)
but retained in val/test so evaluation stays representative.

HONESTY: provisional labels and TF-IDF features share the same surface text, so
every metric is an OPTIMISTIC UPPER BOUND - not real-world accuracy. The corpus
is small (396) and rights are UNVERIFIED. This is a DEVELOPMENT artifact.

Run:  python backend/ml/scripts/ml_train_predict.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    BACKEND,
    CANDIDATES_DIR,
    DATASET_ID,
    ERROR_MD,
    FALLBACK_LABEL,
    FINAL_DATASET,
    FINAL_META,
    FINAL_MODEL,
    LEARNING_MD,
    MODEL_CARD_FINAL,
    PREDICTIONS_DIR,
    PREPROCESSING_VERSION,
    RANDOM_SEED,
    RIGHTS_STATUS,
    SELECTION_MD,
    TAXONOMY,
    TRAIN_RESULTS_JSON,
)
from ml_train_eval import LABELS, _candidates, _metrics  # noqa: E402

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

PROBA_CAPABLE = {"A_unigram_CNB", "B_unigram_LR", "D_bigram_CNB", "E_bigram_LR"}


def _load_final():
    return [json.loads(line) for line in open(FINAL_DATASET, encoding="utf-8") if line.strip()]


def _predict(model, texts):
    """Return (labels, confidences|None). SVC -> decision_function, no proba."""
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(texts)
        idx = proba.argmax(axis=1)
        return [model.classes_[i] for i in idx], [float(proba[i, idx[i]]) for i in range(len(idx))]
    labels = model.predict(texts)
    return list(labels), [None] * len(labels)


def _write_predictions(model_name, dataset, split, ids, y_true, y_pred, conf):
    path = os.path.join(PREDICTIONS_DIR, f"{model_name}__{dataset}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for i, rid in enumerate(ids):
            f.write(json.dumps({
                "id": rid, "true_label": y_true[i], "predicted_label": y_pred[i],
                "confidence": (round(conf[i], 4) if conf[i] is not None else None),
                "correct": bool(y_true[i] == y_pred[i]), "model": model_name,
                "dataset": dataset, "split": split,
            }, ensure_ascii=False) + "\n")
    return path


def _external_sets():
    """frozen-99 (SEED holdout) + real-world handcrafted probes, as (name, texts,
    labels) tuples. These are EXTERNAL / non-dev populations - reported separately
    and never used for tuning."""
    out = []
    try:
        from app.services.processing.news_topics_eval import (
            REAL_WORLD_VALIDATION, split_corpus,
        )
        hold_t, hold_l = split_corpus()["holdout"]
        out.append(("frozen99", hold_t, hold_l))
        rw_t = [t for t, _ in REAL_WORLD_VALIDATION]
        rw_l = [l for _t, l in REAL_WORLD_VALIDATION]
        out.append(("realworld_probes", rw_t, rw_l))
    except Exception as e:  # pragma: no cover
        print(f"[warn] external sets unavailable: {e}")
    return out


def main():
    import joblib
    import numpy as np

    recs = _load_final()
    tr = [r for r in recs if r["split"] == "train" and r["usable_for_training"]]
    va = [r for r in recs if r["split"] == "val"]
    te = [r for r in recs if r["split"] == "test"]
    Xtr, ytr = [r["model_text"] for r in tr], [r["label"] for r in tr]
    Xva, yva = [r["model_text"] for r in va], [r["label"] for r in va]
    Xte, yte = [r["model_text"] for r in te], [r["label"] for r in te]
    print(f"train(usable)={len(tr)} val={len(va)} test={len(te)} "
          f"| train dist={dict(Counter(ytr))}")

    external = _external_sets()

    # ---- PHASE E: train + save every candidate separately ----
    results = {}
    fitted = {}
    for name, model in _candidates().items():
        t0 = time.perf_counter()
        model.fit(Xtr, ytr)
        dt = round(time.perf_counter() - t0, 3)
        fitted[name] = model
        cpath = os.path.join(CANDIDATES_DIR, f"{name}.joblib")
        joblib.dump(model, cpath)
        vocab = len(model.named_steps["tfidf"].vocabulary_)
        vm = _metrics(yva, model.predict(Xva))
        tm = _metrics(yte, model.predict(Xte))
        results[name] = {
            "deployable": name in PROBA_CAPABLE,
            "hyperparameters": {"vectorizer_ngram": (1, 2) if name in
                                ("D_bigram_CNB", "E_bigram_LR") else (1, 1),
                                "classifier": str(model.named_steps["clf"])},
            "vocab_size": vocab, "train_n": len(tr), "val_n": len(va), "test_n": len(te),
            "train_seconds": dt, "artifact_bytes": os.path.getsize(cpath),
            "validation": vm, "test": tm,
        }
        print(f"[{name}] vocab={vocab} {dt}s | val acc={vm['accuracy']} "
              f"macroF1={vm['macro_f1']} | test acc={tm['accuracy']} macroF1={tm['macro_f1']}")

    # ---- PHASE F: prediction artifacts (train/val/test + external) ----
    for name, model in fitted.items():
        for split, X, y, R in (("train", Xtr, ytr, tr), ("val", Xva, yva, va),
                               ("test", Xte, yte, te)):
            pred, conf = _predict(model, X)
            _write_predictions(name, f"dev_{split}", split, [r["id"] for r in R], y, pred, conf)
        for ename, etexts, elabels in external:
            pred, conf = _predict(model, etexts)
            em = _metrics(elabels, pred)
            results[name].setdefault("external", {})[ename] = {
                "accuracy": em["accuracy"], "macro_f1": em["macro_f1"],
                "note": "EXTERNAL/non-dev population - never used for tuning",
            }
            _write_predictions(name, ename, "external", list(range(len(etexts))),
                               elabels, pred, conf)

    # ---- PHASE R: documented model selection (validation-driven) ----
    deployable = {k: v for k, v in results.items() if v["deployable"]}
    best_name = max(deployable, key=lambda k: (deployable[k]["validation"]["macro_f1"],
                                               deployable[k]["validation"]["weighted_f1"]))
    best = fitted[best_name]
    svc_note = max(results, key=lambda k: results[k]["validation"]["macro_f1"])
    print(f"\nDEVELOPMENT CANDIDATE (deployable) = {best_name}; "
          f"overall-best-on-val = {svc_note}")

    # ---- threshold on VALIDATION only (selected model) ----
    from sklearn.metrics import f1_score
    proba_val = best.predict_proba(Xva)
    top = proba_val.max(axis=1); pidx = proba_val.argmax(axis=1)
    vtrue = [LABELS.index(y) for y in yva]
    chosen_thr, chosen_obj = 0.30, -1.0
    thr_table = []
    for thr in [round(x * 0.05, 2) for x in range(2, 19)]:
        cov_idx = [i for i in range(len(top)) if top[i] >= thr]
        cov = len(cov_idx) / len(top)
        if cov_idx:
            acc = sum(pidx[i] == vtrue[i] for i in cov_idx) / len(cov_idx)
            pc = [LABELS[pidx[i]] for i in cov_idx]; tc = [yva[i] for i in cov_idx]
            present = sorted(set(pc) | set(tc))
            mf1 = f1_score(tc, pc, labels=present, average="macro", zero_division=0) if present else 0.0
        else:
            acc, mf1 = 0.0, 0.0
        obj = acc * cov
        thr_table.append({"threshold": thr, "coverage": round(cov, 3),
                          "accuracy_on_covered": round(acc, 4), "macro_f1_on_covered": round(float(mf1), 4)})
        if obj > chosen_obj:
            chosen_obj, chosen_thr = obj, thr

    # ---- PHASE G: per-class + confusion + error analysis (dev test) ----
    pred_te, conf_te_list = _predict(best, Xte)
    test_m = results[best_name]["test"]
    pairs = Counter()
    err_ids = []
    for t, p, r in zip(yte, pred_te, te):
        if t != p:
            pairs[f"{t} -> {p}"] += 1
            err_ids.append({"id": r["id"], "true": t, "pred": p})
    cm = test_m["confusion_matrix"]; labs = test_m["confusion_labels"]
    row_sums = [sum(row) or 1 for row in cm]
    norm_cm = [[round(cm[i][j] / row_sums[i], 3) for j in range(len(cm[i]))] for i in range(len(cm))]
    watched = ["Technology -> Science", "Science -> Technology", "Politics -> Crime",
               "Crime -> Politics", "Climate -> Science", "Science -> Climate",
               "Climate -> World", "World -> Climate", "Business -> Technology",
               "Technology -> Business", "Health -> Science", "Science -> Health",
               "Entertainment -> Sports", "Sports -> Entertainment"]
    _write_error_md(test_m, pairs, err_ids, watched)

    # ---- PHASE H: learning curve ----
    curve = []
    rng = np.random.default_rng(RANDOM_SEED)
    for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
        k = max(20, int(len(tr) * frac))
        idx = rng.choice(len(tr), size=k, replace=False)
        fresh = _candidates()[best_name]
        fresh.fit([Xtr[i] for i in idx], [ytr[i] for i in idx])
        m = _metrics(yva, fresh.predict(Xva))
        curve.append({"train_fraction": frac, "train_n": int(k),
                      "val_macro_f1": m["macro_f1"], "val_accuracy": m["accuracy"]})
    _write_learning_md(curve, best_name)

    # ---- PHASE S: final development model + metadata ----
    joblib.dump(best, FINAL_MODEL)
    assert set(best.classes_) <= set(LABELS)
    meta = {
        "model_name": "NewsLens Topic Classifier - Development FINAL v0.1",
        "designation": "DEVELOPMENT CANDIDATE (NOT production model)",
        "model_version": "dev_final_v0.1", "dataset_id": DATASET_ID, "dataset_version": "final_v0.1",
        "preprocessing_version": PREPROCESSING_VERSION,
        "model_text_builder": "app.services.processing.model_text.build_model_text (SHARED train+inference)",
        "selected_candidate": best_name, "seed": RANDOM_SEED,
        "class_list": list(best.classes_), "full_taxonomy": LABELS,
        "vectorizer": {"sublinear_tf": True, "min_df": 1, "stop_words": "english",
                       "lowercase": True,
                       "ngram_range": (1, 2) if best_name in ("D_bigram_CNB", "E_bigram_LR") else (1, 1)},
        "classifier": str(best.named_steps["clf"]),
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "training_row_count": len(tr), "validation_row_count": len(va), "test_row_count": len(te),
        "abstention_threshold": chosen_thr, "threshold_tuned_on": "validation",
        "calibration_status": "uncalibrated_raw_proba (see calibration_audit_v0.1)",
        "validation_metrics": {k: results[best_name]["validation"][k]
                               for k in ("accuracy", "macro_f1", "weighted_f1", "macro_precision", "macro_recall")},
        "test_metrics": {k: results[best_name]["test"][k]
                         for k in ("accuracy", "macro_f1", "weighted_f1", "macro_precision", "macro_recall")},
        "external_metrics": results[best_name].get("external", {}),
        "learning_curve": curve,
        "rights_status": RIGHTS_STATUS, "production_approved": False,
        "evaluation_caveat": ("Optimistic upper bound: labels + features share surface text; "
                              "396 records insufficient for production; human annotation absent."),
    }
    with open(FINAL_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # persist machine-readable training results for later phases
    with open(TRAIN_RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump({"selected": best_name, "best_on_val_any": svc_note,
                   "chosen_threshold": chosen_thr, "threshold_calibration_val": thr_table,
                   "candidates": {k: {"deployable": v["deployable"], "vocab_size": v["vocab_size"],
                                      "train_seconds": v["train_seconds"], "artifact_bytes": v["artifact_bytes"],
                                      "val_acc": v["validation"]["accuracy"], "val_macro_f1": v["validation"]["macro_f1"],
                                      "val_weighted_f1": v["validation"]["weighted_f1"],
                                      "test_acc": v["test"]["accuracy"], "test_macro_f1": v["test"]["macro_f1"],
                                      "external": v.get("external", {})} for k, v in results.items()},
                   "learning_curve": curve}, f, indent=2, ensure_ascii=False)

    _write_selection_md(results, best_name, svc_note, chosen_thr)
    _write_model_card(meta, test_m, norm_cm, labs, pairs)
    print(f"\nSaved FINAL model -> {FINAL_MODEL}")
    print("DONE E-H/R-S-U")


def _write_error_md(test_m, pairs, err_ids, watched):
    L = ["# NewsLens Dev Model - Error Analysis (v0.1)",
         "", "**Population:** development TEST split (39 records).", "",
         "## Top confusion pairs (dev test)",]
    for pair, c in pairs.most_common(15):
        L.append(f"- {pair}: {c}")
    L += ["", "## Watched boundary pairs (Technology/Science, Politics/Crime, Climate/Science, "
          "Climate/World, Business/Technology, Health/Science, Entertainment/Sports)"]
    for w in watched:
        L.append(f"- {w}: {pairs.get(w, 0)}")
    L += ["", "## Confusion matrix (counts, rows=true, cols=pred)",
          "- labels: " + ", ".join(test_m["confusion_labels"])]
    for i, row in enumerate(test_m["confusion_matrix"]):
        if sum(row):
            L.append(f"  - {test_m['confusion_labels'][i]}: {row}")
    L += ["", "## Misclassified record ids (no article text)",
          "- " + (", ".join(str(e["id"]) for e in err_ids) if err_ids else "(none)"), "",
          "_Error patterns derived from actual misclassified records; no explanations invented._", ""]
    with open(ERROR_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_learning_md(curve, best_name):
    L = [f"# Learning Curve - {best_name} (dev)", "",
         "| train fraction | train n | val macro-F1 | val accuracy |",
         "|---|---|---|---|"]
    for c in curve:
        L.append(f"| {int(c['train_fraction']*100)}% | {c['train_n']} | "
                 f"{c['val_macro_f1']} | {c['val_accuracy']} |")
    rising = curve[-1]["val_macro_f1"] >= curve[0]["val_macro_f1"]
    L += ["", f"- Trend: {'still rising / data-hungry' if rising else 'plateauing'} "
          "at the smallest end (tiny class supports make low fractions noisy).",
          "- **Conclusion:** more labelled data is expected to help the under-represented "
          "classes, but per-class support (<20 for several classes) limits how meaningful "
          "the low-fraction points are. Not a substitute for a larger rights-cleared corpus.", ""]
    with open(LEARNING_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_selection_md(results, best_name, svc_note, thr):
    L = ["# Model Selection - DEVELOPMENT CANDIDATE (v0.1)", "",
         "Selection uses documented **validation** criteria (never the frozen-99 or a "
         "single test set). Primary: validation macro-F1 among *probability-capable* "
         "candidates (required for the confidence/abstention runtime).", "",
         "| candidate | deployable | val acc | val macroF1 | val weightedF1 | test macroF1 |",
         "|---|---|---|---|---|---|"]
    for k, v in results.items():
        L.append(f"| {k} | {v['deployable']} | {v['validation']['accuracy']} | "
                 f"{v['validation']['macro_f1']} | {v['validation']['weighted_f1']} | "
                 f"{v['test']['macro_f1']} |")
    L += ["", f"- **Selected DEVELOPMENT CANDIDATE:** `{best_name}` "
          "(probability-capable; loadable by the runtime artifact loader).",
          f"- **Documented tradeoff:** the overall best validation macro-F1 was "
          f"`{svc_note}`. If that is `C_unigram_SVC` it is **excluded from deployment** "
          "because LinearSVC has no native `predict_proba`, so it cannot feed the "
          "confidence/abstention layer without extra calibration. This is stated rather "
          "than hidden.",
          f"- **Abstention threshold:** {thr} (tuned on validation only).",
          "- Selection is NOT a production decision; the winner remains a development "
          "artifact on an optimistic-upper-bound evaluation.", ""]
    with open(SELECTION_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_model_card(meta, test_m, norm_cm, labs, pairs):
    L = ["# MODEL CARD - NewsLens Topic Classifier (Development FINAL v0.1)", "",
         "**This model is a development artifact and is not approved for production use.**",
         "",
         "## 1. Purpose / 2. Intended use", "- Assign an L1 news topic to headline+description text.",
         "- Intended use: internal development experimentation / a rule-first fallback signal.",
         "## 3. Prohibited use", "- Production serving, redistribution, publication, or "
         "any commercial training claim (rights UNVERIFIED).",
         "## 4. Dataset / 5. Provenance / 6. Rights", f"- `{meta['dataset_id']}` final_v0.1, "
         f"{meta['training_row_count']} train / {meta['validation_row_count']} val / "
         f"{meta['test_row_count']} test. Google-News collected. **rights_status="
         f"{meta['rights_status']}**.",
         "## 7. Taxonomy (L1, single-select)", f"- {', '.join(meta['full_taxonomy'])}",
         "## 8. Preprocessing", f"- `{meta['preprocessing_version']}` via shared "
         "build_model_text (NFKC + HTML strip + entity unescape + whitespace collapse); "
         "identical at train and inference (no train/serve skew).",
         "## 9. Architecture / 10. Training", f"- {meta['selected_candidate']} "
         f"(TF-IDF {meta['vectorizer']['ngram_range']} -> `{meta['classifier']}`), seed="
         f"{meta['seed']}, vocab-bounded by {meta['training_row_count']} docs.",
         "## 11. Evaluation (optimistic upper bound)",
         f"- val: acc={meta['validation_metrics']['accuracy']} macroF1={meta['validation_metrics']['macro_f1']}",
         f"- dev test: acc={meta['test_metrics']['accuracy']} macroF1={meta['test_metrics']['macro_f1']} "
         f"weightedF1={meta['test_metrics']['weighted_f1']}",
         "## 12. Per-class metrics (dev test)",
         "| class | precision | recall | f1 | support |", "|---|---|---|---|---|"]
    for lab, m in test_m["per_class"].items():
        L.append(f"| {lab} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    L += ["", "## 13. Limitations", "- 396 records; several classes <20 examples -> unreliable "
          "per-class scores; single-annotator provisional labels; optimistic upper bound.",
          "## 14. Calibration / 15. Abstention", f"- raw probabilities (uncalibrated here; see "
          "calibration_audit). Abstention threshold {0} tuned on validation.".format(meta["abstention_threshold"]),
          "## 16. Known imbalance / 17. Temporal / 18. Annotation", "- Sports/Health/"
          "Entertainment/Crime under-represented; ~80% of records in one month; no human "
          "second annotator (automated method-agreement only).",
          "## 19. Frozen benchmark", "- Evaluated separately in frozen_benchmark_v0.1.md "
          "(external, untouched SEED-derived 99).",
          "## 20. Unseen benchmark", "- No rights-cleared unseen real-world set -> see "
          "benchmarks_audit_v0.1.md (NOT AVAILABLE).",
          "## 21. Production status", f"- production_approved=**{meta['production_approved']}**, "
          f"rights_status=**{meta['rights_status']}**.", "",
          "## Normalized confusion matrix (dev test, rows=true)",
          "- labels: " + ", ".join(labs)]
    for i, row in enumerate(norm_cm):
        if any(row):
            L.append(f"  - {labs[i]}: {row}")
    L.append("")
    with open(MODEL_CARD_FINAL, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
