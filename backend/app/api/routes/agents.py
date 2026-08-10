from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.agent_service import AgentError, AgentService
from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


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
        agent = AgentService(db).create_agent(current.tenant_id, payload)
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
        agent = AgentService(db).update_agent(agent_id, current.tenant_id, payload)
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
