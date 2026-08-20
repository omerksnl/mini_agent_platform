from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class A2ATextPart(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=50000)


class A2AFileContent(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=255)
    mimeType: Literal["application/pdf"] = "application/pdf"
    bytes: str = Field(min_length=1, max_length=13_400_000)


class A2AFilePart(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: Literal["file"] = "file"
    file: A2AFileContent


class A2AMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: Literal["message"] = "message"
    role: Literal["user", "agent"]
    parts: list[A2ATextPart | A2AFilePart] = Field(min_length=1, max_length=6)
    messageId: str | None = None
    contextId: str | None = None


class A2AMessageSendParams(BaseModel):
    message: A2AMessage
    configuration: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class A2AJsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"]
    id: str | int | None = None
    method: str
    params: A2AMessageSendParams | None = None
