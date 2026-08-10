from dataclasses import dataclass, field
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_llm_client
from app.core.security import create_access_token, hash_password
from app.core.services.llm_service import LLMError, LLMResult
from app.main import app
from app.models import Agent, User
from tests.test_phase1 import auth_headers, create_agent, register


@dataclass
class FakeLLMClient:
    response: str = "Fake assistant response"
    calls: list[dict] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)
    used_skills: list[str] = field(default_factory=list)

    def complete(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        http_tools: list | None = None,
    ) -> LLMResult:
        self.calls.append(
            {
                "model": agent.model,
                "temperature": agent.temperature,
                "system_prompt": agent.system_prompt,
                "messages": messages,
            }
        )
        return LLMResult(
            content=self.response,
            used_tools=self.used_tools,
            used_skills=self.used_skills,
        )


class FailingLLMClient:
    def complete(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        http_tools: list | None = None,
    ) -> str:
        raise LLMError("The language model request failed")


def create_conversation(client: TestClient, token: str, agent_id: str) -> dict:
    response = client.post(
        "/api/conversations",
        headers=auth_headers(token),
        json={"agent_id": agent_id, "title": "Test conversation"},
    )
    assert response.status_code == 201
    return response.json()


def test_conversation_crud_and_tenant_isolation(client: TestClient) -> None:
    tenant_a_token = register(client, email="conversation-a@example.com", tenant_name="Tenant A")
    tenant_a_agent = create_agent(client, tenant_a_token)
    conversation = create_conversation(client, tenant_a_token, tenant_a_agent["id"])
    conversation_id = conversation["id"]

    listed = client.get("/api/conversations", headers=auth_headers(tenant_a_token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [conversation_id]

    updated = client.patch(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(tenant_a_token),
        json={"title": "Updated conversation"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated conversation"

    tenant_b_token = register(client, email="conversation-b@example.com", tenant_name="Tenant B")
    tenant_b_headers = auth_headers(tenant_b_token)
    assert client.get("/api/conversations", headers=tenant_b_headers).json() == []
    assert client.get(f"/api/conversations/{conversation_id}", headers=tenant_b_headers).status_code == 404
    assert client.patch(
        f"/api/conversations/{conversation_id}",
        headers=tenant_b_headers,
        json={"title": "Stolen conversation"},
    ).status_code == 404
    assert client.delete(
        f"/api/conversations/{conversation_id}",
        headers=tenant_b_headers,
    ).status_code == 404

    deleted = client.delete(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(tenant_a_token),
    )
    assert deleted.status_code == 204


def test_single_turn_chat_uses_agent_configuration_and_saves_messages(client: TestClient) -> None:
    token = register(client, email="chat@example.com")
    agent = create_agent(client, token)
    conversation = create_conversation(client, token, agent["id"])
    fake_llm = FakeLLMClient(used_tools=["calculator"])
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
        json={"content": "Hello model"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "assistant"
    assert response.json()["content"] == "Fake assistant response"
    assert response.json()["used_tools"] == ["calculator"]
    assert response.json()["used_skills"] == []
    assert fake_llm.calls == [
        {
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.7,
            "system_prompt": "You are a test assistant.",
            "messages": [{"role": "user", "content": "Hello model"}],
        }
    ]

    messages = client.get(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
    )
    assert messages.status_code == 200
    assert [(item["role"], item["content"]) for item in messages.json()] == [
        ("user", "Hello model"),
        ("assistant", "Fake assistant response"),
    ]


def test_llm_failure_does_not_save_partial_turn(client: TestClient) -> None:
    token = register(client, email="failed-chat@example.com")
    agent = create_agent(client, token)
    conversation = create_conversation(client, token, agent["id"])
    app.dependency_overrides[get_llm_client] = lambda: FailingLLMClient()

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
        json={"content": "This request fails"},
    )

    assert response.status_code == 502
    messages = client.get(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
    )
    assert messages.json() == []


def test_short_term_memory_sends_previous_messages_in_order(client: TestClient) -> None:
    token = register(client, email="memory@example.com")
    agent = create_agent(client, token)
    conversation = create_conversation(client, token, agent["id"])
    fake_llm = FakeLLMClient(response="First answer")
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    first_response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
        json={"content": "My name is Ada"},
    )
    assert first_response.status_code == 200

    fake_llm.response = "Your name is Ada"
    second_response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
        json={"content": "What is my name?"},
    )
    assert second_response.status_code == 200
    assert fake_llm.calls[1]["messages"] == [
        {"role": "user", "content": "My name is Ada"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "What is my name?"},
    ]


def test_users_in_same_tenant_share_conversations(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    owner_token = register(client, email="conversation-owner@example.com", tenant_name="Shared Tenant")
    agent = create_agent(client, owner_token)
    conversation = create_conversation(client, owner_token, agent["id"])
    fake_llm = FakeLLMClient(response="Shared answer")
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    owner_message = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(owner_token),
        json={"content": "Shared question"},
    )
    assert owner_message.status_code == 200

    with db_session_factory() as db:
        owner = db.scalar(select(User).where(User.email == "conversation-owner@example.com"))
        assert owner is not None
        colleague = User(
            id=uuid4(),
            tenant_id=owner.tenant_id,
            email="conversation-colleague@example.com",
            hashed_password=hash_password("test-password"),
            full_name="Tenant Colleague",
        )
        db.add(colleague)
        db.commit()
        colleague_token = create_access_token(
            subject=str(colleague.id),
            tenant_id=str(colleague.tenant_id),
        )

    colleague_headers = auth_headers(colleague_token)
    listed = client.get("/api/conversations", headers=colleague_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [conversation["id"]]

    history = client.get(
        f"/api/conversations/{conversation['id']}/messages",
        headers=colleague_headers,
    )
    assert history.status_code == 200
    assert [(item["role"], item["content"]) for item in history.json()] == [
        ("user", "Shared question"),
        ("assistant", "Shared answer"),
    ]

    fake_llm.response = "Colleague answer"
    colleague_message = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=colleague_headers,
        json={"content": "Colleague question"},
    )
    assert colleague_message.status_code == 200
    assert colleague_message.json()["content"] == "Colleague answer"
