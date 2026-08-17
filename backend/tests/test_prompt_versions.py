from fastapi.testclient import TestClient


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
