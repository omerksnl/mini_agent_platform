from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Attachment


class AttachmentError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AttachmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def create_pdf(
        self,
        tenant_id: UUID,
        user_id: UUID,
        original_name: str,
        content_type: str | None,
        data: bytes,
    ) -> Attachment:
        if not original_name.lower().endswith(".pdf"):
            raise AttachmentError("Only PDF files are supported")
        if content_type not in {None, "", "application/pdf", "application/octet-stream"}:
            raise AttachmentError("Only PDF files are supported")
        if not data.startswith(b"%PDF-"):
            raise AttachmentError("The uploaded file is not a valid PDF")
        if not data:
            raise AttachmentError("The PDF is empty")
        if len(data) > self.settings.attachment_max_bytes:
            raise AttachmentError(
                f"PDF exceeds the {self.settings.attachment_max_bytes // 1_000_000} MB limit",
                status_code=413,
            )

        attachment_id = uuid4()
        tenant_directory = Path(self.settings.upload_directory).resolve() / str(tenant_id)
        tenant_directory.mkdir(parents=True, exist_ok=True)
        storage_key = f"{tenant_id}/{attachment_id}.pdf"
        path = (Path(self.settings.upload_directory).resolve() / storage_key).resolve()
        if tenant_directory not in path.parents:
            raise AttachmentError("Invalid attachment path")
        path.write_bytes(data)

        attachment = Attachment(
            id=attachment_id,
            tenant_id=tenant_id,
            uploaded_by_id=user_id,
            original_name=Path(original_name).name[:255],
            content_type="application/pdf",
            size_bytes=len(data),
            storage_key=storage_key,
        )
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)
        return attachment

    def claim_for_message(
        self,
        attachment_ids: list[UUID],
        tenant_id: UUID,
        user_id: UUID,
        message_id: UUID,
    ) -> list[Attachment]:
        if not attachment_ids:
            return []
        unique_ids = list(dict.fromkeys(attachment_ids))
        attachments = list(self.db.scalars(select(Attachment).where(
            Attachment.id.in_(unique_ids),
            Attachment.tenant_id == tenant_id,
            Attachment.uploaded_by_id == user_id,
            Attachment.message_id.is_(None),
        )).all())
        if len(attachments) != len(unique_ids):
            raise AttachmentError("One or more attachments are unavailable", status_code=404)
        for attachment in attachments:
            attachment.message_id = message_id
        return attachments

    def path_for(self, attachment: Attachment) -> Path:
        root = Path(self.settings.upload_directory).resolve()
        path = (root / attachment.storage_key).resolve()
        tenant_root = (root / str(attachment.tenant_id)).resolve()
        if tenant_root not in path.parents:
            raise AttachmentError("Invalid attachment path")
        return path
