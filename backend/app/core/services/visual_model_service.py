from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import VisualModel
from app.schemas.visual_model import VisualModelCreate, VisualModelUpdate


class VisualModelError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class VisualModelService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, tenant_id: UUID) -> list[VisualModel]:
        return list(self.db.scalars(
            select(VisualModel)
            .where(VisualModel.tenant_id == tenant_id)
            .order_by(VisualModel.updated_at.desc())
        ).all())

    def get(self, visual_model_id: UUID, tenant_id: UUID) -> VisualModel:
        item = self.db.scalar(select(VisualModel).where(
            VisualModel.id == visual_model_id,
            VisualModel.tenant_id == tenant_id,
        ))
        if not item:
            raise VisualModelError("Visual model not found", 404)
        return item

    def create(self, tenant_id: UUID, payload: VisualModelCreate) -> VisualModel:
        item = VisualModel(tenant_id=tenant_id, status="draft", **payload.model_dump())
        self.db.add(item)
        return self._commit(item)

    def update(
        self, visual_model_id: UUID, tenant_id: UUID, payload: VisualModelUpdate
    ) -> VisualModel:
        item = self.get(visual_model_id, tenant_id)
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
        return self._commit(item)

    def delete(self, visual_model_id: UUID, tenant_id: UUID) -> None:
        self.db.delete(self.get(visual_model_id, tenant_id))
        self.db.commit()

    def _commit(self, item: VisualModel) -> VisualModel:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise VisualModelError("A visual model with this name already exists") from exc
        self.db.refresh(item)
        return item
