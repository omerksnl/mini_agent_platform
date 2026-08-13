from datetime import datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.core.services.llm_service import ApiCostCallbackHandler, OpenRouterLLMClient, RoutingDecision
from app.core.tools import calculator, current_datetime


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1847 * 239", "441433"),
        ("(10 + 2) / 4", "3.0"),
        ("2 ** 10", "1024"),
    ],
)
def test_calculator(expression: str, expected: str) -> None:
    assert calculator.invoke({"expression": expression}) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').getcwd()",
        "2 ** 100",
        "1 / 0",
        "[1, 2, 3]",
    ],
)
def test_calculator_rejects_unsafe_or_excessive_input(expression: str) -> None:
    with pytest.raises(ValueError):
        calculator.invoke({"expression": expression})


def test_current_datetime_uses_requested_timezone() -> None:
    result = current_datetime.invoke({"timezone_name": "Europe/Istanbul"})
    fields = dict(part.split("=", 1) for part in result.split("; "))
    parsed = datetime.fromisoformat(f"{fields['date']}T{fields['time']}{fields['utc_offset']}")

    assert fields["timezone"] == "Europe/Istanbul"
    assert parsed.utcoffset() is not None


def test_current_datetime_rejects_unknown_timezone() -> None:
    with pytest.raises(ValueError, match="Unknown timezone"):
        current_datetime.invoke({"timezone_name": "Not/A_Timezone"})


def test_api_cost_prefers_openrouter_upstream_cost_when_cost_is_zero() -> None:
    callback = ApiCostCallbackHandler(input_rate=1.0, output_rate=5.0)
    response = SimpleNamespace(
        llm_output={
            "token_usage": {
                "cost": 0,
                "cost_details": {"upstream_inference_cost": 0.017666},
            }
        },
        generations=[],
    )
    callback.on_llm_end(response)
    assert callback.total_cost_usd == pytest.approx(0.017666)


def test_datetime_response_removes_incorrect_colloquial_time() -> None:
    messages = [
        ToolMessage(
            content="timezone=Europe/Vienna; date=2026-08-05; time=11:59:12; utc_offset=+02:00",
            tool_call_id="call-1",
            name="current_datetime",
        ),
        AIMessage(content="Viyana'da saat **11:58** (sabah 11 buçuk 58)."),
    ]

    result = OpenRouterLLMClient._normalize_datetime_response(
        messages[-1].content,
        messages,
    )

    assert result == "Viyana'da saat 11:59."


def test_datetime_response_appends_omitted_tool_result() -> None:
    messages = [
        ToolMessage(
            content="timezone=Europe/Istanbul; date=2026-08-06; time=14:27:12; utc_offset=+03:00",
            tool_call_id="call-1",
            name="current_datetime",
        ),
        AIMessage(content="XML, etiketlerle veri saklama biçimidir."),
    ]

    result = OpenRouterLLMClient._normalize_datetime_response(messages[-1].content, messages)

    assert result == (
        "XML, etiketlerle veri saklama biçimidir.\n\n"
        "Saat bilgisi (Europe/Istanbul): 14:27."
    )


def test_router_deduplicates_selected_skills_and_tools() -> None:
    class StructuredRouter:
        def invoke(self, messages):
            return RoutingDecision(
                request_parts=["Explain HTML", "Give current Istanbul time"],
                skill_names=["beginner_tutor", "beginner_tutor"],
                required_tool_names=["current_datetime", "current_datetime"],
            )

    class FakeModel:
        def with_structured_output(self, schema):
            return StructuredRouter()

    client = object.__new__(OpenRouterLLMClient)
    decision = client._route_request(
        FakeModel(),
        [{"role": "user", "content": "HTML nedir? İstanbul'da saat kaç?"}],
        [SimpleNamespace(name="beginner_tutor", description="Explain simply")],
        [current_datetime],
    )

    assert decision.request_parts == ["Explain HTML", "Give current Istanbul time"]
    assert decision.skill_names == ["beginner_tutor"]
    assert decision.required_tool_names == ["current_datetime"]


def test_correction_instructions_cover_tools_and_missing_parts() -> None:
    result = OpenRouterLLMClient._correction_instructions(
        ["current_datetime"],
        ["Give current Istanbul time"],
    )

    assert "current_datetime" in result
    assert "Give current Istanbul time" in result
    assert "Retry the entire answer" in result


def test_tool_free_agent_invokes_model_directly_once() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.calls = []

        def invoke(self, messages, config):
            self.calls.append((messages, config))
            return AIMessage(content="Scoring completed")

    client = object.__new__(OpenRouterLLMClient)
    model = FakeModel()
    callback = ApiCostCallbackHandler(input_rate=1.0, output_rate=5.0)

    result = client._invoke_agent(
        model,
        [],
        "Score the candidate.",
        [{"role": "user", "content": "Evaluate this profile."}],
        callback,
        is_collection_run=True,
    )

    assert len(model.calls) == 1
    assert model.calls[0][0][0].content == "Score the candidate."
    assert result == [AIMessage(content="Scoring completed")]
