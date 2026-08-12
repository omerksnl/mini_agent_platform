import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.services.llm_service import LLMClient, LLMResult
from app.core.services.workflow_service import WorkflowError, WorkflowService
from app.core.tools import SYSTEM_TOOL_MAP
from app.core.tools.http_tools import build_http_tool
from app.models import Workflow, WorkflowRoute, WorkflowRun, WorkflowStep, WorkflowStepRun


MAX_WORKFLOW_STEPS = 50


class WorkflowExecutionService:
    def __init__(self, db: Session, llm_client: LLMClient | None) -> None:
        self.db = db
        self.llm_client = llm_client

    def start(self, workflow_id: UUID, tenant_id: UUID, input_data: dict) -> WorkflowRun:
        workflow = WorkflowService(self.db).get_workflow(workflow_id, tenant_id)
        if not workflow.is_active:
            raise WorkflowError("Workflow is inactive", 409)
        start_step = self._start_step(workflow)
        run = WorkflowRun(
            tenant_id=tenant_id,
            workflow_id=workflow.id,
            status="running",
            input_data=input_data,
            output_data={"context": input_data, "steps": {}},
        )
        self.db.add(run)
        self.db.commit()
        return self._execute(run, workflow, start_step)

    def resume(self, run_id: UUID, tenant_id: UUID, input_data: dict) -> WorkflowRun:
        run = self.get_run(run_id, tenant_id)
        if run.status != "waiting" or run.current_step is None:
            raise WorkflowError("Workflow run is not waiting for input", 409)
        waiting = next((item for item in reversed(run.step_runs) if item.status == "waiting"), None)
        if waiting is None or waiting.workflow_step_id != run.current_step_id:
            raise WorkflowError("Waiting workflow step was not found", 409)
        now = datetime.now(timezone.utc)
        waiting.status = "completed"
        waiting.output_data = {"human_input": input_data}
        waiting.completed_at = now
        state = dict(run.output_data)
        state["last_output"] = waiting.output_data
        state.setdefault("steps", {})[waiting.step_key] = waiting.output_data
        run.output_data = state
        run.status = "running"
        next_step = self._next_step(run.workflow, run.current_step, "input_available")
        self.db.commit()
        if next_step is None:
            return self._complete(run)
        return self._execute(run, run.workflow, next_step)

    def get_run(self, run_id: UUID, tenant_id: UUID) -> WorkflowRun:
        run = self.db.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.id == run_id, WorkflowRun.tenant_id == tenant_id)
            .options(
                selectinload(WorkflowRun.step_runs),
                selectinload(WorkflowRun.current_step),
                selectinload(WorkflowRun.workflow).selectinload(Workflow.steps),
                selectinload(WorkflowRun.workflow).selectinload(Workflow.routes).selectinload(WorkflowRoute.source_step),
                selectinload(WorkflowRun.workflow).selectinload(Workflow.routes).selectinload(WorkflowRoute.target_step),
            )
        )
        if run is None:
            raise WorkflowError("Workflow run not found", 404)
        return run

    def list_runs(self, workflow_id: UUID, tenant_id: UUID) -> list[WorkflowRun]:
        WorkflowService(self.db).get_workflow(workflow_id, tenant_id)
        return list(self.db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id, WorkflowRun.tenant_id == tenant_id)
            .options(selectinload(WorkflowRun.step_runs))
            .order_by(WorkflowRun.created_at.desc())
        ).all())

    def _execute(self, run: WorkflowRun, workflow: Workflow, step: WorkflowStep) -> WorkflowRun:
        executed = len(run.step_runs)
        current: WorkflowStep | None = step
        while current is not None:
            if executed >= MAX_WORKFLOW_STEPS:
                return self._fail_run(run, "Workflow execution limit reached")
            run.current_step_id = current.id
            step_run = WorkflowStepRun(
                workflow_run=run,
                workflow_step_id=current.id,
                sequence=executed,
                step_key=current.step_key,
                step_name=current.name,
                step_type=current.step_type,
                status="running",
                input_data=dict(run.output_data),
                output_data={},
            )
            self.db.add(step_run)
            self.db.commit()
            if current.step_type == "human_wait":
                step_run.status = "waiting"
                run.status = "waiting"
                self.db.commit()
                return self.get_run(run.id, run.tenant_id)
            try:
                output, cost = self._execute_step(current, run.output_data)
                step_run.status = "completed"
                step_run.output_data = output
                step_run.api_cost_usd = cost
                step_run.completed_at = datetime.now(timezone.utc)
                run.total_api_cost_usd += cost
                state = dict(run.output_data)
                state["last_output"] = output
                state.setdefault("steps", {})[current.step_key] = output
                run.output_data = state
                next_step = self._next_step(workflow, current, "success")
            except Exception as exc:  # execution failures are persisted for inspection
                message = str(exc) or exc.__class__.__name__
                step_run.status = "failed"
                step_run.error = message
                step_run.completed_at = datetime.now(timezone.utc)
                state = dict(run.output_data)
                state["last_error"] = message
                run.output_data = state
                next_step = self._next_step(workflow, current, "failure")
                if next_step is None:
                    self.db.commit()
                    return self._fail_run(run, message)
            self.db.commit()
            current = next_step
            executed += 1
        return self._complete(run)

    def _execute_step(self, step: WorkflowStep, state: dict) -> tuple[dict, float]:
        if step.step_type == "agent" and step.agent is not None:
            if self.llm_client is None:
                raise WorkflowError("LLM client is unavailable")
            request = state.get("request") or state.get("prompt") or "Continue this workflow task."
            context = json.dumps(state, ensure_ascii=False, default=str)
            result = self.llm_client.complete(
                step.agent,
                [{"role": "user", "content": f"{request}\n\nWORKFLOW CONTEXT\n{context}"}],
                step.agent.http_tools,
                db=self.db if step.agent.collections or step.agent.agent_type == "supervisor" else None,
            )
            if isinstance(result, LLMResult):
                return {
                    "content": result.content,
                    "used_tools": result.used_tools,
                    "used_skills": result.used_skills,
                    "used_agents": result.used_agents,
                }, result.api_cost_usd
            return {"content": str(result)}, 0.0
        arguments = dict(step.config.get("arguments", {}))
        if not arguments and isinstance(state.get("arguments"), dict):
            arguments = state["arguments"]
        if step.step_type == "http_tool" and step.http_tool is not None:
            return {"result": build_http_tool(step.http_tool).invoke(arguments)}, 0.0
        if step.step_type == "system_tool" and step.system_tool_name is not None:
            tool = SYSTEM_TOOL_MAP.get(step.system_tool_name)
            if tool is None:
                raise WorkflowError(f"Unsupported workflow system tool: {step.system_tool_name}")
            return {"result": tool.invoke(arguments)}, 0.0
        raise WorkflowError(f"Workflow step {step.step_key} has no executable target")

    @staticmethod
    def _start_step(workflow: Workflow) -> WorkflowStep:
        targets = {route.target_step_id for route in workflow.routes}
        starts = [step for step in workflow.steps if step.id not in targets]
        if not starts:
            raise WorkflowError("Workflow has no start step")
        if len(starts) != 1:
            raise WorkflowError("Workflow must have exactly one start step")
        return starts[0]

    @staticmethod
    def _next_step(workflow: Workflow, step: WorkflowStep, event: str) -> WorkflowStep | None:
        routes = sorted(
            (route for route in workflow.routes if route.source_step_id == step.id),
            key=lambda item: item.priority,
        )
        route = next((item for item in routes if item.condition == event), None)
        if route is None:
            route = next((item for item in routes if item.condition == "always"), None)
        return route.target_step if route else None

    def _complete(self, run: WorkflowRun) -> WorkflowRun:
        run.status = "completed"
        run.current_step_id = None
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get_run(run.id, run.tenant_id)

    def _fail_run(self, run: WorkflowRun, error: str) -> WorkflowRun:
        run.status = "failed"
        run.error = error
        run.current_step_id = None
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get_run(run.id, run.tenant_id)
