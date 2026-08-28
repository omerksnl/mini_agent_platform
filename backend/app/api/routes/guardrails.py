from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.guardrail_service import GuardrailError, GuardrailService
from app.db.session import get_db
from app.schemas.guardrail import GuardrailCreate, GuardrailResponse, GuardrailUpdate

router = APIRouter(prefix="/guardrails", tags=["guardrails"])


@router.get("", response_model=list[GuardrailResponse])
def list_guardrails(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    return GuardrailService(db).list_guardrails(current.tenant_id)


@router.post("", response_model=GuardrailResponse, status_code=status.HTTP_201_CREATED)
def create_guardrail(payload: GuardrailCreate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        return GuardrailService(db).create(current.tenant_id, payload)
    except GuardrailError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.put("/{guardrail_id}", response_model=GuardrailResponse)
def update_guardrail(guardrail_id: UUID, payload: GuardrailUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        return GuardrailService(db).update(guardrail_id, current.tenant_id, payload)
    except GuardrailError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@router.delete("/{guardrail_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_guardrail(guardrail_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        GuardrailService(db).delete(guardrail_id, current.tenant_id)
    except GuardrailError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
