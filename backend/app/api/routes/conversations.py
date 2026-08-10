from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_llm_client
from app.core.services.agent_service import AgentError
from app.core.services.conversation_service import ConversationError, ConversationService
from app.core.services.llm_service import LLMClient, LLMError
from app.db.session import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def raise_conversation_error(exc: ConversationError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[ConversationResponse]:
    conversations = ConversationService(db).list_conversations(current.tenant_id)
    return [ConversationResponse.model_validate(item) for item in conversations]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> ConversationResponse:
    try:
        conversation = ConversationService(db).create_conversation(current.tenant_id, payload)
    except (ConversationError, AgentError) as exc:
        raise_conversation_error(exc)
    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> ConversationResponse:
    try:
        conversation = ConversationService(db).get_conversation(conversation_id, current.tenant_id)
    except ConversationError as exc:
        raise_conversation_error(exc)
    return ConversationResponse.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> ConversationResponse:
    try:
        conversation = ConversationService(db).update_conversation(
            conversation_id,
            current.tenant_id,
            payload,
        )
    except ConversationError as exc:
        raise_conversation_error(exc)
    return ConversationResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        ConversationService(db).delete_conversation(conversation_id, current.tenant_id)
    except ConversationError as exc:
        raise_conversation_error(exc)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> list[MessageResponse]:
    try:
        messages = ConversationService(db).list_messages(conversation_id, current.tenant_id)
    except ConversationError as exc:
        raise_conversation_error(exc)
    return [MessageResponse.model_validate(item) for item in messages]


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    llm_client: LLMClient = Depends(get_llm_client),
) -> MessageResponse:
    try:
        message = ConversationService(db).send_message(
            conversation_id,
            current.tenant_id,
            current.id,
            payload.content,
            payload.attachment_ids,
            llm_client,
        )
    except ConversationError as exc:
        raise_conversation_error(exc)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MessageResponse.model_validate(message)
