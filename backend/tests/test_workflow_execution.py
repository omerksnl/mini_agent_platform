import time

from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.core.services.llm_service import LLMResult
from app.core.services.collection_service import CollectionService
from app.core.services.workflow_execution_service import WorkflowExecutionService
from app.main import app


class FakeWorkflowLLM:
    messages: list[list[dict]] = []
    attachment_counts: list[int] = []

    validation_flags: list[bool] = []
    collection_flags: list[bool] = []

    def complete(
        self, agent, messages, http_tools=None, attachments=None, db=None,
        skip_response_validation=False, use_collections=True,
        skip_request_routing=False, max_output_tokens=None,
    ):
        self.messages.append(messages)
        self.attachment_counts.append(len(attachments or []))
        self.validation_flags.append(skip_response_validation)
        self.collection_flags.append(use_collections)
        return LLMResult(
            content=f"processed by {agent.name}",
            used_tools=[],
            used_skills=[],
            used_agents=[],
            api_cost_usd=0.0125,
        )


def register(client: TestClient, email: str, tenant: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "password123",
        "full_name": "Workflow Runner",
        "tenant_name": tenant,
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wait_for_run(client: TestClient, token: str, run_id: str, statuses: set[str]) -> dict:
    for _ in range(500):
        run = client.get(f"/api/workflows/runs/{run_id}", headers=headers(token)).json()
        if run["status"] in statuses:
            return run
        time.sleep(0.01)
    raise AssertionError(f"Workflow run did not reach {statuses}")


def create_agent(client: TestClient, token: str, name: str) -> dict:
    response = client.post("/api/agents", headers=headers(token), json={"name": name})
    assert response.status_code == 201
    return response.json()


def create_execution_workflow(client: TestClient, token: str, agent_id: str) -> dict:
    response = client.post("/api/workflows", headers=headers(token), json={
        "name": "Candidate pipeline",
        "steps": [
            {"step_key": "extract", "name": "Extract", "step_type": "agent", "position": 0, "agent_id": agent_id},
            {"step_key": "approval", "name": "Approval", "step_type": "human_wait", "position": 1, "config": {"required_input": "approval"}},
            {"step_key": "calculate", "name": "Calculate", "step_type": "system_tool", "position": 2, "system_tool_name": "calculator", "config": {"arguments": {"expression": "6 * 7"}}},
        ],
        "routes": [
            {"source_step_key": "extract", "target_step_key": "approval", "condition": "success"},
            {"source_step_key": "approval", "target_step_key": "calculate", "condition": "input_available"},
        ],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_workflow_runs_until_human_wait_and_resumes(client: TestClient) -> None:
    FakeWorkflowLLM.messages.clear()
    FakeWorkflowLLM.attachment_counts.clear()
    FakeWorkflowLLM.validation_flags.clear()
    FakeWorkflowLLM.collection_flags.clear()
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "runner@example.com", "Runner Tenant")
    agent = create_agent(client, token, "cv_ai")
    workflow = create_execution_workflow(client, token, agent["id"])

    started = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(token),
        json={"input_data": {"request": "Process this candidate"}},
    )
    assert started.status_code == 201, started.text
    run = started.json()
    assert run["status"] == "running"
    run = wait_for_run(client, token, run["id"], {"waiting"})
    assert run["status"] == "waiting"
    assert [item["status"] for item in run["step_runs"]] == ["completed", "waiting"]
    assert run["step_runs"][0]["output_data"]["content"] == "processed by cv_ai"
    assert run["total_api_cost_usd"] == 0.0125
    assert [item["artifact_key"] for item in run["artifacts"]] == ["workflow_input", "extract"]
    assert run["artifacts"][0]["data"] == {"request": "Process this candidate"}
    assert run["artifacts"][1]["artifact_type"] == "agent_output"

    resumed = client.post(
        f"/api/workflows/runs/{run['id']}/resume",
        headers=headers(token),
        json={"input_data": {"approved": True}},
    )
    assert resumed.status_code == 200, resumed.text
    completed = resumed.json()
    assert completed["status"] == "running"
    completed = wait_for_run(client, token, run["id"], {"completed"})
    assert completed["status"] == "completed"
    assert completed["current_step_id"] is None
    assert completed["step_runs"][-1]["output_data"] == {"result": "42"}
    assert completed["output_data"]["steps"]["approval"] == {"human_input": {"approved": True}}
    assert [item["artifact_key"] for item in completed["artifacts"]] == [
        "workflow_input", "extract", "approval", "calculate"
    ]
    assert completed["artifacts"][2]["artifact_type"] == "human_input"
    assert completed["artifacts"][3]["artifact_type"] == "tool_output"


def test_agent_receives_all_prior_workflow_artifacts(client: TestClient) -> None:
    FakeWorkflowLLM.messages.clear()
    FakeWorkflowLLM.attachment_counts.clear()
    FakeWorkflowLLM.validation_flags.clear()
    FakeWorkflowLLM.collection_flags.clear()
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "artifact-context@example.com", "Artifact Context")
    first = create_agent(client, token, "cv_ai")
    second = create_agent(client, token, "job_fitter_ai")
    workflow = client.post("/api/workflows", headers=headers(token), json={
        "name": "Artifact handoff",
        "steps": [
            {"step_key": "candidate_profile", "name": "Candidate profile", "step_type": "agent", "position": 0, "agent_id": first["id"]},
            {"step_key": "job_fit", "name": "Job fit", "step_type": "agent", "position": 1, "agent_id": second["id"], "config": {"task_instructions": "Use prior candidate evidence only.", "use_collections": False}},
        ],
        "routes": [{"source_step_key": "candidate_profile", "target_step_key": "job_fit", "condition": "success"}],
    }).json()

    response = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(token),
        json={"input_data": {"request": "Evaluate candidate"}},
    )

    assert response.status_code == 201, response.text
    wait_for_run(client, token, response.json()["id"], {"completed", "failed", "waiting"})
    assert len(FakeWorkflowLLM.messages) == 2
    second_prompt = FakeWorkflowLLM.messages[1][0]["content"]
    assert '"key":"workflow_input"' not in second_prompt
    assert '"key":"candidate_profile"' in second_prompt
    assert "processed by cv_ai" in second_prompt
    assert "Execute only your assigned specialist task" in second_prompt
    assert "NODE TASK INSTRUCTIONS" in second_prompt
    assert "Use prior candidate evidence only." in second_prompt
    assert not second_prompt.startswith("Evaluate candidate\n")
    assert FakeWorkflowLLM.validation_flags == [True, True]
    assert FakeWorkflowLLM.collection_flags == [False, False]


