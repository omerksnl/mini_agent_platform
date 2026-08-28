from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_platform_llm_client
from app.core.services.a2a_service import A2AError, A2AService
from app.core.services.llm_service import LLMClient
from app.db.session import get_db
from app.schemas.a2a import A2AFilePart, A2AJsonRpcRequest, A2ATextPart


router = APIRouter(prefix="/a2a/agents", tags=["a2a"])


def _raise_a2a_error(exc: A2AError) -> None:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    raise HTTPException(status_code=exc.status_code, detail=exc.message, headers=headers) from exc


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


@router.get("/{agent_id}/.well-known/agent-card.json")
def get_agent_card(
    agent_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    try:
        agent = A2AService(db).get_published(agent_id)
    except A2AError as exc:
        _raise_a2a_error(exc)
    endpoint = f"{str(request.base_url).rstrip('/')}/a2a/agents/{agent.id}"
    advertised_skills = [
        {
            "id": str(skill.id),
            "name": skill.name,
            "description": skill.description,
            "tags": [skill.name.lower().replace(" ", "-")],
        }
        for skill in agent.skills
    ]
    if not advertised_skills:
        advertised_skills = [{
            "id": f"agent-{agent.id}",
            "name": agent.name,
            "description": agent.a2a_description or "General AI agent capability",
            "tags": [agent.agent_type, "assistant"],
        }]
    return {
        "name": agent.name,
        "description": agent.a2a_description or f"A2A endpoint for {agent.name}",
        "supportedInterfaces": [{
            "url": endpoint,
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }],
        "provider": {
            "organization": "Mini Agent Platform",
            "url": str(request.base_url).rstrip("/"),
        },
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "securitySchemes": {
            "bearerAuth": {
                "httpAuthSecurityScheme": {
                    "scheme": "Bearer",
                    "description": "Agent-specific A2A API key",
                }
            }
        },
        "securityRequirements": [{"schemes": {"bearerAuth": {"list": []}}}],
        "defaultInputModes": ["text/plain"] + (["application/pdf"] if "pdf_to_text" in agent.system_tools else []),
        "defaultOutputModes": ["text/plain"],
        "skills": advertised_skills,
    }


@router.post("/{agent_id}")
def send_a2a_message(
    agent_id: UUID,
    payload: A2AJsonRpcRequest,
    authorization: str | None = Header(default=None),
    a2a_version: str | None = Header(default=None, alias="A2A-Version"),
    billing_token: str | None = Header(default=None, alias="X-A2A-Billing-Token"),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_platform_llm_client),
) -> dict:
    request_id = payload.id
    if a2a_version not in {None, "0.3", "1.0"}:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32009, "message": "Unsupported A2A protocol version"},
        }
    if payload.method not in {"SendMessage", "message/send"}:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
    if payload.params is None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "Message parameters are required"},
        }
    try:
        service = A2AService(db)
        agent = service.get_published(agent_id)
        service.authenticate(agent, _bearer_token(authorization))
        text = "\n".join(part.text for part in payload.params.message.parts if isinstance(part, A2ATextPart)).strip()
        attachments = [
            service.create_received_pdf(agent, part.file.name, part.file.mimeType, part.file.bytes)
            for part in payload.params.message.parts
            if isinstance(part, A2AFilePart)
        ]
        if not text:
            text = "Process the attached PDF."
        billing = service.billing_context(agent, billing_token, llm_client)
        content, api_cost, billing_metadata = service.invoke(
            agent, text, llm_client, attachments, billing
        )
    except A2AError as exc:
        _raise_a2a_error(exc)
    context_id = payload.params.message.contextId or str(uuid4())
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "kind": "message",
            "role": "agent",
            "messageId": str(uuid4()),
            "contextId": context_id,
            "parts": [{"kind": "text", "text": content}],
            "metadata": {"apiCostUsd": api_cost, **billing_metadata},
        },
    }
