import json
import re
from pathlib import Path
from typing import Any

import pytest


WORKFLOW_DIRECTORY = Path(__file__).parents[1] / "n8n" / "workflows"
EXPECTED_EXPORTS = {
    "01-caller-context.json",
    "02-maintenance-request.json",
    "03-emergency-escalation.json",
    "04-post-call-processing.json",
}
EXPECTED_WEBHOOK_PATHS = {
    "01-caller-context.json": "caller-context",
    "02-maintenance-request.json": "maintenance-request",
    "03-emergency-escalation.json": "emergency-escalation",
    "04-post-call-processing.json": "fonio-post-call-processing",
}
HTTP_REQUEST_TYPE = "n8n-nodes-base.httpRequest"
GENERIC_NODE_NAME = re.compile(
    r"^(?:HTTP Request|Edit Fields|Code in JavaScript|Respond to Webhook)\d*$|^If$",
    re.IGNORECASE,
)
SIDE_EFFECT_PATH = re.compile(r"/(?:tickets|call-outcomes)(?:[/?#]|$)")
SECRET_LITERAL = re.compile(
    r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9_-]{8,}|"
    r"Bearer\s+[A-Za-z0-9._~+/-]{8,}|"
    r"https?://[^/\s:@]+:[^/\s@]+@|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    re.IGNORECASE,
)


def _load_exports() -> dict[str, dict[str, Any]]:
    actual = {path.name for path in WORKFLOW_DIRECTORY.glob("*.json")}
    assert actual == EXPECTED_EXPORTS
    return {
        name: json.loads((WORKFLOW_DIRECTORY / name).read_text(encoding="utf-8"))
        for name in sorted(EXPECTED_EXPORTS)
    }


@pytest.fixture(scope="module")
def exports() -> dict[str, dict[str, Any]]:
    return _load_exports()


def _http_nodes(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node
        for node in workflow["nodes"]
        if node.get("type") == HTTP_REQUEST_TYPE
    ]


def _json_from_string(value: str) -> Any:
    candidate = value.strip()
    if candidate.startswith("="):
        candidate = candidate[1:].strip()
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None


