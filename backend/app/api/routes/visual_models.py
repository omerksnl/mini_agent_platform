from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.visual_model_service import VisualModelError, VisualModelService
from app.core.services.visual_dataset_service import VisualDatasetError, VisualDatasetService
from app.core.services.visual_training_service import (
    available_training_devices,
    VisualTrainingError,
    VisualTrainingService,
    execute_visual_training,
)
from app.db.session import get_db
from app.schemas.visual_model import (
    VisualDatasetSummary,
    VisualDatasetUploadResponse,
    VisualModelCreate,
    VisualModelResponse,
    VisualModelUpdate,
    VisualPredictionResponse,
    VisualTrainingRunCreate,
    VisualTrainingRunResponse,
    VisualComputeDeviceResponse,
)

router = APIRouter(prefix="/visual-models", tags=["visual-models"])
visual_training_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visual-training")


@router.get("/training-devices", response_model=list[VisualComputeDeviceResponse])
def get_visual_training_devices(current: CurrentUser = Depends(get_current_user)):
    del current
    import tensorflow as tf

    return available_training_devices(tf)


@router.post("/{visual_model_id}/predict", response_model=VisualPredictionResponse)
async def predict_visual_model(
    visual_model_id: UUID,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Use a JPG, PNG, or WEBP image")
    try:
        return VisualTrainingService(db).predict(
            visual_model_id, current.tenant_id, await image.read()
        )
    except VisualTrainingError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.post(
    "/{visual_model_id}/training-runs",
    response_model=VisualTrainingRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_visual_training(
    visual_model_id: UUID,
    payload: VisualTrainingRunCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        run = VisualTrainingService(db).start(visual_model_id, current.tenant_id, payload)
    except VisualTrainingError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    visual_training_executor.submit(execute_visual_training, run.id, current.tenant_id)
    return run


@router.get(
    "/{visual_model_id}/training-runs/latest",
    response_model=VisualTrainingRunResponse | None,
)
def get_latest_visual_training(
    visual_model_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        return VisualTrainingService(db).latest(visual_model_id, current.tenant_id)
    except VisualTrainingError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.get("/training-runs/{run_id}", response_model=VisualTrainingRunResponse)
def get_visual_training_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    try:
        return VisualTrainingService(db).get(run_id, current.tenant_id)
    except VisualTrainingError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


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
