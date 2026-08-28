from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.services.tool_service import ToolError, ToolService
from app.models import Skill
from app.schemas.skill import SkillCreate, SkillUpdate

AVAILABLE_SYSTEM_TOOLS = {"calculator", "current_datetime", "pdf_to_text", "text_to_pdf"}


class SkillError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SkillService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_skills(self, tenant_id: UUID) -> list[Skill]:
        return list(self.db.scalars(
            select(Skill).where(Skill.tenant_id == tenant_id).order_by(Skill.created_at.desc())
        ).all())

    def get_skill(self, skill_id: UUID, tenant_id: UUID) -> Skill:
        skill = self.db.scalar(select(Skill).where(Skill.id == skill_id, Skill.tenant_id == tenant_id))
        if not skill:
            raise SkillError("Skill not found", status_code=404)
        return skill

    def get_skills(self, skill_ids: list[UUID], tenant_id: UUID) -> list[Skill]:
        if not skill_ids:
            return []
        skills = list(self.db.scalars(select(Skill).where(
            Skill.id.in_(skill_ids), Skill.tenant_id == tenant_id
        )).all())
        if len(skills) != len(set(skill_ids)):
            raise SkillError("One or more skills were not found")
        by_id = {skill.id: skill for skill in skills}
        return [by_id[skill_id] for skill_id in skill_ids]

    def create_skill(self, tenant_id: UUID, payload: SkillCreate) -> Skill:
        self._validate_system_tools(payload.required_system_tools)
        http_tools = self._get_http_tools(payload.required_tool_ids, tenant_id)
        skill = Skill(
            tenant_id=tenant_id,
            name=payload.name,
            description=payload.description,
            instructions=payload.instructions,
            output_schema=payload.output_schema,
            required_system_tools=payload.required_system_tools,
            is_active=payload.is_active,
            http_tools=http_tools,
        )
        self.db.add(skill)
        self._commit(skill)
        return skill

    def update_skill(self, skill_id: UUID, tenant_id: UUID, payload: SkillUpdate) -> Skill:
        skill = self.get_skill(skill_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        tool_ids = data.pop("required_tool_ids", None)
        if "required_system_tools" in data:
            self._validate_system_tools(data["required_system_tools"])
        if tool_ids is not None:
            skill.http_tools = self._get_http_tools(tool_ids, tenant_id)
        for key, value in data.items():
            setattr(skill, key, value)
        self._commit(skill)
        return skill

    def delete_skill(self, skill_id: UUID, tenant_id: UUID) -> None:
        skill = self.get_skill(skill_id, tenant_id)
        self.db.delete(skill)
        self.db.commit()

    def _get_http_tools(self, tool_ids: list[UUID], tenant_id: UUID):
        try:
            return ToolService(self.db).get_tools(tool_ids, tenant_id)
        except ToolError as exc:
            raise SkillError(exc.message, exc.status_code) from exc

    @staticmethod
    def _validate_system_tools(names: list[str]) -> None:
        if not set(names).issubset(AVAILABLE_SYSTEM_TOOLS):
            raise SkillError("Invalid required system tool selection")

    def _commit(self, skill: Skill) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise SkillError("A skill with this name already exists", status_code=409) from exc
        self.db.refresh(skill)
