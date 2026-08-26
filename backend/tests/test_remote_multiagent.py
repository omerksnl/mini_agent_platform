import time
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.services.remote_agent_service import RemoteAgentService
from app.core.tools.remote_agent_tools import build_remote_agent_tools
from app.models import RemoteAgent


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/auth/register", json={
        "email": email, "password": "test-password", "full_name": "A2A Tester", "tenant_name": email,
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def remote_card() -> dict:
    return {
        "name": "Remote CV Specialist",
        "description": "Extracts structured CV profiles.",
        "supportedInterfaces": [{
            "url": "https://remote.example.com/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
        }],
        "skills": [{"id": "cv", "name": "CV extraction"}],
    }


def create_remote(client: TestClient, headers: dict[str, str], monkeypatch) -> dict:
    monkeypatch.setattr(RemoteAgentService, "_fetch_card", lambda self, url: remote_card())
    response = client.post("/api/remote-agents", headers=headers, json={
        "agent_card_url": "https://remote.example.com/card.json", "api_key": "a2a_test_key",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_remote_agents_can_be_assigned_to_supervisor_and_router(client: TestClient, monkeypatch) -> None:
    owner = register(client, "remote-multiagent@example.com")
    remote = create_remote(client, owner, monkeypatch)

    supervisor = client.post("/api/agents", headers=owner, json={
        "name": "External supervisor", "agent_type": "supervisor",
        "managed_remote_agent_ids": [remote["id"]],
    })
    assert supervisor.status_code == 201, supervisor.text
    assert supervisor.json()["managed_remote_agent_ids"] == [remote["id"]]

    router = client.post("/api/agents", headers=owner, json={
        "name": "External router", "agent_type": "router",
        "router_remote_agent_ids": [remote["id"]],
    })
    assert router.status_code == 201, router.text
    assert router.json()["router_remote_agent_ids"] == [remote["id"]]


def test_normal_agent_can_use_remote_agent_as_a_tool(
    client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch
) -> None:
    owner = register(client, "remote-tool-owner@example.com")
    remote = create_remote(client, owner, monkeypatch)
    local = client.post("/api/agents", headers=owner, json={
        "name": "Local coordinator", "remote_agent_ids": [remote["id"]],
    })
    assert local.status_code == 201, local.text
    assert local.json()["remote_agent_ids"] == [remote["id"]]

    with db_session_factory() as db:
        remote_model = db.scalar(select(RemoteAgent).where(RemoteAgent.id == UUID(remote["id"])))
        assert remote_model is not None
        calls: list[str] = []
        tools = build_remote_agent_tools(
            [remote_model], lambda target, task: calls.append(f"{target.name}:{task}") or "remote answer",
        )
        assert tools[0].invoke({"task": "Analyze this"}) == "remote answer"
        assert calls == ["Remote CV Specialist:Analyze this"]


def test_remote_workflow_node_executes_and_propagates_cost(client: TestClient, monkeypatch) -> None:
    owner = register(client, "remote-workflow@example.com")
    remote = create_remote(client, owner, monkeypatch)
    monkeypatch.setattr(
        RemoteAgentService, "send",
        lambda self, remote_id, tenant_id, user_id, content, attachment_ids: (
            "Remote profile result", "context-1", 0.03125, "owner", "agent_owner", None,
        ),
    )
    workflow = client.post("/api/workflows", headers=owner, json={
        "name": "Remote CV workflow",
        "steps": [{
            "step_key": "remote_cv", "name": "Remote CV", "step_type": "remote_agent",
            "position": 0, "remote_agent_id": remote["id"],
            "config": {"task_instructions": "Extract the candidate profile."},
        }],
        "routes": [],
    })
    assert workflow.status_code == 201, workflow.text
    started = client.post(
        f"/api/workflows/{workflow.json()['id']}/runs", headers=owner,
        json={"input_data": {"request": "Process this candidate"}},
    )
    assert started.status_code == 201, started.text
    run_id = started.json()["id"]
    for _ in range(200):
        run = client.get(f"/api/workflows/runs/{run_id}", headers=owner).json()
        if run["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert run["status"] == "completed", run
    assert run["total_api_cost_usd"] == 0.03125
    assert run["artifacts"][-1]["data"]["content"] == "Remote profile result"
