from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)


class CollectionDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    original_name: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: datetime


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    description: str
    documents: list[CollectionDocumentResponse]
    created_at: datetime
    updated_at: datetime
