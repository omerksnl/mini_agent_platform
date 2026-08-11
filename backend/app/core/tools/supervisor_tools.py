import re
from collections.abc import Callable

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from app.models import Agent


class DelegationInput(BaseModel):
    task: str = Field(
        min_length=1,
        description="A self-contained task with all input data the managed agent needs",
    )


def delegation_tool_name(agent: Agent) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", agent.name.lower()).strip("_") or "agent"
    return f"delegate_to_{slug}_{str(agent.id)[:8]}"


def build_delegation_tools(
    supervisor: Agent,
    delegate: Callable[[Agent, str], str],
) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    for managed_agent in supervisor.managed_agents:
        skill_names = ", ".join(skill.name for skill in managed_agent.skills) or "none"
        collection_names = ", ".join(item.name for item in managed_agent.collections) or "none"
        system_tools = ", ".join(managed_agent.system_tools) or "none"

        def run(task: str, child: Agent = managed_agent) -> str:
            try:
                return delegate(child, task)
            except Exception as exc:
                raise ToolException(f"Delegation to {child.name} failed: {exc}") from exc

        tools.append(StructuredTool.from_function(
            func=run,
            name=delegation_tool_name(managed_agent),
            description=(
                f"Delegate a self-contained specialist task to managed agent '{managed_agent.name}'. "
                f"Its skills: {skill_names}. Its system tools: {system_tools}. "
                f"Its knowledge collections: {collection_names}. "
                "Pass complete prior-agent output in task when this step depends on it."
            ),
            args_schema=DelegationInput,
            handle_tool_error=True,
        ))
    return tools
