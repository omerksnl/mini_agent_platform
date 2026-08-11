from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.workflow_service import WorkflowError, WorkflowService
from app.db.session import get_db
from app.schemas.workflow import WorkflowCreate, WorkflowResponse, WorkflowUpdate

router = APIRouter(prefix="/workflows", tags=["workflows"])


def raise_workflow_error(exc: WorkflowError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[WorkflowResponse]:
    workflows = WorkflowService(db).list_workflows(current.tenant_id)
    return [WorkflowResponse.model_validate(item) for item in workflows]


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> WorkflowResponse:
    try:
        workflow = WorkflowService(db).create_workflow(current.tenant_id, payload)
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowResponse.model_validate(workflow)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> WorkflowResponse:
    try:
        workflow = WorkflowService(db).get_workflow(workflow_id, current.tenant_id)
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowResponse.model_validate(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> WorkflowResponse:
    try:
        workflow = WorkflowService(db).update_workflow(
            workflow_id, current.tenant_id, payload
        )
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowResponse.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        WorkflowService(db).delete_workflow(workflow_id, current.tenant_id)
    except WorkflowError as exc:
        raise_workflow_error(exc)
