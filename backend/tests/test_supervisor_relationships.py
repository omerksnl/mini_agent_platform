from fastapi.testclient import TestClient


def register(client: TestClient, email: str, tenant: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "password123",
        "full_name": "Supervisor Tester",
        "tenant_name": tenant,
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_agent(client: TestClient, token: str, name: str, **extra) -> dict:
    response = client.post("/api/agents", headers=headers(token), json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_supervisor_manages_normal_agents_and_delete_removes_links(client: TestClient) -> None:
    token = register(client, "supervisor@example.com", "Supervisor Tenant")
    cv_agent = create_agent(client, token, "cv_ai")
    fit_agent = create_agent(client, token, "job_fit_ai")

    supervisor = create_agent(
        client,
        token,
        "recruitment_supervisor",
        agent_type="supervisor",
        managed_agent_ids=[cv_agent["id"], fit_agent["id"]],
    )
    assert supervisor["agent_type"] == "supervisor"
    assert supervisor["supervisor_ids"] == []
    assert set(supervisor["managed_agent_ids"]) == {cv_agent["id"], fit_agent["id"]}

    refreshed_cv = client.get(f"/api/agents/{cv_agent['id']}", headers=headers(token)).json()
    assert refreshed_cv["agent_type"] == "normal"
    assert refreshed_cv["supervisor_ids"] == [supervisor["id"]]

    assert client.delete(f"/api/agents/{supervisor['id']}", headers=headers(token)).status_code == 204
    released_cv = client.get(f"/api/agents/{cv_agent['id']}", headers=headers(token)).json()
    assert released_cv["supervisor_ids"] == []


def test_supervisor_relationship_validation(client: TestClient) -> None:
    token = register(client, "rules@example.com", "Rules Tenant")
    child = create_agent(client, token, "child")
    supervisor = create_agent(
        client, token, "supervisor", agent_type="supervisor", managed_agent_ids=[child["id"]]
    )

    normal_manager = client.post(
        "/api/agents", headers=headers(token),
        json={"name": "invalid", "managed_agent_ids": [child["id"]]},
    )
    assert normal_manager.status_code == 400

    shared_owner = client.post(
        "/api/agents", headers=headers(token),
        json={"name": "other", "agent_type": "supervisor", "managed_agent_ids": [child["id"]]},
    )
    assert shared_owner.status_code == 201
    refreshed_child = client.get(f"/api/agents/{child['id']}", headers=headers(token)).json()
    assert set(refreshed_child["supervisor_ids"]) == {supervisor["id"], shared_owner.json()["id"]}

    self_managed = client.patch(
        f"/api/agents/{supervisor['id']}", headers=headers(token),
        json={"managed_agent_ids": [supervisor["id"]]},
    )
    assert self_managed.status_code == 400

    nested_supervisor = client.patch(
        f"/api/agents/{child['id']}", headers=headers(token), json={"agent_type": "supervisor"},
    )
    assert nested_supervisor.status_code == 400


def test_supervisor_cannot_manage_agents_from_another_tenant(client: TestClient) -> None:
    first = register(client, "first-supervisor@example.com", "First Tenant")
    second = register(client, "second-supervisor@example.com", "Second Tenant")
    foreign_agent = create_agent(client, second, "foreign")

    response = client.post(
        "/api/agents", headers=headers(first),
        json={
            "name": "invalid_supervisor",
            "agent_type": "supervisor",
            "managed_agent_ids": [foreign_agent["id"]],
        },
    )
    assert response.status_code == 404
