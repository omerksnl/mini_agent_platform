from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProviderSettingsResponse(BaseModel):
    provider: Literal["openrouter", "openai"]
    source: Literal["personal", "platform"]
    has_personal_key: bool
    masked_key: str | None = None


class ProviderSettingsUpdate(BaseModel):
    name: str = Field(default="Personal key", min_length=1, max_length=100)
    provider: Literal["openrouter", "openai"]
    api_key: str = Field(min_length=16, max_length=500)


class ProviderTestResponse(BaseModel):
    status: Literal["ok"] = "ok"
    provider: Literal["openrouter", "openai"]


class ProviderModelResponse(BaseModel):
    id: str
    label: str


class ProviderCredentialResponse(BaseModel):
    id: UUID
    name: str
    provider: Literal["openrouter", "openai"]
    masked_key: str = "••••••••"
    is_active: bool
    created_at: datetime


class ProviderCompatibilityResponse(BaseModel):
    provider: Literal["openrouter", "openai"]
    incompatible_agents: list[str]
    recommended_model: str | None = None


class AgentProviderAssignmentUpdate(BaseModel):
    credential_id: UUID | None = None


class AgentProviderAssignmentResponse(BaseModel):
    agent_id: UUID
    credential_id: UUID
