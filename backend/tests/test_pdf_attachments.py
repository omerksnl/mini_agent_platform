from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.core.services.llm_service import LLMResult
from app.main import app
from app.models import Agent, Attachment
from tests.test_phase1 import auth_headers, register
from tests.test_phase2_initial import create_conversation


@dataclass
class AttachmentAwareLLM:
    calls: list[dict] = field(default_factory=list)

    def complete(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        http_tools: list | None = None,
        attachments: list[Attachment] | None = None,
        db=None,
    ) -> LLMResult:
        self.calls.append({
            "messages": messages,
            "attachment_ids": [str(item.id) for item in attachments or []],
        })
        return LLMResult(
            content='{"full_name":"Test Candidate"}',
            used_tools=["pdf_to_text"],
            used_skills=["cv_extraction"],
        )


def create_pdf_agent(client: TestClient, token: str) -> dict:
    response = client.post("/api/agents", headers=auth_headers(token), json={
        "name": "CV Extraction Agent",
        "system_prompt": "Extract CV data.",
        "model": "anthropic/claude-haiku-4.5",
        "temperature": 0,
        "system_tools": ["pdf_to_text"],
    })
    assert response.status_code == 201
    return response.json()


def upload_pdf(client: TestClient, token: str, name: str = "candidate.pdf") -> dict:
    response = client.post(
        "/api/attachments",
        headers=auth_headers(token),
        files={"file": (name, b"%PDF-1.4\n% test", "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_pdf_attachment_is_linked_to_chat_message(client: TestClient) -> None:
    token = register(client, email="pdf@example.com")
    agent = create_pdf_agent(client, token)
    conversation = create_conversation(client, token, agent["id"])
    attachment = upload_pdf(client, token)
    fake = AttachmentAwareLLM()
    app.dependency_overrides[get_llm_client] = lambda: fake

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth_headers(token),
        json={"content": "Extract the CandidateProfile", "attachment_ids": [attachment["id"]]},
    )

    assert response.status_code == 200
    assert fake.calls[0]["attachment_ids"] == [attachment["id"]]
    messages = client.get(
        f"/api/conversations/{conversation['id']}/messages", headers=auth_headers(token)
    ).json()
    assert messages[0]["attachments"][0]["original_name"] == "candidate.pdf"
    assert messages[1]["used_tools"] == ["pdf_to_text"]
    assert messages[1]["used_skills"] == ["cv_extraction"]


def test_attachment_cannot_cross_tenants(client: TestClient) -> None:
    token_a = register(client, email="pdf-a@example.com", tenant_name="A")
    attachment = upload_pdf(client, token_a)
    token_b = register(client, email="pdf-b@example.com", tenant_name="B")
    agent_b = create_pdf_agent(client, token_b)
    conversation_b = create_conversation(client, token_b, agent_b["id"])
    app.dependency_overrides[get_llm_client] = lambda: AttachmentAwareLLM()

    response = client.post(
        f"/api/conversations/{conversation_b['id']}/messages",
        headers=auth_headers(token_b),
        json={"content": "Read this", "attachment_ids": [attachment["id"]]},
    )

    assert response.status_code == 404


def test_upload_rejects_non_pdf(client: TestClient) -> None:
    token = register(client, email="not-pdf@example.com")
    response = client.post(
        "/api/attachments",
        headers=auth_headers(token),
        files={"file": ("candidate.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400
