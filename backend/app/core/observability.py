from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import logging
from typing import Any, Iterator

from app.config import Settings


logger = logging.getLogger(__name__)
_trace_context: ContextVar[dict[str, str]] = ContextVar("langfuse_trace_context", default={})


@contextmanager
def bind_trace_context(**values: Any) -> Iterator[None]:
    """Attach request/workflow metadata to Langfuse callbacks in this context."""
    current = dict(_trace_context.get())
    current.update({key: str(value) for key, value in values.items() if value is not None})
    token = _trace_context.set(current)
    try:
        yield
    finally:
        _trace_context.reset(token)


@lru_cache(maxsize=1)
def _langfuse_client(
    public_key: str,
    secret_key: str,
    base_url: str,
    environment: str,
) -> Any:
    from langfuse import Langfuse

    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        environment=environment,
    )


def build_langfuse_handler(settings: Settings) -> Any | None:
    """Create an optional callback; observability must never be required to run the app."""
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        _langfuse_client(
            settings.langfuse_public_key,
            settings.langfuse_secret_key,
            settings.langfuse_base_url,
            settings.langfuse_tracing_environment,
        )
        return CallbackHandler(public_key=settings.langfuse_public_key)
    except Exception:
        logger.exception("Langfuse callback initialization failed; continuing without tracing")
        return None


def langfuse_metadata(*, agent_name: str, agent_type: str) -> dict[str, Any]:
    context = _trace_context.get()
    metadata: dict[str, Any] = {
        "langfuse_trace_name": context.get("workflow_name", f"agent:{agent_name}"),
        "langfuse_tags": ["mini-agent-platform", agent_type],
        "agent_name": agent_name,
        "agent_type": agent_type,
    }
    if session_id := context.get("workflow_run_id"):
        metadata["langfuse_session_id"] = session_id
    if tenant_id := context.get("tenant_id"):
        metadata["tenant_id"] = tenant_id
    if workflow_id := context.get("workflow_id"):
        metadata["workflow_id"] = workflow_id
    if step_key := context.get("step_key"):
        metadata["workflow_step_key"] = step_key
    return metadata
