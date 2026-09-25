"""Aggregate API router.

Later phases mount their routers here (auth, search, articles, analytics,
exports, bookmarks, history) so `main.py` only includes a single api_router.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import analytics, articles, auth, bookmarks, exports, health, news, search

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(search.router)
api_router.include_router(articles.router)
api_router.include_router(analytics.router)
api_router.include_router(exports.router)
api_router.include_router(bookmarks.router)
api_router.include_router(news.router)
