from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from crypto_ai.context.models import ProviderCapability

logger = logging.getLogger(__name__)


class ContextProvider(Protocol):
    provider_id: str
    capabilities: frozenset[ProviderCapability]


class ContextProviderError(RuntimeError):
    """Raised when a public contextual-data provider response is unusable."""


class RetryingPublicJsonClient:
    """Small public-GET-only client; credentials and mutating methods are unsupported."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        retry_base_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._sleep = sleeper
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "crypto-trading-ai-context/0.1.0"},
        )

    def __enter__(self) -> RetryingPublicJsonClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_json(self, path: str, params: dict[str, object] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
                retryable = response.status_code in {418, 429} or response.status_code >= 500
                if retryable and attempt < self._max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        server_wait = float(retry_after) if retry_after is not None else 0.0
                    except ValueError:
                        server_wait = 0.0
                    delay = max(server_wait, self._retry_base_seconds * (2**attempt))
                    logger.warning(
                        "Retrying public context GET",
                        extra={
                            "event": "context_provider_retry",
                            "path": path,
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                            "delay_seconds": delay,
                        },
                    )
                    self._sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = self._retry_base_seconds * (2**attempt)
                self._sleep(delay)
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise ContextProviderError(
                    f"Public context request failed for {path}: {exc}"
                ) from exc
        raise ContextProviderError(
            f"Public context request failed for {path}: {last_error}"
        ) from last_error
