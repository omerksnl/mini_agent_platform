from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.services.agent_service import AgentService
from app.core.services.prompt_optimization_service import PromptOptimizationService


def register(client: TestClient, email: str, tenant_name: str) -> dict[str, str]:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "test-password",
        "full_name": "Prompt Tester",
        "tenant_name": tenant_name,
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_agent(client: TestClient, headers: dict[str, str], prompt: str) -> dict:
    response = client.post("/api/agents", headers=headers, json={
        "name": "Versioned Agent",
        "system_prompt": prompt,
        "model": "anthropic/claude-haiku-4.5",
        "temperature": 0.2,
    })
    assert response.status_code == 201
    return response.json()


def test_prompt_history_keeps_latest_three_distinct_prompt_updates(client: TestClient) -> None:
    headers = register(client, "versions@example.com", "Versions Tenant")
    agent = create_agent(client, headers, "Prompt v1")

    # A non-prompt update must not create a prompt version.
    response = client.patch(
        f"/api/agents/{agent['id']}", headers=headers, json={"temperature": 0.4}
    )
    assert response.status_code == 200

    for prompt in ("Prompt v2", "Prompt v3", "Prompt v4"):
        response = client.patch(
            f"/api/agents/{agent['id']}", headers=headers, json={"system_prompt": prompt}
        )
        assert response.status_code == 200

    versions = client.get(
        f"/api/agents/{agent['id']}/prompt-versions", headers=headers
    )
    assert versions.status_code == 200
    assert [item["version_number"] for item in versions.json()] == [4, 3, 2]
    assert [item["system_prompt"] for item in versions.json()] == [
        "Prompt v4", "Prompt v3", "Prompt v2"
    ]


def test_restore_creates_a_new_current_version_and_is_tenant_isolated(client: TestClient) -> None:
    owner = register(client, "owner-versions@example.com", "Owner Tenant")
    outsider = register(client, "outsider-versions@example.com", "Outsider Tenant")
    agent = create_agent(client, owner, "Original prompt")
    client.patch(
        f"/api/agents/{agent['id']}", headers=owner, json={"system_prompt": "Updated prompt"}
    )
    versions = client.get(
        f"/api/agents/{agent['id']}/prompt-versions", headers=owner
    ).json()
    original = next(item for item in versions if item["system_prompt"] == "Original prompt")

    assert client.get(
        f"/api/agents/{agent['id']}/prompt-versions", headers=outsider
    ).status_code == 404
    assert client.post(
        f"/api/agents/{agent['id']}/prompt-versions/{original['id']}/restore",
        headers=outsider,
    ).status_code == 404

    restored = client.post(
        f"/api/agents/{agent['id']}/prompt-versions/{original['id']}/restore",
        headers=owner,
    )
    assert restored.status_code == 200
    assert restored.json()["system_prompt"] == "Original prompt"
    restored_versions = client.get(
        f"/api/agents/{agent['id']}/prompt-versions", headers=owner
    ).json()
    assert [item["version_number"] for item in restored_versions] == [2, 1]
    current = next(item for item in restored_versions if item["is_current"])
    assert current["version_number"] == 1
    assert current["system_prompt"] == "Original prompt"


def test_prompt_versions_can_be_evaluated_without_calling_a_real_model(
    client: TestClient, monkeypatch
) -> None:
    headers = register(client, "evaluate@example.com", "Evaluation Tenant")
    agent = create_agent(client, headers, "Ground every answer in supplied evidence.")

    def fake_evaluate(self, agent_id, tenant_id):
        versions = AgentService(self.db).list_prompt_versions(agent_id, tenant_id)
        versions[0].evaluation = {
            "score": 9,
        }
        versions[0].evaluated_at = datetime.now(timezone.utc)
        self.db.commit()
        return versions, 0.00125

    monkeypatch.setattr(PromptOptimizationService, "evaluate_versions", fake_evaluate)
    response = client.post(
        f"/api/agents/{agent['id']}/prompt-versions/evaluate", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["api_cost_usd"] == 0.00125
    assert response.json()["versions"][0]["evaluation"]["score"] == 9
    assert response.json()["versions"][0]["evaluated_at"] is not None


def test_create_with_ai_returns_a_draft_and_does_not_create_a_version(
    client: TestClient, monkeypatch
) -> None:
    headers = register(client, "improve@example.com", "Improve Tenant")
    agent = create_agent(client, headers, "Answer questions.")

    def fake_improve(self, agent_id, tenant_id, draft_prompt):
        AgentService(self.db).get_agent(agent_id, tenant_id)
        assert draft_prompt == "Answer questions."
        return SimpleNamespace(
            improved_prompt="Answer using only supplied evidence.",
            rationale=["Added an evidence boundary"],
        ), 0.0025

    monkeypatch.setattr(PromptOptimizationService, "improve_prompt", fake_improve)
    response = client.post(
        f"/api/agents/{agent['id']}/prompt-improvements",
        headers=headers,
        json={"draft_prompt": "Answer questions."},
    )

    assert response.status_code == 200
    assert response.json()["improved_prompt"] == "Answer using only supplied evidence."
    assert response.json()["api_cost_usd"] == 0.0025
    versions = client.get(
        f"/api/agents/{agent['id']}/prompt-versions", headers=headers
    ).json()
    assert len(versions) == 1
    assert versions[0]["system_prompt"] == "Answer questions."
