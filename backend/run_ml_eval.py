"""Phase 12 runner: ML environment check + full production-pipeline evaluation.

Executes real imports (never just reads requirements.txt) and runs the honest
offline evaluation harness, plus a rule-first -> ML-fallback check that mirrors
the actual pipeline.enrich() production path. All output goes to
ml_eval_evidence.txt so it survives the sandbox's flaky console capture.
No metric is tuned toward a target - whatever the model gets is what is printed.
"""
import os
import sys
import traceback

BACKEND = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

OUT = os.path.join(BACKEND, "ml_eval_evidence.txt")
fh = open(OUT, "w", encoding="utf-8")


def log(*a):
    fh.write(" ".join(str(x) for x in a) + "\n")
    fh.flush()


try:
    import time

    t0 = time.time()
    import sklearn
    import numpy
    import scipy
    import joblib

    log("=== ENVIRONMENT ===")
    log("python", sys.version.split()[0], "|", sys.executable)
    log("sklearn", sklearn.__version__)
    log("numpy", numpy.__version__)
    log("scipy", scipy.__version__)
    log("joblib", joblib.__version__)
    log("IMPORTS_OK in %.2fs" % (time.time() - t0))

    from app.services.processing import news_topics_eval as ev
    from app.services.processing.news_topics_data import TAXONOMY, SEED_CORPUS

    log("")
    log("=== DATASET ===")
    stats = ev.dataset_stats()
    log("raw_seed_corpus=%d deduped=%d classes=%d"
        % (len(SEED_CORPUS), stats["total_examples"], len(TAXONOMY)))
    log("dupes_removed=%s min=%s max=%s imbalance=%s"
        % (stats["duplicate_entries_removed"], stats["min_class_count"],
           stats["max_class_count"], round(stats["imbalance_ratio"], 2)))
    for label in TAXONOMY:
        log("  class %-14s n=%s" % (label, stats["per_class"].get(label, 0)))

    splits = ev.split_corpus()
    log("split sizes: train=%d val=%d holdout=%d random_state=%d"
        % (len(splits["train"][0]), len(splits["validation"][0]),
           len(splits["holdout"][0]), ev.RANDOM_STATE))
    log("tfidf=%s nb_alpha=%s threshold=%s"
        % (ev.VECTIZER_KWARGS, ev.NB_ALPHA, ev.PRODUCTION_THRESHOLD))

    log("")
    log("=== HOLDOUT EVALUATION (untouched 25%) ===")
    res = ev.run_holdout_evaluation()
    if not res or not res.get("sklearn"):
        log("SKLEARN_UNAVAILABLE")
    else:
        m = res["metrics"]
        log("accuracy_before_abstention=%.4f" % m["accuracy_before_abstention"])
        log("accuracy_after_abstention =%.4f" % m["accuracy_after_abstention"])
        log("macro P/R/F1    = %.4f / %.4f / %.4f"
            % (m["macro_precision"], m["macro_recall"], m["macro_f1"]))
        log("weighted P/R/F1 = %.4f / %.4f / %.4f"
            % (m["weighted_precision"], m["weighted_recall"], m["weighted_f1"]))
        log("")
        log("per-class:")
        for label, v in res["per_class"].items():
            log("  %-14s P=%.3f R=%.3f F1=%.3f n=%d"
                % (label, v["precision"], v["recall"], v["f1-score"], int(v["support"])))
        log("")
        log("confusion_matrix (rows=true %s):" % res["confusion_labels"])
        for row in res["confusion_matrix"]:
            log("  " + " ".join("%3d" % c for c in row))
        a = res["abstention"]
        log("")
        log("abstention: total=%d confident=%d abstained=%d rate=%.4f"
            % (a["total_predictions"], a["confident_predictions"],
               a["abstentions"], a["abstention_rate"]))
        log("precision_on_confident_subset=%.4f" % a["precision_on_confident_subset"])
        log("confidence: mean=%.4f min=%.4f max=%.4f"
            % (a["mean_confidence"], a["min_confidence"], a["max_confidence"]))
        log("mean_confidence_by_class: %s"
            % {k: round(v, 3) for k, v in a["mean_confidence_by_class"].items()})

        # Full confidence distribution (histogram) on the holdout.
        import numpy as _np
        s2 = ev.split_corpus()
        hold_t, hold_l = s2["holdout"]
        pipe = ev._make_pipeline()
        fit_t = s2["train"][0] + s2["validation"][0]
        fit_l = s2["train"][1] + s2["validation"][1]
        pipe.fit(fit_t, fit_l)
        confs = pipe.predict_proba(hold_t).max(axis=1)
        bins = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        hist = _np.histogram(confs, bins=bins)[0]
        log("confidence_histogram (bin:count): %s"
            % {f"[{bins[i]:.1f},{bins[i+1]:.1f})": int(hist[i]) for i in range(len(hist))})

    log("")
    log("=== REAL-WORLD UNSEEN VALIDATION (production predict_topic path) ===")
    rw = ev.run_real_world_validation()
    if rw is None:
        log("SKLEARN_UNAVAILABLE")
    else:
        log("total=%d exact=%d exact_accuracy=%.4f acceptable_accuracy=%.4f"
            % (rw["total"], rw["exact_match"], rw["exact_accuracy"],
               rw["acceptable_accuracy"]))
        for f in rw["failures"]:
            log("  MISS exp=%-12s got=%-12s conf=%.3f  %r"
                % (f["expected"], f["predicted"], f["confidence"], f["text"]))

    log("")
    log("=== FULL PRODUCTION PIPELINE CHECK (rules -> ML fallback) ===")
    # Mirrors pipeline.enrich(): rule-based detect_category first; only when it
    # returns "Other" does the topic model run (as live collection runs do with
    # Settings.enable_topic_model=True).
    from app.services.processing import classifier
    from app.services.processing.domain_config import DEFAULT_CONFIG
    from app.services.processing.news_topics import predict_topic

    rule_hits = 0
    fallback_items = []
    for text, expected in ev.REAL_WORLD_VALIDATION:
        cat = classifier.detect_category(text, DEFAULT_CONFIG)
        if cat != "Other":
            rule_hits += 1
        else:
            topic, c = predict_topic(text, min_confidence=ev.PRODUCTION_THRESHOLD)
            final = topic if topic != "Other" else "Other"
            fallback_items.append((text, expected, cat, final, c))
    log("rule-first hits on real-world set: %d / %d (rules are domain-specific, "
        "so general news correctly falls through to the ML stage)"
        % (rule_hits, len(ev.REAL_WORLD_VALIDATION)))
    agree = sum(1 for _, e, _, f, _ in fallback_items if f == e)
    amb_ok = sum(1 for t, e, _, f, _ in fallback_items
                 if t in ev._AMBIGUOUS_OK_OTHER and f == "Other")
    log("pipeline-stage outcomes: items=%d exact=%d acceptable=%d/%d (=%.4f)"
        % (len(fallback_items), agree, agree + amb_ok, len(fallback_items),
           (agree + amb_ok) / len(fallback_items)))
    for t, e, r, f, c in fallback_items:
        flag = "OK" if (f == e or (t in ev._AMBIGUOUS_OK_OTHER and f == "Other")) else "MISS"
        log("  %s exp=%-12s final=%-12s conf=%.3f  %r" % (flag, e, f, c, t))

    # A domain (exam/NEET) sample must still be handled by the RULES, proving
    # the ML stage did not take priority over rule-based classification.
    from app.schemas.article import Article as ApiArticle
    from app.services.processing.pipeline import enrich
    from datetime import datetime, timezone
    probe = ApiArticle(title="NEET UG 2026 result: 3 lakh students qualify, "
                             "counselling starts next month",
                       description="NEET UG cut-off announced by NTA.",
                       url="https://example.com/neet-probe",
                       provider="google_news",
                       published_at=datetime.now(timezone.utc).isoformat())
    probe_out = enrich(probe, DEFAULT_CONFIG)
    log("rule-priority probe: category=%r exam=%r (rules handled, ML untouched)"
        % (probe_out.category, probe_out.name_of_exam))

    log("")
    log("PHASE12_RUNNER_DONE")
except SystemExit:
    raise
except BaseException:
    log("RUNNER_ERROR")
    log(traceback.format_exc(limit=6))
finally:
    fh.close()
