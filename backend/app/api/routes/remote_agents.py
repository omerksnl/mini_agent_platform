from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.remote_agent_service import RemoteAgentError, RemoteAgentService
from app.db.session import get_db
from app.schemas.remote_agent import (
    RemoteAgentCreate,
    RemoteAgentMessageRequest,
    RemoteAgentMessageResponse,
    RemoteAgentResponse,
)


router = APIRouter(prefix="/remote-agents", tags=["remote-agents"])


def _raise(exc: RemoteAgentError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[RemoteAgentResponse])
def list_remote_agents(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[RemoteAgentResponse]:
    return [
        RemoteAgentResponse.model_validate(item)
        for item in RemoteAgentService(db).list(current.tenant_id, current.user.id)
    ]


@router.post("", response_model=RemoteAgentResponse, status_code=status.HTTP_201_CREATED)
def create_remote_agent(
    payload: RemoteAgentCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> RemoteAgentResponse:
    try:
        item = RemoteAgentService(db).create(
            current.tenant_id,
            current.user.id,
            str(payload.agent_card_url),
            payload.api_key,
            payload.billing_mode,
            payload.provider_credential_id,
        )
    except RemoteAgentError as exc:
        _raise(exc)
    return RemoteAgentResponse.model_validate(item)


@router.delete("/{remote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_remote_agent(
    remote_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        RemoteAgentService(db).delete(remote_id, current.tenant_id, current.user.id)
    except RemoteAgentError as exc:
        _raise(exc)


@router.post("/{remote_id}/messages", response_model=RemoteAgentMessageResponse)
def send_remote_agent_message(
    remote_id: UUID,
    payload: RemoteAgentMessageRequest,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> RemoteAgentMessageResponse:
    try:
        content, context_id, api_cost_usd, billing_mode, billed_to, provider = RemoteAgentService(db).send(
            remote_id,
            current.tenant_id,
            current.user.id,
            payload.content,
            payload.attachment_ids,
        )
    except RemoteAgentError as exc:
        _raise(exc)
    return RemoteAgentMessageResponse(
        content=content,
        context_id=context_id,
        api_cost_usd=api_cost_usd,
        billing_mode=billing_mode,
        billed_to=billed_to,
        provider=provider,
    )