def _field_names(value: Any) -> set[str]:
    """Collect object keys and n8n name/value parameter names."""
    names: set[str] = set()
    if isinstance(value, dict):
        names.update(str(key).lower() for key in value)
        name = value.get("name")
        if isinstance(name, str):
            names.add(name.lower())
        for nested in value.values():
            names.update(_field_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(_field_names(nested))
    elif isinstance(value, str):
        parsed = _json_from_string(value)
        if parsed is not None and parsed != value:
            names.update(_field_names(parsed))
        for quoted, unquoted in re.findall(
            r"""(?:["']([A-Za-z][A-Za-z0-9_-]*)["']|"""
            r"""(?<![.\w])([A-Za-z][A-Za-z0-9_-]*))\s*:""",
            value,
        ):
            names.add((quoted or unquoted).lower())
    return names


def _header_configuration(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in parameters.items()
        if "header" in key.lower()
    }


def _body_configuration(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in parameters.items()
        if "body" in key.lower() and key not in {"sendBody"}
    }


def _method(node: dict[str, Any]) -> str:
    return str(node.get("parameters", {}).get("method", "GET")).upper()


def _url(node: dict[str, Any]) -> str:
    return str(node.get("parameters", {}).get("url", "")).lstrip("=")


def test_exports_have_expected_top_level_metadata(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        assert isinstance(workflow.get("name"), str) and workflow["name"].strip(), filename
        assert isinstance(workflow.get("nodes"), list) and workflow["nodes"], filename
        assert isinstance(workflow.get("connections"), dict), filename
        assert isinstance(workflow.get("settings"), dict), filename
        assert workflow.get("active") is False, filename
        assert workflow.get("pinData") == {}, filename

        if "id" in workflow:
            assert isinstance(workflow["id"], str) and workflow["id"].strip(), filename
        if "versionId" in workflow:
            assert isinstance(workflow["versionId"], str) and workflow["versionId"].strip(), filename
        if "tags" in workflow:
            assert isinstance(workflow["tags"], list), filename
        if "meta" in workflow:
            assert isinstance(workflow["meta"], dict), filename


def test_exports_use_stable_descriptive_webhook_paths(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, expected_path in EXPECTED_WEBHOOK_PATHS.items():
        webhook_nodes = [
            node
            for node in exports[filename]["nodes"]
            if node.get("type") == "n8n-nodes-base.webhook"
        ]
        assert len(webhook_nodes) == 1, filename
        assert webhook_nodes[0]["parameters"]["path"] == expected_path, filename
        assert webhook_nodes[0].get("webhookId"), filename


def test_exports_contain_no_secrets_or_hardcoded_api_keys(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        serialized = json.dumps(workflow, ensure_ascii=False)
        assert SECRET_LITERAL.search(serialized) is None, filename

        for node in _http_nodes(workflow):
            headers = _header_configuration(node.get("parameters", {}))
            hardcoded_auth = {"x-api-key", "authorization"} & _field_names(headers)
            assert not hardcoded_auth, (
                f"{filename}: {node['name']} hardcodes an authentication header "
                "instead of using the n8n credential"
            )


def test_http_requests_use_internal_api_url(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            url = _url(node)
            assert "http://api:8000/" in url, (
                f"{filename}: {node['name']} has invalid URL {url!r}"
            )
            assert "localhost" not in url.lower(), filename
            external_hosts = [
                host
                for host in re.findall(r"https?://([^/'\"}\s]+)", url)
                if host != "api:8000"
            ]
            assert not external_hosts, (
                f"{filename}: {node['name']} references external hosts "
                f"{external_hosts}"
            )


def test_http_requests_use_named_header_auth_credential(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            parameters = node.get("parameters", {})
            credential = node.get("credentials", {}).get("httpHeaderAuth")
            assert parameters.get("authentication") == "genericCredentialType", (
                filename,
                node["name"],
            )
            assert parameters.get("genericAuthType") == "httpHeaderAuth", (
                filename,
                node["name"],
            )
            assert isinstance(credential, dict), (filename, node["name"])
            assert credential.get("name") == "Fonio FastAPI API Key", (
                filename,
                node["name"],
            )


def test_backend_requests_send_conversation_id(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            headers = _header_configuration(node.get("parameters", {}))
            assert "x-conversation-id" in _field_names(headers), (
                f"{filename}: {node['name']} does not send X-Conversation-ID"
            )


def test_side_effect_posts_send_event_id(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            if _method(node) == "POST" and SIDE_EFFECT_PATH.search(_url(node)):
                headers = _header_configuration(node.get("parameters", {}))
                assert "x-event-id" in _field_names(headers), (
                    f"{filename}: {node['name']} does not send X-Event-ID"
                )


def test_http_requests_have_timeout_and_bounded_retries(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            timeout = node.get("parameters", {}).get("options", {}).get("timeout")
            assert isinstance(timeout, (int, float)) and 0 < timeout <= 120_000, (
                f"{filename}: {node['name']} needs a finite timeout"
            )
            assert node.get("retryOnFail") is True, (
                f"{filename}: {node['name']} must enable bounded retries"
            )
            max_tries = node.get("maxTries")
            assert isinstance(max_tries, int) and 2 <= max_tries <= 5, (
                f"{filename}: {node['name']} has invalid maxTries"
            )
            wait = node.get("waitBetweenTries")
            assert isinstance(wait, int) and 0 < wait <= 5_000, (
                f"{filename}: {node['name']} has invalid waitBetweenTries"
            )
            assert node.get("onError") in {
                "continueErrorOutput",
                "continueRegularOutput",
            }, f"{filename}: {node['name']} needs an explicit error path"
            if node.get("onError") == "continueRegularOutput":
                response_options = (
                    node.get("parameters", {})
                    .get("options", {})
                    .get("response", {})
                    .get("response", {})
                )
                assert response_options.get("neverError") is True, (
                    f"{filename}: {node['name']} must expose HTTP error "
                    "responses to its regular status branch"
                )


def test_separate_error_outputs_are_connected(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            if node.get("onError") != "continueErrorOutput":
                continue
            outputs = workflow["connections"].get(node["name"], {}).get("main", [])
            assert len(outputs) > 1 and outputs[1], (
                f"{filename}: {node['name']} does not connect its error output"
            )


def test_nodes_have_descriptive_names(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        names = [node.get("name") for node in workflow["nodes"]]
        assert all(isinstance(name, str) and name.strip() for name in names), filename
        assert len(names) == len(set(names)), filename
        generic = [name for name in names if GENERIC_NODE_NAME.fullmatch(name)]
        assert not generic, f"{filename}: generic node names: {generic}"


def test_ticket_post_bodies_only_contain_ticket_schema_fields(
    exports: dict[str, dict[str, Any]],
) -> None:
    for filename, workflow in exports.items():
        for node in _http_nodes(workflow):
            if _method(node) != "POST" or not re.search(
                r"/tickets(?:[/?#]|$)", _url(node)
            ):
                continue
            body_fields = _field_names(
                _body_configuration(node.get("parameters", {}))
            )
            forbidden = {"event_id", "conversation_id"} & body_fields
            assert not forbidden, (
                f"{filename}: {node['name']} puts header fields in its body: "
                f"{sorted(forbidden)}"
            )


def test_maintenance_lookup_preserves_an_empty_ticket_array(
    exports: dict[str, dict[str, Any]],
) -> None:
    workflow = exports["02-maintenance-request.json"]
    lookup = next(
        node
        for node in workflow["nodes"]
        if node["name"] == "Check Customer Open Tickets"
    )
    response_options = lookup["parameters"]["options"]["response"]["response"]
    assert response_options.get("fullResponse") is True
    assert response_options.get("responseFormat") == "json"

    matcher = next(
        node
        for node in workflow["nodes"]
        if node["name"] == "Find Matching Open Ticket"
    )
    assert "item.json.body ?? item.json" in matcher["parameters"]["jsCode"]
