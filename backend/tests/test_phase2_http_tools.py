from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import ToolException

from app.core.tools.http_tools import HttpToolExecutor, build_http_tool
from app.models import HttpTool
from tests.test_phase1 import auth_headers, register


def tool_payload(name: str = "weather_lookup") -> dict:
    return {
        "name": name,
        "description": "Get weather information for a city",
        "url": "https://api.example.com/weather",
        "method": "GET",
        "parameters": [
            {
                "name": "city",
                "type": "string",
                "description": "City name",
                "required": True,
            }
        ],
    }


def create_tool(client: TestClient, token: str, name: str = "weather_lookup") -> dict:
    response = client.post("/api/tools", headers=auth_headers(token), json=tool_payload(name))
    assert response.status_code == 201, response.text
    return response.json()


def test_http_tool_crud_and_tenant_isolation(client: TestClient) -> None:
    tenant_a = register(client, email="tool-a@example.com", tenant_name="Tools A")
    tool = create_tool(client, tenant_a)

    listed = client.get("/api/tools", headers=auth_headers(tenant_a))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [tool["id"]]

    updated = client.patch(
        f"/api/tools/{tool['id']}",
        headers=auth_headers(tenant_a),
        json={"description": "Updated weather description", "method": "POST"},
    )
    assert updated.status_code == 200
    assert updated.json()["method"] == "POST"

    duplicate = client.post("/api/tools", headers=auth_headers(tenant_a), json=tool_payload())
    assert duplicate.status_code == 409

    tenant_b = register(client, email="tool-b@example.com", tenant_name="Tools B")
    tenant_b_headers = auth_headers(tenant_b)
    assert client.get("/api/tools", headers=tenant_b_headers).json() == []
    assert client.get(f"/api/tools/{tool['id']}", headers=tenant_b_headers).status_code == 404
    assert client.patch(
        f"/api/tools/{tool['id']}", headers=tenant_b_headers, json={"description": "stolen"}
    ).status_code == 404
    assert client.delete(f"/api/tools/{tool['id']}", headers=tenant_b_headers).status_code == 404

    assert client.delete(f"/api/tools/{tool['id']}", headers=auth_headers(tenant_a)).status_code == 204


def test_agent_can_select_only_its_tenant_tools(client: TestClient) -> None:
    tenant_a = register(client, email="agent-tool-a@example.com", tenant_name="Agent Tools A")
    tool = create_tool(client, tenant_a)
    agent_response = client.post(
        "/api/agents",
        headers=auth_headers(tenant_a),
        json={
            "name": "weather_agent",
            "system_prompt": "Use tools when needed.",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.2,
            "system_tools": ["calculator"],
            "tool_ids": [tool["id"]],
        },
    )
    assert agent_response.status_code == 201, agent_response.text
    assert agent_response.json()["system_tools"] == ["calculator"]
    assert agent_response.json()["tool_ids"] == [tool["id"]]

    tenant_b = register(client, email="agent-tool-b@example.com", tenant_name="Agent Tools B")
    forbidden = client.post(
        "/api/agents",
        headers=auth_headers(tenant_b),
        json={"name": "bad_agent", "tool_ids": [tool["id"]]},
    )
    assert forbidden.status_code == 400


def test_tool_validation_rejects_invalid_definitions(client: TestClient) -> None:
    token = register(client, email="invalid-tool@example.com")
    invalid_name = client.post(
        "/api/tools", headers=auth_headers(token), json=tool_payload("Invalid Tool")
    )
    assert invalid_name.status_code == 422

    duplicate_parameters = tool_payload("duplicate_parameters")
    duplicate_parameters["parameters"].append(duplicate_parameters["parameters"][0])
    assert client.post(
        "/api/tools", headers=auth_headers(token), json=duplicate_parameters
    ).status_code == 422

    reserved = client.post(
        "/api/tools", headers=auth_headers(token), json=tool_payload("calculator")
    )
    assert reserved.status_code == 409


@pytest.mark.parametrize("url", ["http://localhost/test", "http://127.0.0.1/test", "http://10.0.0.1/test"])
def test_http_executor_blocks_local_and_private_networks(url: str) -> None:
    with pytest.raises(ToolException, match="Local|private"):
        HttpToolExecutor.validate_public_url(url)


def test_structured_http_tool_validates_model_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    definition = HttpTool(
        id=uuid4(),
        tenant_id=uuid4(),
        name="population_lookup",
        description="Look up population",
        url="https://api.example.com/population",
        method="GET",
        parameters=[
            {"name": "city", "type": "string", "description": "City", "required": True},
            {"name": "year", "type": "integer", "description": "Year", "required": False},
        ],
    )
    captured: dict = {}

    def fake_execute(_definition: HttpTool, arguments: dict) -> str:
        captured.update(arguments)
        return '{"population": 1}'

    monkeypatch.setattr(HttpToolExecutor, "execute", fake_execute)
    structured_tool = build_http_tool(definition)

    assert structured_tool.invoke({"city": "Izmir", "year": 2026}) == '{"population": 1}'
    assert captured == {"city": "Izmir", "year": 2026}
    with pytest.raises(Exception):
        structured_tool.invoke({"year": "not-an-integer"})


def test_get_tool_preserves_url_query_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    definition = HttpTool(
        id=uuid4(),
        tenant_id=uuid4(),
        name="weather",
        description="Current weather",
        url="https://api.example.com/forecast?current=temperature_2m&timezone=auto",
        method="GET",
        parameters=[],
    )
    captured: dict = {}

    class FakeResponse:
        is_redirect = False
        encoding = "utf-8"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b'{"current":{"temperature_2m":29.2}}'

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, method: str, url: str, **kwargs):
            captured.update({"method": method, "url": url, **kwargs})
            return FakeResponse()

    monkeypatch.setattr(HttpToolExecutor, "validate_public_url", lambda _url: None)
    monkeypatch.setattr("app.core.tools.http_tools.httpx.Client", FakeClient)

    result = HttpToolExecutor.execute(definition, {"latitude": 38.4161, "longitude": 27.1398})

    assert captured["params"] == [
        ("current", "temperature_2m"),
        ("timezone", "auto"),
        ("latitude", 38.4161),
        ("longitude", 27.1398),
    ]
    assert '"temperature_2m": 29.2' in result
