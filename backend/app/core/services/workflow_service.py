from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Agent, HttpTool, RemoteAgent, Workflow, WorkflowRoute, WorkflowStep
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowRouteInput,
    WorkflowStepInput,
    WorkflowUpdate,
)


class WorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _load_options() -> tuple:
        return (
            selectinload(Workflow.steps),
            selectinload(Workflow.routes).selectinload(WorkflowRoute.source_step),
            selectinload(Workflow.routes).selectinload(WorkflowRoute.target_step),
        )

    def list_workflows(self, tenant_id: UUID) -> list[Workflow]:
        stmt = (
            select(Workflow)
            .where(Workflow.tenant_id == tenant_id)
            .options(*self._load_options())
            .order_by(Workflow.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_workflow(self, workflow_id: UUID, tenant_id: UUID) -> Workflow:
        workflow = self.db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
            .options(*self._load_options())
        )
        if not workflow:
            raise WorkflowError("Workflow not found", 404)
        return workflow

    def create_workflow(self, tenant_id: UUID, payload: WorkflowCreate, user_id: UUID | None = None) -> Workflow:
        self._ensure_name_available(tenant_id, payload.name)
        self._validate_definition(tenant_id, payload.steps, payload.routes, user_id)
        workflow = Workflow(
            tenant_id=tenant_id,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
        )
        self.db.add(workflow)
        self.db.flush()
        self._set_definition(workflow, payload.steps, payload.routes)
        self._commit()
        return self.get_workflow(workflow.id, tenant_id)

    def update_workflow(
        self, workflow_id: UUID, tenant_id: UUID, payload: WorkflowUpdate, user_id: UUID | None = None
    ) -> Workflow:
        workflow = self.get_workflow(workflow_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        steps = data.pop("steps", None)
        routes = data.pop("routes", None)
        if "name" in data and data["name"] != workflow.name:
            self._ensure_name_available(tenant_id, data["name"], workflow.id)
        if steps is not None and routes is not None:
            step_inputs = [WorkflowStepInput.model_validate(item) for item in steps]
            route_inputs = [WorkflowRouteInput.model_validate(item) for item in routes]
            self._validate_definition(tenant_id, step_inputs, route_inputs, user_id)
            workflow.routes.clear()
            self.db.flush()
            workflow.steps.clear()
            self.db.flush()
            self._set_definition(workflow, step_inputs, route_inputs)
        for key, value in data.items():
            setattr(workflow, key, value)
        self._commit()
        return self.get_workflow(workflow.id, tenant_id)

    def delete_workflow(self, workflow_id: UUID, tenant_id: UUID) -> None:
        workflow = self.get_workflow(workflow_id, tenant_id)
        self.db.delete(workflow)
        self._commit()

    def _set_definition(
        self,
        workflow: Workflow,
        steps: list[WorkflowStepInput],
        routes: list[WorkflowRouteInput],
    ) -> None:
        step_models = [
            WorkflowStep(
                step_key=item.step_key,
                name=item.name,
                step_type=item.step_type,
                position=item.position,
                agent_id=item.agent_id,
                remote_agent_id=item.remote_agent_id,
                http_tool_id=item.http_tool_id,
                system_tool_name=item.system_tool_name,
                config=item.config,
            )
            for item in sorted(steps, key=lambda value: value.position)
        ]
        workflow.steps = step_models
        self.db.flush()
        by_key = {item.step_key: item for item in step_models}
        workflow.routes = [
            WorkflowRoute(
                source_step_id=by_key[item.source_step_key].id,
                target_step_id=by_key[item.target_step_key].id,
                condition=item.condition,
                priority=item.priority,
                config=item.config,
            )
            for item in routes
        ]

    def _validate_definition(
        self,
        tenant_id: UUID,
        steps: list[WorkflowStepInput],
        routes: list[WorkflowRouteInput],
        user_id: UUID | None = None,
    ) -> None:
        keys = [item.step_key for item in steps]
        positions = [item.position for item in steps]
        if len(keys) != len(set(keys)):
            raise WorkflowError("Workflow step keys must be unique")
        if len(positions) != len(set(positions)):
            raise WorkflowError("Workflow step positions must be unique")

        key_set = set(keys)
        edges: list[tuple[str, str]] = []
        route_signatures: set[tuple[str, str, str]] = set()
        for route in routes:
            if route.source_step_key not in key_set or route.target_step_key not in key_set:
                raise WorkflowError("Workflow route references an unknown step")
            if route.source_step_key == route.target_step_key:
                raise WorkflowError("Workflow routes cannot target the same step")
            signature = (route.source_step_key, route.target_step_key, route.condition)
            if signature in route_signatures:
                raise WorkflowError("Workflow contains a duplicate route")
            route_signatures.add(signature)
            edges.append((route.source_step_key, route.target_step_key))
        self._reject_cycles(keys, edges)

        agent_ids = list({item.agent_id for item in steps if item.agent_id is not None})
        if agent_ids:
            found_agents = set(self.db.scalars(select(Agent.id).where(
                Agent.id.in_(agent_ids), Agent.tenant_id == tenant_id
            )).all())
            if found_agents != set(agent_ids):
                raise WorkflowError("One or more workflow agents were not found", 404)

        remote_ids = list({item.remote_agent_id for item in steps if item.remote_agent_id is not None})
        if remote_ids:
            if user_id is None:
                raise WorkflowError("User context is required for remote workflow agents")
            found_remote = set(self.db.scalars(select(RemoteAgent.id).where(
                RemoteAgent.id.in_(remote_ids),
                RemoteAgent.tenant_id == tenant_id,
                RemoteAgent.owner_user_id == user_id,
            )).all())
            if found_remote != set(remote_ids):
                raise WorkflowError("One or more remote workflow agents were not found", 404)

        tool_ids = list({item.http_tool_id for item in steps if item.http_tool_id is not None})
        if tool_ids:
            found_tools = set(self.db.scalars(select(HttpTool.id).where(
                HttpTool.id.in_(tool_ids), HttpTool.tenant_id == tenant_id
            )).all())
            if found_tools != set(tool_ids):
                raise WorkflowError("One or more workflow tools were not found", 404)

    @staticmethod
    def _reject_cycles(nodes: list[str], edges: list[tuple[str, str]]) -> None:
        adjacency = {node: [] for node in nodes}
        for source, target in edges:
            adjacency[source].append(target)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise WorkflowError("Workflow routes must not contain cycles")
            if node in visited:
                return
            visiting.add(node)
            for target in adjacency[node]:
                visit(target)
            visiting.remove(node)
            visited.add(node)

        for node in nodes:
            visit(node)

    def _ensure_name_available(
        self, tenant_id: UUID, name: str, exclude_id: UUID | None = None
    ) -> None:
        stmt = select(Workflow.id).where(
            Workflow.tenant_id == tenant_id, Workflow.name == name
        )
        if exclude_id is not None:
            stmt = stmt.where(Workflow.id != exclude_id)
        if self.db.scalar(stmt):
            raise WorkflowError("A workflow with this name already exists", 409)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise WorkflowError("Workflow could not be saved", 409) from exc
