from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VisualArchitecture = Literal["simple_cnn", "mobilenet_v2", "resnet50"]


class VisualModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    task_type: Literal["image_classification"] = "image_classification"
    architecture: VisualArchitecture
    class_names: list[str] = Field(min_length=2, max_length=100)
    image_width: int = Field(default=224, ge=32, le=2048)
    image_height: int = Field(default=224, ge=32, le=2048)
    channels: Literal[1, 3] = 3
    use_pretrained_weights: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("class_names")
    @classmethod
    def validate_classes(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Class names cannot be empty")
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError("Class names must be unique")
        return cleaned

    @model_validator(mode="after")
    def validate_architecture(self) -> Self:
        if self.architecture == "simple_cnn" and self.use_pretrained_weights:
            raise ValueError("Simple CNN does not support pretrained weights")
        return self


class VisualModelUpdate(VisualModelCreate):
    pass


class VisualModelResponse(VisualModelCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: Literal["draft", "dataset_ready"]
    created_at: datetime
    updated_at: datetime


class VisualDatasetClassSummary(BaseModel):
    class_name: str
    image_count: int
    total_bytes: int


class VisualDatasetSummary(BaseModel):
    visual_model_id: UUID
    total_images: int
    total_bytes: int
    ready_for_training: bool
    classes: list[VisualDatasetClassSummary]


class VisualDatasetUploadResponse(BaseModel):
    added_images: int
    skipped_duplicates: int
    summary: VisualDatasetSummary
