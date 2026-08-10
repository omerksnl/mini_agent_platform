from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.tool_service import ToolError, ToolService
from app.db.session import get_db
from app.schemas.tool import HttpToolCreate, HttpToolResponse, HttpToolUpdate

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[HttpToolResponse])
def list_tools(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[HttpToolResponse]:
    return [HttpToolResponse.model_validate(item) for item in ToolService(db).list_tools(current.tenant_id)]


@router.post("", response_model=HttpToolResponse, status_code=status.HTTP_201_CREATED)
def create_tool(payload: HttpToolCreate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> HttpToolResponse:
    try:
        tool = ToolService(db).create_tool(current.tenant_id, payload)
    except ToolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return HttpToolResponse.model_validate(tool)


@router.get("/{tool_id}", response_model=HttpToolResponse)
def get_tool(tool_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> HttpToolResponse:
    try:
        tool = ToolService(db).get_tool(tool_id, current.tenant_id)
    except ToolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return HttpToolResponse.model_validate(tool)


@router.patch("/{tool_id}", response_model=HttpToolResponse)
def update_tool(tool_id: UUID, payload: HttpToolUpdate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> HttpToolResponse:
    try:
        tool = ToolService(db).update_tool(tool_id, current.tenant_id, payload)
    except ToolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return HttpToolResponse.model_validate(tool)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(tool_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> None:
    try:
        ToolService(db).delete_tool(tool_id, current.tenant_id)
    except ToolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
