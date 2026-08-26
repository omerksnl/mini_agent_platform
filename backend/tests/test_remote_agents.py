import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from uuid import uuid4

from app.core.security import create_access_token, hash_password
from app.core.services.remote_agent_service import RemoteAgentService
from app.models import User


def register(client: TestClient, email: str, tenant_name: str) -> dict[str, str]:
    response = client.post("/api/auth/register", json={
        "email": email, "password": "test-password", "full_name": "Remote Tester", "tenant_name": tenant_name,
    })
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def card() -> dict:
    return {
        "name": "External Helper",
        "description": "Handles delegated external tasks.",
        "supportedInterfaces": [{
            "url": "https://agent.example.com/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
        }],
        "skills": [{"id": "helper", "name": "Helper", "description": "Helps", "tags": ["help"]}],
    }


def test_remote_connection_is_tenant_isolated_and_hides_api_key(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(RemoteAgentService, "_fetch_card", lambda self, url: card())
    owner = register(client, "remote-owner@example.com", "Remote Owner")
    outsider = register(client, "remote-outsider@example.com", "Remote Outsider")
    created = client.post("/api/remote-agents", headers=owner, json={
        "agent_card_url": "https://agent.example.com/.well-known/agent-card.json",
        "api_key": "a2a_private_test_key",
    })
    assert created.status_code == 201
    assert created.json()["name"] == "External Helper"
    assert "api_key" not in created.text
    assert "encrypted" not in created.text
    remote_id = created.json()["id"]

    assert len(client.get("/api/remote-agents", headers=owner).json()) == 1
    assert client.get("/api/remote-agents", headers=outsider).json() == []
    assert client.delete(f"/api/remote-agents/{remote_id}", headers=outsider).status_code == 404


def test_remote_connections_are_private_between_users_in_same_tenant(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(RemoteAgentService, "_fetch_card", lambda self, url: card())
    owner = register(client, "remote-private-owner@example.com", "Shared Remote Tenant")

    with db_session_factory() as db:
        first_user = db.scalar(select(User).where(User.email == "remote-private-owner@example.com"))
        assert first_user is not None
        colleague = User(
            id=uuid4(),
            tenant_id=first_user.tenant_id,
            email="remote-private-colleague@example.com",
            hashed_password=hash_password("test-password"),
            full_name="Remote Colleague",
        )
        db.add(colleague)
        db.commit()
        colleague_token = create_access_token(
            subject=str(colleague.id), tenant_id=str(colleague.tenant_id)
        )
    colleague_headers = {"Authorization": f"Bearer {colleague_token}"}

    created = client.post("/api/remote-agents", headers=owner, json={
        "agent_card_url": "https://agent.example.com/.well-known/agent-card.json",
        "api_key": "a2a_private_same_tenant_key",
    })
    assert created.status_code == 201, created.text
    remote_id = created.json()["id"]

    assert len(client.get("/api/remote-agents", headers=owner).json()) == 1
    assert client.get("/api/remote-agents", headers=colleague_headers).json() == []
    assert client.delete(f"/api/remote-agents/{remote_id}", headers=colleague_headers).status_code == 404
    assert client.post(
        f"/api/remote-agents/{remote_id}/messages",
        headers=colleague_headers,
        json={"content": "Do not allow this"},
    ).status_code == 404


def test_remote_message_uses_encrypted_key_and_returns_a2a_text(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(RemoteAgentService, "_fetch_card", lambda self, url: card())
    monkeypatch.setattr(RemoteAgentService, "_request_url", staticmethod(lambda value: value))
    owner = register(client, "remote-message@example.com", "Remote Message")
    remote = client.post("/api/remote-agents", headers=owner, json={
        "agent_card_url": "https://agent.example.com/.well-known/agent-card.json",
        "api_key": "a2a_secret_message_key",
    }).json()

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        assert url == "https://agent.example.com/a2a"
        assert headers["Authorization"] == "Bearer a2a_secret_message_key"
        assert json["params"]["message"]["parts"][0]["text"] == "Do the task"
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "jsonrpc": "2.0", "id": json["id"],
            "result": {
                "role": "agent", "contextId": "context-1", "parts": [{"text": "Task complete"}],
                "metadata": {"apiCostUsd": 0.004321},
            },
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    response = client.post(
        f"/api/remote-agents/{remote['id']}/messages", headers=owner, json={"content": "Do the task"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "content": "Task complete", "context_id": "context-1", "api_cost_usd": 0.004321,
        "billing_mode": "owner", "billed_to": "agent_owner", "provider": None,
    }


def test_remote_message_sends_tenant_pdf_as_a2a_file_part(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(RemoteAgentService, "_fetch_card", lambda self, url: card())
    monkeypatch.setattr(RemoteAgentService, "_request_url", staticmethod(lambda value: value))
    owner = register(client, "remote-pdf@example.com", "Remote PDF")
    remote = client.post("/api/remote-agents", headers=owner, json={
        "agent_card_url": "https://agent.example.com/.well-known/agent-card.json",
        "api_key": "a2a_secret_pdf_key",
    }).json()
    uploaded = client.post(
        "/api/attachments",
        headers=owner,
        files={"file": ("candidate.pdf", b"%PDF-1.4\nremote test", "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        parts = json["params"]["message"]["parts"]
        assert parts[0] == {"kind": "text", "text": "Extract this CV"}
        assert parts[1]["kind"] == "file"
        assert parts[1]["file"]["name"] == "candidate.pdf"
        assert parts[1]["file"]["mimeType"] == "application/pdf"
        assert parts[1]["file"]["bytes"] == "JVBERi0xLjQKcmVtb3RlIHRlc3Q="
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "jsonrpc": "2.0", "id": json["id"],
            "result": {"role": "agent", "parts": [{"text": "Profile extracted"}]},
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    response = client.post(
        f"/api/remote-agents/{remote['id']}/messages",
        headers=owner,
        json={"content": "Extract this CV", "attachment_ids": [uploaded.json()["id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Profile extracted"
    assert response.json()["api_cost_usd"] == 0.0
