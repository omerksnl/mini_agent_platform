from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.core.services.llm_service import LLMResult, OpenRouterLLMClient, RouterAgentDecision
from app.models import Agent


def register(client: TestClient, email: str, tenant: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email, "password": "password123", "full_name": "Router Tester", "tenant_name": tenant,
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_agent(client: TestClient, token: str, name: str, **extra) -> dict:
    response = client.post("/api/agents", headers=headers(token), json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_router_targets_normal_agents_and_is_tenant_isolated(client: TestClient) -> None:
    owner = register(client, "router-owner@example.com", "Router Tenant")
    outsider = register(client, "router-outsider@example.com", "Other Tenant")
    movie = create_agent(client, owner, "movie_series_agent")
    cooking = create_agent(client, owner, "cooking_agent")
    foreign = create_agent(client, outsider, "foreign_agent")

    router = create_agent(
        client, owner, "free_time_router", agent_type="router",
        router_target_ids=[movie["id"], cooking["id"]],
    )
    assert router["agent_type"] == "router"
    assert set(router["router_target_ids"]) == {movie["id"], cooking["id"]}

    refreshed_movie = client.get(f"/api/agents/{movie['id']}", headers=headers(owner)).json()
    assert refreshed_movie["router_ids"] == [router["id"]]

    invalid = client.patch(
        f"/api/agents/{router['id']}", headers=headers(owner),
        json={"router_target_ids": [foreign["id"]]},
    )
    assert invalid.status_code == 404


def test_router_selects_exactly_one_agent(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    token = register(client, "router-selection@example.com", "Selection Tenant")
    movie = create_agent(client, token, "movie_series_agent", system_prompt="Recommend movies and series.")
    cooking = create_agent(client, token, "cooking_agent", system_prompt="Recommend recipes.")
    router_data = create_agent(
        client, token, "free_time_router", agent_type="router",
        router_target_ids=[movie["id"], cooking["id"]],
    )
    db = db_session_factory()
    try:
        router = db.scalar(select(Agent).where(Agent.id == UUID(router_data["id"])))

        class Selector:
            received_messages = None

            def invoke(self, messages, config=None):
                Selector.received_messages = messages
                return RouterAgentDecision(target_agent_id=movie["id"])

        class Model:
            def with_structured_output(self, _schema):
                return Selector()

        class RecordingClient(OpenRouterLLMClient):
            def __init__(self) -> None:
                self.settings = get_settings()
                self.called: list[str] = []

            def complete(self, agent, messages, http_tools=None, attachments=None, db=None, **kwargs):
                self.called.append(agent.name)
                return LLMResult(content="Watch Arrival.", used_tools=[], api_cost_usd=0.004)

        llm = RecordingClient()
        result = llm._complete_router(
            router, Model(), [{"role": "user", "content": "I want a science-fiction movie"}],
            [], db, SimpleNamespace(total_cost_usd=0.001), [], {},
        )
        assert llm.called == ["movie_series_agent"]
        assert result.content == "Watch Arrival."
        assert result.used_agents == ["movie_series_agent"]
        assert result.api_cost_usd == 0.005
        assert "RECENT CONVERSATION" in Selector.received_messages[-1].content
        assert "I want a science-fiction movie" in Selector.received_messages[-1].content
    finally:
        db.close()
