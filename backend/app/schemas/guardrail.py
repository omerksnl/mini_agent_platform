from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

GuardrailType = Literal["pii_redaction", "blocked_terms", "required_output_fields"]
GuardrailStage = Literal["input", "tool_input", "tool_output", "output"]
GuardrailAction = Literal["warn", "redact", "block"]


class GuardrailCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    guardrail_type: GuardrailType
    stages: list[GuardrailStage] = Field(min_length=1, max_length=4)
    action: GuardrailAction
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("Guardrail stages must be unique")
        if self.guardrail_type == "pii_redaction" and self.action != "redact":
            raise ValueError("PII redaction guardrails must use the redact action")
        if self.guardrail_type == "blocked_terms":
            terms = self.config.get("terms")
            if not isinstance(terms, list) or not terms or any(not isinstance(v, str) or not v.strip() for v in terms):
                raise ValueError("Blocked terms guardrails require a non-empty terms list")
            if len(terms) > 100 or any(len(v) > 200 for v in terms):
                raise ValueError("Blocked terms configuration is too large")
        if self.guardrail_type == "required_output_fields":
            fields = self.config.get("fields")
            if not isinstance(fields, list) or not fields or any(not isinstance(v, str) or not v.strip() for v in fields):
                raise ValueError("Required output fields guardrails require a non-empty fields list")
            if "output" not in self.stages:
                raise ValueError("Required output fields guardrails must run at output")
            if self.action == "redact":
                raise ValueError("Required output fields guardrails must warn or block")
        return self


class GuardrailUpdate(GuardrailCreate):
    pass


class GuardrailResponse(GuardrailCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
