from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from typing import Any

import httpx

from app.integrations.errors import (
    CustomerSystemResponseError,
    CustomerSystemTimeoutError,
    CustomerSystemUnavailableError,
)
from app.observability.logging import log_event

TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})


@dataclass(frozen=True)
class CustomerSystemClientConfig:
    base_url: str
    connect_timeout_seconds: float = 2.0
    read_timeout_seconds: float = 5.0
    maximum_attempts: int = 3
    retry_delays_seconds: tuple[float, ...] = (0.25, 0.75)

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("Customer system base URL cannot be blank")
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ValueError("Customer system timeouts must be positive")
        if not 1 <= self.maximum_attempts <= 5:
            raise ValueError("maximum_attempts must be between 1 and 5")
        if any(delay < 0 for delay in self.retry_delays_seconds):
            raise ValueError("Retry delays cannot be negative")
        if len(self.retry_delays_seconds) < self.maximum_attempts - 1:
            raise ValueError("A retry delay is required for every retry")


class CustomerSystemClient:
    def __init__(
        self,
        config: CustomerSystemClientConfig,
        *,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._config = config
        self._client = http_client or httpx.Client(base_url=config.base_url)
        self._owns_client = http_client is None
        self._sleeper = sleeper
        self._timeout = httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.read_timeout_seconds,
            pool=config.connect_timeout_seconds,
        )

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        for attempt in range(1, self._config.maximum_attempts + 1):
            try:
                response = self._client.request(
                    method,
                    self._url(path),
                    timeout=self._timeout,
                    **kwargs,
                )
            except httpx.TimeoutException as error:
                if attempt == self._config.maximum_attempts:
                    self._log_terminal_failure("timeout", attempt)
                    raise CustomerSystemTimeoutError(attempt) from error
                self._retry("timeout", attempt)
                continue
            except httpx.RequestError as error:
                if attempt == self._config.maximum_attempts:
                    self._log_terminal_failure("network_error", attempt)
                    raise CustomerSystemUnavailableError(attempt) from error
                self._retry("network_error", attempt)
                continue

            if response.status_code in TRANSIENT_STATUS_CODES:
                if attempt == self._config.maximum_attempts:
                    self._log_terminal_failure(
                        "transient_status", attempt, response.status_code
                    )
                    raise CustomerSystemUnavailableError(
                        attempt, response.status_code
                    )
                self._retry("transient_status", attempt, response.status_code)
                continue

            if response.is_error:
                self._log_terminal_failure(
                    "permanent_status", attempt, response.status_code
                )
                raise CustomerSystemResponseError(response.status_code)

            log_event(
                "customer_system_request_succeeded",
                attempt=attempt,
                upstream_status=response.status_code,
            )
            return response

        raise RuntimeError("Customer-system retry loop ended unexpectedly")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _url(self, path: str) -> str:
        return f"{self._config.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _retry(
        self, reason: str, attempt: int, upstream_status: int | None = None
    ) -> None:
        delay = self._config.retry_delays_seconds[attempt - 1]
        log_event(
            "customer_system_retry",
            attempt=attempt,
            next_attempt=attempt + 1,
            delay_seconds=delay,
            reason=reason,
            upstream_status=upstream_status,
        )
        self._sleeper(delay)

    @staticmethod
    def _log_terminal_failure(
        reason: str, attempt: int, upstream_status: int | None = None
    ) -> None:
        log_event(
            "customer_system_failed",
            attempts=attempt,
            reason=reason,
            upstream_status=upstream_status,
        )
