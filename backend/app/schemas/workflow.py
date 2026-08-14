from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


StepType = Literal["agent", "http_tool", "system_tool", "human_wait", "report"]
RouteCondition = Literal["success", "failure", "input_available", "always"]


class WorkflowStepInput(BaseModel):
    step_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=255)
    step_type: StepType
    position: int = Field(ge=0)
    agent_id: UUID | None = None
    http_tool_id: UUID | None = None
    system_tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        target_count = sum(
            value is not None
            for value in (self.agent_id, self.http_tool_id, self.system_tool_name)
        )
        expected = {
            "agent": self.agent_id is not None and target_count == 1,
            "http_tool": self.http_tool_id is not None and target_count == 1,
            "system_tool": self.system_tool_name is not None and target_count == 1,
            "human_wait": target_count == 0,
            "report": target_count == 0,
        }[self.step_type]
        if not expected:
            raise ValueError(f"Invalid target fields for {self.step_type} step")
        if self.step_type == "report":
            input_key = self.config.get("input_artifact_key")
            template_id = self.config.get("template_id")
            filename = self.config.get("filename")
            title = self.config.get("title")
            if not isinstance(input_key, str) or not input_key or len(input_key) > 64:
                raise ValueError("Report input_artifact_key is required")
            if template_id not in {"blank_markdown", "two_column"}:
                raise ValueError("Report template_id must be blank_markdown or two_column")
            if not isinstance(filename, str) or not filename.strip() or len(filename) > 120:
                raise ValueError("Report filename is required")
            if title is not None and (not isinstance(title, str) or len(title) > 255):
                raise ValueError("Report title must be text up to 255 characters")
        if self.step_type == "agent":
            task_instructions = self.config.get("task_instructions", "")
            use_collections = self.config.get("use_collections", True)
            collection_mode = self.config.get("collection_mode")
            if not isinstance(task_instructions, str) or len(task_instructions) > 4000:
                raise ValueError("Agent task_instructions must be text up to 4000 characters")
            if not isinstance(use_collections, bool):
                raise ValueError("Agent use_collections must be true or false")
            if collection_mode is not None and collection_mode not in {"off", "search", "full_context"}:
                raise ValueError("Agent collection_mode must be off, search, or full_context")
            input_artifact_keys = self.config.get("input_artifact_keys")
            if input_artifact_keys is not None and (
                not isinstance(input_artifact_keys, list)
                or len(input_artifact_keys) > 20
                or any(not isinstance(key, str) or not key or len(key) > 64 for key in input_artifact_keys)
            ):
                raise ValueError("Agent input_artifact_keys must be a list of up to 20 artifact keys")
            max_output_tokens = self.config.get("max_output_tokens")
            if max_output_tokens is not None and (
                not isinstance(max_output_tokens, int) or not 256 <= max_output_tokens <= 8000
            ):
                raise ValueError("Agent max_output_tokens must be between 256 and 8000")
        return self


class WorkflowRouteInput(BaseModel):
    source_step_key: str = Field(min_length=1, max_length=64)
    target_step_key: str = Field(min_length=1, max_length=64)
    condition: RouteCondition = "success"
    priority: int = Field(default=0, ge=0)
    config: dict = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    is_active: bool = True
    steps: list[WorkflowStepInput] = Field(min_length=1)
    routes: list[WorkflowRouteInput] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    steps: list[WorkflowStepInput] | None = Field(default=None, min_length=1)
    routes: list[WorkflowRouteInput] | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        null_fields = [
            name for name in self.model_fields_set if getattr(self, name) is None
        ]
        if null_fields:
            raise ValueError("Fields cannot be null: " + ", ".join(sorted(null_fields)))
        steps_set = "steps" in self.model_fields_set
        routes_set = "routes" in self.model_fields_set
        if steps_set != routes_set:
            raise ValueError("Steps and routes must be updated together")
        return self


class WorkflowStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_key: str
    name: str
    step_type: StepType
    position: int
    agent_id: UUID | None
    http_tool_id: UUID | None
    system_tool_name: str | None
    config: dict


class WorkflowRouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_step_key: str
    target_step_key: str
    condition: RouteCondition
    priority: int
    config: dict


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str
    is_active: bool
    steps: list[WorkflowStepResponse]
    routes: list[WorkflowRouteResponse]
    created_at: datetime
    updated_at: datetime


RunStatus = Literal["running", "waiting", "completed", "failed"]


class WorkflowRunStart(BaseModel):
    input_data: dict = Field(default_factory=dict)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)


class WorkflowRunResume(BaseModel):
    input_data: dict = Field(min_length=1)


class WorkflowStepRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    step_key: str
    step_name: str
    step_type: StepType
    status: RunStatus
    input_data: dict
    output_data: dict
    error: str | None
    api_cost_usd: float
    started_at: datetime
    completed_at: datetime | None


class WorkflowArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_run_id: UUID | None
    sequence: int
    artifact_key: str
    name: str
    artifact_type: Literal["workflow_input", "agent_output", "human_input", "tool_output", "generated_file"]
    data: dict
    created_at: datetime


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workflow_id: UUID
    status: RunStatus
    current_step_id: UUID | None
    input_data: dict
    output_data: dict
    error: str | None
    total_api_cost_usd: float
    step_runs: list[WorkflowStepRunResponse]
    artifacts: list[WorkflowArtifactResponse]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
