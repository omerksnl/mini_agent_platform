from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, AgentSkill, Skill
from app.schemas.agent import AgentCreate, AgentUpdate
from app.core.services.tool_service import ToolError, ToolService
from app.core.services.skill_service import SkillError, SkillService
from app.core.services.collection_service import CollectionError, CollectionService

AVAILABLE_SYSTEM_TOOLS = {"calculator", "current_datetime", "pdf_to_text"}


class AgentError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AgentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_agents(self, tenant_id: UUID) -> list[Agent]:
        stmt = (
            select(Agent)
            .where(Agent.tenant_id == tenant_id)
            .order_by(Agent.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_agent(self, agent_id: UUID, tenant_id: UUID) -> Agent:
        agent = self.db.scalar(
            select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id)
        )
        if not agent:
            raise AgentError("Agent not found", status_code=404)
        return agent

    def create_agent(self, tenant_id: UUID, payload: AgentCreate) -> Agent:
        self._validate_system_tools(payload.system_tools)
        if payload.agent_type == "normal" and payload.managed_agent_ids:
            raise AgentError("Normal agents cannot manage other agents")
        try:
            http_tools = ToolService(self.db).get_tools(payload.tool_ids, tenant_id)
        except ToolError as exc:
            raise AgentError(exc.message, exc.status_code) from exc
        skills = self._get_skills(payload.skill_ids, tenant_id)
        collections = self._get_collections(payload.collection_ids, tenant_id)
        managed_agents = self._get_managed_agents(payload.managed_agent_ids, tenant_id)
        self._validate_skill_requirements(skills, payload.system_tools, http_tools)
        agent = Agent(
            tenant_id=tenant_id,
            name=payload.name,
            agent_type=payload.agent_type,
            system_prompt=payload.system_prompt,
            model=payload.model,
            temperature=payload.temperature,
            system_tools=payload.system_tools,
            http_tools=http_tools,
            collections=collections,
            managed_agents=managed_agents,
        )
        agent.skill_links = [AgentSkill(skill=skill, position=index) for index, skill in enumerate(skills)]
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def update_agent(self, agent_id: UUID, tenant_id: UUID, payload: AgentUpdate) -> Agent:
        agent = self.get_agent(agent_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        tool_ids = data.pop("tool_ids", None)
        skill_ids = data.pop("skill_ids", None)
        collection_ids = data.pop("collection_ids", None)
        managed_agent_ids = data.pop("managed_agent_ids", None)
        target_type = data.get("agent_type", agent.agent_type)
        if target_type == "supervisor" and agent.supervisors:
            raise AgentError("A managed agent cannot become a supervisor")
        if target_type == "normal":
            requested_managed = managed_agent_ids if managed_agent_ids is not None else agent.managed_agent_ids
            if requested_managed:
                raise AgentError("Normal agents cannot manage other agents")
        if "system_tools" in data:
            self._validate_system_tools(data["system_tools"])
        if tool_ids is not None:
            try:
                agent.http_tools = ToolService(self.db).get_tools(tool_ids, tenant_id)
            except ToolError as exc:
                raise AgentError(exc.message, exc.status_code) from exc
        skills = self._get_skills(skill_ids, tenant_id) if skill_ids is not None else [link.skill for link in agent.skill_links]
        self._validate_skill_requirements(
            skills,
            data.get("system_tools", agent.system_tools),
            agent.http_tools,
        )
        if skill_ids is not None:
            agent.skill_links = [AgentSkill(skill=skill, position=index) for index, skill in enumerate(skills)]
        if collection_ids is not None:
            agent.collections = self._get_collections(collection_ids, tenant_id)
        if managed_agent_ids is not None:
            agent.managed_agents = self._get_managed_agents(managed_agent_ids, tenant_id, supervisor_id=agent.id)
        for key, value in data.items():
            setattr(agent, key, value)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def delete_agent(self, agent_id: UUID, tenant_id: UUID) -> None:
        agent = self.get_agent(agent_id, tenant_id)
        self.db.delete(agent)
        self.db.commit()

    @staticmethod
    def _validate_system_tools(names: list[str]) -> None:
        if len(names) != len(set(names)) or not set(names).issubset(AVAILABLE_SYSTEM_TOOLS):
            raise AgentError("Invalid system tool selection")

    def _get_skills(self, skill_ids: list[UUID], tenant_id: UUID) -> list[Skill]:
        try:
            skills = SkillService(self.db).get_skills(skill_ids, tenant_id)
        except SkillError as exc:
            raise AgentError(exc.message, exc.status_code) from exc
        if any(not skill.is_active for skill in skills):
            raise AgentError("Inactive skills cannot be assigned")
        return skills

    def _get_collections(self, collection_ids: list[UUID], tenant_id: UUID) -> list:
        try:
            return CollectionService(self.db).get_many(collection_ids, tenant_id)
        except CollectionError as exc:
            raise AgentError(exc.message, exc.status_code) from exc

    def _get_managed_agents(
        self,
        agent_ids: list[UUID],
        tenant_id: UUID,
        supervisor_id: UUID | None = None,
    ) -> list[Agent]:
        if not agent_ids:
            return []
        unique_ids = list(dict.fromkeys(agent_ids))
        if len(unique_ids) != len(agent_ids):
            raise AgentError("Managed agent selection contains duplicates")
        if supervisor_id is not None and supervisor_id in unique_ids:
            raise AgentError("A supervisor cannot manage itself")
        agents = list(self.db.scalars(select(Agent).where(
            Agent.id.in_(unique_ids), Agent.tenant_id == tenant_id
        )).all())
        if len(agents) != len(unique_ids):
            raise AgentError("One or more managed agents were not found", 404)
        by_id = {item.id: item for item in agents}
        ordered = [by_id[item_id] for item_id in unique_ids]
        if any(item.agent_type != "normal" for item in ordered):
            raise AgentError("Supervisors can manage only normal agents")
        return ordered

    @staticmethod
    def _validate_skill_requirements(skills: list[Skill], system_tools: list[str], http_tools: list) -> None:
        available_system = set(system_tools)
        available_http = {tool.id for tool in http_tools}
        missing: list[str] = []
        for skill in skills:
            missing_names = sorted([
                *(set(skill.required_system_tools) - available_system),
                *(tool.name for tool in skill.http_tools if tool.id not in available_http),
            ])
            if missing_names:
                missing.append(f"{skill.name}: {', '.join(missing_names)}")
        if missing:
            raise AgentError("Skill requirements are not selected on the agent: " + "; ".join(missing))
