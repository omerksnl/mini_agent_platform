import re
from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=1000)
    instructions: str = Field(min_length=1, max_length=20_000)
    output_schema: dict[str, Any] | None = None
    required_system_tools: list[str] = Field(default_factory=list)
    required_tool_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def unique_requirements(self) -> Self:
        if len(self.required_system_tools) != len(set(self.required_system_tools)):
            raise ValueError("Required system tools must be unique")
        if len(self.required_tool_ids) != len(set(self.required_tool_ids)):
            raise ValueError("Required HTTP tools must be unique")
        return self


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    instructions: str | None = Field(default=None, min_length=1, max_length=20_000)
    output_schema: dict[str, Any] | None = None
    required_system_tools: list[str] | None = None
    required_tool_ids: list[UUID] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        for field_name in self.model_fields_set:
            if field_name != "output_schema" and getattr(self, field_name) is None:
                raise ValueError(f"Field cannot be null: {field_name}")
        if self.required_system_tools is not None and len(self.required_system_tools) != len(set(self.required_system_tools)):
            raise ValueError("Required system tools must be unique")
        if self.required_tool_ids is not None and len(self.required_tool_ids) != len(set(self.required_tool_ids)):
            raise ValueError("Required HTTP tools must be unique")
        return self


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str
    instructions: str
    output_schema: dict[str, Any] | None
    required_system_tools: list[str]
    required_tool_ids: list[UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime
