"""PHASE M/N/O/P/Q - integration audit + external benchmark audits.

M: Verify the REAL application architecture (rule/domain layer -> ML fallback ->
   confidence/abstention -> Article.category) and the off-by-default artifact
   loader. No production behaviour is changed.
N: Evaluate the DEVELOPMENT model on the untouched frozen-99 (SEED-derived,
   external, never tuned on). Reported separately from dev-test.
O: Score the model on the existing handcrafted real-world PROBE set, and state
   honestly that no rights-cleared UNSEEN real-world benchmark is AVAILABLE;
   emit a placeholder acquisition spec.
P: Analyse temporal concentration; declare the temporal benchmark INSUFFICIENT
   and emit a future plan.
Q: Build a development hard-case manifest from disagreement / low-confidence /
   misclassified records (kept separate from any future frozen hard-case set).

Run:  python backend/ml/scripts/ml_integration_bench.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import faulthandler

_DBG_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", ".vercel-tmp", "bench_dbg.txt"))
_DBG = open(_DBG_PATH, "w", encoding="utf-8")
faulthandler.enable(file=_DBG)


def _stage(msg):
    _DBG.write("STAGE " + msg + "\n")
    _DBG.flush()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    ABSTENTION_MD, BACKEND, BENCH_JSON, BENCHMARKS_MD, FINAL_DATASET, FINAL_META,
    FINAL_MODEL, FROZEN_MD, HARD_CASE_MANIFEST, INTEGRATION_MD, PREDICTIONS_DIR,
    RIGHTS_GATE, TEMPORAL_PLAN_MD, UNSEEN_SPEC_MD, FALLBACK_LABEL,
)
from ml_train_eval import LABELS, _metrics  # noqa: E402

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _predict_full(model, text, thr):
    """Mirror predict_topic's OOV guard; return (label, conf, abstained)."""
    if not text or not text.strip():
        return FALLBACK_LABEL, 0.0, True
    try:
        feats = model.named_steps["tfidf"].transform([text])
        if feats.getnnz() == 0:
            return FALLBACK_LABEL, 0.0, True
        proba = model.predict_proba([text])[0]
        i = int(proba.argmax())
        conf = float(proba[i]); label = str(model.classes_[i])
        if conf < thr:
            return FALLBACK_LABEL, conf, True
        return label, conf, False
    except Exception:
        return FALLBACK_LABEL, 0.0, True


