import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.tools import StructuredTool

from app.core.observability import emit_guardrail_event
from app.models import Guardrail

logger = logging.getLogger(__name__)
GuardrailDecision = Literal["pass", "warn", "redact", "block"]


@dataclass(frozen=True)
class GuardrailResult:
    guardrail_name: str
    stage: str
    decision: GuardrailDecision
    content: str
    reason: str = ""


class GuardrailViolation(Exception):
    pass


_PII_PATTERNS = {
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE),
    "phone": re.compile(r"(?<!\w)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}(?!\w)"),
    "ip_address": re.compile(r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"),
}


class GuardrailRunner:
    """Runs local deterministic policies. It never invokes an LLM."""

    def __init__(self, guardrails: list[Guardrail], *, agent_name: str, tenant_id: Any) -> None:
        self.guardrails = [item for item in guardrails if item.is_active]
        self.agent_name = agent_name
        self.tenant_id = str(tenant_id)

    def apply(self, stage: str, content: str) -> str:
        current = content
        for policy in self.guardrails:
            if stage not in policy.stages:
                continue
            result = self._evaluate(policy, stage, current)
            self._record(result)
            if result.decision == "block":
                raise GuardrailViolation(result.reason or f"Blocked by {policy.name}")
            current = result.content
        return current

    def record_tool_permission(self, tool_name: str, allowed_names: set[str]) -> None:
        decision: GuardrailDecision = "pass" if tool_name in allowed_names else "block"
        result = GuardrailResult(
            "platform_tool_permission",
            "tool_input",
            decision,
            "",
            "Tool is assigned to the agent" if decision == "pass" else "Tool is not assigned to the agent",
        )
        self._record(result, {"tool_name": tool_name})
        if decision == "block":
            raise GuardrailViolation(result.reason)

    def wrap_tools(self, tools: list[Any]) -> list[Any]:
        """Apply configured tool-input/output policies at the actual execution boundary."""
        wrapped: list[Any] = []
        allowed_names = {getattr(tool, "name", "") for tool in tools}
        for tool in tools:
            name = getattr(tool, "name", "")
            args_schema = getattr(tool, "args_schema", None)

            def invoke_guarded(_tool=tool, _name=name, **kwargs: Any) -> Any:
                self.record_tool_permission(_name, allowed_names)
                serialized = json.dumps(kwargs, ensure_ascii=False, default=str)
                guarded = self.apply("tool_input", serialized)
                safe_kwargs = json.loads(guarded)
                result = _tool.invoke(safe_kwargs)
                if isinstance(result, str):
                    return self.apply("tool_output", result)
                guarded_result = self.apply("tool_output", json.dumps(result, ensure_ascii=False, default=str))
                try:
                    return json.loads(guarded_result)
                except json.JSONDecodeError:
                    return guarded_result

            wrapped.append(StructuredTool.from_function(
                func=invoke_guarded,
                name=name,
                description=getattr(tool, "description", ""),
                args_schema=args_schema,
            ))
        return wrapped

    def _evaluate(self, policy: Guardrail, stage: str, content: str) -> GuardrailResult:
        if policy.guardrail_type == "pii_redaction":
            redacted = content
            found: list[str] = []
            selected = policy.config.get("types", list(_PII_PATTERNS))
            for kind in selected:
                pattern = _PII_PATTERNS.get(kind)
                if pattern and pattern.search(redacted):
                    found.append(kind)
                    redacted = pattern.sub(f"[REDACTED_{kind.upper()}]", redacted)
            return GuardrailResult(policy.name, stage, "redact" if found else "pass", redacted, ", ".join(found))

        if policy.guardrail_type == "blocked_terms":
            matched = [term for term in policy.config.get("terms", []) if term.casefold() in content.casefold()]
            if not matched:
                return GuardrailResult(policy.name, stage, "pass", content)
            if policy.action == "redact":
                redacted = content
                for term in matched:
                    redacted = re.sub(re.escape(term), "[REDACTED_TERM]", redacted, flags=re.IGNORECASE)
                return GuardrailResult(policy.name, stage, "redact", redacted, "Blocked term redacted")
            return GuardrailResult(policy.name, stage, policy.action, content, "Blocked topic detected")

        if policy.guardrail_type == "required_output_fields":
            try:
                parsed = json.loads(self._strip_json_fence(content))
            except (json.JSONDecodeError, TypeError):
                return GuardrailResult(policy.name, stage, policy.action, content, "Output is not valid JSON")
            missing = [field for field in policy.config.get("fields", []) if not self._has_path(parsed, field)]
            return GuardrailResult(
                policy.name, stage, policy.action if missing else "pass", content,
                f"Missing required fields: {', '.join(missing)}" if missing else "",
            )
        return GuardrailResult(policy.name, stage, "warn", content, "Unknown guardrail type")

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        return text

    @staticmethod
    def _has_path(value: Any, path: str) -> bool:
        current = value
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current or current[key] in (None, "", []):
                return False
            current = current[key]
        return True

    def _record(self, result: GuardrailResult, extra: dict[str, Any] | None = None) -> None:
        metadata = {
            "guardrail": result.guardrail_name,
            "stage": result.stage,
            "decision": result.decision,
            "reason": result.reason,
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            **(extra or {}),
        }
        logger.info("guardrail.check", extra={"guardrail_event": metadata})
        emit_guardrail_event(metadata)
