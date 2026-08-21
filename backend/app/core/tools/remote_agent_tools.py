import re
from collections.abc import Callable

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from app.models import RemoteAgent


class RemoteAgentTaskInput(BaseModel):
    task: str = Field(
        min_length=1,
        description="A self-contained task containing all context the remote A2A agent needs",
    )


def remote_agent_tool_name(agent: RemoteAgent) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", agent.name.lower()).strip("_") or "agent"
    return f"ask_remote_{slug}_{str(agent.id)[:8]}"


def build_remote_agent_tools(
    remote_agents: list[RemoteAgent],
    call_remote: Callable[[RemoteAgent, str], str],
) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    for remote_agent in remote_agents:
        skill_names = ", ".join(
            str(skill.get("name") or skill.get("id") or "skill")
            for skill in remote_agent.skills if isinstance(skill, dict)
        ) or "none"

        def run(task: str, target: RemoteAgent = remote_agent) -> str:
            try:
                return call_remote(target, task)
            except Exception as exc:
                raise ToolException(f"Remote A2A call to {target.name} failed: {exc}") from exc

        tools.append(StructuredTool.from_function(
            func=run,
            name=remote_agent_tool_name(remote_agent),
            description=(
                f"Ask remote A2A specialist '{remote_agent.name}' to perform a task. "
                f"Capability: {remote_agent.description or 'not specified'}. Skills: {skill_names}. "
                "Use this when the remote specialist is better suited than the local agent."
            ),
            args_schema=RemoteAgentTaskInput,
            handle_tool_error=True,
        ))
    return tools
