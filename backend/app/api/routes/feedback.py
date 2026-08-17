from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.feedback_service import FeedbackError, FeedbackService
from app.db.session import get_db
from app.schemas.feedback import HumanFeedbackCreate, HumanFeedbackResponse


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=HumanFeedbackResponse)
def submit_feedback(
    payload: HumanFeedbackCreate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> HumanFeedbackResponse:
    try:
        FeedbackService(db).submit(payload, tenant_id=current.tenant_id, user_id=current.id)
    except FeedbackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return HumanFeedbackResponse()
