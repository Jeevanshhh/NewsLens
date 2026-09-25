"""Structured logging + request correlation for the backend.

A single, dependency-light setup shared by every phase:

* Logs are emitted as **JSON** in production (machine-parseable for any log
  pipeline) and as a compact readable line in development, chosen via the
  ``LOG_JSON`` setting.
* Every API request is tagged with a request id (see ``request_id`` context
  var, wired by the middleware in :mod:`app.main`); the id is injected into
  each log record so a single request's lines can be correlated, and is echoed
  back to the client on the ``X-Request-ID`` response header.
* Technical detail stays server-side: the HTTP layer only ever returns generic
  error bodies (see the global exception handler in ``main``).
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Carries the active request id across the handling of a single request.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_RESERVED = set(
    """
    name msg args exc_info exc_text stack_info lineno filename module pathname
    funcName created msecs relativeCreated levelname levelno asctime taskName
    """.split()
)


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render a record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Include any structured extras a caller passed via ``extra=``.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    """Configure root logging once, idempotently."""
    root = logging.getLogger()
    if getattr(root, "_newslens_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(RequestIdFilter())

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Tame noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    root._newslens_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