def test_collection_prefetch_query_includes_every_human_wait(
    client: TestClient, monkeypatch
) -> None:
    FakeWorkflowLLM.messages.clear()
    captured_queries: list[str] = []
    monkeypatch.setattr(
        CollectionService,
        "search_text",
        lambda self, tenant_id, collection_ids, query, **kwargs: captured_queries.append(query) or "Complete selected-role criteria",
    )
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "all-human-inputs@example.com", "All Human Inputs")
    collection = client.post(
        "/api/collections",
        headers=headers(token),
        json={"name": "Role criteria", "description": "Engineering roles"},
    ).json()
    agent = client.post(
        "/api/agents",
        headers=headers(token),
        json={"name": "review_ai", "collection_ids": [collection["id"]]},
    ).json()
    workflow = client.post("/api/workflows", headers=headers(token), json={
        "name": "Review context",
        "steps": [
            {"step_key": "selected_role", "name": "Selected role", "step_type": "human_wait", "position": 0, "config": {"required_input": "Select role"}},
            {"step_key": "interview", "name": "Interview", "step_type": "human_wait", "position": 1, "config": {"required_input": "Interview answers"}},
            {"step_key": "review", "name": "Review", "step_type": "agent", "position": 2, "agent_id": agent["id"], "config": {"collection_mode": "search"}},
        ],
        "routes": [
            {"source_step_key": "selected_role", "target_step_key": "interview", "condition": "input_available"},
            {"source_step_key": "interview", "target_step_key": "review", "condition": "input_available"},
        ],
    }).json()

    started = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(token), json={"input_data": {"request": "Assess candidate"}},
    ).json()
    first_wait = wait_for_run(client, token, started["id"], {"waiting"})
    resumed = client.post(
        f"/api/workflows/runs/{first_wait['id']}/resume",
        headers=headers(token), json={"input_data": {"response": "Machine Learning Engineer"}},
    ).json()
    second_wait = wait_for_run(client, token, resumed["id"], {"waiting"})
    client.post(
        f"/api/workflows/runs/{second_wait['id']}/resume",
        headers=headers(token), json={"input_data": {"response": "Five concise interview answers"}},
    )
    wait_for_run(client, token, second_wait["id"], {"completed", "failed"})

    assert len(captured_queries) == 1
    assert "Machine Learning Engineer" in captured_queries[0]
    assert "Five concise interview answers" in captured_queries[0]


