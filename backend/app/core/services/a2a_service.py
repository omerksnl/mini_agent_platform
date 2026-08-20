import hashlib
import hmac
import secrets
import base64
import binascii
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.observability import bind_trace_context
from app.core.services.agent_service import AgentError, AgentService
from app.core.services.llm_service import LLMClient, LLMError, LLMResult
from app.core.services.attachment_service import AttachmentError, AttachmentService
from app.models import Agent, Attachment, User


class A2AError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class A2AService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def publish(self, agent_id: UUID, tenant_id: UUID, description: str) -> tuple[Agent, str]:
        agent = AgentService(self.db).get_agent(agent_id, tenant_id)
        api_key = f"a2a_{secrets.token_urlsafe(32)}"
        agent.a2a_enabled = True
        agent.a2a_description = description.strip()
        agent.a2a_api_key_hash = self.hash_api_key(api_key)
        self.db.commit()
        self.db.refresh(agent)
        return agent, api_key

    def unpublish(self, agent_id: UUID, tenant_id: UUID) -> Agent:
        agent = AgentService(self.db).get_agent(agent_id, tenant_id)
        agent.a2a_enabled = False
        agent.a2a_api_key_hash = None
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def get_published(self, agent_id: UUID) -> Agent:
        agent = self.db.scalar(select(Agent).where(Agent.id == agent_id, Agent.a2a_enabled.is_(True)))
        if not agent:
            raise A2AError("Published agent not found", 404)
        return agent

    def authenticate(self, agent: Agent, api_key: str | None) -> None:
        if not api_key or not agent.a2a_api_key_hash:
            raise A2AError("A2A authentication required", 401)
        supplied_hash = self.hash_api_key(api_key)
        if not hmac.compare_digest(supplied_hash, agent.a2a_api_key_hash):
            raise A2AError("Invalid A2A API key", 401)

    def create_received_pdf(self, agent: Agent, name: str, mime_type: str, encoded: str) -> Attachment:
        if "pdf_to_text" not in agent.system_tools:
            raise A2AError("This agent does not accept PDF attachments")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise A2AError("A2A PDF attachment is not valid base64") from exc
        owner = self.db.scalar(select(User).where(User.tenant_id == agent.tenant_id).order_by(User.created_at))
        if owner is None:
            raise A2AError("Published agent has no tenant owner", 500)
        try:
            return AttachmentService(self.db).create_pdf(agent.tenant_id, owner.id, name, mime_type, data)
        except AttachmentError as exc:
            raise A2AError(exc.message, exc.status_code) from exc

    def invoke(
        self,
        agent: Agent,
        text: str,
        llm_client: LLMClient,
        attachments: list[Attachment] | None = None,
    ) -> tuple[str, float]:
        messages = [{"role": "user", "content": text}]
        try:
            with bind_trace_context(
                workflow_run_id=uuid4(),
                workflow_name=f"a2a:{agent.name}",
                tenant_id=agent.tenant_id,
            ):
                needs_db = bool(
                    agent.collections
                    or agent.agent_type in {"supervisor", "router"}
                    or "text_to_pdf" in agent.system_tools
                    or attachments
                )
                result = llm_client.complete(
                    agent,
                    messages,
                    agent.http_tools,
                    attachments=attachments,
                    db=self.db if needs_db else None,
                )
        except LLMError as exc:
            raise A2AError(str(exc), 502) from exc
        if isinstance(result, LLMResult):
            return result.content, result.api_cost_usd
        return str(result), 0.0
