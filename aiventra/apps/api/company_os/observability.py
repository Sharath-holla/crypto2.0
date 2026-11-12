"""Correlated structured application logs without request bodies or credentials."""

import json
import logging
import re
import time
from contextvars import ContextVar

from starlette.requests import Request

from .db import uid
from .security import redact

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
logger = logging.getLogger("aiventra")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "level": record.levelname,
            "event": redact(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", correlation_id.get()),
        }
        for key in ("workflow_id", "error_type", "status", "duration_ms", "method", "path"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["error_type"] = record.exc_info[0].__name__
        return json.dumps(data)


def configure_logging():
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


async def request_trace(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    identifier = supplied if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", supplied) else uid()
    marker = correlation_id.set(identifier)
    started = time.monotonic()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = identifier
        logger.info(
            "http.request",
            extra={
                "status": response.status_code,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "method": request.method,
                "path": request.scope.get("route").path if request.scope.get("route") else "unmatched",
            },
        )
        return response
    except Exception as exc:
        logger.error("http.failure", extra={"error_type": type(exc).__name__})
        raise
    finally:
        correlation_id.reset(marker)
