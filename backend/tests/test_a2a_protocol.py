from fastapi.testclient import TestClient
import base64
from sqlalchemy import select

from app.api.deps import get_llm_client, get_platform_llm_client
from app.core.security import create_a2a_billing_token
from app.core.services.llm_service import LLMResult, OpenRouterLLMClient
from app.main import app
from app.models import ProviderCredential, User


def register(client: TestClient, email: str, tenant_name: str) -> dict[str, str]:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "test-password",
        "full_name": "A2A Tester",
        "tenant_name": tenant_name,
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_agent(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/api/agents", headers=headers, json={
        "name": "Public Research Agent",
        "system_prompt": "Answer research questions briefly.",
        "system_tools": [],
    })
    assert response.status_code == 201
    return response.json()


class FakeLLMClient:
    def complete(self, agent, messages, http_tools=None, attachments=None, db=None, **kwargs):
        assert agent.name == "Public Research Agent"
        assert messages == [{"role": "user", "content": "Explain A2A briefly"}]
        return LLMResult(
            content="A2A lets independent agents exchange tasks.",
            used_tools=[],
            api_cost_usd=0.001,
        )


def test_published_agent_exposes_card_and_accepts_authenticated_message(client: TestClient) -> None:
    owner = register(client, "a2a-owner@example.com", "A2A Owner")
    agent = create_agent(client, owner)

    unpublished = client.get(f"/a2a/agents/{agent['id']}/.well-known/agent-card.json")
    assert unpublished.status_code == 404

    published = client.post(
        f"/api/agents/{agent['id']}/a2a/publish",
        headers=owner,
        json={"description": "Answers short research questions."},
    )
    assert published.status_code == 200
    api_key = published.json()["api_key"]
    assert api_key.startswith("a2a_")

    card = client.get(published.json()["agent_card_url"])
    assert card.status_code == 200
    assert card.json()["name"] == "Public Research Agent"
    assert card.json()["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
    assert "system_prompt" not in card.text
    assert "tenant" not in card.text.lower()

    payload = {
        "jsonrpc": "2.0",
        "id": "request-1",
        "method": "SendMessage",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": "message-1",
                "parts": [{"kind": "text", "text": "Explain A2A briefly"}],
            }
        },
    }
    assert client.post(published.json()["endpoint_url"], json=payload).status_code == 401

    app.dependency_overrides[get_platform_llm_client] = lambda: FakeLLMClient()
    try:
        response = client.post(
            published.json()["endpoint_url"],
            headers={"Authorization": f"Bearer {api_key}", "A2A-Version": "1.0"},
            json=payload,
        )
    finally:
        app.dependency_overrides.pop(get_platform_llm_client, None)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "request-1"
    assert body["result"]["role"] == "agent"
    assert body["result"]["parts"][0]["text"] == "A2A lets independent agents exchange tasks."
    assert body["result"]["metadata"]["apiCostUsd"] == 0.001


def test_a2a_key_rotation_and_unpublish_invalidate_previous_access(client: TestClient) -> None:
    owner = register(client, "a2a-rotate@example.com", "A2A Rotate")
    agent = create_agent(client, owner)
    first = client.post(
        f"/api/agents/{agent['id']}/a2a/publish", headers=owner, json={"description": "First"}
    ).json()
    second = client.post(
        f"/api/agents/{agent['id']}/a2a/publish", headers=owner, json={"description": "Second"}
    ).json()
    assert first["api_key"] != second["api_key"]

    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
        "params": {"message": {"role": "user", "parts": [{"text": "hello"}]}},
    }
    assert client.post(
        second["endpoint_url"], headers={"Authorization": f"Bearer {first['api_key']}"}, json=payload
    ).status_code == 401

    disabled = client.delete(f"/api/agents/{agent['id']}/a2a/publish", headers=owner)
    assert disabled.status_code == 200
    assert disabled.json()["a2a_enabled"] is False
    assert client.get(second["agent_card_url"]).status_code == 404


