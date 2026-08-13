from types import SimpleNamespace

from app.core.observability import bind_trace_context, build_langfuse_handler, langfuse_metadata


def test_langfuse_is_disabled_without_both_keys() -> None:
    settings = SimpleNamespace(langfuse_enabled=False)
    assert build_langfuse_handler(settings) is None


def test_workflow_context_becomes_langfuse_metadata() -> None:
    with bind_trace_context(
        workflow_run_id="run-1",
        workflow_id="workflow-1",
        workflow_name="jobhunt",
        tenant_id="tenant-1",
        step_key="job_fit",
    ):
        metadata = langfuse_metadata(agent_name="job_fitter_ai", agent_type="normal")

    assert metadata["langfuse_trace_name"] == "jobhunt"
    assert metadata["langfuse_session_id"] == "run-1"
    assert metadata["workflow_step_key"] == "job_fit"
    assert metadata["agent_name"] == "job_fitter_ai"

