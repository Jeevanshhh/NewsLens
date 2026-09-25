"""News provider collectors.

Each module exposes ``collect(ctx, ...) -> list[Article]`` returning the
provider-agnostic :class:`~app.schemas.article.Article` model.
"""
