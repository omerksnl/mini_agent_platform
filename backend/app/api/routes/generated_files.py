from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.generated_file_service import GeneratedFileError, GeneratedFileService
from app.db.session import get_db


router = APIRouter(prefix="/generated-files", tags=["generated-files"])


@router.get("/{file_id}/download")
def download_generated_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    service = GeneratedFileService(db)
    try:
        generated = service.get(file_id, current.tenant_id)
        path = service.path_for(generated)
    except GeneratedFileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return FileResponse(
        path,
        media_type=generated.content_type,
        filename=generated.original_name,
    )
