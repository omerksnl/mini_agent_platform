from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.skill_service import SkillError, SkillService
from app.db.session import get_db
from app.schemas.skill import SkillCreate, SkillResponse, SkillUpdate

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillResponse])
def list_skills(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[SkillResponse]:
    return [SkillResponse.model_validate(skill) for skill in SkillService(db).list_skills(current.tenant_id)]


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> SkillResponse:
    try:
        skill = SkillService(db).create_skill(current.tenant_id, payload)
    except SkillError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return SkillResponse.model_validate(skill)


@router.get("/{skill_id}", response_model=SkillResponse)
def get_skill(skill_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> SkillResponse:
    try:
        skill = SkillService(db).get_skill(skill_id, current.tenant_id)
    except SkillError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return SkillResponse.model_validate(skill)


@router.patch("/{skill_id}", response_model=SkillResponse)
def update_skill(skill_id: UUID, payload: SkillUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> SkillResponse:
    try:
        skill = SkillService(db).update_skill(skill_id, current.tenant_id, payload)
    except SkillError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return SkillResponse.model_validate(skill)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> None:
    try:
        SkillService(db).delete_skill(skill_id, current.tenant_id)
    except SkillError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