def test_published_pdf_agent_receives_a2a_file_as_attachment(client: TestClient) -> None:
    owner = register(client, "a2a-pdf@example.com", "A2A PDF")
    created = client.post("/api/agents", headers=owner, json={
        "name": "PDF Extractor",
        "system_prompt": "Extract PDFs.",
        "system_tools": ["pdf_to_text"],
    })
    assert created.status_code == 201, created.text
    published = client.post(
        f"/api/agents/{created.json()['id']}/a2a/publish",
        headers=owner,
        json={"description": "Extracts PDF documents."},
    ).json()
    assert "application/pdf" in client.get(published["agent_card_url"]).json()["defaultInputModes"]

    class PdfLLM:
        def complete(self, agent, messages, http_tools=None, attachments=None, db=None, **kwargs):
            assert messages == [{"role": "user", "content": "Extract this CV"}]
            assert len(attachments) == 1
            assert attachments[0].original_name == "candidate.pdf"
            return LLMResult(content="CandidateProfile created", used_tools=["pdf_to_text"], api_cost_usd=0.001)

    payload = {
        "jsonrpc": "2.0", "id": "pdf-request", "method": "SendMessage",
        "params": {"message": {"role": "user", "parts": [
            {"kind": "text", "text": "Extract this CV"},
            {"kind": "file", "file": {
                "name": "candidate.pdf", "mimeType": "application/pdf",
                "bytes": base64.b64encode(b"%PDF-1.4\na2a inbound").decode("ascii"),
            }},
        ]}},
    }
    app.dependency_overrides[get_platform_llm_client] = lambda: PdfLLM()
    try:
        response = client.post(
            published["endpoint_url"],
            headers={"Authorization": f"Bearer {published['api_key']}"},
            json=payload,
        )
    finally:
        app.dependency_overrides.pop(get_platform_llm_client, None)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["parts"][0]["text"] == "CandidateProfile created"


def test_published_agent_can_bill_the_callers_saved_provider_profile(
    client: TestClient, db_session_factory, monkeypatch
) -> None:
    owner = register(client, "a2a-byok-owner@example.com", "A2A BYOK Owner")
    caller = register(client, "a2a-byok-caller@example.com", "A2A BYOK Caller")
    agent = create_agent(client, owner)
    published = client.post(
        f"/api/agents/{agent['id']}/a2a/publish",
        headers=owner,
        json={"description": "Uses the caller's provider profile."},
    ).json()
    saved = client.put("/api/provider-settings", headers=caller, json={
        "name": "Caller OpenAI",
        "provider": "openai",
        "api_key": "sk-caller-a2a-key-that-never-leaves-the-server-123456",
    })
    assert saved.status_code == 200, saved.text

    db = db_session_factory()
    try:
        caller_user = db.scalar(select(User).where(User.email == "a2a-byok-caller@example.com"))
        profile = db.scalar(select(ProviderCredential).where(ProviderCredential.user_id == caller_user.id))
        caller_id = str(caller_user.id)
        profile_id = str(profile.id)
    finally:
        db.close()

    def fake_complete(self, agent, messages, http_tools=None, **kwargs):
        assert self.credentials.provider == "openai"
        assert self.credentials.api_key == "sk-caller-a2a-key-that-never-leaves-the-server-123456"
        return LLMResult(content="Caller-paid result", used_tools=[], api_cost_usd=0.0042)

    monkeypatch.setattr(OpenRouterLLMClient, "complete", fake_complete)
    billing_token = create_a2a_billing_token(
        user_id=caller_id,
        credential_id=profile_id,
        agent_id=agent["id"],
    )
    payload = {
        "jsonrpc": "2.0", "id": "byok-request", "method": "SendMessage",
        "params": {"message": {"role": "user", "parts": [{"text": "Use my provider"}]}},
    }
    response = client.post(
        published["endpoint_url"],
        headers={
            "Authorization": f"Bearer {published['api_key']}",
            "X-A2A-Billing-Token": billing_token,
        },
        json=payload,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["parts"][0]["text"] == "Caller-paid result"
    assert result["metadata"] == {
        "apiCostUsd": 0.0042,
        "billingMode": "caller",
        "billedTo": "caller",
        "provider": "openai",
    }
