import json
from pathlib import Path
from typing import Any

import pytest


SCENARIO_DIRECTORY = Path(__file__).parents[1] / "scenarios"
EXPECTED_SCENARIOS = {
    "ambiguous-caller.json",
    "crm-timeout.json",
    "crm-unavailable.json",
    "duplicate-webhook.json",
    "emergency.json",
    "existing-ticket.json",
    "normal-maintenance.json",
    "transfer-failure.json",
    "unknown-caller.json",
}
CALLER_SCENARIOS = {
    "ambiguous-caller.json",
    "crm-timeout.json",
    "crm-unavailable.json",
    "unknown-caller.json",
}
ACTION_SCENARIOS = {
    "emergency.json",
    "existing-ticket.json",
    "normal-maintenance.json",
    "transfer-failure.json",
}
ACTION_FIELDS = {
    "event_id",
    "conversation_id",
    "customer_id",
    "property_id",
    "intent",
    "category",
    "description",
    "severity",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((SCENARIO_DIRECTORY / name).read_text(encoding="utf-8"))


def _assert_non_empty_strings(payload: dict[str, Any]) -> None:
    assert payload
    assert all(isinstance(value, str) and value.strip() for value in payload.values())


def test_expected_scenario_set_is_complete() -> None:
    actual = {path.name for path in SCENARIO_DIRECTORY.glob("*.json")}
    assert actual == EXPECTED_SCENARIOS


@pytest.mark.parametrize("name", sorted(CALLER_SCENARIOS))
def test_caller_scenarios_match_webhook_contract(name: str) -> None:
    payload = _load(name)
    assert set(payload) == {"conversation_id", "phone"}
    _assert_non_empty_strings(payload)
    assert payload["phone"].startswith("+")
    assert payload["phone"][1:].isdigit()


@pytest.mark.parametrize("name", sorted(ACTION_SCENARIOS))
def test_action_scenarios_match_webhook_contract(name: str) -> None:
    payload = _load(name)
    assert set(payload) == ACTION_FIELDS
    _assert_non_empty_strings(payload)
    assert payload["severity"] in {"normal", "high", "critical"}


def test_emergency_scenarios_are_critical() -> None:
    for name in ("emergency.json", "transfer-failure.json"):
        payload = _load(name)
        assert payload["intent"] == "emergency"
        assert payload["severity"] == "critical"


def test_existing_ticket_scenario_targets_canonical_heating_ticket() -> None:
    payload = _load("existing-ticket.json")
    assert payload["customer_id"] == "customer-anna-mueller"
    assert payload["property_id"] == "property-neubaugasse-17"
    assert payload["category"] == "heating"


def test_duplicate_webhook_replays_identical_logical_event() -> None:
    scenario = _load("duplicate-webhook.json")
    assert set(scenario) == {"scenario", "deliveries"}
    assert isinstance(scenario["scenario"], str) and scenario["scenario"].strip()
    deliveries = scenario["deliveries"]
    assert isinstance(deliveries, list) and len(deliveries) == 2
    assert deliveries[0] == deliveries[1]
    assert set(deliveries[0]) == ACTION_FIELDS
    _assert_non_empty_strings(deliveries[0])
