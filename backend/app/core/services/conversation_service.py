from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.observability import bind_trace_context
from app.core.services.agent_service import AgentService
from app.core.services.llm_service import LLMClient, LLMError, LLMResult
from app.core.services.attachment_service import AttachmentError, AttachmentService
from app.models import Conversation, Message
from app.schemas.conversation import ConversationCreate, ConversationUpdate


class ConversationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_conversations(self, tenant_id: UUID) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_conversation(self, conversation_id: UUID, tenant_id: UUID) -> Conversation:
        conversation = self.db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        if not conversation:
            raise ConversationError("Conversation not found", status_code=404)
        return conversation

    def create_conversation(self, tenant_id: UUID, payload: ConversationCreate) -> Conversation:
        AgentService(self.db).get_agent(payload.agent_id, tenant_id)
        conversation = Conversation(
            tenant_id=tenant_id,
            agent_id=payload.agent_id,
            title=payload.title,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_conversation(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        payload: ConversationUpdate,
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id, tenant_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(conversation, key, value)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete_conversation(self, conversation_id: UUID, tenant_id: UUID) -> None:
        conversation = self.get_conversation(conversation_id, tenant_id)
        self.db.delete(conversation)
        self.db.commit()

    def list_messages(self, conversation_id: UUID, tenant_id: UUID) -> list[Message]:
        self.get_conversation(conversation_id, tenant_id)
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.tenant_id == tenant_id,
            )
            .order_by(Message.created_at.asc(), Message.role.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_recent_messages(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        limit: int,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.tenant_id == tenant_id,
            )
            .order_by(Message.created_at.desc(), Message.role.asc())
            .limit(limit)
        )
        return list(reversed(self.db.scalars(stmt).all()))

    def send_message(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        content: str,
        attachment_ids: list[UUID],
        llm_client: LLMClient,
    ) -> Message:
        conversation = self.get_conversation(conversation_id, tenant_id)
        memory_limit = get_settings().short_term_memory_messages
        recent_messages = self.get_recent_messages(
            conversation.id,
            tenant_id,
            memory_limit,
        )
        llm_messages = []
        for message in recent_messages:
            message_content = message.content
            if conversation.agent.agent_type == "router" and message.role == "assistant" and message.used_agents:
                message_content = (
                    f"[ROUTING HISTORY: {', '.join(message.used_agents)}]\n"
                    + message_content
                )
            llm_messages.append({"role": message.role, "content": message_content})
        user_message = Message(
            id=uuid4(),
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=content.strip() or "Please process the attached PDF.",
        )
        self.db.add(user_message)
        try:
            attachments = AttachmentService(self.db).claim_for_message(
                attachment_ids,
                tenant_id,
                user_id,
                user_message.id,
            )
        except AttachmentError as exc:
            self.db.rollback()
            raise ConversationError(exc.message, exc.status_code) from exc

        llm_content = user_message.content
        if attachments:
            attachment_lines = "\n".join(
                f"- attachment_id={item.id}; filename={item.original_name}; type={item.content_type}"
                for item in attachments
            )
            llm_content += (
                "\n\nATTACHMENTS AVAILABLE TO TOOLS\n"
                + attachment_lines
                + "\nUse pdf_to_text before making claims about PDF contents."
            )
        llm_messages.append({"role": "user", "content": llm_content})
        try:
            with bind_trace_context(
                workflow_run_id=conversation.id,
                workflow_name=f"chat:{conversation.agent.name}",
                tenant_id=tenant_id,
            ):
                if attachments:
                    llm_result = llm_client.complete(
                        conversation.agent,
                        llm_messages,
                        conversation.agent.http_tools,
                        attachments,
                        self.db,
                    )
                else:
                    if (
                        conversation.agent.collections
                        or conversation.agent.agent_type in {"supervisor", "router"}
                        or conversation.agent.remote_agent_tools
                        or "text_to_pdf" in conversation.agent.system_tools
                    ):
                        llm_result = llm_client.complete(
                            conversation.agent,
                            llm_messages,
                            conversation.agent.http_tools,
                            db=self.db,
                        )
                    else:
                        if getattr(llm_client, "user_id", None) is not None:
                            llm_result = llm_client.complete(
                                conversation.agent, llm_messages, conversation.agent.http_tools, db=self.db
                            )
                        else:
                            llm_result = llm_client.complete(
                                conversation.agent, llm_messages, conversation.agent.http_tools
                            )
        except LLMError as exc:
            self.db.rollback()
            raise ConversationError(str(exc), status_code=502) from exc

        if isinstance(llm_result, LLMResult):
            assistant_content = llm_result.content
            used_tools = llm_result.used_tools
            used_skills = llm_result.used_skills
            used_agents = llm_result.used_agents
            api_cost_usd = llm_result.api_cost_usd
        else:
            assistant_content = llm_result
            used_tools = []
            used_skills = []
            used_agents = []
            api_cost_usd = 0.0
        assistant_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_content,
            used_tools=used_tools,
            used_skills=used_skills,
            used_agents=used_agents,
            api_cost_usd=api_cost_usd,
        )
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)
        return assistant_message
