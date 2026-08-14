from pathlib import Path
import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import GeneratedFile


class GeneratedFileError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GeneratedFileService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def create_pdf(
        self,
        tenant_id: UUID,
        agent_id: UUID | None,
        filename: str,
        template_id: str,
        data: bytes,
    ) -> GeneratedFile:
        safe_name = self._safe_pdf_name(filename)
        if not data.startswith(b"%PDF-"):
            raise GeneratedFileError("The generated output is not a valid PDF")
        if len(data) > self.settings.generated_file_max_bytes:
            raise GeneratedFileError("The generated PDF exceeds the configured size limit")

        file_id = uuid4()
        root = Path(self.settings.upload_directory).resolve()
        tenant_directory = root / str(tenant_id) / "generated"
        tenant_directory.mkdir(parents=True, exist_ok=True)
        storage_key = f"{tenant_id}/generated/{file_id}.pdf"
        path = (root / storage_key).resolve()
        if tenant_directory.resolve() not in path.parents:
            raise GeneratedFileError("Invalid generated file path")
        path.write_bytes(data)

        generated = GeneratedFile(
            id=file_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            original_name=safe_name,
            content_type="application/pdf",
            template_id=template_id,
            size_bytes=len(data),
            storage_key=storage_key,
        )
        self.db.add(generated)
        self.db.flush()
        return generated

    def get(self, file_id: UUID, tenant_id: UUID) -> GeneratedFile:
        generated = self.db.scalar(select(GeneratedFile).where(
            GeneratedFile.id == file_id,
            GeneratedFile.tenant_id == tenant_id,
        ))
        if generated is None:
            raise GeneratedFileError("Generated file not found", status_code=404)
        return generated

    def path_for(self, generated: GeneratedFile) -> Path:
        root = Path(self.settings.upload_directory).resolve()
        path = (root / generated.storage_key).resolve()
        tenant_root = (root / str(generated.tenant_id) / "generated").resolve()
        if tenant_root not in path.parents or not path.is_file():
            raise GeneratedFileError("Generated file is unavailable", status_code=404)
        return path

    @staticmethod
    def _safe_pdf_name(filename: str) -> str:
        name = Path(filename).name.strip()
        stem = Path(name).stem[:100]
        stem = re.sub(r"[^A-Za-z0-9._ -]+", "-", stem).strip(" .-") or "document"
        return f"{stem}.pdf"
