from fastapi.testclient import TestClient


def register(client: TestClient, email: str, tenant_name: str = "Team") -> str:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "password123",
        "full_name": "Workflow Tester",
        "tenant_name": tenant_name,
    })
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_agent(client: TestClient, token: str, name: str) -> dict:
    response = client.post("/api/agents", headers=headers(token), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def create_tool(client: TestClient, token: str) -> dict:
    response = client.post("/api/tools", headers=headers(token), json={
        "name": "notify_recruiter",
        "description": "Notify the recruiter",
        "url": "https://example.com/notify",
        "method": "POST",
        "parameters": [],
    })
    assert response.status_code == 201, response.text
    return response.json()


def workflow_payload(agent_id: str, tool_id: str) -> dict:
    return {
        "name": "Recruitment Workflow",
        "description": "Prepare and review a candidate",
        "steps": [
            {
                "step_key": "extract_cv",
                "name": "Extract CV",
                "step_type": "agent",
                "position": 0,
                "agent_id": agent_id,
            },
            {
                "step_key": "wait_for_interview",
                "name": "Wait for interview",
                "step_type": "human_wait",
                "position": 1,
                "config": {"required_input": "interview_answers"},
            },
            {
                "step_key": "notify",
                "name": "Notify recruiter",
                "step_type": "http_tool",
                "position": 2,
                "http_tool_id": tool_id,
            },
        ],
        "routes": [
            {
                "source_step_key": "extract_cv",
                "target_step_key": "wait_for_interview",
                "condition": "success",
                "priority": 0,
            },
            {
                "source_step_key": "wait_for_interview",
                "target_step_key": "notify",
                "condition": "input_available",
                "priority": 0,
                "config": {"input": "interview_answers"},
            },
        ],
    }


def test_workflow_crud_with_agent_tool_and_routes(client: TestClient) -> None:
    token = register(client, "workflow-crud@example.com")
    agent = create_agent(client, token, "cv_ai")
    tool = create_tool(client, token)

    created = client.post(
        "/api/workflows",
        headers=headers(token),
        json=workflow_payload(agent["id"], tool["id"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Recruitment Workflow"
    assert [item["step_key"] for item in body["steps"]] == [
        "extract_cv", "wait_for_interview", "notify"
    ]
    assert body["steps"][0]["agent_id"] == agent["id"]
    assert body["steps"][2]["http_tool_id"] == tool["id"]
    assert body["routes"][1]["condition"] == "input_available"

    listed = client.get("/api/workflows", headers=headers(token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]

    updated_payload = workflow_payload(agent["id"], tool["id"])
    updated_payload["steps"].append({
        "step_key": "calculate",
        "name": "Calculate score",
        "step_type": "system_tool",
        "position": 3,
        "system_tool_name": "calculator",
    })
    updated_payload["routes"].append({
        "source_step_key": "notify",
        "target_step_key": "calculate",
        "condition": "success",
    })
    updated = client.patch(
        f"/api/workflows/{body['id']}",
        headers=headers(token),
        json={
            "name": "Recruitment Review Workflow",
            "steps": updated_payload["steps"],
            "routes": updated_payload["routes"],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Recruitment Review Workflow"
    assert updated.json()["steps"][-1]["system_tool_name"] == "calculator"

    deleted = client.delete(f"/api/workflows/{body['id']}", headers=headers(token))
    assert deleted.status_code == 204
    assert client.get(f"/api/workflows/{body['id']}", headers=headers(token)).status_code == 404


def test_workflow_rejects_cross_tenant_resources(client: TestClient) -> None:
    owner_token = register(client, "workflow-owner@example.com", "Owner")
    other_token = register(client, "workflow-other@example.com", "Other")
    foreign_agent = create_agent(client, other_token, "foreign_agent")
    owner_tool = create_tool(client, owner_token)

    response = client.post(
        "/api/workflows",
        headers=headers(owner_token),
        json=workflow_payload(foreign_agent["id"], owner_tool["id"]),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "One or more workflow agents were not found"


def test_workflow_is_tenant_isolated(client: TestClient) -> None:
    first_token = register(client, "workflow-first@example.com", "First")
    second_token = register(client, "workflow-second@example.com", "Second")
    agent = create_agent(client, first_token, "cv_ai")
    tool = create_tool(client, first_token)
    workflow = client.post(
        "/api/workflows",
        headers=headers(first_token),
        json=workflow_payload(agent["id"], tool["id"]),
    ).json()

    assert client.get(
        f"/api/workflows/{workflow['id']}", headers=headers(second_token)
    ).status_code == 404
    assert client.patch(
        f"/api/workflows/{workflow['id']}",
        headers=headers(second_token),
        json={"name": "stolen"},
    ).status_code == 404
    assert client.delete(
        f"/api/workflows/{workflow['id']}", headers=headers(second_token)
    ).status_code == 404


def test_workflow_rejects_cycles_and_invalid_updates(client: TestClient) -> None:
    token = register(client, "workflow-cycle@example.com")
    agent = create_agent(client, token, "cv_ai")
    tool = create_tool(client, token)
    payload = workflow_payload(agent["id"], tool["id"])
    payload["routes"].append({
        "source_step_key": "notify",
        "target_step_key": "extract_cv",
        "condition": "success",
    })

    cycle = client.post("/api/workflows", headers=headers(token), json=payload)
    assert cycle.status_code == 400
    assert cycle.json()["detail"] == "Workflow routes must not contain cycles"

    valid_payload = workflow_payload(agent["id"], tool["id"])
    workflow = client.post(
        "/api/workflows", headers=headers(token), json=valid_payload
    ).json()
    incomplete_update = client.patch(
        f"/api/workflows/{workflow['id']}",
        headers=headers(token),
        json={"steps": valid_payload["steps"]},
    )
    assert incomplete_update.status_code == 422
