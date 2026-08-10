import ipaddress
import json
import socket
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field, create_model

from app.config import get_settings
from app.models import HttpTool

PARAMETER_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


class HttpToolExecutor:
    @staticmethod
    def validate_public_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ToolException("Tool URL must use HTTP or HTTPS")
        if parsed.username or parsed.password:
            raise ToolException("Credentials are not allowed in tool URLs")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ToolException("Local network addresses are not allowed")
        try:
            addresses = socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ToolException("Tool host could not be resolved") from exc
        for address in addresses:
            if not ipaddress.ip_address(address[4][0]).is_global:
                raise ToolException("Local or private network addresses are not allowed")

    @classmethod
    def execute(cls, definition: HttpTool, arguments: dict[str, Any]) -> str:
        cls.validate_public_url(definition.url)
        settings = get_settings()
        payload = {key: value for key, value in arguments.items() if value is not None}
        try:
            with httpx.Client(
                timeout=settings.http_tool_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                request_kwargs = (
                    {
                        "params": [
                            *parse_qsl(urlsplit(definition.url).query, keep_blank_values=True),
                            *payload.items(),
                        ]
                    }
                    if definition.method == "GET"
                    else {"json": payload}
                )
                with client.stream(definition.method, definition.url, **request_kwargs) as response:
                    if response.is_redirect:
                        raise ToolException("Tool redirects are not allowed")
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > settings.http_tool_max_response_bytes:
                            raise ToolException("Tool response is too large")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
        except ToolException:
            raise
        except (httpx.HTTPError, UnicodeError) as exc:
            raise ToolException("HTTP tool request failed") from exc
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            return body
        return json.dumps(parsed_body, ensure_ascii=False)


def _argument_schema(definition: HttpTool) -> type[BaseModel]:
    fields: dict[str, tuple[Any, Any]] = {}
    for parameter in definition.parameters:
        python_type = PARAMETER_TYPES[parameter["type"]]
        description = parameter.get("description", "")
        if parameter.get("required", True):
            fields[parameter["name"]] = (python_type, Field(..., description=description))
        else:
            fields[parameter["name"]] = (python_type | None, Field(None, description=description))
    return create_model(f"{definition.name.title().replace('_', '')}Arguments", **fields)


def build_http_tool(definition: HttpTool) -> StructuredTool:
    def call_http_tool(**kwargs: Any) -> str:
        return HttpToolExecutor.execute(definition, kwargs)

    return StructuredTool.from_function(
        func=call_http_tool,
        name=definition.name,
        description=definition.description,
        args_schema=_argument_schema(definition),
        handle_tool_error=True,
    )


def build_http_tools(definitions: list[HttpTool]) -> list[StructuredTool]:
    return [build_http_tool(definition) for definition in definitions]
