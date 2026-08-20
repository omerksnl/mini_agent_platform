from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class RemoteAgentCreate(BaseModel):
    agent_card_url: HttpUrl
    api_key: str = Field(min_length=8, max_length=500)


class RemoteAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    name: str
    description: str
    agent_card_url: str
    endpoint_url: str
    protocol_version: str
    skills: list[dict]
    created_at: datetime
    updated_at: datetime


class RemoteAgentMessageRequest(BaseModel):
    content: str = Field(default="", max_length=20000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "RemoteAgentMessageRequest":
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("Message content or a PDF attachment is required")
        return self


class RemoteAgentMessageResponse(BaseModel):
    content: str
    context_id: str | None = None
    api_cost_usd: float = 0.0
