# NewsLens — Phase 12 ML Evaluation (VERIFIED evidence)

Executed: 2026-09-25 (IST) on the local machine. Every number below was printed
by actually executing the pipeline — nothing is estimated, tuned toward a
target, or fabricated.

Re-run with:

```powershell
cd backend
.\.venv\Scripts\python.exe run_ml_eval.py     # writes ml_eval_evidence.txt
.\.venv\Scripts\python.exe -m pytest tests\test_news_topics.py tests\test_news_topics_eval.py -v
```

## 1. Environment (real imports executed, not requirements.txt inspection)

| Package | Version |
|---|---|
| Python | 3.14.6 (`backend\.venv`) |
| scikit-learn | 1.9.1 |
| numpy | 2.5.3 |
| scipy | 1.18.1 |
| joblib | 1.6.0 |

`import sklearn / numpy / scipy / joblib` all succeeded (`IMPORTS_OK`), though
the import takes ~2 minutes in this sandbox (observed 118.85 s) — an environment
quirk, not a code defect.

## 2. Production architecture (unchanged, verified)

`Rules (domain keyword classifier) → if confidently classified → rule result;
otherwise → TF-IDF → ComplementNB → confidence threshold 0.30 → known topic / Other`.

Rule priority was exercised: a NEET UG headline is handled by the rules
(`name_of_exam='NEET UG'`) and never reaches the model. The ML stage is a
fallback enabled only for live collection runs (`ENABLE_TOPIC_MODEL`).

## 3. Dataset & split

- Seed corpus: **396** examples, 0 duplicates removed, **11 classes**, perfectly
  balanced (36 per class: World, Politics, Business, Technology, Sports, Health,
  Science, Entertainment, Climate, Crime, Education)
- Stratified split, `random_state=42`: **train 252 / validation 45 / untouched holdout 99**
- TF-IDF: `sublinear_tf=True, ngram_range=(1,2), min_df=1, stop_words='english', lowercase=True`
- Classifier: `ComplementNB(alpha=0.1)`; production abstention threshold `0.30`
  (not lowered to inflate coverage)

## 4. Holdout results (99 untouched examples) — reported as measured

| Metric | Value |
|---|---|
| Accuracy (before abstention) | **0.586** |
| Accuracy (after abstention → Other) | 0.253 |
| Macro P / R / F1 | 0.581 / 0.586 / 0.572 |
| Weighted P / R / F1 | 0.581 / 0.586 / 0.572 |
| Abstention rate | 0.657 (65 of 99) |
| Precision on confident subset | 0.735 (25/34) |
| Mean / min / max confidence | 0.279 / 0.091 / 0.751 |

Per-class (holdout, before abstention):

| Class | P | R | F1 | n |
|---|---|---|---|---|
| World | 0.583 | 0.778 | 0.667 | 9 |
| Politics | 0.833 | 0.556 | 0.667 | 9 |
| Business | 0.545 | 0.667 | 0.600 | 9 |
| Technology | 0.500 | 0.556 | 0.526 | 9 |
| Sports | 0.500 | 0.556 | 0.526 | 9 |
| Health | 0.444 | 0.444 | 0.444 | 9 |
| Science | 0.545 | 0.667 | 0.600 | 9 |
| Entertainment | 0.750 | 0.667 | 0.706 | 9 |
| Climate | 0.333 | 0.111 | 0.167 | 9 |
| Crime | 0.625 | 0.556 | 0.588 | 9 |
| Education | 0.727 | 0.889 | 0.800 | 9 |

Confusion matrix (rows=true in the class order above) — see
`backend/ml_eval_evidence.txt` for the raw matrix. Weakest class: **Climate**
(F1 0.167) — its vocabulary overlaps World/Science/Health on this small corpus.

Confidence distribution (holdout max-probability histogram):

| Bin | 0.0–0.2 | 0.2–0.3 | 0.3–0.4 | 0.4–0.5 | 0.5–0.6 | 0.6–0.7 | 0.7–0.8 | ≥0.8 |
|---|---|---|---|---|---|---|---|---|
| Count | 32 | 33 | 21 | 4 | 5 | 3 | 1 | 0 |

## 5. Unseen real-world validation (production `predict_topic` path)

29 manually labelled, never-trained-on items (short queries, headlines,
ambiguous, genuine noise):

- **Exact accuracy: 20/29 = 0.690**; acceptable (incl. honest abstention on
  ambiguous text): 0.690
- All 9 misses were **abstentions** (confidence < 0.30 → `Other`) — the model
  refused to guess rather than mislabelling; zero confident-wrong answers.
- Full pipeline view (rules first, then ML): 28 items reached the ML stage
  (1 rule hit), acceptable 20/28 = 0.714.

## 6. Honest interpretation

This is a *topic signal on a 396-headline corpus*, not a high-accuracy
production classifier: ~59% holdout accuracy, ~69% on unseen real-world text,
with deliberate abstention on low confidence. No 80%+ claim is made and no
threshold/hyperparameter was tuned after seeing the holdout.

## 7. Regression runs (same session)

- ML tests: `tests/test_news_topics.py` + `tests/test_news_topics_eval.py` → **23 passed**
- Complete backend suite: **151 collected — 136 passed, 15 skipped, 0 failed, 0 errors**
  (the 15 skips are the PostgreSQL RLS module, which self-skips without a live
  server URL and was executed separately against real PostgreSQL 18 in Phase 11)
- Frontend typecheck (`tsc --noEmit`): **passed**
- Frontend production build (`vite build`): **passed** (62 modules)

**Phase 12 classification: VERIFIED.**