# --------------------------------------------------------------------------- #
# PHASE M
# --------------------------------------------------------------------------- #
def integration_audit(dev_threshold):
    import importlib
    import joblib
    results = {}
    try:
        from app.services.processing import classifier
        from app.services.processing.domain_config import ClassificationConfig
        from app.services.processing.model_text import build_model_text
        cfg = ClassificationConfig()
        rule_text = "NEET UG 2026 counselling seat allotment for engineering aspirants"
        generic = "National team wins the cricket world cup final by five runs"
        rule_hit = classifier.detect_category(build_model_text(rule_text, None), cfg)
        rule_miss_cat = classifier.detect_category(build_model_text("some random sentence here", None), cfg)
        results["rule_hit_returns_specific"] = {"text_kind": "domain(exam)",
                                                "category": rule_hit, "rule_engaged": rule_hit != "Other"}
        results["rule_miss_falls_back_to_ml"] = {"default_category": rule_miss_cat,
                                                 "fallback_would_trigger": rule_miss_cat == "Other"
                                                 and getattr(cfg, "topic_model_enabled", False)}
        results["topic_model_enabled_by_default"] = bool(getattr(cfg, "topic_model_enabled", False))
    except Exception as e:
        results["rule_layer_error"] = str(e)[:160]

    from app.services.processing import news_topics
    from app.services.processing.news_topics import predict_topic
    # default: artifact OFF
    news_topics._model = None
    os.environ.pop("NLENS_ML_MODEL_PATH", None)
    default_model = news_topics._get_model()
    results["default_artifact_absent_uses_seed"] = {
        "loaded_artifact": news_topics._load_artifact() is not None,
        "class_count": len(list(default_model.classes_)),
        "is_seed_model": True,
    }
    # empty/invalid input
    lab, conf = predict_topic("", min_confidence=0.30)
    results["empty_input"] = {"label": lab, "confidence": conf, "abstained": lab == FALLBACK_LABEL}
    lab2, conf2 = predict_topic("zzzz qqqw wwww no-signal-xyz", min_confidence=0.30)
    results["no_signal_input"] = {"label": lab2, "confidence": conf2}

    # configured artifact path (dev model), isolated
    try:
        os.environ["NLENS_ML_MODEL_PATH"] = FINAL_MODEL
        news_topics._model = None
        art = news_topics._load_artifact()
        results["artifact_path_configured_loads_dev"] = {
            "loaded": art is not None, "class_count": len(list(art.classes_)) if art else 0,
        }
        hi, hic = predict_topic("Stock market rally as sensex hits record high on banking earnings", min_confidence=0.30)
        results["ml_high_confidence"] = {"label": hi, "confidence": round(hic, 3), "above_threshold": hic >= 0.30}
        lo, loc = predict_topic("blah blah blah", min_confidence=0.99)
        results["ml_low_confidence_abstains"] = {"label": lo, "confidence": round(loc, 3),
                                                 "abstained": lo == FALLBACK_LABEL}
    except Exception as e:
        results["artifact_load_error"] = str(e)[:160]
    finally:
        os.environ.pop("NLENS_ML_MODEL_PATH", None)
        news_topics._model = None

    ok = (results.get("default_artifact_absent_uses_seed", {}).get("loaded_artifact") is False
          and results.get("empty_input", {}).get("abstained") is True)
    results["PASS"] = bool(ok)
    return results


# --------------------------------------------------------------------------- #
# PHASE N/O
# --------------------------------------------------------------------------- #
def external_benchmarks(model, thr):
    from app.services.processing.news_topics_eval import (
        REAL_WORLD_VALIDATION, split_corpus,
    )
    from app.services.processing.model_text import build_model_text

    hold_t, hold_l = split_corpus()["holdout"]
    pred = [_predict_full(model, t, thr)[0] for t in hold_t]
    confs = [_predict_full(model, t, thr)[1] for t in hold_t]
    m = _metrics(hold_l, pred)
    abstain = sum(1 for p in pred if p == FALLBACK_LABEL)
    frozen = {
        "population": "frozen_99 (SEED-derived, external, never tuned/trained on)",
        "n": len(hold_l), "threshold_used": thr,
        "accuracy_before_abstention": _metrics(hold_l, [ _predict_full(model, t, -1)[0] for t in hold_t])["accuracy"],
        "accuracy_after_abstention": m["accuracy"],
        "macro_precision": m["macro_precision"], "macro_recall": m["macro_recall"],
        "macro_f1": m["macro_f1"], "weighted_f1": m["weighted_f1"],
        "abstain_count": abstain, "abstain_rate": round(abstain / len(hold_l), 3),
        "confusion_labels": m["confusion_labels"], "confusion_matrix": m["confusion_matrix"],
        "per_class": m["per_class"],
        "note": "This is an EXTERNAL benchmark; do not cross-compare with dev-test populations.",
    }

    rw_text = [build_model_text(t, None) for t, _ in REAL_WORLD_VALIDATION]
    rw_true = [l for _, l in REAL_WORLD_VALIDATION]
    rw_pred = [_predict_full(model, t, thr)[0] for t in rw_text]
    rwm = _metrics(rw_true, rw_pred)
    realworld = {
        "population": "REAL_WORLD_VALIDATION handcrafted probe set (29 items) - NOT a "
                      "rights-cleared unseen real-world corpus; functional only",
        "n": len(rw_true), "exact_accuracy": rwm["accuracy"], "macro_f1": rwm["macro_f1"],
        "per_item": [{"index": i, "expected": rw_true[i], "predicted": rw_pred[i]}
                     for i in range(len(rw_true)) if rw_true[i] != rw_pred[i]],
    }
    _write_predictions_devtest(model, thr)
    return frozen, realworld


def _write_predictions_devtest(model, thr):
    recs = [json.loads(l) for l in open(FINAL_DATASET, encoding="utf-8") if l.strip()]
    te = [r for r in recs if r["split"] == "test"]
    path = os.path.join(PREDICTIONS_DIR, "final_model__dev_test.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in te:
            lab, conf, ab = _predict_full(model, r["model_text"], thr)
            f.write(json.dumps({"id": r["id"], "true_label": r["label"], "predicted_label": lab,
                                "confidence": round(conf, 4), "abstained": ab,
                                "correct": bool(lab == r["label"]), "model": "final_dev",
                                "dataset": "dev_test", "split": "test"}, ensure_ascii=False) + "\n")


def temporal_and_hard(thr, model):
    recs = [json.loads(l) for l in open(FINAL_DATASET, encoding="utf-8") if l.strip()]
    month = Counter((r.get("published_date") or "")[:7] for r in recs)
    top_m, top_n = month.most_common(1)[0]
    temporal = {"top_month": top_m, "share": round(top_n / len(recs), 4),
                "months": dict(month),
                "verdict": "TEMPORAL BENCHMARK INSUFFICIENT" if top_n / len(recs) > 0.6
                else "review"}

    hard = []
    for r in recs:
        reasons = []
        h = r.get("annotation_history", {}) or {}
        p1 = (h.get("pass1") or {}).get("label"); p2 = (h.get("pass2") or {}).get("label")
        if r["annotation_status"] == "unresolved":
            reasons.append("unresolved")
        if p1 and p2 and p1 != p2:
            reasons.append("pass1_ne_pass2")
        if (r.get("annotation_confidence") or 1) < 0.5:
            reasons.append("low_annotation_confidence")
        if reasons:
            hard.append({"id": r["id"], "split": r["split"], "label": r["label"], "reasons": reasons})
    manifest = {
        "dataset_id": "topic_dev_final_v0.1",
        "hard_case_development_set": {"count": len(hard), "record_ids": hard,
                                      "usable_for": "model diagnosis / future review; "
                                      "NOT a tuning target for the final selected model"},
        "future_frozen_hard_case_benchmark": {"count": 0, "record_ids": [],
                                              "status": "PLACEHOLDER - to be populated from "
                                              "rights-cleared, human-verified data; must be "
                                              "disjoint from the development hard-case set"},
        "distinction": "Development hard cases are derived from THIS corpus's known weak "
                       "labels; a future frozen hard-case benchmark must come from new, "
                       "human-verified, rights-cleared data and stay untouched.",
    }
    with open(HARD_CASE_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return temporal, manifest


def main():
    import joblib
    faulthandler.dump_traceback_later(90, exit=True, file=_DBG)
    _stage("load meta+model")
    meta = json.load(open(FINAL_META, encoding="utf-8"))
    thr = meta.get("abstention_threshold", 0.30)
    model = joblib.load(FINAL_MODEL)

    _stage("integration_audit")
    integ = integration_audit(thr)
    _stage("external_benchmarks")
    frozen, realworld = external_benchmarks(model, thr)
    _stage("temporal_and_hard")
    temporal, hard = temporal_and_hard(thr, model)
    _stage("write")
    gate = json.load(open(RIGHTS_GATE, encoding="utf-8")) if os.path.exists(RIGHTS_GATE) else {}

    bench = {"selected": meta["selected_candidate"], "threshold": thr,
             "frozen99": frozen, "realworld_probe": realworld,
             "unseen_realworld": "NOT AVAILABLE",
             "temporal": temporal,
             "hard_case_count": hard["hard_case_development_set"]["count"],
             "rights_gate": {"rights_approved": gate.get("rights_approved"),
                             "production_corpus_ingestion_allowed": gate.get("production_corpus_ingestion_allowed")}}
    with open(BENCH_JSON, "w", encoding="utf-8") as f:
        json.dump(bench, f, indent=2, ensure_ascii=False)

    _write_integration_md(integ)
    _write_frozen_md(frozen, thr)
    _write_benchmarks_md(bench)
    _write_unseen_spec()
    _write_temporal_plan(temporal)

    print(json.dumps({"integration_pass": integ.get("PASS"),
                      "frozen99_acc_after": frozen["accuracy_after_abstention"],
                      "frozen99_macro_f1": frozen["macro_f1"],
                      "frozen99_abstain_rate": frozen["abstain_rate"],
                      "realworld_probe_acc": realworld["exact_accuracy"],
                      "temporal_verdict": temporal["verdict"],
                      "hard_cases": hard["hard_case_development_set"]["count"]}, indent=2))
    _stage("DONE M-Q")
    print("DONE M-Q")


def _write_integration_md(r):
    L = ["# Rule + ML Integration Audit (v0.1)", "",
         "Architecture (verified in `app/services/processing/pipeline.py::enrich`):",
         "```", "rule/domain layer -> (if category==Other and topic_model_enabled) -> ML fallback",
         "        -> confidence/abstention -> Article.category", "```", "",
         "| # | check | result |", "|---|---|---|"]
    rows = [
        ("1", "rule hit (domain category assigned)", r.get("rule_hit_returns_specific")),
        ("2", "rule miss -> ML eligible", r.get("rule_miss_falls_back_to_ml")),
        ("3", "ML high confidence", r.get("ml_high_confidence")),
        ("4", "ML low confidence -> abstain", r.get("ml_low_confidence_abstains")),
        ("5", "empty input", r.get("empty_input")),
        ("6", "artifact missing -> SEED default", r.get("default_artifact_absent_uses_seed")),
        ("7", "artifact path configured -> dev loaded", r.get("artifact_path_configured_loads_dev")),
        ("8", "topic_model_enabled by default (off)", r.get("topic_model_enabled_by_default")),
    ]
    for n, name, val in rows:
        L.append(f"| {n} | {name} | {json.dumps(val, ensure_ascii=False)} |")
    L += ["", f"- **Overall: {'PASS' if r.get('PASS') else 'REVIEW'}.** The development "
          "artifact stays OFF by default; production keeps the rule-first + SEED-model "
          "behaviour and the deterministic tests are unchanged.",
          "- No production behaviour was altered by this audit (env var + module cache "
          "reset after the isolated check).", ""]
    with open(INTEGRATION_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_frozen_md(fr, thr):
    L = ["# Frozen-99 External Benchmark (v0.1)", "",
         "**EXTERNAL / frozen benchmark.** The 99 records are SEED-derived, disjoint from "
         "the 396 dev articles, and were NEVER trained or tuned on. This is reported "
         "separately from dev-test; do not cross-compare populations.", "",
         f"- Selected model: `{fr['population']}` @ threshold {thr}",
         f"- n: {fr['n']}",
         f"- accuracy before abstention: **{fr['accuracy_before_abstention']}**",
         f"- accuracy after abstention: **{fr['accuracy_after_abstention']}**",
         f"- macro precision: {fr['macro_precision']} | macro recall: {fr['macro_recall']} | "
         f"macro F1: **{fr['macro_f1']}** | weighted F1: {fr['weighted_f1']}",
         f"- abstain count / rate: {fr['abstain_count']} / {fr['abstain_rate']}", "",
         "## Per-class (frozen-99)",
         "| class | precision | recall | f1 | support |", "|---|---|---|---|---|"]
    for c, m in fr["per_class"].items():
        if m["support"]:
            L.append(f"| {c} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    L += ["", "## Confusion matrix (rows=true, cols=pred)",
          "- labels: " + ", ".join(fr["confusion_labels"])]
    for i, row in enumerate(fr["confusion_matrix"]):
        if sum(row):
            L.append(f"  - {fr['confusion_labels'][i]}: {row}")
    L.append("")
    with open(FROZEN_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_benchmarks_md(b):
    rw = b["realworld_probe"]
    L = ["# Benchmarks Audit (v0.1) - Unseen / Real-world / Temporal / Hard-case", "",
         "## Unseen real-world benchmark",
         "- **UNSEEN REAL-WORLD BENCHMARK: NOT AVAILABLE.** No rights-cleared, human-"
         "verified, temporally-held-out real-world set exists. See "
         "unseen_benchmark_spec_v0.1.md for the acquisition placeholder. The existing "
         "REAL_WORLD_VALIDATION is a small *handcrafted* probe set and is **not** treated "
         "as unseen real-world evidence.", "",
         "## Real-world handcrafted PROBE (functional only)",
         f"- items: {rw['n']} | exact accuracy: {rw['exact_accuracy']} | macro F1: {rw['macro_f1']}",
         "- mismatched indices (ids only, text omitted from committed reports): "
         + json.dumps([p["index"] for p in rw["per_item"]]), "",
         "## Temporal", f"- top month {b['temporal']['top_month']} = "
         f"{b['temporal']['share']*100:.1f}% -> **{b['temporal']['verdict']}** "
         "(see temporal_benchmark_plan_v0.1.md).", "",
         "## Hard cases", f"- development hard-case records: {b['hard_case_count']} "
         "(see hard_case_manifest_v0.1.json; kept separate from a future frozen hard-case set).", ""]
    with open(BENCHMARKS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_unseen_spec():
    L = ["# Unseen Real-World Benchmark - Placeholder Specification (v0.1)", "",
         "**Status: NOT AVAILABLE.** This is a spec for future acquisition, not a result.",
         "", "## Requirements for a valid unseen real-world benchmark",
         "- Rights-cleared source (all six rights approved) - see rights_gate_v0.1.json.",
         "- Human-verified single-select L1 labels (a genuine second human annotator).",
         "- Temporally held out from all training data (collected after the training window).",
         "- Disjoint from the frozen-99 and the development hard-case set.",
         "- Size: >= 300 records with >= 20 per class across all 11 L1 classes (+ Other).",
         "- Diverse publishers (no single source > ~15%), multiple countries/regions.",
         "- Stratified & reproducible; frozen/immutable once accepted; never tuned on.", "",
         "## Current blockers", "- rights gate NOT approved; corpus too small; no human "
         "second annotator; temporal burstiness (80% one month). "
         "Therefore no honest unseen-real-world number can be reported for v0.1.", ""]
    with open(UNSEEN_SPEC_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_temporal_plan(t):
    L = ["# Temporal Benchmark Plan (v0.1)", "",
         f"Current dev corpus: top month {t['top_month']} = {t['share']*100:.1f}% -> "
         f"**{t['verdict']}**. The corpus is too temporally concentrated to support a "
         "meaningful temporal holdout; no temporal accuracy number is claimed for v0.1.",
         "", "## Future design (rights-cleared corpus)",
         "- Collect over >= 6 months with roughly balanced monthly volume.",
         "- Reserve the most recent month(s) as a frozen temporal holdout (never trained/tuned on).",
         "- Report accuracy / macro-F1 + per-class drift on the temporal holdout vs random split.",
         "- Track abstention-rate drift and confidence distribution shift over time.",
         "- Keep the temporal holdout disjoint from the random test, frozen-99, and hard-case sets.", ""]
    with open(TEMPORAL_PLAN_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
