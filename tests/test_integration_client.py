import asyncio
import io
import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import (
    customer_system_response_handler,
    customer_system_timeout_handler,
    customer_system_unavailable_handler,
    register_exception_handlers,
)
from app.integrations.client import CustomerSystemClient, CustomerSystemClientConfig
from app.integrations.errors import (
    CustomerSystemResponseError,
    CustomerSystemTimeoutError,
    CustomerSystemUnavailableError,
)
from app.observability.logging import (
    JsonFormatter,
    application_logger,
    conversation_id_context,
    request_id_context,
)
from app.observability.middleware import RequestObservabilityMiddleware


def make_client(
    handler,
    *,
    sleeps: list[float] | None = None,
    maximum_attempts: int = 3,
) -> CustomerSystemClient:
    sleep_calls = sleeps if sleeps is not None else []
    return CustomerSystemClient(
        CustomerSystemClientConfig(
            base_url="https://customer-system.example",
            maximum_attempts=maximum_attempts,
            retry_delays_seconds=(0.25, 0.75, 1.0, 1.0),
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleep_calls.append,
    )


def test_successful_request_is_not_retried_and_preserves_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    sleeps: list[float] = []
    client = make_client(handler, sleeps=sleeps)
    response = client.request(
        "GET",
        "/customers/123",
        headers={"X-Event-ID": "event-123"},
    )

    assert response.json() == {"status": "ok"}
    assert len(requests) == 1
    assert requests[0].url == "https://customer-system.example/customers/123"
    assert requests[0].headers["X-Event-ID"] == "event-123"
    assert requests[0].extensions["timeout"] == {
        "connect": 2.0,
        "read": 5.0,
        "write": 5.0,
        "pool": 2.0,
    }
    assert sleeps == []


def test_timeout_twice_then_success_uses_bounded_delays() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("slow customer system", request=request)
        return httpx.Response(200, json={"status": "ok"})

    sleeps: list[float] = []
    response = make_client(handler, sleeps=sleeps).request("GET", "/customers/123")
    assert response.status_code == 200
    assert attempts == 3
    assert sleeps == [0.25, 0.75]


@pytest.mark.parametrize("status_code", [502, 503, 504])
def test_transient_status_twice_then_success_is_retried(status_code: int) -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code if attempts < 3 else 200)

    sleeps: list[float] = []
    response = make_client(handler, sleeps=sleeps).request("GET", "/resource")
    assert response.status_code == 200
    assert attempts == 3
    assert sleeps == [0.25, 0.75]


def test_timeouts_stop_after_maximum_attempts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("slow customer system", request=request)

    sleeps: list[float] = []
    with pytest.raises(CustomerSystemTimeoutError) as raised:
        make_client(handler, sleeps=sleeps).request("GET", "/resource")
    assert raised.value.attempts == 3
    assert attempts == 3
    assert sleeps == [0.25, 0.75]


def test_connection_errors_stop_after_maximum_attempts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection refused", request=request)

    sleeps: list[float] = []
    with pytest.raises(CustomerSystemUnavailableError) as raised:
        make_client(handler, sleeps=sleeps).request("GET", "/resource")
    assert raised.value.attempts == 3
    assert raised.value.upstream_status is None
    assert attempts == 3
    assert sleeps == [0.25, 0.75]


@pytest.mark.parametrize("status_code", [502, 503, 504])
def test_exhausted_transient_status_returns_unavailable(status_code: int) -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code)

    sleeps: list[float] = []
    with pytest.raises(CustomerSystemUnavailableError) as raised:
        make_client(handler, sleeps=sleeps).request("GET", "/resource")
    assert raised.value.attempts == 3
    assert raised.value.upstream_status == status_code
    assert attempts == 3
    assert sleeps == [0.25, 0.75]


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 422, 500])
def test_permanent_status_is_never_retried(status_code: int) -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code)

    sleeps: list[float] = []
    with pytest.raises(CustomerSystemResponseError) as raised:
        make_client(handler, sleeps=sleeps).request("POST", "/resource")
    assert raised.value.upstream_status == status_code
    assert attempts == 1
    assert sleeps == []


