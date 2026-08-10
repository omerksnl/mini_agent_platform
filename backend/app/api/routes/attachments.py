from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.config import get_settings
from app.core.services.attachment_service import AttachmentError, AttachmentService
from app.db.session import get_db
from app.schemas.attachment import AttachmentResponse

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AttachmentResponse:
    maximum = get_settings().attachment_max_bytes
    data = await file.read(maximum + 1)
    try:
        attachment = AttachmentService(db).create_pdf(
            current.tenant_id,
            current.id,
            file.filename or "attachment.pdf",
            file.content_type,
            data,
        )
    except AttachmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    finally:
        await file.close()
    return AttachmentResponse.model_validate(attachment)
