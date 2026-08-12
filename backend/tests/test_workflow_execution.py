from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.core.services.llm_service import LLMResult
from app.main import app


class FakeWorkflowLLM:
    def complete(self, agent, messages, http_tools=None, attachments=None, db=None):
        return LLMResult(
            content=f"processed by {agent.name}",
            used_tools=[],
            used_skills=[],
            used_agents=[],
            api_cost_usd=0.0125,
        )


def register(client: TestClient, email: str, tenant: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "password123",
        "full_name": "Workflow Runner",
        "tenant_name": tenant,
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_agent(client: TestClient, token: str, name: str) -> dict:
    response = client.post("/api/agents", headers=headers(token), json={"name": name})
    assert response.status_code == 201
    return response.json()


def create_execution_workflow(client: TestClient, token: str, agent_id: str) -> dict:
    response = client.post("/api/workflows", headers=headers(token), json={
        "name": "Candidate pipeline",
        "steps": [
            {"step_key": "extract", "name": "Extract", "step_type": "agent", "position": 0, "agent_id": agent_id},
            {"step_key": "approval", "name": "Approval", "step_type": "human_wait", "position": 1, "config": {"required_input": "approval"}},
            {"step_key": "calculate", "name": "Calculate", "step_type": "system_tool", "position": 2, "system_tool_name": "calculator", "config": {"arguments": {"expression": "6 * 7"}}},
        ],
        "routes": [
            {"source_step_key": "extract", "target_step_key": "approval", "condition": "success"},
            {"source_step_key": "approval", "target_step_key": "calculate", "condition": "input_available"},
        ],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_workflow_runs_until_human_wait_and_resumes(client: TestClient) -> None:
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "runner@example.com", "Runner Tenant")
    agent = create_agent(client, token, "cv_ai")
    workflow = create_execution_workflow(client, token, agent["id"])

    started = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(token),
        json={"input_data": {"request": "Process this candidate"}},
    )
    assert started.status_code == 201, started.text
    run = started.json()
    assert run["status"] == "waiting"
    assert [item["status"] for item in run["step_runs"]] == ["completed", "waiting"]
    assert run["step_runs"][0]["output_data"]["content"] == "processed by cv_ai"
    assert run["total_api_cost_usd"] == 0.0125

    resumed = client.post(
        f"/api/workflows/runs/{run['id']}/resume",
        headers=headers(token),
        json={"input_data": {"approved": True}},
    )
    assert resumed.status_code == 200, resumed.text
    completed = resumed.json()
    assert completed["status"] == "completed"
    assert completed["current_step_id"] is None
    assert completed["step_runs"][-1]["output_data"] == {"result": "42"}
    assert completed["output_data"]["steps"]["approval"] == {"human_input": {"approved": True}}


def test_failed_step_is_persisted(client: TestClient) -> None:
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "failed-run@example.com", "Failed Tenant")
    workflow = client.post("/api/workflows", headers=headers(token), json={
        "name": "Broken calculation",
        "steps": [{"step_key": "calculate", "name": "Calculate", "step_type": "system_tool", "position": 0, "system_tool_name": "calculator"}],
    }).json()
    response = client.post(
        f"/api/workflows/{workflow['id']}/runs", headers=headers(token), json={"input_data": {}}
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "failed"
    assert run["step_runs"][0]["status"] == "failed"
    assert run["error"]


def test_workflow_runs_are_tenant_isolated(client: TestClient) -> None:
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    owner = register(client, "run-owner@example.com", "Run Owner")
    other = register(client, "run-other@example.com", "Run Other")
    agent = create_agent(client, owner, "owner_agent")
    workflow = create_execution_workflow(client, owner, agent["id"])
    run = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(owner), json={"input_data": {"request": "test"}},
    ).json()

    assert client.get(f"/api/workflows/runs/{run['id']}", headers=headers(other)).status_code == 404
    assert client.post(
        f"/api/workflows/runs/{run['id']}/resume",
        headers=headers(other), json={"input_data": {"approved": True}},
    ).status_code == 404
    assert client.get(f"/api/workflows/{workflow['id']}/runs", headers=headers(other)).status_code == 404
