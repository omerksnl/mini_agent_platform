from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.agent_service import AgentError, AgentService
from app.core.services.a2a_service import A2AService
from app.core.services.prompt_optimization_service import (
    PromptOptimizationError,
    PromptOptimizationService,
)
from app.db.session import get_db
from app.schemas.agent import (
    AgentCreate,
    AgentA2APublishRequest,
    AgentA2APublishResponse,
    AgentPromptVersionResponse,
    AgentResponse,
    AgentUpdate,
    PromptEvaluationBatchResponse,
    PromptImproveRequest,
    PromptImproveResponse,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/{agent_id}/a2a/publish", response_model=AgentA2APublishResponse)
def publish_agent_a2a(
    agent_id: UUID,
    payload: AgentA2APublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AgentA2APublishResponse:
    try:
        agent, api_key = A2AService(db).publish(agent_id, current.tenant_id, payload.description)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    base_url = str(request.base_url).rstrip("/")
    endpoint = f"{base_url}/a2a/agents/{agent.id}"
    return AgentA2APublishResponse(
        api_key=api_key,
        agent_card_url=f"{endpoint}/.well-known/agent-card.json",
        endpoint_url=endpoint,
    )


@router.delete("/{agent_id}/a2a/publish", response_model=AgentResponse)
def unpublish_agent_a2a(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    try:
        agent = A2AService(db).unpublish(agent_id, current.tenant_id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AgentResponse.model_validate(agent)


@router.get("", response_model=list[AgentResponse])
def list_agents(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[AgentResponse]:
    agents = AgentService(db).list_agents(current.tenant_id)
    return [AgentResponse.model_validate(agent) for agent in agents]


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    try:
        agent = AgentService(db).create_agent(current.tenant_id, payload, current.id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    try:
        agent = AgentService(db).get_agent(agent_id, current.tenant_id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: UUID,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    try:
        agent = AgentService(db).update_agent(agent_id, current.tenant_id, payload, current.id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/prompt-versions", response_model=list[AgentPromptVersionResponse])
def list_prompt_versions(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[AgentPromptVersionResponse]:
    try:
        service = AgentService(db)
        agent = service.get_agent(agent_id, current.tenant_id)
        versions = service.list_prompt_versions(agent_id, current.tenant_id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return [AgentPromptVersionResponse(
        id=version.id,
        agent_id=version.agent_id,
        version_number=version.version_number,
        system_prompt=version.system_prompt,
        created_at=version.created_at,
        is_current=version.id == agent.active_prompt_version_id,
        evaluation=version.evaluation,
        evaluated_at=version.evaluated_at,
    ) for version in versions]


@router.post(
    "/{agent_id}/prompt-versions/evaluate",
    response_model=PromptEvaluationBatchResponse,
)
def evaluate_prompt_versions(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> PromptEvaluationBatchResponse:
    try:
        service = PromptOptimizationService(db, current.user)
        versions, cost = service.evaluate_versions(agent_id, current.tenant_id)
        agent = AgentService(db).get_agent(agent_id, current.tenant_id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except PromptOptimizationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PromptEvaluationBatchResponse(
        versions=[AgentPromptVersionResponse(
            id=version.id,
            agent_id=version.agent_id,
            version_number=version.version_number,
            system_prompt=version.system_prompt,
            created_at=version.created_at,
            is_current=version.id == agent.active_prompt_version_id,
            evaluation=version.evaluation,
            evaluated_at=version.evaluated_at,
        ) for version in versions],
        api_cost_usd=cost,
    )


@router.post("/{agent_id}/prompt-improvements", response_model=PromptImproveResponse)
def improve_prompt(
    agent_id: UUID,
    payload: PromptImproveRequest,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> PromptImproveResponse:
    try:
        result, cost = PromptOptimizationService(db, current.user).improve_prompt(
            agent_id, current.tenant_id, payload.draft_prompt
        )
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except PromptOptimizationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PromptImproveResponse(
        improved_prompt=result.improved_prompt,
        rationale=result.rationale,
        api_cost_usd=cost,
    )


@router.post("/{agent_id}/prompt-versions/{version_id}/restore", response_model=AgentResponse)
def restore_prompt_version(
    agent_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    try:
        agent = AgentService(db).restore_prompt_version(agent_id, version_id, current.tenant_id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        AgentService(db).delete_agent(agent_id, current.tenant_id)
    except AgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
