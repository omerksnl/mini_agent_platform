from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.guardrails import GuardrailRunner, GuardrailViolation
from tests.test_phase1 import auth_headers, register


def policy(name: str, kind: str, stages: list[str], action: str, config: dict):
    return SimpleNamespace(name=name, guardrail_type=kind, stages=stages, action=action, config=config, is_active=True)


def test_deterministic_guardrail_runner_redacts_and_blocks() -> None:
    runner = GuardrailRunner([
        policy("privacy", "pii_redaction", ["output"], "redact", {"types": ["email", "phone"]}),
        policy("competitors", "blocked_terms", ["input"], "block", {"terms": ["Competitor X"]}),
    ], agent_name="test", tenant_id="tenant")

    assert runner.apply("output", "Mail a@example.com or call +90 555 123 4567") == (
        "Mail [REDACTED_EMAIL] or call [REDACTED_PHONE]"
    )
    assert runner.apply("output", "Project date: 2026-08-03") == "Project date: 2026-08-03"
    with pytest.raises(GuardrailViolation, match="Blocked topic"):
        runner.apply("input", "Tell me about Competitor X")


def test_required_output_fields_support_nested_json_paths() -> None:
    runner = GuardrailRunner([
        policy("profile schema", "required_output_fields", ["output"], "block", {"fields": ["candidate.name", "skills"]}),
    ], agent_name="test", tenant_id="tenant")
    assert runner.apply("output", '{"candidate":{"name":"Ada"},"skills":["Python"]}')
    with pytest.raises(GuardrailViolation, match="Missing required fields: skills"):
        runner.apply("output", '{"candidate":{"name":"Ada"},"skills":[]}')


def test_guardrail_crud_assignment_and_tenant_isolation(client: TestClient) -> None:
    token_a = register(client, email="guard-a@example.com", tenant_name="Guard A")
    created = client.post("/api/guardrails", headers=auth_headers(token_a), json={
        "name": "Hide contacts", "guardrail_type": "pii_redaction", "stages": ["output"],
        "action": "redact", "config": {"types": ["email", "phone"]}, "is_active": True,
    })
    assert created.status_code == 201, created.text
    guardrail_id = created.json()["id"]
    agent = client.post("/api/agents", headers=auth_headers(token_a), json={
        "name": "Guarded", "system_prompt": "Test", "system_tools": [], "guardrail_ids": [guardrail_id],
    })
    assert agent.status_code == 201, agent.text
    assert agent.json()["guardrail_ids"] == [guardrail_id]

    token_b = register(client, email="guard-b@example.com", tenant_name="Guard B")
    assert client.get("/api/guardrails", headers=auth_headers(token_b)).json() == []
    cross_tenant = client.post("/api/agents", headers=auth_headers(token_b), json={
        "name": "Invalid", "system_prompt": "Test", "system_tools": [], "guardrail_ids": [guardrail_id],
    })
    assert cross_tenant.status_code == 404
