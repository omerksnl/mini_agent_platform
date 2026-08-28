from sqlalchemy import select
from uuid import UUID

from app.models import AgentProviderAssignment, ProviderCredential, User


def register(client):
    response = client.post("/api/auth/register", json={
        "email": "provider@example.com", "password": "password123",
        "full_name": "Provider User", "tenant_name": "Provider Tenant",
    })
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_personal_provider_key_is_encrypted_and_can_be_cleared(client, db_session_factory) -> None:
    headers = register(client)
    response = client.put("/api/provider-settings", headers=headers, json={
        "name": "Personal OpenAI", "provider": "openai", "api_key": "sk-personal-openai-test-key-123456789",
    })
    assert response.status_code == 200, response.text
    assert response.json() == {
        "provider": "openai", "source": "personal", "has_personal_key": True,
        "masked_key": "••••••••",
    }
    assert "sk-personal" not in response.text

    db = db_session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "provider@example.com"))
        profile = db.scalar(select(ProviderCredential).where(ProviderCredential.user_id == user.id))
        assert profile.name == "Personal OpenAI"
        assert profile.provider == "openai"
        assert profile.is_active is True
        assert "sk-personal" not in profile.encrypted_api_key
    finally:
        db.close()

    models = client.get("/api/provider-settings/models", headers=headers)
    assert models.status_code == 200
    assert "gpt-4o-mini" in [item["id"] for item in models.json()]
    assert "gpt-4.1-nano" in [item["id"] for item in models.json()]

    listed = client.get("/api/provider-settings/credentials", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Personal OpenAI"
    assert listed.json()[0]["masked_key"] == "••••••••"
    assert "sk-personal" not in listed.text

    cleared = client.delete("/api/provider-settings", headers=headers)
    assert cleared.status_code == 204


def test_agent_can_use_a_user_specific_provider_profile(client, db_session_factory) -> None:
    headers = register(client)
    saved = client.put("/api/provider-settings", headers=headers, json={
        "name": "CV OpenAI", "provider": "openai",
        "api_key": "sk-personal-openai-agent-key-123456789",
    })
    assert saved.status_code == 200
    profile_id = client.get("/api/provider-settings/credentials", headers=headers).json()[0]["id"]
    agent = client.post("/api/agents", headers=headers, json={
        "name": "Profile Agent", "system_prompt": "Help.", "model": "gpt-4.1-mini",
        "temperature": 0.2, "system_tools": [], "tool_ids": [], "skill_ids": [],
        "collection_ids": [],
    })
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    assigned = client.put(
        f"/api/provider-settings/agent-assignments/{agent_id}", headers=headers,
        json={"credential_id": profile_id},
    )
    assert assigned.status_code == 204, assigned.text
    assert client.get("/api/provider-settings/agent-assignments", headers=headers).json() == [{
        "agent_id": agent_id, "credential_id": profile_id,
    }]

    db = db_session_factory()
    try:
        mapping = db.get(AgentProviderAssignment, {
            "user_id": db.scalar(select(User).where(User.email == "provider@example.com")).id,
            "agent_id": UUID(agent_id),
        })
        assert str(mapping.provider_credential_id) == profile_id
    finally:
        db.close()
