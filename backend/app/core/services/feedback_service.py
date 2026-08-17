from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.observability import submit_human_feedback
from app.models import Message, WorkflowRun
from app.schemas.feedback import HumanFeedbackCreate


class FeedbackError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class FeedbackService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def submit(
        self,
        payload: HumanFeedbackCreate,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        if payload.target_type == "message":
            message = self.db.scalar(select(Message).where(
                Message.id == payload.target_id,
                Message.tenant_id == tenant_id,
                Message.role == "assistant",
            ))
            if not message:
                raise FeedbackError("Assistant message not found", 404)
            session_id = str(message.conversation_id)
        else:
            run = self.db.scalar(select(WorkflowRun).where(
                WorkflowRun.id == payload.target_id,
                WorkflowRun.tenant_id == tenant_id,
            ))
            if not run:
                raise FeedbackError("Workflow run not found", 404)
            session_id = str(run.id)

        try:
            submit_human_feedback(
                get_settings(),
                session_id=session_id,
                target_type=payload.target_type,
                target_id=payload.target_id,
                user_id=user_id,
                tenant_id=tenant_id,
                score=payload.score,
                comment=payload.comment.strip() or None,
            )
        except Exception as exc:
            raise FeedbackError("Feedback could not be sent to Langfuse", 502) from exc
