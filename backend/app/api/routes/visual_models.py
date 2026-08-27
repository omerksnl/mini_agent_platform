from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.visual_model_service import VisualModelError, VisualModelService
from app.core.services.visual_dataset_service import VisualDatasetError, VisualDatasetService
from app.db.session import get_db
from app.schemas.visual_model import (
    VisualDatasetSummary,
    VisualDatasetUploadResponse,
    VisualModelCreate,
    VisualModelResponse,
    VisualModelUpdate,
)

router = APIRouter(prefix="/visual-models", tags=["visual-models"])


@router.get("/{visual_model_id}/dataset", response_model=VisualDatasetSummary)
def get_visual_dataset(
    visual_model_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        return VisualDatasetService(db).summary(visual_model_id, current.tenant_id)
    except VisualDatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.post("/{visual_model_id}/dataset", response_model=VisualDatasetUploadResponse)
def upload_visual_dataset(
    visual_model_id: UUID,
    files: list[UploadFile] = File(...),
    class_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        return VisualDatasetService(db).upload(
            visual_model_id, current.tenant_id, files, class_name
        )
    except VisualDatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.delete("/{visual_model_id}/dataset", status_code=status.HTTP_204_NO_CONTENT)
def clear_visual_dataset(
    visual_model_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        VisualDatasetService(db).clear(visual_model_id, current.tenant_id)
    except VisualDatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.get("", response_model=list[VisualModelResponse])
def list_visual_models(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
):
    return VisualModelService(db).list(current.tenant_id)


@router.post("", response_model=VisualModelResponse, status_code=status.HTTP_201_CREATED)
def create_visual_model(
    payload: VisualModelCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        return VisualModelService(db).create(current.tenant_id, payload)
    except VisualModelError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.put("/{visual_model_id}", response_model=VisualModelResponse)
def update_visual_model(
    visual_model_id: UUID,
    payload: VisualModelUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        return VisualModelService(db).update(visual_model_id, current.tenant_id, payload)
    except VisualModelError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.delete("/{visual_model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_visual_model(
    visual_model_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        VisualModelService(db).delete(visual_model_id, current.tenant_id)
    except VisualModelError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
