"""Shared configuration for the NewsLens Topic ML *development* pipeline.

Everything here is deliberately isolated from the production application:
- No path under here writes to the SQLite database.
- All generated dataset / model / report artifacts live beneath ``backend/ml``
  and are git-ignored (see ``.gitignore``): article text must never reach Git.

RIGHTS STATUS: the 396 source articles were collected through Google News and
their publisher-content rights for ML training are UNVERIFIED. This is an
INTERNAL DEVELOPMENT / EXPERIMENTAL build only. Do not publish or redistribute
any artifact produced here.
"""
from __future__ import annotations

import os

# ---- directory layout -------------------------------------------------------
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ML = os.path.join(BACKEND, "ml")
SCRIPTS = os.path.join(ML, "scripts")
DATASETS = os.path.join(ML, "datasets")
DEV_DIR = os.path.join(DATASETS, "development")
MODELS_DIR = os.path.join(ML, "models")
REPORTS_DIR = os.path.join(ML, "reports")
CONFIGS_DIR = os.path.join(ML, "configs")

for _d in (DEV_DIR, MODELS_DIR, REPORTS_DIR, CONFIGS_DIR):
    os.makedirs(_d, exist_ok=True)

DB_PATH = os.path.join(BACKEND, "newslens.db")

# ---- dataset / artifact identity -------------------------------------------
DATASET_ID = "newslens_topic_dev_v0.1"
ORIGINAL_DATASET = "newslens_google_news_local_corpus"
RIGHTS_STATUS = "UNVERIFIED_GOOGLE_NEWS"
PREPROCESSING_VERSION = "model_text_v1"
MODEL_SERIES = "newslens_topic_classifier_dev"
ANNOTATOR_ID = "assistant_single_annotator_v0"

# Canonical export (Phase 1-2).
RAW_JSONL = os.path.join(DEV_DIR, "corpus_raw_v0.1.jsonl")
ANNOTATION_WORKSHEET = os.path.join(DEV_DIR, "annotation_worksheet.tsv")
MANIFEST = os.path.join(DEV_DIR, "manifest.json")

# Annotated / deduped / split artifacts (Phase 4-7).
LABELLED_JSONL = os.path.join(DEV_DIR, "corpus_labelled_v0.1.jsonl")
ANNOTATIONS_JSONL = os.path.join(DEV_DIR, "annotations_v0.1.jsonl")
ANNOTATION_QA = os.path.join(REPORTS_DIR, "annotation_qa_v0.1.json")
DEDUPED_JSONL = os.path.join(DEV_DIR, "corpus_deduped_v0.1.jsonl")
SPLITS_MANIFEST = os.path.join(DEV_DIR, "splits_v0.1.json")

# Trained artifacts (Phase 8-13).
MODEL_ARTIFACT = os.path.join(MODELS_DIR, "topic_model_dev_v0.1.joblib")
MODEL_METADATA = os.path.join(MODELS_DIR, "topic_model_dev_v0.1.meta.json")
TRAINING_CONFIG = os.path.join(CONFIGS_DIR, "training_config_v0.1.json")
MODEL_CARD = os.path.join(REPORTS_DIR, "model_card_v0.1.md")
COMPARISON_REPORT = os.path.join(REPORTS_DIR, "candidate_comparison_v0.1.json")

# Label validation / agreement / adjudication / rights (Phase 21-24).
PASS2_ANNOTATIONS = os.path.join(DEV_DIR, "annotations_pass2_v0.1.jsonl")
BLIND_REVIEW_WORKSHEET = os.path.join(DEV_DIR, "blind_review_worksheet.tsv")
AGREEMENT_JSON = os.path.join(REPORTS_DIR, "annotation_agreement_v0.1.json")
AGREEMENT_MD = os.path.join(REPORTS_DIR, "annotation_agreement_v0.1.md")
ADJUDICATION_JSONL = os.path.join(DEV_DIR, "adjudication_v0.1.jsonl")
ADJUDICATION_MD = os.path.join(REPORTS_DIR, "adjudication_report_v0.1.md")
FINAL_ANNOTATIONS = os.path.join(DEV_DIR, "annotations_final_v0.1.jsonl")
DATASET_QA_MD = os.path.join(REPORTS_DIR, "dataset_quality_v0.1.md")
DATASET_QA_JSON = os.path.join(REPORTS_DIR, "dataset_quality_v0.1.json")
RIGHTS_GATE = os.path.join(CONFIGS_DIR, "rights_gate_v0.1.json")


