from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_llm_client
from app.core.prompts import build_effective_system_prompt
from app.main import app
from app.models import Agent
from tests.test_phase1 import auth_headers, register
from tests.test_phase2_initial import FakeLLMClient, create_conversation


def create_skill(client: TestClient, token: str, **overrides) -> dict:
    payload = {
        "name": "structured_answer",
        "description": "Return a structured answer",
        "instructions": "Only use facts present in the input.",
        "output_schema": {"answer": "string"},
        "required_system_tools": [],
        "required_tool_ids": [],
        "is_active": True,
        **overrides,
    }
    response = client.post("/api/skills", headers=auth_headers(token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_skill_crud_and_tenant_isolation(client: TestClient) -> None:
    token_a = register(client, email="skill-a@example.com", tenant_name="Tenant A")
    skill = create_skill(client, token_a)
    token_b = register(client, email="skill-b@example.com", tenant_name="Tenant B")

    assert client.get("/api/skills", headers=auth_headers(token_b)).json() == []
    assert client.get(f"/api/skills/{skill['id']}", headers=auth_headers(token_b)).status_code == 404

    updated = client.patch(
        f"/api/skills/{skill['id']}",
        headers=auth_headers(token_a),
        json={"description": "Updated description", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated description"
    assert updated.json()["is_active"] is False

    deleted = client.delete(f"/api/skills/{skill['id']}", headers=auth_headers(token_a))
    assert deleted.status_code == 204


def test_agent_skill_assignment_order_and_prompt(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    token = register(client, email="skill-prompt@example.com")
    first = create_skill(client, token, name="first_skill", instructions="FIRST INSTRUCTION", output_schema=None)
    second = create_skill(client, token, name="second_skill", instructions="SECOND INSTRUCTION")
    response = client.post(
        "/api/agents",
        headers=auth_headers(token),
        json={
            "name": "Skilled Agent",
            "system_prompt": "BASE INSTRUCTION",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.2,
            "system_tools": [],
            "tool_ids": [],
            "skill_ids": [second["id"], first["id"]],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["skill_ids"] == [second["id"], first["id"]]

    with db_session_factory() as db:
        agent = db.get(Agent, UUID(response.json()["id"]))
        assert agent is not None
        prompt = build_effective_system_prompt(agent, "PLATFORM INSTRUCTION")
        assert prompt.index("BASE INSTRUCTION") < prompt.index("SECOND INSTRUCTION") < prompt.index("FIRST INSTRUCTION")
        assert '"answer": "string"' in prompt


def test_skill_requirements_must_be_granted_to_agent(client: TestClient) -> None:
    token = register(client, email="skill-tools@example.com")
    tool_response = client.post(
        "/api/tools",
        headers=auth_headers(token),
        json={
            "name": "book_finder",
            "description": "Find books",
            "url": "https://openlibrary.org/search.json",
            "method": "GET",
            "parameters": [{"name": "q", "type": "string", "description": "Query", "required": True}],
        },
    )
    assert tool_response.status_code == 201
    tool_id = tool_response.json()["id"]
    skill = create_skill(
        client,
        token,
        name="book_research",
        required_system_tools=["calculator"],
        required_tool_ids=[tool_id],
    )

    missing = client.post(
        "/api/agents",
        headers=auth_headers(token),
        json={
            "name": "Missing Tools",
            "system_prompt": "Test",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.7,
            "system_tools": [],
            "tool_ids": [],
            "skill_ids": [skill["id"]],
        },
    )
    assert missing.status_code == 400
    assert "book_finder" in missing.json()["detail"]
    assert "calculator" in missing.json()["detail"]

    valid = client.post(
        "/api/agents",
        headers=auth_headers(token),
        json={
            "name": "Complete Agent",
            "system_prompt": "Test",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.7,
            "system_tools": ["calculator"],
            "tool_ids": [tool_id],
            "skill_ids": [skill["id"]],
        },
    )
    assert valid.status_code == 201, valid.text


def test_other_tenant_skill_cannot_be_assigned(client: TestClient) -> None:
    token_a = register(client, email="skill-owner@example.com")
    skill = create_skill(client, token_a)
    token_b = register(client, email="skill-thief@example.com")
    response = client.post(
        "/api/agents",
        headers=auth_headers(token_b),
        json={
            "name": "Invalid Agent",
            "system_prompt": "Test",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.7,
            "skill_ids": [skill["id"]],
        },
    )
    assert response.status_code == 400


def test_assistant_message_records_active_skill_names(client: TestClient) -> None:
    token = register(client, email="skill-message@example.com")
    skill = create_skill(client, token, name="book_summary")
    agent_response = client.post(
        "/api/agents",
        headers=auth_headers(token),
        json={
            "name": "Skill Message Agent",
            "system_prompt": "Test",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.7,
            "skill_ids": [skill["id"]],
        },
    )
    assert agent_response.status_code == 201
    conversation = create_conversation(client, token, agent_response.json()["id"])
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(used_skills=["book_summary"])
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
        json={"content": "Use the skill"},
    )
    assert response.status_code == 200
    assert response.json()["used_skills"] == ["book_summary"]
