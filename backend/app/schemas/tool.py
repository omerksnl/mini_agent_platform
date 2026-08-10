import re
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ToolParameter(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    type: Literal["string", "integer", "number", "boolean"] = "string"
    description: str = Field(default="", max_length=500)
    required: bool = True


class HttpToolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=1000)
    url: HttpUrl
    method: Literal["GET", "POST"] = "GET"
    parameters: list[ToolParameter] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_parameter_names(self) -> Self:
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("Tool parameter names must be unique")
        return self


class HttpToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    url: HttpUrl | None = None
    method: Literal["GET", "POST"] | None = None
    parameters: list[ToolParameter] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"Field cannot be null: {field_name}")
        if self.parameters is not None:
            names = [parameter.name for parameter in self.parameters]
            if len(names) != len(set(names)):
                raise ValueError("Tool parameter names must be unique")
        return self


class HttpToolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str
    url: str
    method: str
    parameters: list[ToolParameter]
    created_at: datetime
    updated_at: datetime
