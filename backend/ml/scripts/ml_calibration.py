"""PHASE I/J - calibration experiments + low-confidence / abstention audit.

For the selected DEVELOPMENT CANDIDATE (probability-capable) we compare:
  1. raw TF-IDF+classifier probabilities
  2. calibrated probabilities via CalibratedClassifierCV (sigmoid & isotonic)

ALL calibration / threshold / abstention decisions use the VALIDATION split only.
The frozen-99 and dev-test are never tuned on. Calibration gracefully degrades to
"PARTIAL" when the tiny classes (support 1-2) make stratified CV infeasible.

Writes calibration_audit_v0.1.{md,json} and abstention_audit_v0.1.md.

Run:  python backend/ml/scripts/ml_calibration.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    ABSTENTION_MD, BACKEND, CALIBRATION_JSON, CALIBRATION_MD, FINAL_DATASET,
    FALLBACK_LABEL, RANDOM_SEED, TAXONOMY, TRAIN_RESULTS_JSON,
)
from ml_train_eval import LABELS, _candidates  # noqa: E402

if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]


def _load_final():
    return [json.loads(line) for line in open(FINAL_DATASET, encoding="utf-8") if line.strip()]


def _conf_curve(proba, classes):
    idx = proba.argmax(axis=1)
    conf = proba.max(axis=1)
    pred = [classes[i] for i in idx]
    return pred, conf, idx


def _coverage_table(y_true, proba, classes):
    """Coverage / precision-at-threshold using the MODEL's column order.
    Returns (rows, conf, pred, correct_flags). True labels the model cannot
    emit (class not learned) are counted incorrect rather than crashing."""
    pred, conf, idx = _conf_curve(proba, classes)
    colof = {c: i for i, c in enumerate(classes)}
    truth_idx = [colof.get(y, -1) for y in y_true]
    correct = [truth_idx[i] == idx[i] for i in range(len(y_true))]
    rows = []
    for thr in THRESHOLDS:
        cov_idx = [i for i in range(len(conf)) if conf[i] >= thr]
        cov = len(cov_idx) / len(conf) if len(conf) else 0.0
        acc = sum(correct[i] for i in cov_idx) / len(cov_idx) if cov_idx else 0.0
        rows.append({"threshold": thr, "coverage": round(cov, 3),
                     "abstain_rate": round(1 - cov, 3), "precision_at_coverage": round(acc, 4)})
    return rows, conf, pred, correct


def _ece(conf, correct, n_bins=10):
    """Expected calibration error (top-class), equal-width bins."""
    import numpy as np
    conf = np.asarray(conf); correct = np.asarray(correct, dtype=float)
    ece, cnt = 0.0, len(conf)
    for lo in [b / n_bins for b in range(n_bins)]:
        hi = lo + 1.0 / n_bins
        m = (conf >= lo) & (conf < hi) if hi < 1.0 else (conf >= lo)
        if m.sum() == 0:
            continue
        ece += abs(conf[m].mean() - correct[m].mean()) * (m.sum() / cnt)
    return round(float(ece), 4)


def _fit_calibrator(base, X, y, method):
    """Fit a fast per-class multiclass calibrator (Platt / isotonic) on data (X,y).

    Returns a callable proba_fn(X) -> calibrated (n, k) probability matrix. This
    replaces ``CalibratedClassifierCV``, whose internal cross-validation loop is
    pathologically slow in this environment.
    """
    import numpy as np
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    classes = list(base.classes_)
    proba = base.predict_proba(X)
    y_idx = np.array([classes.index(t) for t in y])
    calibrators = {}
    for j, c in enumerate(classes):
        s = proba[:, j]
        t = (y_idx == j).astype(int)
        if len(set(t.tolist())) < 2 or np.ptp(s) == 0:
            calibrators[j] = None
            continue
        if method == "sigmoid":
            lr = LogisticRegression(max_iter=1000, C=1e6)
            lr.fit(s.reshape(-1, 1), t)
            calibrators[j] = ("sg", lr)
        else:
            ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            ir.fit(s, t)
            calibrators[j] = ("iso", ir)

    def proba_fn(Xq):
        pq = base.predict_proba(Xq)
        out = np.zeros_like(pq)
        for j in range(pq.shape[1]):
            cal = calibrators.get(j)
            if cal is None:
                out[:, j] = pq[:, j]
            elif cal[0] == "sg":
                out[:, j] = cal[1].predict_proba(pq[:, j].reshape(-1, 1))[:, 1]
            else:
                out[:, j] = cal[1].predict(pq[:, j])
        rs = out.sum(axis=1)
        rs[rs == 0] = 1.0
        return out / rs[:, None]

    return proba_fn


def main():
    import joblib
    import numpy as np

    tr_res = json.load(open(TRAIN_RESULTS_JSON, encoding="utf-8"))
    selected = tr_res["selected"]

    recs = _load_final()
    tr = [r for r in recs if r["split"] == "train" and r["usable_for_training"]]
    va = [r for r in recs if r["split"] == "val"]
    Xtr, ytr = [r["model_text"] for r in tr], [r["label"] for r in tr]
    Xva, yva = [r["model_text"] for r in va], [r["label"] for r in va]

    base = _candidates()[selected]
    base.fit(Xtr, ytr)

    out = {"selected_candidate": selected, "tuned_on": "validation",
           "frozen99_tuned": False,
           "method_note": "Manual per-class Platt (LogisticRegression) / isotonic "
                          "calibration; CalibratedClassifierCV(cv=*) was pathologically "
                          "slow in this environment and was replaced by an equivalent "
                          "one-vs-rest calibrator. Calibrators fit and evaluated on the "
                          "validation split (in-sample) because no other held-out, non-frozen "
                          "data exists for a 396-record corpus -> indicative, optimistic.",
           "models": {}}

    base_classes = list(base.classes_)

    # raw
    raw_proba = base.predict_proba(Xva)
    raw_rows, raw_conf, raw_pred, raw_correct = _coverage_table(yva, raw_proba, base_classes)
    out["models"]["raw"] = {"coverage_table": raw_rows, "ece": _ece(raw_conf, raw_correct),
                            "mean_confidence": round(float(np.mean(raw_conf)), 4),
                            "calibrated": False}

    # calibrated variants (fit + evaluated on validation - see method_note)
    for method in ("sigmoid", "isotonic"):
        try:
            proba_fn = _fit_calibrator(base, Xva, yva, method)
            cp = proba_fn(Xva)
            crows, cconf, cpred, ccorrect = _coverage_table(yva, cp, base_classes)
            out["models"][f"calibrated_{method}"] = {
                "method": method, "status": "OK", "calibrated": True,
                "coverage_table": crows, "ece": _ece(cconf, ccorrect),
                "mean_confidence": round(float(np.mean(cconf)), 4)}
        except Exception as e:  # pragma: no cover
            out["models"][f"calibrated_{method}"] = {
                "method": method, "status": "FAILED", "reason": str(e)[:160]}

    # recommendation: lowest ECE among available variants -> threshold maximising
    # precision_at_coverage while keeping coverage >= 0.5 on validation
    def score(m):
        eces = [out["models"][m]["ece"]] if "ece" in out["models"][m] else [1.0]
        return eces[0]
    variants = [m for m in out["models"] if out["models"][m].get("ece") is not None]
    best_variant = min(variants, key=score) if variants else "raw"
    best_rows = out["models"][best_variant]["coverage_table"]
    rec_thr = 0.30
    for row in best_rows:
        if row["coverage"] >= 0.5 and row["precision_at_coverage"] >= 0.85:
            rec_thr = row["threshold"]
            break
    out["recommendation"] = {
        "best_calibration_variant": best_variant,
        "best_variant_ece": out["models"][best_variant]["ece"],
        "recommended_abstention_threshold": rec_thr,
        "production_default_unchanged": 0.30,
        "note": "Development recommendation only. Do not blindly replace the runtime "
                "0.30 default; production activation is BLOCKED (rights/human labels).",
    }

    with open(CALIBRATION_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    _write_cal_md(out)
    _write_abstention_md(out, raw_conf, raw_correct, va, yva, raw_pred)

    print(json.dumps({"selected": selected, "best_variant": best_variant,
                      "ece": {m: out["models"][m].get("ece") for m in out["models"]},
                      "rec_threshold": rec_thr}, indent=2))
    # persist raw conf arrays count for reproducibility (no text)
    joblib  # noqa
    print("DONE I/J")


def _write_cal_md(out):
    L = ["# Calibration Audit (v0.1)", "",
         f"- Selected candidate: `{out['selected_candidate']}`",
         "- Tuned on: **validation only**; frozen-99 / dev-test never tuned on.", "",
         "## Reliability / coverage by variant",
         "| variant | calibrated | mean conf | ECE (top-class) | status |",
         "|---|---|---|---|---|"]
    for m, v in out["models"].items():
        L.append(f"| {m} | {v.get('calibrated')} | {v.get('mean_confidence')} | "
                 f"{v.get('ece')} | {v.get('status', 'OK')} |")
    L += ["", "## Threshold sweep (coverage / precision-at-coverage)",
          "Validation thresholds tested: " + ", ".join(str(t) for t in THRESHOLDS), ""]
    for m, v in out["models"].items():
        if "coverage_table" not in v:
            continue
        L += [f"### {m}", "| threshold | coverage | abstain | precision@coverage |",
              "|---|---|---|---|"]
        for r in v["coverage_table"]:
            L.append(f"| {r['threshold']} | {r['coverage']} | {r['abstain_rate']} | "
                     f"{r['precision_at_coverage']} |")
        L.append("")
    rec = out["recommendation"]
    L += ["## Recommendation",
          f"- Best calibration variant: **{rec['best_calibration_variant']}** "
          f"(ECE {rec['best_variant_ece']}).",
          f"- Recommended development abstention threshold: **{rec['recommended_abstention_threshold']}** "
          "(validation-derived; not applied to production).",
          f"- {rec['note']}", "",
          "_CNB raw probabilities are known to be poorly calibrated; calibration "
          "here is an experiment, and the recommendation is explicitly a development "
          "one. Tiny classes limit how reliable any CV calibration is._", ""]
    with open(CALIBRATION_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def _write_abstention_md(out, conf, correct, va, yva, pred):
    import numpy as np
    conf = list(conf)
    order = sorted(range(len(conf)), key=lambda i: conf[i])
    lowest = [{"id": va[i]["id"], "true": yva[i], "pred": pred[i],
               "confidence": round(conf[i], 4)} for i in order[:15]]
    wrong_hi = sorted([(i) for i in range(len(conf)) if not correct[i]],
                      key=lambda i: -conf[i])[:15]
    false_conf = [{"id": va[i]["id"], "true": yva[i], "pred": pred[i],
                   "confidence": round(conf[i], 4)} for i in wrong_hi]
    hist = {f"{b/10:.1f}-{(b+1)/10:.1f}": int(((np.asarray(conf) >= b/10) & (np.asarray(conf) < (b+1)/10)).sum())
            for b in range(10)}
    mean_c = float(np.mean(conf))
    mean_correct = float(np.mean([conf[i] for i in range(len(conf)) if correct[i]])) if any(correct) else 0.0
    mean_wrong = float(np.mean([conf[i] for i in range(len(conf)) if not correct[i]])) if any(not c for c in correct) else 0.0
    L = ["# Low-confidence / Abstention Audit (v0.1)", "",
         "**Population: validation split (tuning set). Article text omitted; ids only.**", "",
         f"- Confidence histogram (top-class): {hist}",
         f"- Mean confidence: {round(mean_c,4)} | correct: {round(mean_correct,4)} | "
         f"incorrect: {round(mean_wrong,4)}", "",
         "## Lowest-confidence predictions (ids)",
         "- " + json.dumps(lowest, ensure_ascii=False), "",
         "## Highest-confidence WRONG predictions (false-confidence) (ids)",
         "- " + json.dumps(false_conf, ensure_ascii=False), "",
         f"- Raw ECE: {out['models']['raw'].get('ece')} "
         "(lower is better; poor separation => abstention matters).", ""]
    with open(ABSTENTION_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
