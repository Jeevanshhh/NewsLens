"""ORM models package.

Importing this module registers every table on ``Base.metadata``.
"""
from app.models._mixins import TimestampMixin, utcnow
from app.models.article import Article
from app.models.bookmark import Bookmark
from app.models.report import Report
from app.models.search import Search, search_results
from app.models.user import User

__all__ = [
    "Article",
    "Bookmark",
    "Report",
    "Search",
    "search_results",
    "User",
    "TimestampMixin",
    "utcnow",
]
