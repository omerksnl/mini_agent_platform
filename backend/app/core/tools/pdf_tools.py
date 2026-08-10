from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.services.attachment_service import AttachmentService
from app.models import Attachment


class PdfToTextInput(BaseModel):
    attachment_id: UUID = Field(description="ID of a PDF attached to the current user message")


def build_pdf_to_text_tool(db: Session, attachments: list[Attachment]) -> StructuredTool:
    allowed = {attachment.id: attachment for attachment in attachments}
    settings = get_settings()

    def extract(attachment_id: UUID) -> str:
        attachment = allowed.get(attachment_id)
        if attachment is None:
            raise ValueError("This PDF is not attached to the current message")
        if attachment.extracted_text is not None:
            return attachment.extracted_text

        path = AttachmentService(db).path_for(attachment)
        try:
            reader = PdfReader(path)
        except Exception as exc:
            raise ValueError("The PDF could not be read") from exc
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")
        if len(reader.pages) > settings.pdf_max_pages:
            raise ValueError(f"PDF exceeds the {settings.pdf_max_pages}-page limit")

        parts: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(f"--- Page {page_number} ---\n{text}")
        result = "\n\n".join(parts).strip()
        if not result:
            raise ValueError("No selectable text was found; this PDF may require OCR")
        if len(result) > settings.pdf_max_text_characters:
            result = result[: settings.pdf_max_text_characters]
            result += "\n\n[Text truncated at the configured safety limit]"
        attachment.extracted_text = result
        db.flush()
        return result

    return StructuredTool.from_function(
        func=extract,
        name="pdf_to_text",
        description=(
            "Extract selectable text from a PDF attached to the current user message. "
            "Use the exact attachment_id shown in the message."
        ),
        args_schema=PdfToTextInput,
    )
