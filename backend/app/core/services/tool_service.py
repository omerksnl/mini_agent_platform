from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import HttpTool
from app.schemas.tool import HttpToolCreate, HttpToolUpdate

RESERVED_TOOL_NAMES = {"calculator", "current_datetime"}


class ToolError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ToolService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_tools(self, tenant_id: UUID) -> list[HttpTool]:
        return list(
            self.db.scalars(
                select(HttpTool)
                .where(HttpTool.tenant_id == tenant_id)
                .order_by(HttpTool.created_at.desc())
            ).all()
        )

    def get_tool(self, tool_id: UUID, tenant_id: UUID) -> HttpTool:
        tool = self.db.scalar(
            select(HttpTool).where(HttpTool.id == tool_id, HttpTool.tenant_id == tenant_id)
        )
        if not tool:
            raise ToolError("Tool not found", status_code=404)
        return tool

    def get_tools(self, tool_ids: list[UUID], tenant_id: UUID) -> list[HttpTool]:
        if not tool_ids:
            return []
        tools = list(
            self.db.scalars(
                select(HttpTool).where(
                    HttpTool.id.in_(tool_ids),
                    HttpTool.tenant_id == tenant_id,
                )
            ).all()
        )
        if len(tools) != len(set(tool_ids)):
            raise ToolError("One or more tools were not found", status_code=400)
        by_id = {tool.id: tool for tool in tools}
        return [by_id[tool_id] for tool_id in tool_ids]

    def create_tool(self, tenant_id: UUID, payload: HttpToolCreate) -> HttpTool:
        if payload.name in RESERVED_TOOL_NAMES:
            raise ToolError("This name is reserved for a system tool", status_code=409)
        tool = HttpTool(
            tenant_id=tenant_id,
            name=payload.name,
            description=payload.description,
            url=str(payload.url),
            method=payload.method,
            parameters=[parameter.model_dump() for parameter in payload.parameters],
        )
        self.db.add(tool)
        self._commit(tool)
        return tool

    def update_tool(self, tool_id: UUID, tenant_id: UUID, payload: HttpToolUpdate) -> HttpTool:
        tool = self.get_tool(tool_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        if data.get("name") in RESERVED_TOOL_NAMES:
            raise ToolError("This name is reserved for a system tool", status_code=409)
        if "url" in data:
            data["url"] = str(data["url"])
        if "parameters" in data:
            data["parameters"] = [parameter.model_dump() for parameter in payload.parameters or []]
        for key, value in data.items():
            setattr(tool, key, value)
        self._commit(tool)
        return tool

    def delete_tool(self, tool_id: UUID, tenant_id: UUID) -> None:
        tool = self.get_tool(tool_id, tenant_id)
        self.db.delete(tool)
        self.db.commit()

    def _commit(self, tool: HttpTool) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ToolError("A tool with this name already exists", status_code=409) from exc
        self.db.refresh(tool)
