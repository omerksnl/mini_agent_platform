from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GeneratedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_name: str
    content_type: str
    template_id: str
    size_bytes: int
    created_at: datetime
