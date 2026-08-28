from dataclasses import dataclass, field
import hashlib
import json
import logging
import re
from typing import Any, Protocol

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.prompts import build_effective_system_prompt
from app.core.tools import SYSTEM_TOOL_MAP
from app.core.tools.http_tools import build_http_tools
from app.models import Agent, HttpTool
from app.models import Attachment
from sqlalchemy.orm import Session
from app.core.tools.pdf_tools import build_pdf_to_text_tool
from app.core.tools.text_to_pdf_tools import build_text_to_pdf_tool
from app.core.tools.collection_tools import build_collection_search_tool
from app.core.tools.supervisor_tools import build_delegation_tools, build_remote_delegation_tools
from app.core.tools.remote_agent_tools import build_remote_agent_tools, remote_agent_tool_name
from app.core.services.remote_agent_service import RemoteAgentService
from app.core.candidate_profile import normalize_candidate_profile_json
from app.core.observability import build_langfuse_handler, langfuse_metadata
from app.core.guardrails import GuardrailRunner, GuardrailViolation
from app.core.services.provider_service import ProviderCredentials, ProviderError, ProviderService


logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class LLMResult:
    content: str
    used_tools: list[str]
    used_skills: list[str] = field(default_factory=list)
    used_agents: list[str] = field(default_factory=list)
    api_cost_usd: float = 0.0


