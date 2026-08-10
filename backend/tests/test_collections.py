from uuid import uuid4

from fastapi.testclient import TestClient


def register(client: TestClient, email: str, tenant: str) -> str:
    response = client.post("/api/auth/register", json={"email": email, "password": "password123", "full_name": "Test User", "tenant_name": tenant})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_collection_crud_and_agent_assignment_are_tenant_isolated(client: TestClient) -> None:
    first = register(client, "rag-one@example.com", "RAG One")
    second = register(client, "rag-two@example.com", "RAG Two")
    created = client.post("/api/collections", headers=headers(first), json={"name": "HR Instructions", "description": "Reusable hiring policy"})
    assert created.status_code == 201
    collection_id = created.json()["id"]
    assert client.get("/api/collections", headers=headers(first)).json()[0]["name"] == "HR Instructions"
    assert client.get("/api/collections", headers=headers(second)).json() == []

    agent = client.post("/api/agents", headers=headers(first), json={"name": "HR Agent", "system_prompt": "Use sources.", "model": "anthropic/claude-haiku-4.5", "temperature": 0.2, "system_tools": [], "tool_ids": [], "skill_ids": [], "collection_ids": [collection_id]})
    assert agent.status_code == 201
    assert agent.json()["collection_ids"] == [collection_id]
    forbidden = client.post("/api/agents", headers=headers(second), json={"name": "Bad", "collection_ids": [collection_id]})
    assert forbidden.status_code == 404
    assert client.delete(f"/api/collections/{uuid4()}", headers=headers(first)).status_code == 404