# ---- MASTER COMPLETION (Phase A-Z) artifact paths --------------------------
INVENTORY_MD = os.path.join(REPORTS_DIR, "ml_completion_inventory_v0.1.md")

# Phase B - canonical final development dataset + split id manifest.
FINAL_DATASET = os.path.join(DEV_DIR, "topic_dev_final_v0.1.jsonl")
SPLIT_IDS = os.path.join(DEV_DIR, "split_ids_v0.1.json")
DATASET_AUDIT_MD = os.path.join(REPORTS_DIR, "final_dataset_audit_v0.1.md")

# Phase E-H - per-candidate models, prediction artifacts, error + learning.
CANDIDATES_DIR = os.path.join(MODELS_DIR, "candidates")
PREDICTIONS_DIR = os.path.join(DEV_DIR, "predictions")
TRAIN_RESULTS_JSON = os.path.join(REPORTS_DIR, "train_results_v0.1.json")
ERROR_MD = os.path.join(REPORTS_DIR, "error_analysis_v0.1.md")
LEARNING_MD = os.path.join(REPORTS_DIR, "learning_curve_v0.1.md")
SELECTION_MD = os.path.join(REPORTS_DIR, "model_selection_v0.1.md")

# Phase R/S - final development model.
FINAL_MODEL = os.path.join(MODELS_DIR, "topic_model_dev_final_v0.1.joblib")
FINAL_META = os.path.join(MODELS_DIR, "topic_model_dev_final_v0.1.meta.json")
MODEL_CARD_FINAL = os.path.join(REPORTS_DIR, "model_card_dev_final_v0.1.md")

# Phase I/J - calibration + abstention.
CALIBRATION_MD = os.path.join(REPORTS_DIR, "calibration_audit_v0.1.md")
CALIBRATION_JSON = os.path.join(REPORTS_DIR, "calibration_audit_v0.1.json")
ABSTENTION_MD = os.path.join(REPORTS_DIR, "abstention_audit_v0.1.md")

# Phase K/L - robustness + edge cases.
ROBUSTNESS_MD = os.path.join(REPORTS_DIR, "robustness_audit_v0.1.md")

# Phase M-Q - integration / frozen / unseen / temporal / hard-case.
INTEGRATION_MD = os.path.join(REPORTS_DIR, "integration_audit_v0.1.md")
FROZEN_MD = os.path.join(REPORTS_DIR, "frozen_benchmark_v0.1.md")
BENCHMARKS_MD = os.path.join(REPORTS_DIR, "benchmarks_audit_v0.1.md")
UNSEEN_SPEC_MD = os.path.join(REPORTS_DIR, "unseen_benchmark_spec_v0.1.md")
TEMPORAL_PLAN_MD = os.path.join(REPORTS_DIR, "temporal_benchmark_plan_v0.1.md")
HARD_CASE_MANIFEST = os.path.join(DEV_DIR, "hard_case_manifest_v0.1.json")
BENCH_JSON = os.path.join(REPORTS_DIR, "benchmarks_v0.1.json")

# Phase W/X/V/Z - compile.
REPRO_JSON = os.path.join(REPORTS_DIR, "reproducibility_manifest_v0.1.json")
BEFORE_AFTER_MD = os.path.join(REPORTS_DIR, "ml_before_after_v0.1.md")
CONSOLIDATED_MD = os.path.join(REPORTS_DIR, "NEWSLENS_ML_DEVELOPMENT_AUDIT_v0.1.md")
FINAL_STATUS_MD = os.path.join(REPORTS_DIR, "FINAL_ML_STATUS_v0.1.md")

for _d in (CANDIDATES_DIR, PREDICTIONS_DIR):
    os.makedirs(_d, exist_ok=True)


# ---- taxonomy (single-select, L1 only - do NOT expand) ---------------------
TAXONOMY = [
    "World", "Politics", "Business", "Technology", "Sports", "Health",
    "Science", "Entertainment", "Climate", "Crime", "Education",
]
FALLBACK_LABEL = "Other"

# ---- reproducibility --------------------------------------------------------
RANDOM_SEED = 42

# Existing frozen holdout (SEED-corpus derived, 99 items) is preserved untouched.
# See backend/app/services/processing/news_topics_eval.py. The development
# corpus is DISJOINT from that synthetic seed corpus, so it cannot contaminate
# the frozen 99.
FROZEN_HOLDOUT_NAME = "seed_frozen_99"