class ApiCostCallbackHandler(BaseCallbackHandler):
    """Sum exact OpenRouter costs, with a token-price fallback."""

    def __init__(self, input_rate: float, output_rate: float) -> None:
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.total_cost_usd = 0.0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        token_usage = (response.llm_output or {}).get("token_usage") or {}
        exact_cost = token_usage.get("cost")
        upstream_cost = (token_usage.get("cost_details") or {}).get("upstream_inference_cost")
        if isinstance(exact_cost, (int, float)) and exact_cost > 0:
            self.total_cost_usd += float(exact_cost)
            return
        if isinstance(upstream_cost, (int, float)) and upstream_cost > 0:
            self.total_cost_usd += float(upstream_cost)
            return

        try:
            usage = response.generations[0][0].message.usage_metadata or {}
        except (AttributeError, IndexError, TypeError):
            usage = {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        self.total_cost_usd += (
            input_tokens * self.input_rate + output_tokens * self.output_rate
        ) / 1_000_000


class RoutingDecision(BaseModel):
    request_parts: list[str] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    required_tool_names: list[str] = Field(default_factory=list)


class ValidationDecision(BaseModel):
    complete: bool
    missing_parts: list[str] = Field(default_factory=list)


class RouterAgentDecision(BaseModel):
    target_agent_id: str | None = None
    clarification_question: str | None = None


class LLMClient(Protocol):
    def complete(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        http_tools: list[HttpTool] | None = None,
        attachments: list[Attachment] | None = None,
        db: Session | None = None,
        skip_response_validation: bool = False,
        use_collections: bool = True,
        skip_request_routing: bool = False,
        max_output_tokens: int | None = None,
    ) -> LLMResult | str: ...


class OpenRouterLLMClient:
    TOOL_RESULT_INSTRUCTIONS = (
        "Identify and answer every independently requested part of the user's message. "
        "When reporting a tool result, preserve its numeric values exactly. "
        "For current_datetime, write the time in HH:MM format exactly as returned; "
        "do not turn it into an approximate or colloquial time expression."
    )

    def __init__(self, credentials: ProviderCredentials | None = None, user_id=None) -> None:
        settings = get_settings()
        self.settings = settings
        self.user_id = user_id
        try:
            self.credentials = credentials or ProviderService(settings=settings).resolve()
        except ProviderError as exc:
            raise LLMError(str(exc)) from exc

    def _model_name(self, configured_model: str, credentials: ProviderCredentials | None = None) -> str:
        credentials = credentials or getattr(self, "credentials", None)
        if credentials is None:
            try:
                credentials = ProviderService(settings=self.settings).resolve()
                self.credentials = credentials
            except ProviderError as exc:
                raise LLMError(str(exc)) from exc
        if credentials.provider == "openrouter":
            return configured_model
        if configured_model.startswith("openai/"):
            return configured_model.removeprefix("openai/")
        if configured_model.startswith(("gpt-", "o1", "o3", "o4")):
            return configured_model
        raise LLMError(
            f"Model '{configured_model}' is not available through direct OpenAI. "
            "Select an OpenAI model or switch the provider to OpenRouter."
        )

    def _chat_model(self, configured_model: str, temperature: float, max_tokens: int, credentials: ProviderCredentials | None = None) -> ChatOpenAI:
        if not hasattr(self, "credentials"):
            try:
                self.credentials = ProviderService(settings=self.settings).resolve()
            except ProviderError as exc:
                raise LLMError(str(exc)) from exc
        credentials = credentials or self.credentials
        kwargs: dict[str, Any] = {
            "model": self._model_name(configured_model, credentials),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": credentials.api_key,
            "base_url": credentials.base_url,
        }
        if credentials.provider == "openrouter":
            kwargs["default_headers"] = {"X-OpenRouter-Title": self.settings.openrouter_app_title}
        return ChatOpenAI(**kwargs)

    def complete(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        http_tools: list[HttpTool] | None = None,
        attachments: list[Attachment] | None = None,
        db: Session | None = None,
        skip_response_validation: bool = False,
        use_collections: bool = True,
        skip_request_routing: bool = False,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        guardrails = GuardrailRunner(agent.guardrails, agent_name=agent.name, tenant_id=agent.tenant_id)
        guarded_messages = []
        try:
            for message in messages:
                guarded_messages.append({
                    **message,
                    "content": guardrails.apply("input", message["content"])
                    if message.get("role") == "user" else message["content"],
                })
        except GuardrailViolation as exc:
            raise LLMError(f"Guardrail blocked the request: {exc}") from exc
        messages = guarded_messages
        is_supervisor = agent.agent_type == "supervisor"
        is_router = agent.agent_type == "router"
        if is_supervisor and not (agent.managed_agents or agent.managed_remote_agents):
            raise LLMError("This supervisor has no managed agents")
        if is_supervisor and db is None:
            raise LLMError("Supervisor database context is unavailable")
        if is_router and not (agent.router_targets or agent.router_remote_targets):
            raise LLMError("This router has no target agents")
        if is_router and db is None:
            raise LLMError("Router database context is unavailable")
        if agent.remote_agent_tools and db is None:
            raise LLMError("Remote agent database context is unavailable")
        cost_callback = ApiCostCallbackHandler(
            self.settings.llm_input_cost_per_million_usd,
            self.settings.llm_output_cost_per_million_usd,
        )
        langfuse_handler = build_langfuse_handler(self.settings)
        tracing_callbacks = [cost_callback]
        if langfuse_handler is not None:
            tracing_callbacks.append(langfuse_handler)
        tracing_metadata = langfuse_metadata(
            agent_name=agent.name,
            agent_type=agent.agent_type,
        )
        default_max_tokens = (
            self.settings.cv_extraction_max_tokens
            if attachments and not is_supervisor
            else self.settings.supervisor_max_tokens
            if is_supervisor
            else self.settings.rag_max_tokens
            if agent.collections
            else self.settings.llm_max_tokens
        )
        max_tokens = max_output_tokens or default_max_tokens
        credentials = getattr(self, "credentials", None)
        user_id = getattr(self, "user_id", None)
        if db is not None and user_id is not None:
            try:
                credentials = ProviderService(db).resolve_for_agent(user_id, agent.id)
            except ProviderError as exc:
                raise LLMError(str(exc)) from exc
        model = self._chat_model(agent.model, agent.temperature, max_tokens, credentials)
        if is_router:
            router_result = self._complete_router(
                agent,
                model,
                messages,
                attachments or [],
                db,
                cost_callback,
                tracing_callbacks,
                tracing_metadata,
            )
            try:
                guarded_content = guardrails.apply("output", router_result.content)
            except GuardrailViolation as exc:
                raise LLMError(f"Guardrail blocked the response: {exc}") from exc
            return LLMResult(
                content=guarded_content,
                used_tools=router_result.used_tools,
                used_skills=router_result.used_skills,
                used_agents=router_result.used_agents,
                api_cost_usd=router_result.api_cost_usd,
            )
        selected_system_tools = [
            SYSTEM_TOOL_MAP[name]
            for name in agent.system_tools
            if name in SYSTEM_TOOL_MAP
        ]
        if attachments and not is_supervisor and "pdf_to_text" in agent.system_tools:
            if db is None:
                raise LLMError("PDF tool database context is unavailable")
            selected_system_tools.append(build_pdf_to_text_tool(db, attachments))
        if "text_to_pdf" in agent.system_tools:
            if db is None:
                raise LLMError("Text-to-PDF tool database context is unavailable")
            selected_system_tools.append(build_text_to_pdf_tool(db, agent))
        selected_tools = [*selected_system_tools, *build_http_tools(http_tools or [])]
        used_agents: list[str] = []
        delegated_cost_usd = 0.0
        if agent.remote_agent_tools:
            def call_remote_tool(target, task: str) -> str:
                nonlocal delegated_cost_usd
                text, _, cost, _, _, _ = RemoteAgentService(db).send(
                    target.id, target.tenant_id, target.owner_user_id, task.strip(),
                    [item.id for item in attachments or []],
                )
                if target.name not in used_agents:
                    used_agents.append(target.name)
                delegated_cost_usd += cost
                return text

            selected_tools.extend(build_remote_agent_tools(agent.remote_agent_tools, call_remote_tool))
        has_collection_content = any(
            document.chunks
            for collection in agent.collections
            for document in collection.documents
        )
        if agent.collections and use_collections and has_collection_content:
            if db is None:
                raise LLMError("Collection tool database context is unavailable")
            selected_tools.append(build_collection_search_tool(db, agent))
        if is_supervisor:
            def delegate_to_child(child: Agent, task: str) -> str:
                nonlocal delegated_cost_usd
                child_attachments = attachments if attachments and "pdf_to_text" in child.system_tools else []
                child_content = task.strip()
                if child_attachments:
                    attachment_lines = "\n".join(
                        f"- attachment_id={item.id}; filename={item.original_name}; type={item.content_type}"
                        for item in child_attachments
                    )
                    child_content += (
                        "\n\nATTACHMENTS AVAILABLE TO TOOLS\n"
                        + attachment_lines
                        + "\nUse pdf_to_text before making claims about PDF contents."
                    )
                child_result = self.complete(
                    child,
                    [{"role": "user", "content": child_content}],
                    child.http_tools,
                    child_attachments,
                    db,
                    skip_response_validation=True,
                )
                if child.name not in used_agents:
                    used_agents.append(child.name)
                delegated_cost_usd += child_result.api_cost_usd
                return child_result.content

            selected_tools.extend(build_delegation_tools(agent, delegate_to_child))

            def delegate_to_remote(child, task: str) -> str:
                nonlocal delegated_cost_usd
                text, _, cost, _, _, _ = RemoteAgentService(db).send(
                    child.id, child.tenant_id, child.owner_user_id, task.strip(),
                    [item.id for item in attachments],
                )
                if child.name not in used_agents:
                    used_agents.append(child.name)
                delegated_cost_usd += cost
                return text

            selected_tools.extend(build_remote_delegation_tools(agent, delegate_to_remote))

        selected_tools = guardrails.wrap_tools(selected_tools)

        if attachments and not is_supervisor and "pdf_to_text" not in agent.system_tools and agent.remote_agent_tools:
            latest_user = next(
                (item["content"] for item in reversed(messages) if item["role"] == "user"),
                "Process the attached PDF using the appropriate remote specialist",
            )
            required = (
                [remote_agent_tool_name(agent.remote_agent_tools[0])]
                if len(agent.remote_agent_tools) == 1 else []
            )
            routing = RoutingDecision(request_parts=[latest_user], required_tool_names=required)
            selected_skills = []
        elif attachments and not is_supervisor:
            if "pdf_to_text" not in agent.system_tools:
                raise LLMError("Enable pdf_to_text on this agent before sending a PDF")
            selected_skills = [skill for skill in agent.skills if skill.name == "cv_extraction"]
            if not selected_skills:
                raise LLMError("Assign the cv_extraction skill to this agent before sending a CV")
            latest_user = next(
                (item["content"] for item in reversed(messages) if item["role"] == "user"),
                "Extract CandidateProfile from the attached CV",
            )
            routing = RoutingDecision(
                request_parts=[latest_user],
                skill_names=["cv_extraction"],
                required_tool_names=["pdf_to_text"],
            )
        elif skip_request_routing or is_supervisor:
            latest_user = next(
                (item["content"] for item in reversed(messages) if item["role"] == "user"),
                "",
            )
            routing = RoutingDecision(request_parts=[latest_user])
            selected_skills = []
        else:
            routing = self._route_request(
                model,
                messages,
                agent.skills,
                selected_tools,
                cost_callback,
                tracing_callbacks,
                tracing_metadata,
            )
            selected_skill_names = set(routing.skill_names)
            selected_skills = [skill for skill in agent.skills if skill.name in selected_skill_names]
        available_tool_names = {tool.name for tool in selected_tools}
        unavailable_skill_tools: dict[str, list[str]] = {}
        usable_skills = []
        for skill in selected_skills:
            skill_requirements = {
                *skill.required_system_tools,
                *(tool.name for tool in skill.http_tools),
            }
            missing_for_skill = sorted(skill_requirements - available_tool_names)
            if missing_for_skill:
                unavailable_skill_tools[skill.name] = missing_for_skill
            else:
                usable_skills.append(skill)
        selected_skills = usable_skills
        required_tool_names = {
            name for name in routing.required_tool_names if name in available_tool_names
        }
        for skill in selected_skills:
            required_tool_names.update(skill.required_system_tools)
            required_tool_names.update(tool.name for tool in skill.http_tools)

        # Collection-backed recommendations should not depend on whether a
        # particular model decides to emit a tool call. The request router has
        # already established that collection_search is required, so execute
        # that deterministic retrieval once and ground the answer with its
        # result. This also avoids a failed answer plus a second paid retry.
        prefetched_tool_names: list[str] = []
        prefetched_context = ""
        if "collection_search" in required_tool_names:
            collection_tool = next(
                (tool for tool in selected_tools if getattr(tool, "name", "") == "collection_search"),
                None,
            )
            if collection_tool is not None:
                latest_user = next(
                    (item["content"] for item in reversed(messages) if item["role"] == "user"),
                    "recommendation",
                )
                try:
                    collection_result = collection_tool.invoke({"query": latest_user})
                except Exception as exc:
                    raise LLMError("The assigned collection could not be searched") from exc
                prefetched_tool_names.append("collection_search")
                required_tool_names.discard("collection_search")
                selected_tools = [
                    tool for tool in selected_tools
                    if getattr(tool, "name", "") != "collection_search"
                ]
                prefetched_context = (
                    "\n\nPREFETCHED COLLECTION SEARCH RESULT\n"
                    "Use this retrieved collection content as the source of truth for the answer. "
                    "Do not claim that no collection was searched.\n"
                    f"{collection_result}"
                )

        system_prompt = self._execution_prompt(
            agent, selected_skills, required_tool_names, unavailable_skill_tools
        ) + prefetched_context
        result_messages = self._invoke_agent(
            model,
            selected_tools,
            system_prompt,
            messages,
            cost_callback,
            is_collection_run=bool(agent.collections),
            tracing_callbacks=tracing_callbacks,
            tracing_metadata=tracing_metadata,
        )
        content = self._last_assistant_text(result_messages)
        if not content:
            raise LLMError("The language model returned an empty response")
        used_tools = [*prefetched_tool_names, *self._used_tool_names(result_messages)]
        missing_tools = sorted(required_tool_names - set(used_tools))
        validation = self._validate_response(
            model,
            messages,
            routing.request_parts,
            content,
            result_messages,
            cost_callback,
            tracing_callbacks,
            tracing_metadata,
        ) if not skip_response_validation and not attachments and "text_to_pdf" not in used_tools and (len(routing.request_parts) > 1 or required_tool_names) else ValidationDecision(complete=True)
        profile_invalid = self._candidate_profile_invalid(selected_skills, content)

        if missing_tools or not validation.complete or profile_invalid:
            correction = self._correction_instructions(missing_tools, validation.missing_parts)
            if profile_invalid:
                correction += " Return only one valid CandidateProfile JSON object matching the skill schema."
            retry_prompt = f"{system_prompt}\n\nCORRECTION REQUIRED\n{correction}"
            result_messages = self._invoke_agent(
                model,
                selected_tools,
                retry_prompt,
                messages,
                cost_callback,
                is_collection_run=bool(agent.collections),
                tracing_callbacks=tracing_callbacks,
                tracing_metadata=tracing_metadata,
            )
            content = self._last_assistant_text(result_messages)
            if not content:
                raise LLMError("The language model returned an empty response")
            used_tools = [*prefetched_tool_names, *self._used_tool_names(result_messages)]
            missing_tools = sorted(required_tool_names - set(used_tools))
            validation = self._validate_response(
                model,
                messages,
                routing.request_parts,
                content,
                result_messages,
                cost_callback,
                tracing_callbacks,
                tracing_metadata,
            ) if not skip_response_validation and not attachments else ValidationDecision(complete=True)
            profile_invalid = self._candidate_profile_invalid(selected_skills, content)
            if missing_tools:
                raise LLMError("The agent did not call required tools: " + ", ".join(missing_tools))
            if profile_invalid:
                raise LLMError("The model returned CandidateProfile JSON that did not match the required schema")
            if not validation.complete:
                raise LLMError(
                    "The agent did not answer these request parts: "
                    + "; ".join(validation.missing_parts)
                )

        content = self._normalize_datetime_response(content, result_messages)
        content = self._append_generated_file_links(content, result_messages)
        if any(skill.name == "cv_extraction" for skill in selected_skills):
            content = normalize_candidate_profile_json(content)
        try:
            content = guardrails.apply("output", content)
        except GuardrailViolation as exc:
            raise LLMError(f"Guardrail blocked the response: {exc}") from exc
        return LLMResult(
            content=content,
            used_tools=[name for name in used_tools if not name.startswith(("delegate_to_", "ask_remote_"))],
            used_skills=[skill.name for skill in selected_skills],
            used_agents=used_agents,
            api_cost_usd=round(cost_callback.total_cost_usd + delegated_cost_usd, 8),
        )

    def _complete_router(
        self,
        router_agent: Agent,
        model: ChatOpenAI,
        messages: list[dict[str, str]],
        attachments: list[Attachment],
        db: Session,
        cost_callback: ApiCostCallbackHandler,
        callbacks: list[Any],
        metadata: dict[str, Any],
    ) -> LLMResult:
        catalog = "\n\n".join(
            [f"TARGET ID: local:{target.id}\nNAME: {target.name}\nSPECIALTY: {target.system_prompt[:1200]}"
             for target in router_agent.router_targets]
            + [f"TARGET ID: remote:{target.id}\nNAME: {target.name}\nSPECIALTY: {target.description[:1200]}"
               for target in router_agent.router_remote_targets]
        )
        latest_user = next(
            (item["content"] for item in reversed(messages) if item["role"] == "user"), ""
        )
        recent_context = "\n".join(
            f"{item['role'].upper()}: {item['content'][:800]}"
            for item in messages[-6:]
        )
        selector = model.with_structured_output(RouterAgentDecision)
        try:
            decision = selector.invoke([
                SystemMessage(content=(
                    f"{router_agent.system_prompt}\n\n"
                    "Select exactly one target agent that best matches the latest user request. "
                    "Use the recent conversation to understand rejection phrases such as 'another one' or 'I did not like it'. "
                    "Use only a TARGET ID from the catalog and always select exactly one target. "
                    "Never ask a clarification question. Select the closest target even if preferences are incomplete or the request is vague. "
                    "A choice menu may contain up to four short options when the router instructions request it. "
                    "Never answer the user's request yourself.\n\nTARGET AGENTS\n" + catalog
                )),
                HumanMessage(content=f"RECENT CONVERSATION\n{recent_context}\n\nLATEST USER REQUEST\n{latest_user}"),
            ], config={"callbacks": callbacks, "metadata": metadata})
        except Exception as exc:
            raise LLMError("The agent router failed") from exc

        selected_id = decision.target_agent_id or ""
        target = next((item for item in router_agent.router_targets if selected_id in {str(item.id), f"local:{item.id}"}), None)
        remote_target = next((item for item in router_agent.router_remote_targets if selected_id == f"remote:{item.id}"), None)
        if target is None and remote_target is None:
            available_targets = [*(('local', item) for item in router_agent.router_targets), *(("remote", item) for item in router_agent.router_remote_targets)]
            if not available_targets:
                raise LLMError("This router has no target agents")
            fallback_index = int(hashlib.sha256(latest_user.encode("utf-8")).hexdigest(), 16) % len(available_targets)
            fallback_type, fallback = available_targets[fallback_index]
            target = fallback if fallback_type == "local" else None
            remote_target = fallback if fallback_type == "remote" else None

        if remote_target is not None:
            content, _, remote_cost, _, _, _ = RemoteAgentService(db).send(
                remote_target.id, remote_target.tenant_id, remote_target.owner_user_id,
                latest_user, [item.id for item in attachments],
            )
            return LLMResult(
                content=content,
                used_tools=[], used_skills=[], used_agents=[remote_target.name],
                api_cost_usd=round(cost_callback.total_cost_usd + remote_cost, 8),
            )

        forwarded_attachments = attachments if "pdf_to_text" in target.system_tools else []
        # Routing metadata is useful to the selector for category rotation, but
        # it is not part of the conversation and must never reach a specialist
        # as visible assistant text. Keep the previous answer itself so a
        # specialist can still understand requests such as "another one".
        child_messages = [
            {
                **item,
                "content": re.sub(
                    r"^\[ROUTING HISTORY:[^\]\r\n]*\]\s*",
                    "",
                    item["content"],
                    count=1,
                    flags=re.IGNORECASE,
                ),
            }
            for item in messages
        ]
        child_result = self.complete(
            target,
            child_messages,
            target.http_tools,
            forwarded_attachments,
            db,
        )
        child_content = re.sub(
            r"^\[ROUTING HISTORY:[^\]\r\n]*\]\s*",
            "",
            child_result.content,
            count=1,
            flags=re.IGNORECASE,
        )
        return LLMResult(
            content=child_content,
            used_tools=child_result.used_tools,
            used_skills=child_result.used_skills,
            used_agents=[target.name, *[name for name in child_result.used_agents if name != target.name]],
            api_cost_usd=round(cost_callback.total_cost_usd + child_result.api_cost_usd, 8),
        )

    @staticmethod
    def _candidate_profile_invalid(skills: list[Any], content: str) -> bool:
        if not any(skill.name == "cv_extraction" for skill in skills):
            return False
        try:
            normalize_candidate_profile_json(content)
        except ValueError:
            return True
        return False

    def _invoke_agent(
        self,
        model: ChatOpenAI,
        tools: list[Any],
        system_prompt: str,
        messages: list[dict[str, str]],
        cost_callback: ApiCostCallbackHandler,
        is_collection_run: bool = False,
        tracing_callbacks: list[Any] | None = None,
        tracing_metadata: dict[str, Any] | None = None,
    ) -> list[Any]:
        callbacks = tracing_callbacks or [cost_callback]
        metadata = tracing_metadata or {}
        # A tool-free agent does not need a LangGraph execution loop. Calling
        # the chat model directly avoids graph recursion/model-call limits and
        # guarantees that a scoring or formatting-only node makes one model
        # request instead of entering an unnecessary agent cycle.
        if not tools:
            try:
                response = model.invoke(
                    [SystemMessage(content=system_prompt), *messages],
                    config={"callbacks": callbacks, "metadata": metadata},
                )
            except OpenAIError as exc:
                logger.exception(
                    "LLM provider request failed during direct execution: model=%s error_type=%s",
                    getattr(model, "model_name", "unknown"),
                    type(exc).__name__,
                )
                raise LLMError("The language model request failed") from exc
            return [response]

        tool_names = {getattr(tool, "name", "") for tool in tools}
        is_supervisor_run = any(name.startswith("delegate_to_") for name in tool_names)
        # Full-context collection nodes do not expose collection_search, but they
        # still process RAG-sized context and may legitimately need several
        # calculation/tool turns. Keep the collection execution budget for both
        # semantic-search and full-context modes.
        is_rag_run = is_collection_run or "collection_search" in tool_names
        tool_limit = (
            self.settings.supervisor_tool_call_limit if is_supervisor_run
            else self.settings.rag_tool_call_limit if is_rag_run
            else self.settings.agent_tool_call_limit
        )
        model_limit = (
            self.settings.supervisor_model_call_limit if is_supervisor_run
            else self.settings.rag_model_call_limit if is_rag_run
            else self.settings.agent_model_call_limit
        )
        recursion_limit = (
            self.settings.supervisor_recursion_limit if is_supervisor_run
            else self.settings.rag_recursion_limit if is_rag_run
            else self.settings.agent_recursion_limit
        )
        agent_graph = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            middleware=[
                ToolCallLimitMiddleware(run_limit=tool_limit, exit_behavior="error"),
                ModelCallLimitMiddleware(run_limit=model_limit, exit_behavior="error"),
            ],
        )

        try:
            result = agent_graph.invoke(
                {"messages": messages},
                config={
                    "recursion_limit": recursion_limit,
                    "callbacks": callbacks,
                    "metadata": metadata,
                },
            )
        except GraphRecursionError as exc:
            raise LLMError("The agent reached its execution limit") from exc
        except (ModelCallLimitExceededError, ToolCallLimitExceededError) as exc:
            raise LLMError("The agent reached its execution limit") from exc
        except OpenAIError as exc:
            logger.exception(
                "LLM provider request failed during agent execution: model=%s error_type=%s",
                getattr(model, "model_name", "unknown"),
                type(exc).__name__,
            )
            raise LLMError("The language model request failed") from exc
        return result.get("messages", [])

    def _route_request(
        self,
        model: ChatOpenAI,
        messages: list[dict[str, str]],
        skills: list[Any],
        tools: list[Any],
        cost_callback: ApiCostCallbackHandler | None = None,
        tracing_callbacks: list[Any] | None = None,
        tracing_metadata: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        skill_catalog = "\n".join(
            f"- {skill.name}: {skill.description}" for skill in skills
        ) or "- none"
        tool_catalog = "\n".join(
            f"- {tool.name}: {tool.description}" for tool in tools
        ) or "- none"
        latest_user = next((item["content"] for item in reversed(messages) if item["role"] == "user"), "")
        router = model.with_structured_output(RoutingDecision)
        try:
            router_messages = [
                SystemMessage(content=(
                    "Decompose the user's request into independently answerable parts. Select only relevant skills. "
                    "Do not select or execute a skill when the user is only asking how that capability works. "
                    "Select a tool as required when accurate completion needs calculation, current information, "
                    "external data, or an operation the model cannot reliably perform itself. "
                    "When the user asks for a recommendation and collection_search is available, always mark collection_search as required; "
                    "the assigned collection, not the model's general knowledge, must supply the recommendation. Use only catalog names.\n\n"
                    f"SKILLS\n{skill_catalog}\n\nTOOLS\n{tool_catalog}"
                )),
                HumanMessage(content=latest_user),
            ]
            callbacks = tracing_callbacks or ([cost_callback] if cost_callback else [])
            decision = (
                router.invoke(router_messages, config={
                    "callbacks": callbacks,
                    "metadata": tracing_metadata or {},
                })
                if callbacks or tracing_metadata
                else router.invoke(router_messages)
            )
        except Exception as exc:
            logger.exception(
                "Request routing failed: model=%s provider=%s error_type=%s",
                getattr(model, "model_name", "unknown"),
                getattr(getattr(self, "credentials", None), "provider", "unknown"),
                type(exc).__name__,
            )
            raise LLMError("The request router failed") from exc
        decision.skill_names = list(dict.fromkeys(decision.skill_names))
        decision.required_tool_names = list(dict.fromkeys(decision.required_tool_names))
        decision.request_parts = decision.request_parts or [latest_user]
        return decision

    def _execution_prompt(
        self,
        agent: Agent,
        skills: list[Any],
        required_tools: set[str],
        unavailable_skill_tools: dict[str, list[str]] | None = None,
    ) -> str:
        mandatory = ""
        if required_tools:
            mandatory = (
                "MANDATORY TOOLS\nBefore answering, you must call every tool in this list exactly when needed: "
                + ", ".join(sorted(required_tools))
                + ". Do not provide guessed substitutes for their results."
            )
        unavailable = ""
        if unavailable_skill_tools:
            details = "; ".join(
                f"{skill}: {', '.join(tools)}"
                for skill, tools in unavailable_skill_tools.items()
            )
            unavailable = (
                "UNAVAILABLE SKILL TOOLS\n"
                f"These skills cannot execute in this message because tools or attachments are unavailable: {details}. "
                "Do not claim to have processed a document. If the user asks to process one, ask them to attach it. "
                "If the user asks how the capability works, explain it normally without pretending to run the skill."
            )
        supervisor = ""
        if agent.agent_type == "supervisor":
            managed = ", ".join(item.name for item in agent.managed_agents)
            supervisor = (
                "SUPERVISOR MODE\n"
                f"You coordinate these managed agents: {managed}. "
                "Delegate specialist work through the delegate_to tools instead of performing it yourself. "
                "For a multi-stage request, call agents in the required order and pass the complete output of an "
                "earlier agent inside the next delegation task. Managed agents have isolated context and see only "
                "the task you send them. Synthesize their results faithfully and never claim an agent was called "
                "unless its delegation tool was actually used."
            )
        return build_effective_system_prompt(
            agent,
            "\n\n".join(
                part for part in (self.TOOL_RESULT_INSTRUCTIONS, supervisor, mandatory, unavailable) if part
            ),
            skills,
        )

    def _validate_response(
        self,
        model: ChatOpenAI,
        messages: list[dict[str, str]],
        request_parts: list[str],
        content: str,
        result_messages: list[Any],
        cost_callback: ApiCostCallbackHandler,
        tracing_callbacks: list[Any] | None = None,
        tracing_metadata: dict[str, Any] | None = None,
    ) -> ValidationDecision:
        tool_results = [
            f"{message.name}: {message.content}"
            for message in result_messages
            if isinstance(message, ToolMessage)
        ]
        validator = model.with_structured_output(ValidationDecision)
        try:
            return validator.invoke([
                SystemMessage(content=(
                    "Check whether the answer addresses every request part and faithfully incorporates all tool results. "
                    "Mark complete=false for an omitted part, guessed tool-dependent fact, or contradiction."
                )),
                HumanMessage(content=(
                    f"REQUEST PARTS:\n{request_parts}\n\nTOOL RESULTS:\n{tool_results}\n\nANSWER:\n{content}"
                )),
            ], config={
                "callbacks": tracing_callbacks or [cost_callback],
                "metadata": tracing_metadata or {},
            })
        except Exception as exc:
            raise LLMError("The response validator failed") from exc

    @staticmethod
    def _correction_instructions(missing_tools: list[str], missing_parts: list[str]) -> str:
        parts = []
        if missing_tools:
            parts.append("You failed to call these mandatory tools: " + ", ".join(missing_tools) + ".")
        if missing_parts:
            parts.append("You failed to answer these request parts: " + "; ".join(missing_parts) + ".")
        parts.append("Retry the entire answer, call mandatory tools, and answer every part.")
        return " ".join(parts)

    @staticmethod
    def _normalize_datetime_response(content: str, messages: list[Any]) -> str:
        datetime_result = next(
            (
                str(message.content)
                for message in reversed(messages)
                if isinstance(message, ToolMessage) and message.name == "current_datetime"
            ),
            None,
        )
        if not datetime_result:
            return content

        time_match = re.search(r"\btime=(\d{2}:\d{2}):\d{2}\b", datetime_result)
        timezone_match = re.search(r"\btimezone=([^;]+)", datetime_result)
        cleaned = re.sub(r"\s*\([^)]*\bbuçuk\b[^)]*\)", "", content, flags=re.IGNORECASE)
        cleaned = cleaned.replace("**", "")
        if time_match:
            times = list(re.finditer(r"\b\d{1,2}:\d{2}\b", cleaned))
            if times:
                last_time = times[-1]
                cleaned = cleaned[: last_time.start()] + time_match.group(1) + cleaned[last_time.end() :]
            else:
                timezone_name = timezone_match.group(1) if timezone_match else "requested timezone"
                cleaned = f"{cleaned.rstrip()}\n\nSaat bilgisi ({timezone_name}): {time_match.group(1)}."
        return cleaned.strip()

    @staticmethod
    def _used_tool_names(messages: list[Any]) -> list[str]:
        names: list[str] = []
        for message in messages:
            if isinstance(message, ToolMessage) and message.name and message.name not in names:
                names.append(message.name)
        return names

    @staticmethod
    def _append_generated_file_links(content: str, messages: list[Any]) -> str:
        links: list[tuple[str, str]] = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "text_to_pdf":
                continue
            try:
                payload = json.loads(str(message.content))
            except (json.JSONDecodeError, TypeError):
                continue
            url = payload.get("download_url")
            filename = payload.get("filename")
            if isinstance(url, str) and isinstance(filename, str) and (filename, url) not in links:
                links.append((filename, url))
        missing = [(name, url) for name, url in links if url not in content]
        if not missing:
            return content
        block = "\n".join(f"- [{name}]({url})" for name, url in missing)
        return f"{content.rstrip()}\n\nGenerated files:\n{block}"

    @staticmethod
    def _last_assistant_text(messages: list[Any]) -> str | None:
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            if isinstance(message.content, str):
                return message.content.strip() or None
            if isinstance(message.content, list):
                text_parts = [
                    block.get("text", "")
                    for block in message.content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "".join(text_parts).strip()
                return content or None
        return None
