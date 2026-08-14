import json
from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.report_templates import REPORT_TEMPLATES, template_catalog_for_model
from app.core.services.generated_file_service import GeneratedFileService
from app.core.services.report_pdf_service import ReportPdfService
from app.models import Agent


class TextToPdfInput(BaseModel):
    content: str = Field(description="Complete Markdown text to render into the PDF")
    template_id: Literal["blank_markdown", "two_column"] = Field(
        description="Safe registered template identifier"
    )
    filename: str = Field(default="document.pdf", description="Download filename ending in .pdf")
    title: str | None = Field(default=None, description="Optional document title")


def build_text_to_pdf_tool(db: Session, agent: Agent) -> StructuredTool:
    settings = get_settings()

    def render(content: str, template_id: str, filename: str = "document.pdf", title: str | None = None) -> str:
        if len(content) > settings.text_to_pdf_max_characters:
            raise ValueError(
                f"PDF content exceeds the {settings.text_to_pdf_max_characters}-character limit"
            )
        if template_id not in REPORT_TEMPLATES:
            raise ValueError("Unknown report template")
        data = ReportPdfService().render(content, template_id, title)
        generated = GeneratedFileService(db).create_pdf(
            agent.tenant_id,
            agent.id,
            filename,
            template_id,
            data,
        )
        return json.dumps({
            "generated_file_id": str(generated.id),
            "filename": generated.original_name,
            "template_id": generated.template_id,
            "download_url": f"/api/generated-files/{generated.id}/download",
        })

    return StructuredTool.from_function(
        func=render,
        name="text_to_pdf",
        description=(
            "Render complete Markdown into a downloadable PDF using one safe registered template. "
            "Choose the template that best matches the user's request. Always include the returned "
            "download URL in the final answer. Available templates:\n" + template_catalog_for_model()
        ),
        args_schema=TextToPdfInput,
    )
