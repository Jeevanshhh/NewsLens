"""Provider-agnostic internal article model.

Every news collector maps its provider-specific response into this shape so
the rest of the system (processing, storage, API) never needs to know which
provider produced an article.

Data-quality rule: fields a provider does NOT supply are left as ``None``.
We never invent metadata.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Article(BaseModel):
    # Core content
    title: str = ""
    description: Optional[str] = None
    url: str = ""

    # Attribution
    source: Optional[str] = None      # publisher name, when the provider gives it
    provider: str                     # 'google_news' | 'gnews' | 'newsdata'
    author: Optional[str] = None

    # Timing (raw provider value; normalized to a canonical tz in Phase 3)
    published_at: Optional[str] = None

    # Search linkage
    keyword_matched: Optional[str] = None

    # Optional media / locale
    image_url: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
