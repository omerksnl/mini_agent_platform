import json
import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.services.llm_service import LLMClient, LLMResult
from app.core.services.attachment_service import AttachmentError, AttachmentService
from app.core.services.workflow_service import WorkflowError, WorkflowService
from app.core.services.collection_service import CollectionService
from app.core.services.generated_file_service import GeneratedFileService
from app.core.services.report_pdf_service import ReportPdfService
from app.core.services.remote_agent_service import RemoteAgentService
from app.core.tools import SYSTEM_TOOL_MAP
from app.core.tools.http_tools import build_http_tool
from app.core.observability import bind_trace_context
from app.models import (
    Workflow,
    WorkflowArtifact,
    WorkflowRoute,
    WorkflowRun,
    WorkflowStep,
    WorkflowStepRun,
)


MAX_WORKFLOW_STEPS = 50


class WorkflowExecutionService:
    def __init__(self, db: Session, llm_client: LLMClient | None) -> None:
        self.db = db
        self.llm_client = llm_client

    def start(
        self,
        workflow_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        input_data: dict,
        attachment_ids: list[UUID] | None = None,
    ) -> WorkflowRun:
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
        self.db.flush()
        try:
            attachments = AttachmentService(self.db).claim_for_workflow(
                attachment_ids or [], tenant_id, user_id, run.id
            )
        except AttachmentError as exc:
            self.db.rollback()
            raise WorkflowError(exc.message, exc.status_code) from exc
        artifact_input = dict(input_data)
        if attachments:
            artifact_input["attachments"] = [
                {"id": str(item.id), "filename": item.original_name, "content_type": item.content_type}
                for item in attachments
            ]
        run.artifacts.append(WorkflowArtifact(
            tenant_id=tenant_id,
            sequence=0,
            artifact_key="workflow_input",
            name="Workflow input",
            artifact_type="workflow_input",
            data=artifact_input,
        ))
        self.db.commit()
        return self._execute(run, workflow, start_step)

    def start_deferred(
        self,
        workflow_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        input_data: dict,
        attachment_ids: list[UUID] | None = None,
    ) -> WorkflowRun:
        """Create a visible run without blocking the HTTP response on LLM work."""
        workflow = WorkflowService(self.db).get_workflow(workflow_id, tenant_id)
        if not workflow.is_active:
            raise WorkflowError("Workflow is inactive", 409)
        start_step = self._start_step(workflow)
        run = WorkflowRun(
            tenant_id=tenant_id,
            workflow_id=workflow.id,
            status="running",
            current_step_id=start_step.id,
            input_data=input_data,
            output_data={"context": input_data, "steps": {}},
        )
        self.db.add(run)
        self.db.flush()
        try:
            attachments = AttachmentService(self.db).claim_for_workflow(
                attachment_ids or [], tenant_id, user_id, run.id
            )
        except AttachmentError as exc:
            self.db.rollback()
            raise WorkflowError(exc.message, exc.status_code) from exc
        artifact_input = dict(input_data)
        if attachments:
            artifact_input["attachments"] = [
                {"id": str(item.id), "filename": item.original_name, "content_type": item.content_type}
                for item in attachments
            ]
        run.artifacts.append(WorkflowArtifact(
            tenant_id=tenant_id,
            sequence=0,
            artifact_key="workflow_input",
            name="Workflow input",
            artifact_type="workflow_input",
            data=artifact_input,
        ))
        self.db.commit()
        return self.get_run(run.id, tenant_id)

    def execute_deferred(self, run_id: UUID, tenant_id: UUID) -> WorkflowRun:
        run = self.get_run(run_id, tenant_id)
        if run.status != "running" or run.current_step is None:
            return run
        return self._execute(run, run.workflow, run.current_step)

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
        self._store_artifact(
            run,
            waiting,
            waiting.step_key,
            waiting.step_name,
            "human_input",
            waiting.output_data,
        )
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

    def resume_deferred(self, run_id: UUID, tenant_id: UUID, input_data: dict) -> WorkflowRun:
        run = self.get_run(run_id, tenant_id)
        if run.status != "waiting" or run.current_step is None:
            raise WorkflowError("Workflow run is not waiting for input", 409)
        waiting = next((item for item in reversed(run.step_runs) if item.status == "waiting"), None)
        if waiting is None or waiting.workflow_step_id != run.current_step_id:
            raise WorkflowError("Waiting workflow step was not found", 409)
        waiting.status = "completed"
        waiting.output_data = {"human_input": input_data}
        waiting.completed_at = datetime.now(timezone.utc)
        self._store_artifact(run, waiting, waiting.step_key, waiting.step_name, "human_input", waiting.output_data)
        state = dict(run.output_data)
        state["last_output"] = waiting.output_data
        state.setdefault("steps", {})[waiting.step_key] = waiting.output_data
        run.output_data = state
        next_step = self._next_step(run.workflow, run.current_step, "input_available")
        if next_step is None:
            return self._complete(run)
        run.status = "running"
        run.current_step_id = next_step.id
        self.db.commit()
        return self.get_run(run.id, tenant_id)

    def get_run(self, run_id: UUID, tenant_id: UUID) -> WorkflowRun:
        run = self.db.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.id == run_id, WorkflowRun.tenant_id == tenant_id)
            .options(
                selectinload(WorkflowRun.step_runs),
                selectinload(WorkflowRun.artifacts),
                selectinload(WorkflowRun.attachments),
                selectinload(WorkflowRun.current_step),
                selectinload(WorkflowRun.workflow).selectinload(Workflow.steps),
                selectinload(WorkflowRun.workflow).selectinload(Workflow.routes).selectinload(WorkflowRoute.source_step),
                selectinload(WorkflowRun.workflow).selectinload(Workflow.routes).selectinload(WorkflowRoute.target_step),
            )
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise WorkflowError("Workflow run not found", 404)
        return run

    def list_runs(self, workflow_id: UUID, tenant_id: UUID) -> list[WorkflowRun]:
        WorkflowService(self.db).get_workflow(workflow_id, tenant_id)
        return list(self.db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id, WorkflowRun.tenant_id == tenant_id)
            .options(
                selectinload(WorkflowRun.step_runs),
                selectinload(WorkflowRun.artifacts),
                selectinload(WorkflowRun.attachments),
            )
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
                with bind_trace_context(
                    workflow_run_id=run.id,
                    workflow_id=workflow.id,
                    workflow_name=workflow.name,
                    tenant_id=run.tenant_id,
                    step_key=current.step_key,
                ):
                    output, cost = self._execute_step(
                        current, self._state_with_artifacts(run), run.attachments
                    )
                step_run.status = "completed"
                step_run.output_data = output
                step_run.api_cost_usd = cost
                step_run.completed_at = datetime.now(timezone.utc)
                run.total_api_cost_usd += cost
                artifact_type = (
                    "agent_output" if current.step_type in {"agent", "remote_agent"}
                    else "generated_file" if current.step_type == "report"
                    else "tool_output"
                )
                self._store_artifact(
                    run,
                    step_run,
                    current.step_key,
                    current.name,
                    artifact_type,
                    output,
                )
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

    def _execute_step(self, step: WorkflowStep, state: dict, attachments: list) -> tuple[dict, float]:
        if step.step_type == "remote_agent" and step.remote_agent is not None:
            artifacts = [
                {"key": item.artifact_key, "name": item.name, "type": item.artifact_type, "data": item.data}
                for item in state.get("artifacts", [])
            ]
            requested_keys = step.config.get("input_artifact_keys")
            if isinstance(requested_keys, list) and requested_keys:
                allowed = {str(key) for key in requested_keys}
                artifacts = [item for item in artifacts if item["key"] in allowed]
            task = str(step.config.get("task_instructions", "")).strip() or f"Execute workflow step '{step.name}'."
            context = json.dumps(artifacts, ensure_ascii=False, default=str, separators=(",", ":"))
            text, context_id, cost = RemoteAgentService(self.db).send(
                step.remote_agent.id,
                step.remote_agent.tenant_id,
                step.remote_agent.owner_user_id,
                f"{task}\n\nWORKFLOW ARTIFACTS\n{context}",
                [item.id for item in attachments],
            )
            return {"content": text, "used_agents": [step.remote_agent.name], "a2a_context_id": context_id}, cost
        if step.step_type == "agent" and step.agent is not None:
            if self.llm_client is None:
                raise WorkflowError("LLM client is unavailable")
            artifacts = [
                {
                    "key": artifact.artifact_key,
                    "name": artifact.name,
                    "type": artifact.artifact_type,
                    "data": artifact.data,
                }
                for artifact in state.get("artifacts", [])
            ]
            has_agent_output = any(
                artifact.get("type") == "agent_output" for artifact in artifacts
            )
            requested_keys = step.config.get("input_artifact_keys")
            if isinstance(requested_keys, list) and requested_keys:
                allowed_keys = {str(key) for key in requested_keys}
                artifacts = [artifact for artifact in artifacts if artifact["key"] in allowed_keys]
            elif has_agent_output:
                # The original request/attachment metadata has already been transformed
                # into an agent artifact. Avoid paying to send it again downstream.
                artifacts = [artifact for artifact in artifacts if artifact["type"] != "workflow_input"]
            context = json.dumps(artifacts, ensure_ascii=False, default=str, separators=(",", ":"))
            task_instructions = str(step.config.get("task_instructions", "")).strip()
            use_collections = step.config.get("use_collections", True)
            if not isinstance(use_collections, bool):
                use_collections = True
            collection_mode = step.config.get(
                "collection_mode", "search" if use_collections else "off"
            )
            if collection_mode not in {"off", "search", "full_context"}:
                collection_mode = "search" if use_collections else "off"
            full_collection_context = ""
            if collection_mode == "full_context" and step.agent.collections:
                full_collection_context = CollectionService(self.db).read_all_text(
                    step.agent.tenant_id,
                    [collection.id for collection in step.agent.collections],
                )
            elif collection_mode == "search" and step.agent.collections:
                search_query_parts = [task_instructions, step.name]
                # Human waits often capture different pieces of routing context
                # (for example, a selected role and later interview answers).
                # Include all of them so semantic retrieval is not biased toward
                # only the most recent response.
                for artifact in artifacts:
                    if artifact["type"] == "human_input":
                        search_query_parts.append(
                            f"{artifact['name']}: "
                            + json.dumps(artifact["data"], ensure_ascii=False)[:2_000]
                        )
                full_collection_context = CollectionService(self.db).search_text(
                    step.agent.tenant_id,
                    [collection.id for collection in step.agent.collections],
                    "\n".join(part for part in search_query_parts if part),
                )
            request = (
                state.get("request") or state.get("prompt") or f"Execute the {step.name} step."
                if not has_agent_output
                else (
                    f"Execute only your assigned specialist task for workflow step '{step.name}'. "
                    "Use the relevant workflow artifacts below as your inputs. "
                    "Do not repeat an earlier agent's task."
                )
            )
            step_attachments = (
                attachments
                if "pdf_to_text" in step.agent.system_tools and not has_agent_output
                else None
            )
            result = self.llm_client.complete(
                step.agent,
                [{"role": "user", "content": (
                    f"{request}\n\nWORKFLOW ARTIFACTS\n{context}\n\n"
                    "Use every relevant artifact. Do not discard earlier artifacts merely because a newer one exists."
                    + (f"\n\nNODE TASK INSTRUCTIONS\n{task_instructions}" if task_instructions else "")
                    + (f"\n\nPREFETCHED COLLECTION CONTEXT\n{full_collection_context}" if full_collection_context else "")
                )}],
                step.agent.http_tools,
                attachments=step_attachments,
                db=self.db if attachments or step.agent.collections or step.agent.agent_type == "supervisor" else None,
                skip_response_validation=True,
                # Workflow nodes are deterministic. Collection retrieval is done
                # above so the model does not need a router/tool-planning cycle.
                use_collections=False,
                skip_request_routing=True,
                max_output_tokens=step.config.get("max_output_tokens"),
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
        if step.step_type == "report":
            input_key = str(step.config.get("input_artifact_key", ""))
            artifact = next(
                (item for item in state.get("artifacts", []) if item.artifact_key == input_key),
                None,
            )
            step_outputs = state.get("steps", {})
            fallback_data = step_outputs.get(input_key) if isinstance(step_outputs, dict) else None
            if artifact is None and not isinstance(fallback_data, dict):
                raise WorkflowError(f"Report input artifact not found: {input_key}")
            source_data = artifact.data if artifact is not None else fallback_data
            content = self._artifact_markdown(source_data)
            template_id = str(step.config.get("template_id", "blank_markdown"))
            configured_filename = str(step.config.get("filename", "candidate-assessment.pdf"))
            filename = self._report_filename(configured_filename, content)
            title = str(step.config.get("title", "")).strip() or None
            pdf = ReportPdfService().render(content, template_id, title)
            generated = GeneratedFileService(self.db).create_pdf(
                tenant_id=step.workflow.tenant_id,
                agent_id=None,
                filename=filename,
                template_id=template_id,
                data=pdf,
            )
            return {
                "generated_file_id": str(generated.id),
                "filename": generated.original_name,
                "content_type": generated.content_type,
                "template_id": generated.template_id,
                "size_bytes": generated.size_bytes,
                "download_url": f"/api/generated-files/{generated.id}/download",
            }, 0.0
        raise WorkflowError(f"Workflow step {step.step_key} has no executable target")

    @staticmethod
    def _artifact_markdown(data: dict) -> str:
        for key in ("content", "result", "markdown"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def _report_filename(cls, configured_filename: str, content: str) -> str:
        """Resolve the safe default filename from candidate evidence, not model-controlled paths."""
        if configured_filename not in {"candidate-assessment.pdf", "{candidate_name}-assessment.pdf"}:
            return configured_filename
        candidate_name = cls._candidate_name(content)
        if not candidate_name:
            return "candidate-assessment.pdf"
        translated = candidate_name.translate(str.maketrans({"ı": "i", "İ": "I", "ğ": "g", "Ğ": "G"}))
        ascii_name = unicodedata.normalize("NFKD", translated).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
        return f"{slug}-assessment.pdf" if slug else "candidate-assessment.pdf"

    @staticmethod
    def _candidate_name(content: str) -> str | None:
        patterns = (
            r"(?im)^\s*(?:[-*]\s*)?\*{0,2}(?:candidate|candidate name|full name|aday|aday adı)\*{0,2}\s*:\s*\*{0,2}([^\n|]+?)\*{0,2}\s*$",
            r'(?i)"(?:full_name|candidate_name)"\s*:\s*"([^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1).strip().strip("*")
        return None

    def _store_artifact(
        self,
        run: WorkflowRun,
        step_run: WorkflowStepRun,
        key: str,
        name: str,
        artifact_type: str,
        data: dict,
    ) -> None:
        run.artifacts.append(WorkflowArtifact(
            tenant_id=run.tenant_id,
            step_run=step_run,
            sequence=len(run.artifacts),
            artifact_key=key,
            name=name,
            artifact_type=artifact_type,
            data=data,
        ))

    @staticmethod
    def _state_with_artifacts(run: WorkflowRun) -> dict:
        state = {**run.input_data, **run.output_data}
        state["artifacts"] = list(run.artifacts)
        return state

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
