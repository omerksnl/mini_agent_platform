from datetime import datetime
from uuid import UUID

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    agent_type: Literal["normal", "supervisor", "router"] = "normal"
    system_prompt: str = ""
    model: str = Field(default="anthropic/claude-haiku-4.5", min_length=1, max_length=128)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    system_tools: list[str] = Field(default_factory=lambda: ["calculator", "current_datetime"])
    tool_ids: list[UUID] = Field(default_factory=list)
    skill_ids: list[UUID] = Field(default_factory=list)
    collection_ids: list[UUID] = Field(default_factory=list)
    managed_agent_ids: list[UUID] = Field(default_factory=list)
    router_target_ids: list[UUID] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    agent_type: Literal["normal", "supervisor", "router"] | None = None
    system_prompt: str | None = None
    model: str | None = Field(default=None, min_length=1, max_length=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    system_tools: list[str] | None = None
    tool_ids: list[UUID] | None = None
    skill_ids: list[UUID] | None = None
    collection_ids: list[UUID] | None = None
    managed_agent_ids: list[UUID] | None = None
    router_target_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        null_fields = [
            field_name
            for field_name in self.model_fields_set
            if getattr(self, field_name) is None
        ]
        if null_fields:
            fields = ", ".join(sorted(null_fields))
            raise ValueError(f"Fields cannot be null: {fields}")
        return self


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    agent_type: Literal["normal", "supervisor", "router"]
    supervisor_ids: list[UUID]
    system_prompt: str
    model: str
    temperature: float
    system_tools: list[str]
    tool_ids: list[UUID]
    skill_ids: list[UUID]
    collection_ids: list[UUID]
    managed_agent_ids: list[UUID]
    router_target_ids: list[UUID]
    router_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class AgentPromptVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    version_number: int
    system_prompt: str
    created_at: datetime
    is_current: bool