def test_single_attempt_configuration_never_sleeps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    sleeps: list[float] = []
    with pytest.raises(CustomerSystemTimeoutError):
        make_client(handler, sleeps=sleeps, maximum_attempts=1).request(
            "GET", "/resource"
        )
    assert sleeps == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": " "},
        {"base_url": "https://example.com", "connect_timeout_seconds": 0},
        {"base_url": "https://example.com", "read_timeout_seconds": -1},
        {"base_url": "https://example.com", "maximum_attempts": 0},
        {"base_url": "https://example.com", "maximum_attempts": 6},
        {
            "base_url": "https://example.com",
            "maximum_attempts": 3,
            "retry_delays_seconds": (0.1,),
        },
        {
            "base_url": "https://example.com",
            "retry_delays_seconds": (-0.1, 0.2),
        },
    ],
)
def test_invalid_client_configuration_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        CustomerSystemClientConfig(**kwargs)


def test_retry_logs_include_request_correlation() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 200)

    stream = io.StringIO()
    log_handler = logging.StreamHandler(stream)
    log_handler.setFormatter(JsonFormatter())
    application_logger.addHandler(log_handler)
    request_token = request_id_context.set("req-integration-test")
    conversation_token = conversation_id_context.set("conv-integration-test")
    try:
        make_client(handler).request("GET", "/resource")
    finally:
        conversation_id_context.reset(conversation_token)
        request_id_context.reset(request_token)
        application_logger.removeHandler(log_handler)
        log_handler.close()

    logs = [json.loads(line) for line in stream.getvalue().splitlines()]
    retry_log = next(log for log in logs if log["event"] == "customer_system_retry")
    success_log = next(
        log for log in logs if log["event"] == "customer_system_request_succeeded"
    )
    assert retry_log["request_id"] == "req-integration-test"
    assert retry_log["conversation_id"] == "conv-integration-test"
    assert retry_log["attempt"] == 1
    assert retry_log["next_attempt"] == 2
    assert retry_log["reason"] == "transient_status"
    assert success_log["attempt"] == 2


def test_customer_system_errors_map_to_structured_responses() -> None:
    timeout_response = asyncio.run(
        customer_system_timeout_handler(None, CustomerSystemTimeoutError(3))
    )
    unavailable_response = asyncio.run(
        customer_system_unavailable_handler(
            None, CustomerSystemUnavailableError(3, 503)
        )
    )
    permanent_response = asyncio.run(
        customer_system_response_handler(None, CustomerSystemResponseError(400))
    )

    timeout_body = json.loads(timeout_response.body)
    unavailable_body = json.loads(unavailable_response.body)
    permanent_body = json.loads(permanent_response.body)
    assert timeout_response.status_code == 503
    assert timeout_body["error"]["code"] == "CUSTOMER_SYSTEM_TIMEOUT"
    assert timeout_body["error"]["retryable"] is True
    assert timeout_body["error"]["details"] == {"attempts": 3}
    assert unavailable_response.status_code == 503
    assert unavailable_body["error"]["code"] == "CUSTOMER_SYSTEM_UNAVAILABLE"
    assert unavailable_body["error"]["retryable"] is True
    assert permanent_response.status_code == 502
    assert permanent_body["error"]["code"] == "CUSTOMER_SYSTEM_REQUEST_FAILED"
    assert permanent_body["error"]["retryable"] is False
    assert permanent_body["error"]["details"] == {"upstream_status": 400}


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_code", "retryable"),
    [
        ("/timeout", 503, "CUSTOMER_SYSTEM_TIMEOUT", True),
        ("/unavailable", 503, "CUSTOMER_SYSTEM_UNAVAILABLE", True),
        ("/rejected", 502, "CUSTOMER_SYSTEM_REQUEST_FAILED", False),
    ],
)
def test_customer_system_failures_use_http_error_contract(
    path: str, expected_status: int, expected_code: str, retryable: bool
) -> None:
    failure_app = FastAPI()
    failure_app.add_middleware(RequestObservabilityMiddleware)
    register_exception_handlers(failure_app)

    @failure_app.get("/timeout")
    def timeout() -> None:
        raise CustomerSystemTimeoutError(3)

    @failure_app.get("/unavailable")
    def unavailable() -> None:
        raise CustomerSystemUnavailableError(3, 503)

    @failure_app.get("/rejected")
    def rejected() -> None:
        raise CustomerSystemResponseError(400)

    response = TestClient(failure_app).get(
        path, headers={"X-Conversation-ID": "conv-customer-system-failure"}
    )
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["retryable"] is retryable
    assert response.json()["error"]["conversation_id"] == (
        "conv-customer-system-failure"
    )
    assert response.headers["x-conversation-id"] == (
        "conv-customer-system-failure"
    )
    assert "x-request-id" in response.headers
