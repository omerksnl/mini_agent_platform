from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, AgentPromptVersion, AgentSkill, Skill
from app.schemas.agent import AgentCreate, AgentUpdate
from app.core.services.tool_service import ToolError, ToolService
from app.core.services.skill_service import SkillError, SkillService
from app.core.services.collection_service import CollectionError, CollectionService

AVAILABLE_SYSTEM_TOOLS = {"calculator", "current_datetime", "pdf_to_text", "text_to_pdf"}


class AgentError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AgentService:
    PROMPT_VERSION_LIMIT = 3

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
        self._validate_relationship_shape(
            payload.agent_type, payload.managed_agent_ids, payload.router_target_ids
        )
        try:
            http_tools = ToolService(self.db).get_tools(payload.tool_ids, tenant_id)
        except ToolError as exc:
            raise AgentError(exc.message, exc.status_code) from exc
        skills = self._get_skills(payload.skill_ids, tenant_id)
        collections = self._get_collections(payload.collection_ids, tenant_id)
        managed_agents = self._get_managed_agents(payload.managed_agent_ids, tenant_id)
        router_targets = self._get_router_targets(payload.router_target_ids, tenant_id)
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
            router_targets=router_targets,
        )
        agent.skill_links = [AgentSkill(skill=skill, position=index) for index, skill in enumerate(skills)]
        self.db.add(agent)
        self.db.flush()
        initial_version = self._record_prompt_version(agent, payload.system_prompt)
        agent.active_prompt_version_id = initial_version.id
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def update_agent(self, agent_id: UUID, tenant_id: UUID, payload: AgentUpdate) -> Agent:
        agent = self.get_agent(agent_id, tenant_id)
        agent_prompt_before_update = agent.system_prompt
        data = payload.model_dump(exclude_unset=True)
        tool_ids = data.pop("tool_ids", None)
        skill_ids = data.pop("skill_ids", None)
        collection_ids = data.pop("collection_ids", None)
        managed_agent_ids = data.pop("managed_agent_ids", None)
        router_target_ids = data.pop("router_target_ids", None)
        next_prompt = data.get("system_prompt")
        target_type = data.get("agent_type", agent.agent_type)
        if target_type != "normal" and (agent.supervisors or agent.routers):
            raise AgentError("An agent used by a multi-agent system must remain a normal agent")
        requested_managed = managed_agent_ids if managed_agent_ids is not None else agent.managed_agent_ids
        requested_targets = router_target_ids if router_target_ids is not None else agent.router_target_ids
        self._validate_relationship_shape(target_type, requested_managed, requested_targets)
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
        if router_target_ids is not None:
            agent.router_targets = self._get_router_targets(router_target_ids, tenant_id, router_id=agent.id)
        for key, value in data.items():
            setattr(agent, key, value)
        if next_prompt is not None and next_prompt != agent_prompt_before_update:
            new_version = self._record_prompt_version(agent, next_prompt)
            agent.active_prompt_version_id = new_version.id
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def list_prompt_versions(self, agent_id: UUID, tenant_id: UUID) -> list[AgentPromptVersion]:
        self.get_agent(agent_id, tenant_id)
        stmt = (
            select(AgentPromptVersion)
            .where(AgentPromptVersion.agent_id == agent_id)
            .order_by(AgentPromptVersion.version_number.desc())
        )
        return list(self.db.scalars(stmt).all())

    def restore_prompt_version(
        self, agent_id: UUID, version_id: UUID, tenant_id: UUID
    ) -> Agent:
        agent = self.get_agent(agent_id, tenant_id)
        version = self.db.scalar(
            select(AgentPromptVersion).where(
                AgentPromptVersion.id == version_id,
                AgentPromptVersion.agent_id == agent.id,
            )
        )
        if not version:
            raise AgentError("Prompt version not found", status_code=404)
        if version.id != agent.active_prompt_version_id:
            agent.system_prompt = version.system_prompt
            agent.active_prompt_version_id = version.id
            self.db.commit()
            self.db.refresh(agent)
        return agent

    def _record_prompt_version(self, agent: Agent, system_prompt: str) -> AgentPromptVersion:
        latest_number = self.db.scalar(
            select(func.max(AgentPromptVersion.version_number)).where(
                AgentPromptVersion.agent_id == agent.id
            )
        ) or 0
        version = AgentPromptVersion(
            agent_id=agent.id,
            version_number=latest_number + 1,
            system_prompt=system_prompt,
        )
        self.db.add(version)
        self.db.flush()
        stale_versions = list(self.db.scalars(
            select(AgentPromptVersion)
            .where(AgentPromptVersion.agent_id == agent.id)
            .order_by(AgentPromptVersion.version_number.desc())
            .offset(self.PROMPT_VERSION_LIMIT)
        ).all())
        for stale in stale_versions:
            self.db.delete(stale)
        return version

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

    def _get_router_targets(
        self,
        agent_ids: list[UUID],
        tenant_id: UUID,
        router_id: UUID | None = None,
    ) -> list[Agent]:
        if not agent_ids:
            return []
        unique_ids = list(dict.fromkeys(agent_ids))
        if len(unique_ids) != len(agent_ids):
            raise AgentError("Router target selection contains duplicates")
        if router_id is not None and router_id in unique_ids:
            raise AgentError("A router cannot target itself")
        agents = list(self.db.scalars(select(Agent).where(
            Agent.id.in_(unique_ids), Agent.tenant_id == tenant_id
        )).all())
        if len(agents) != len(unique_ids):
            raise AgentError("One or more router targets were not found", 404)
        by_id = {item.id: item for item in agents}
        ordered = [by_id[item_id] for item_id in unique_ids]
        if any(item.agent_type != "normal" for item in ordered):
            raise AgentError("Routers can target only normal agents")
        return ordered

    @staticmethod
    def _validate_relationship_shape(
        agent_type: str,
        managed_agent_ids: list,
        router_target_ids: list,
    ) -> None:
        if agent_type == "normal" and (managed_agent_ids or router_target_ids):
            raise AgentError("Normal agents cannot manage or route to other agents")
        if agent_type == "supervisor" and router_target_ids:
            raise AgentError("Supervisors cannot have router targets")
        if agent_type == "router" and managed_agent_ids:
            raise AgentError("Routers cannot manage supervisor agents")

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
