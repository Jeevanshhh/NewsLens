"""Domain classification configuration (default: the notebook's NEET rules).

IMPORTANT: This is *rule/keyword based* classification, not machine learning.
It is kept here as the default, configurable domain so the platform is not
hard-wired to NEET - a different `ClassificationConfig` can be supplied for
another topic, or the domain rules can be disabled for generic news.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# exam keyword -> structured exam metadata
EXAM_DATABASE: Dict[str, Dict[str, str]] = {
    "NEET": {
        "Name of Exam": "NEET UG",
        "Exam Category": "Medical Entrance",
        "Board": "NTA",
        "Conducted By": "NTA",
        "PBT/CBT": "PBT",
    }
}

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Paper Leak": ["paper leak", "question paper leak", "leaked paper", "question leak"],
    "Protest": ["protest", "students protest", "demonstration", "agitation"],
    "Court Case": ["court", "hearing", "judge", "bail"],
    "Investigation": ["cbi", "investigation", "probe"],
    "Arrest": ["arrest", "arrested"],
    "Malpractice": ["cheating", "fraud", "scam", "irregularities"],
}

INDIAN_STATES: List[str] = [
    "Delhi", "Punjab", "Haryana", "Rajasthan", "Bihar", "Jharkhand",
    "Uttar Pradesh", "Madhya Pradesh", "Maharashtra", "Gujarat", "West Bengal",
    "Odisha", "Assam", "Telangana", "Andhra Pradesh", "Tamil Nadu", "Karnataka",
    "Kerala",
]


@dataclass
class ClassificationConfig:
    """Injectable rule set. Defaults to the NEET/India domain.

    ``topic_model_enabled`` switches on the supervised general-news topic
    classifier (see ``news_topics``) as a *fallback* used only when the
    rule-based ``category_keywords`` above cannot assign a specific category
    (i.e. the result would be ``"Other"``). It is OFF by default so the
    low-level pipeline stays fully deterministic; the search service turns it on
    for real collection runs via the ``ENABLE_TOPIC_MODEL`` setting.
    """

    exam_database: Dict[str, Dict[str, str]] = field(default_factory=lambda: dict(EXAM_DATABASE))
    category_keywords: Dict[str, List[str]] = field(default_factory=lambda: dict(CATEGORY_KEYWORDS))
    indian_states: List[str] = field(default_factory=lambda: list(INDIAN_STATES))
    topic_model_enabled: bool = False
    topic_min_confidence: float = 0.30


# Shared default instance used by the pipeline unless overridden.
DEFAULT_CONFIG = ClassificationConfig()
