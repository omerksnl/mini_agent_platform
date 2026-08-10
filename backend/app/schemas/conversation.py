from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.attachment import AttachmentResponse


class ConversationCreate(BaseModel):
    agent_id: UUID
    title: str = Field(default="New conversation", min_length=1, max_length=255)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def reject_explicit_null(self) -> Self:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Title cannot be null")
        return self


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    agent_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=20_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> Self:
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("Message content or an attachment is required")
        return self


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime
    used_tools: list[str]
    used_skills: list[str]
    api_cost_usd: float
    attachments: list[AttachmentResponse]
