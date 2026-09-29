"""PHASE 4-5: Rule-assisted L1 annotation + annotation QA (DEVELOPMENT build).

HONESTY / METHOD (read before using these labels):
- There is ONE annotator (this coding agent). No second annotator was available,
  so NO inter-annotator agreement statistics are reported or implied.
- Labels are produced by a *deterministic rule-assisted* primary-subject pass
  that reads ONLY ``model_text`` (title + description). It never copies
  ``Article.category`` - the existing category is kept purely as an untrusted
  "hint" for side-by-side review, exactly as the plan requires.
- Every label is therefore PROVISIONAL and must be human-verified before any
  downstream use. Low-confidence / boundary / no-signal records are flagged
  ``provisional_needs_review`` so a human reviewer sees them first.
- The corpus rights status is UNVERIFIED_GOOGLE_NEWS. Do not publish or
  redistribute the output.

The priority-ordered keyword lexicon encodes the NewsLens "dominant editorial
subject" rule: the most specific surviving signal wins (e.g. "NEET ... FIR ...
Supreme Court" is about the exam -> Education, not the courtroom).

Run:  python backend/ml/scripts/ml_annotate.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    ANNOTATIONS_JSONL,
    ANNOTATOR_ID,
    ANNOTATION_QA,
    DATASET_ID,
    FALLBACK_LABEL,
    LABELLED_JSONL,
    RAW_JSONL,
    RIGHTS_STATUS,
    TAXONOMY,
)

# ---------------------------------------------------------------------------
# Lexicon: class -> list of (regex, weight). Regexes use word boundaries where
# a bare substring would over-match (e.g. \bai\b so "said"/"email" don't fire).
# ---------------------------------------------------------------------------
RULES: dict[str, list[tuple[str, float]]] = {
    "Education": [
        (r"\bneet\b", 6), (r"\bexam\b|\bexams\b|\bexamination\b", 3),
        (r"paper leak", 5), (r"\bsyllabus\b", 3), (r"\badmission\b|\badmissions\b", 3),
        (r"\buniversity\b|\buniversities\b", 3), (r"\bcollege\b|\bcolleges\b", 3),
        (r"\bschool\b|\bschools\b", 2), (r"\bstudent\b|\bstudents\b", 2),
        (r"\bupsc\b|\bgate\b|\bcbse\b|\bncert\b|\biit\b|\bmbbs\b|\bbtech\b", 4),
        (r"\bmains\b|\bcut ?off\b|\bsyllabus\b", 2), (r"\bprofessor\b|\bfaculty\b", 2),
    ],
    "Health": [
        (r"\bhealth\b", 3), (r"\bhospital\b|\bhospitals\b", 3), (r"\bpatient\b|\bpatients\b", 2),
        (r"\bdisease\b|\bdiseases\b", 3), (r"\bvaccine\b|\bvaccines\b", 4),
        (r"\bmedicine\b|\bmedicines\b|\bdrug\b|\bdrugs\b", 3), (r"\bwho\b|\bworld health", 2),
        (r"\bepidemic\b|\bpandemic\b|\boutbreak\b", 4), (r"\bvirus\b|\b viral\b", 3),
        (r"\btreatment\b", 2), (r"\bmedical\b", 2), (r"\bmonkey fever\b|\bnipah\b", 4),
        (r"\banesthetic\b", 3), (r"\bbaby food\b|\binfant nutrition\b", 2),
    ],
    "Climate": [
        (r"climate", 4), (r"global warming", 5), (r"\bemissions?\b", 3),
        (r"heat ?wave", 4), (r"el ni[nñ]o", 4), (r"\bcarbon\b", 2), (r"net ?zero", 4),
        (r"planetary boundaries", 5), (r"deforestation", 4), (r"rising sea", 4),
        (r"\bwarming\b", 3), (r"\bfossil fuel", 3), (r"\bcop ?\d", 3),
        (r"climate change", 5), (r"renewable|\bclean power\b|\bclean energy\b", 2),
    ],
    "Sports": [
        (r"\bcricket\b", 4), (r"world cup", 4), (r"asia cup", 5), (r"\bt20\b|\bodi\b|\btest[s]? series", 3),
        (r"\bicc\b", 4), (r"\bmatch\b", 2), (r"\bteam\b", 1), (r"\bplayer\b|\bplayers\b", 2),
        (r"\bsquad\b", 3), (r"\bwicket\b|\bbowling\b|\bbatsman\b", 4), (r"\bumpire\b|\bmcc law", 3),
        (r"asian games", 4), (r"\bfifa\b|\bfootball\b|\bsoccer\b", 4), (r"\bolympic", 4),
        (r"\bprotea[s]?\b|\brabada\b|\binglis\b|\bnetherland", 3), (r"\btournament\b", 2),
    ],
    "Technology": [
        (r"\bai\b", 3), (r"artificial intelligence", 5), (r"\bchip\b|\bchips\b", 4),
        (r"semiconductor", 5), (r"\bsnapdragon\b|\bqualcomm\b|\bmediatek\b", 5),
        (r"smartphone", 4), (r"\biphone\b", 4), (r"\bgadget\b", 4), (r"\bsoftware\b", 2),
        (r"\brobot(?:ics)?\b", 4), (r"data ?center", 4), (r"\bmachine learning\b|\bllm\b|\bagentic\b", 4),
        (r"\bprocessor\b", 4), (r"\bcybercab\b|\bself-driving\b|\bautonomous\b", 4),
        (r"\btech industry\b|\bbig tech\b|\bpost-smartphone\b", 4),
        (r"openai|\bchatgpt\b", 5), (r"\btesla\b", 2),
    ],
    "Business": [
        (r"\bstock\b|\bstocks\b", 4), (r"\bsensex\b|\bnifty\b", 5), (r"stock market", 5),
        (r"\bmarket\b|\bmarkets\b", 2), (r"\blayoff\b|\blayoffs\b", 5), (r"\bworkforce\b", 4),
        (r"\beconomy\b|\beconomic\b", 3), (r"\bgdp\b", 4), (r"\binflation\b", 3),
        (r"\btariff\b|\btariffs\b", 4), (r"\btrade deal\b|\bfree trade\b|\bfta\b", 4),
        (r"\bipo\b", 4), (r"\bmerger\b|\bacquisition\b", 4), (r"\bearnings\b|\bquarterly\b", 3),
        (r"\bupi\b|\bmdr\b|\bdigital payment", 4), (r"\brbi\b|\breserve bank\b|\bbank[s]?\b", 3),
        (r"\bmutual fund\b|\binvestor", 3), (r"\bcompany\b|\bcompanies\b|\bcorporate\b", 1),
        (r"\bwage\b|\bpayroll\b|\bemployment\b|\bjobs\b", 3), (r"growth outlook", 3),
    ],
    "Politics": [
        (r"\bbill\b", 4), (r"parliament", 5), (r"lok sabha|rajya sabha", 5),
        (r"\belection\b|\belections\b|\bmidterm", 4), (r"\bminister\b|\bcabinet\b", 3),
        (r"\bgovernment\b|\bcentre\b|\bnew delhi\b", 3), (r"\bpolicy\b", 2),
        (r"\bsupreme court\b|\bhigh court\b|\bhc\b|\bcourt\b|\bjudge\b|\bjudgment\b|\bverdict\b|\bplea\b", 3),
        (r"\bsanction\b|\bsanctions\b", 3), (r"\bdiplomacy\b|\bdiplomat\b", 3),
        (r"\btrump\b|\bbiden\b|\bmodi\b|\bputin\b|\bzelenesk\w*\b", 2),
        (r"\bcongress\b|\bbjp\b|\bmla\b|\bmp\b|\boffice[rr]?\b", 3),
        (r"\blaw\b|\blaws\b|\blegal\b|\billegal\b|\bact\b|\bamendment\b|\bconstitution\b|\barticle 14\b|\bucc\b", 2),
        (r"\bcitizenship\b|\bvote\b|\bdemocrat\b|\brepublican\b|\bsenate\b", 3),
        (r"\bfir\b|\bquash", 2),
    ],
    "Crime": [
        (r"\bfir\b|\bfirs\b", 4), (r"\barrest\b|\barrested\b|\barrest\b", 5),
        (r"\bpolice\b", 3), (r"\bcrime\b|\bcriminal\b", 4), (r"\bmurder\b", 5),
        (r"\btheft\b|\brobbery\b", 5), (r"\bfraud\b", 5), (r"\baccused\b", 4),
        (r"\bchargesheet\b", 5), (r"\blathi-?charge\b", 4), (r"\bcustody\b", 3),
        (r"\bjail\b|\bconviction\b", 4), (r"\bassault\b", 4), (r"\bkidnap", 5),
        (r"\bsmuggl", 4), (r"\bdrunk\b|\bdui\b", 3), (r"\bdeath trap\b|\bkilled\b", 1),
    ],
    "Science": [
        (r"\bisro\b", 5), (r"\bspace\b", 2), (r"\bsatellite\b|\bsatellites\b", 4),
        (r"\brocket\b|\blaunch vehicle\b", 4), (r"\besa\b|\bnasa\b|\bspacex\b", 4),
        (r"\bgaganyaan\b", 5), (r"\bastronom\w*\b|\btelescope\b", 4),
        (r"\bresearch\b|\bstudy\b|\bstudies\b", 2), (r"\bscientist\b|\bscientists\b", 3),
        (r"\bphysics\b|\bbiology\b|\bchemistry\b", 4), (r"\boceansat\b|\bel nino.*detect", 4),
        (r"\bspace station\b|\bspacewalk\b|\bmoon\b|\bmars\b", 4),
        (r"\bradar\b|\bnetra\b", 3), (r"\bhuman spaceflight\b", 4),
    ],
    "Entertainment": [
        (r"\bmovie\b|\bfilm\b|\bmovies\b", 4), (r"\bbollywood\b|\bhollywood\b", 5),
        (r"\bactor\b|\bactress\b|\bcelebrity\b", 4), (r"\bott\b|\bseries\b|\bweb series\b", 3),
        (r"\bmusic\b|\bsong\b|\bsinger\b", 4), (r"\bstar\b", 1), (r"\bculture\b|\bcultural\b|\barts\b|\btheatre\b|\bfestival\b", 3),
        (r"\bbook\b|\bnovel\b|\bauthor\b", 2), (r"\bstand-up\b|\bcomedian\b|\bcomedy\b", 4),
        (r"\bgames\b(?: ?\bxbox|\bvideo\b)", 3),
    ],
    "World": [
        (r"\bwar\b|\bwars\b", 4), (r"\bukraine\b|\brussia\b", 5), (r"\biran\b|\biranian\b|\btehran\b|\birgc\b", 5),
        (r"\bgaza\b|\bisrael\b|\bwest bank\b", 5), (r"\bconflict\b", 3), (r"\bmissile\b|\bstrike\b|\bbomb", 4),
        (r"\bceasefire\b", 5), (r"\bnato\b", 4), (r"\bun\b|\bunga\b|united nations|\bu\.n\.", 3),
        (r"\bborder\b|\btroops?\b|\bmilitary\b|\bdefense\b|\bdefence\b", 3),
        (r"strait of hormuz", 5), (r"middle east", 4), (r"\bcivil war\b", 5),
        (r"\battack\b|\battacks\b", 3), (r"\bsudan\b|\byemen\b|\bethiopia\b", 5),
        (r"\bflood\b|\bfloods\b|\bflood-?hit\b|flash flood", 2), (r"\brefugee\b|\bdisaster\b", 2),
        (r"world leaders|global order|world cup.*international", 1),
    ],
}

# Specificity order for tie-breaks: the more concrete domain wins a tie.
PRIORITY = [
    "Education", "Health", "Climate", "Sports", "Crime", "Science",
    "Technology", "Business", "Entertainment", "Politics", "World",
]

_RE = {c: [(re.compile(p, re.I), w) for p, w in rules] for c, rules in RULES.items()}


def score_classes(text: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for cls, compiled in _RE.items():
        s = 0.0
        for pat, w in compiled:
            hits = len(pat.findall(text))
            if hits:
                s += w * (1 + 0.15 * min(hits - 1, 4))  # mild repeat boost, capped
        if s > 0:
            scores[cls] = s
    return scores


def annotate(text: str) -> tuple[str, float, str]:
    """Return (label, confidence, status). text is model_text (title+desc)."""
    scores = score_classes(text)
    if not scores:
        return FALLBACK_LABEL, 0.20, "provisional_needs_review"
    ordered = sorted(
        scores.items(),
        key=lambda kv: (-kv[1], PRIORITY.index(kv[0]) if kv[0] in PRIORITY else 99),
    )
    top_cls, top = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = (top - second) / top if top else 0.0
    # Confidence: strong when a class dominates and beats the runner-up.
    conf = round(min(0.95, 0.45 + 0.5 * margin), 2)
    if second == 0:
        conf = max(conf, 0.7)
    if conf < 0.5 or margin < 0.15:
        status = "provisional_needs_review"
    else:
        status = "provisional_single_annotator"
    return top_cls, conf, status


def main() -> None:
    if not os.path.exists(RAW_JSONL):
        raise SystemExit(f"missing raw dataset: {RAW_JSONL} (run ml_export_dataset.py)")

    records = [json.loads(line) for line in open(RAW_JSONL, encoding="utf-8")]

    annotations = {}
    for rec in records:
        label, conf, status = annotate(rec.get("model_text", ""))
        annotations[rec["id"]] = {
            "id": rec["id"],
            "label": label,
            "annotation_confidence": conf,
            "annotation_status": status,
            "annotator_id": ANNOTATOR_ID,
            "current_category_hint": rec.get("current_category_hint"),
            "ambiguous": status == "provisional_needs_review",
        }

    with open(ANNOTATIONS_JSONL, "w", encoding="utf-8") as f:
        for rid in sorted(annotations):
            f.write(json.dumps(annotations[rid], ensure_ascii=False) + "\n")

    # Merge labels back onto the canonical records (keeps provenance + rights).
    for rec in records:
        a = annotations[rec["id"]]
        rec["label"] = a["label"]
        rec["annotation_confidence"] = a["annotation_confidence"]
        rec["annotation_status"] = a["annotation_status"]
        rec["annotator_id"] = a["annotator_id"]
    with open(LABELLED_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- Phase 5 QA report ----
    by_class = Counter(a["label"] for a in annotations.values())
    low_conf = sum(1 for a in annotations.values() if a["annotation_confidence"] < 0.5)
    needs_review = sum(1 for a in annotations.values() if a["ambiguous"])
    hint_agree = sum(
        1 for a in annotations.values()
        if (a["current_category_hint"] or "").lower() == a["label"].lower()
    )

    src_by_class = defaultdict(Counter)
    date_by_class = defaultdict(Counter)
    for rec in records:
        src_by_class[rec["label"]][rec.get("source") or "NULL"] += 1
        d = (rec.get("published_date") or "unknown")[:7]
        date_by_class[rec["label"]][d] += 1

    qa = {
        "dataset_id": DATASET_ID,
        "rights_status": RIGHTS_STATUS,
        "annotator_count": 1,
        "second_annotator_available": False,
        "inter_annotator_agreement": None,
        "agreement_note": (
            "NOT COMPUTED - a single (rule-assisted) annotator produced every label. "
            "No independent second pass exists, so no agreement/Cohen's-kappa is claimed."
        ),
        "labels_are": "PROVISIONAL - deterministic rule-assisted first pass over title+description; requires human verification",
        "auto_assigned_from_article_category": False,
        "total_records": len(records),
        "count_per_class": {c: by_class.get(c, 0) for c in TAXONOMY},
        "other_count": by_class.get(FALLBACK_LABEL, 0),
        "ambiguous_needs_review_count": needs_review,
        "low_confidence_count": low_conf,
        "hint_label_exact_match_count": hint_agree,
        "classes_with_zero_examples": [c for c in TAXONOMY if by_class.get(c, 0) == 0],
        "classes_with_very_low_examples": [c for c in TAXONOMY if 0 < by_class.get(c, 0) < 20],
        "source_distribution_by_class": {
            c: dict(src_by_class[c].most_common(5)) for c in sorted(by_class)
        },
        "top_date_by_class": {c: dict(date_by_class[c].most_common(3)) for c in sorted(by_class)},
    }
    with open(ANNOTATION_QA, "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=2, ensure_ascii=False)

    print(json.dumps(qa, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
