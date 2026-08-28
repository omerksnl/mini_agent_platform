from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Guardrail
from app.schemas.guardrail import GuardrailCreate, GuardrailUpdate


class GuardrailError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GuardrailService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_guardrails(self, tenant_id: UUID) -> list[Guardrail]:
        return list(self.db.scalars(select(Guardrail).where(Guardrail.tenant_id == tenant_id).order_by(Guardrail.created_at.desc())).all())

    def get(self, guardrail_id: UUID, tenant_id: UUID) -> Guardrail:
        item = self.db.scalar(select(Guardrail).where(Guardrail.id == guardrail_id, Guardrail.tenant_id == tenant_id))
        if not item:
            raise GuardrailError("Guardrail not found", 404)
        return item

    def get_many(self, ids: list[UUID], tenant_id: UUID) -> list[Guardrail]:
        if len(ids) != len(set(ids)):
            raise GuardrailError("Guardrail selection contains duplicates")
        if not ids:
            return []
        items = list(self.db.scalars(select(Guardrail).where(Guardrail.id.in_(ids), Guardrail.tenant_id == tenant_id)).all())
        if len(items) != len(ids):
            raise GuardrailError("One or more guardrails were not found", 404)
        by_id = {item.id: item for item in items}
        return [by_id[item_id] for item_id in ids]

    def create(self, tenant_id: UUID, payload: GuardrailCreate) -> Guardrail:
        item = Guardrail(tenant_id=tenant_id, **payload.model_dump())
        self.db.add(item)
        return self._commit(item)

    def update(self, guardrail_id: UUID, tenant_id: UUID, payload: GuardrailUpdate) -> Guardrail:
        item = self.get(guardrail_id, tenant_id)
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
        return self._commit(item)

    def delete(self, guardrail_id: UUID, tenant_id: UUID) -> None:
        self.db.delete(self.get(guardrail_id, tenant_id))
        self.db.commit()

    def _commit(self, item: Guardrail) -> Guardrail:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise GuardrailError("A guardrail with this name already exists") from exc
        self.db.refresh(item)
        return item
