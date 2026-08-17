from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class HumanFeedbackCreate(BaseModel):
    target_type: Literal["message", "workflow_run"]
    target_id: UUID
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class HumanFeedbackResponse(BaseModel):
    status: Literal["submitted"] = "submitted"