def test_workflow_pdf_is_attached_to_run_and_only_first_pdf_agent(client: TestClient) -> None:
    FakeWorkflowLLM.messages.clear()
    FakeWorkflowLLM.attachment_counts.clear()
    FakeWorkflowLLM.validation_flags.clear()
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "workflow-pdf@example.com", "Workflow PDF")
    first = client.post("/api/agents", headers=headers(token), json={
        "name": "cv_ai", "system_tools": ["pdf_to_text"]
    }).json()
    second = client.post("/api/agents", headers=headers(token), json={
        "name": "review_ai", "system_tools": ["pdf_to_text"]
    }).json()
    workflow = client.post("/api/workflows", headers=headers(token), json={
        "name": "PDF artifact handoff",
        "steps": [
            {"step_key": "candidate_profile", "name": "Candidate profile", "step_type": "agent", "position": 0, "agent_id": first["id"]},
            {"step_key": "review", "name": "Review", "step_type": "agent", "position": 1, "agent_id": second["id"]},
        ],
        "routes": [{"source_step_key": "candidate_profile", "target_step_key": "review", "condition": "success"}],
    }).json()
    uploaded = client.post(
        "/api/attachments",
        headers=headers(token),
        files={"file": ("candidate.pdf", b"%PDF-1.4\nworkflow test", "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text

    response = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(token),
        json={
            "input_data": {"request": "Extract and review"},
            "attachment_ids": [uploaded.json()["id"]],
        },
    )

    assert response.status_code == 201, response.text
    wait_for_run(client, token, response.json()["id"], {"completed", "failed", "waiting"})
    assert FakeWorkflowLLM.attachment_counts == [1, 0]
    assert response.json()["artifacts"][0]["data"]["attachments"][0]["filename"] == "candidate.pdf"


def test_failed_step_is_persisted(client: TestClient) -> None:
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "failed-run@example.com", "Failed Tenant")
    workflow = client.post("/api/workflows", headers=headers(token), json={
        "name": "Broken calculation",
        "steps": [{"step_key": "calculate", "name": "Calculate", "step_type": "system_tool", "position": 0, "system_tool_name": "calculator"}],
    }).json()
    response = client.post(
        f"/api/workflows/{workflow['id']}/runs", headers=headers(token), json={"input_data": {}}
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "running"
    run = wait_for_run(client, token, run["id"], {"failed"})
    assert run["status"] == "failed"
    assert run["step_runs"][0]["status"] == "failed"
    assert run["error"]


def test_report_step_renders_prior_artifact_without_llm_cost(client: TestClient) -> None:
    assert WorkflowExecutionService._report_filename(
        "{candidate_name}-assessment.pdf",
        "# Final Candidate Assessment\n\n- **Candidate:** Ömer Kaan Şanal",
    ) == "omer-kaan-sanal-assessment.pdf"
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    token = register(client, "report-run@example.com", "Report Run")
    agent = create_agent(client, token, "review_ai")
    workflow_response = client.post("/api/workflows", headers=headers(token), json={
        "name": "Assessment with PDF",
        "steps": [
            {"step_key": "final_assessment", "name": "Final assessment", "step_type": "agent", "position": 0, "agent_id": agent["id"]},
            {
                "step_key": "pdf_report", "name": "PDF report", "step_type": "report", "position": 1,
                "config": {
                    "input_artifact_key": "final_assessment",
                    "template_id": "two_column",
                    "filename": "candidate-assessment.pdf",
                    "title": "Final Candidate Assessment",
                },
            },
        ],
        "routes": [{"source_step_key": "final_assessment", "target_step_key": "pdf_report", "condition": "success"}],
    })
    assert workflow_response.status_code == 201, workflow_response.text

    started = client.post(
        f"/api/workflows/{workflow_response.json()['id']}/runs",
        headers=headers(token), json={"input_data": {"request": "Assess candidate"}},
    )
    assert started.status_code == 201, started.text
    completed = wait_for_run(client, token, started.json()["id"], {"completed", "failed"})
    assert completed["status"] == "completed", completed.get("error")
    assert completed["total_api_cost_usd"] == 0.0125
    assert completed["step_runs"][1]["api_cost_usd"] == 0
    report = completed["artifacts"][-1]
    assert report["artifact_type"] == "generated_file"
    assert report["data"]["filename"] == "candidate-assessment.pdf"
    assert report["data"]["template_id"] == "two_column"
    downloaded = client.get(report["data"]["download_url"], headers=headers(token))
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF-")

    other = register(client, "report-other@example.com", "Report Other")
    assert client.get(report["data"]["download_url"], headers=headers(other)).status_code == 404


def test_workflow_runs_are_tenant_isolated(client: TestClient) -> None:
    app.dependency_overrides[get_llm_client] = lambda: FakeWorkflowLLM()
    owner = register(client, "run-owner@example.com", "Run Owner")
    other = register(client, "run-other@example.com", "Run Other")
    agent = create_agent(client, owner, "owner_agent")
    workflow = create_execution_workflow(client, owner, agent["id"])
    run = client.post(
        f"/api/workflows/{workflow['id']}/runs",
        headers=headers(owner), json={"input_data": {"request": "test"}},
    ).json()

    assert client.get(f"/api/workflows/runs/{run['id']}", headers=headers(other)).status_code == 404
    assert client.post(
        f"/api/workflows/runs/{run['id']}/resume",
        headers=headers(other), json={"input_data": {"approved": True}},
    ).status_code == 404
    assert client.get(f"/api/workflows/{workflow['id']}/runs", headers=headers(other)).status_code == 404
    # Let the owner's background worker reach its human-wait boundary before
    # the per-test SQLite database is disposed on Windows.
    wait_for_run(client, owner, run["id"], {"waiting", "completed", "failed"})
