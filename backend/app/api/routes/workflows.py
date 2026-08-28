from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_llm_client
from app.core.services.llm_service import LLMClient
from app.core.services.workflow_execution_service import WorkflowExecutionService
from app.core.services.workflow_service import WorkflowError, WorkflowService
from app.db.session import get_db
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunResponse,
    WorkflowRunResume,
    WorkflowRunStart,
    WorkflowUpdate,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])
workflow_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workflow")


def execute_workflow_in_background(
    run_id: UUID, tenant_id: UUID, llm_client: LLMClient, bind: Engine
) -> None:
    db = Session(bind=bind)
    try:
        WorkflowExecutionService(db, llm_client).execute_deferred(run_id, tenant_id)
    finally:
        db.close()


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
        workflow = WorkflowService(db).create_workflow(current.tenant_id, payload, current.id)
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowResponse.model_validate(workflow)


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunResponse])
def list_workflow_runs(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[WorkflowRunResponse]:
    try:
        runs = WorkflowExecutionService(db, llm_client=None).list_runs(
            workflow_id, current.tenant_id
        )
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return [WorkflowRunResponse.model_validate(item) for item in runs]


@router.post("/{workflow_id}/runs", response_model=WorkflowRunResponse, status_code=status.HTTP_201_CREATED)
def start_workflow_run(
    workflow_id: UUID,
    payload: WorkflowRunStart,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    llm_client: LLMClient = Depends(get_llm_client),
) -> WorkflowRunResponse:
    try:
        run = WorkflowExecutionService(db, llm_client).start_deferred(
            workflow_id,
            current.tenant_id,
            current.id,
            payload.input_data,
            payload.attachment_ids,
        )
        workflow_executor.submit(
            execute_workflow_in_background,
            run.id,
            current.tenant_id,
            llm_client,
            db.get_bind(),
        )
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowRunResponse.model_validate(run)


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> WorkflowRunResponse:
    try:
        run = WorkflowExecutionService(db, llm_client=None).get_run(
            run_id, current.tenant_id
        )
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowRunResponse.model_validate(run)


@router.post("/runs/{run_id}/resume", response_model=WorkflowRunResponse)
def resume_workflow_run(
    run_id: UUID,
    payload: WorkflowRunResume,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    llm_client: LLMClient = Depends(get_llm_client),
) -> WorkflowRunResponse:
    try:
        run = WorkflowExecutionService(db, llm_client).resume_deferred(
            run_id, current.tenant_id, payload.input_data
        )
        if run.status == "running":
            workflow_executor.submit(
                execute_workflow_in_background,
                run.id,
                current.tenant_id,
                llm_client,
                db.get_bind(),
            )
    except WorkflowError as exc:
        raise_workflow_error(exc)
    return WorkflowRunResponse.model_validate(run)


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
            workflow_id, current.tenant_id, payload, current.id
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
