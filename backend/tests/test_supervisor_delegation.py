from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_llm_client
from app.config import get_settings
from app.core.services.llm_service import LLMResult, OpenRouterLLMClient, RoutingDecision
from app.core.tools.supervisor_tools import build_delegation_tools
from app.main import app
from app.models import Agent


def register(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email, "password": "password123", "full_name": "Test", "tenant_name": "Team",
    })
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_agent(client: TestClient, token: str, payload: dict) -> dict:
    response = client.post("/api/agents", headers=headers(token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_delegation_tools_wrap_managed_agents(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    token = register(client, "delegation-tools@example.com")
    child = create_agent(client, token, {"name": "CV Agent"})
    supervisor_data = create_agent(client, token, {
        "name": "Recruitment Supervisor",
        "agent_type": "supervisor",
        "managed_agent_ids": [child["id"]],
    })
    db = db_session_factory()
    try:
        supervisor = db.scalar(select(Agent).where(Agent.id == UUID(supervisor_data["id"])))
        calls: list[tuple[str, str]] = []
        tools = build_delegation_tools(
            supervisor,
            lambda agent, task: calls.append((agent.name, task)) or "candidate profile",
        )
        assert len(tools) == 1
        assert tools[0].name.startswith("delegate_to_cv_agent_")
        assert tools[0].invoke({"task": "Extract this CV"}) == "candidate profile"
        assert calls == [("CV Agent", "Extract this CV")]
    finally:
        db.close()


def test_conversation_passes_database_context_to_supervisor(client: TestClient) -> None:
    token = register(client, "supervisor-chat@example.com")
    child = create_agent(client, token, {"name": "child"})
    supervisor = create_agent(client, token, {
        "name": "supervisor", "agent_type": "supervisor", "managed_agent_ids": [child["id"]],
    })
    conversation = client.post("/api/conversations", headers=headers(token), json={
        "agent_id": supervisor["id"], "title": "Delegation",
    }).json()

    class FakeSupervisorClient:
        def complete(self, agent, messages, http_tools=None, attachments=None, db=None):
            assert agent.agent_type == "supervisor"
            assert db is not None
            return LLMResult(content="delegated response", used_tools=[])

    app.dependency_overrides[get_llm_client] = lambda: FakeSupervisorClient()
    try:
        response = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            headers=headers(token), json={"content": "Delegate this task"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "delegated response"
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


def test_supervisor_forwards_attachments_only_to_pdf_capable_child(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    token = register(client, "attachment-delegation@example.com")
    child = create_agent(client, token, {"name": "cv_ai", "system_tools": ["pdf_to_text"]})
    supervisor_data = create_agent(client, token, {
        "name": "supervisor", "agent_type": "supervisor", "managed_agent_ids": [child["id"]],
    })
    db = db_session_factory()
    try:
        supervisor = db.scalar(select(Agent).where(Agent.id == UUID(supervisor_data["id"])))
        attachment = SimpleNamespace(id="attachment-id", original_name="cv.pdf", content_type="application/pdf")

        class RecordingClient(OpenRouterLLMClient):
            def __init__(self) -> None:
                self.settings = get_settings()
                self.forwarded = None

            def complete(self, agent, messages, http_tools=None, attachments=None, db=None):
                if agent.agent_type == "normal":
                    self.forwarded = attachments
                    return LLMResult(content="profile json", used_tools=["pdf_to_text"])
                return super().complete(agent, messages, http_tools, attachments, db)

        llm = RecordingClient()
        llm._route_request = lambda *args, **kwargs: RoutingDecision(request_parts=["process"], required_tool_names=[])

        def invoke(_model, tools, _prompt, _messages, _callback):
            delegation = next(tool for tool in tools if tool.name.startswith("delegate_to_"))
            result = delegation.invoke({"task": "Extract CandidateProfile"})
            return [AIMessage(content=result)]

        llm._invoke_agent = invoke
        result = llm.complete(supervisor, [{"role": "user", "content": "Process CV"}], attachments=[attachment], db=db)
        assert result.content == "profile json"
        assert llm.forwarded == [attachment]
    finally:
        db.close()
