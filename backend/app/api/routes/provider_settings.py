import httpx
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import CurrentUser, get_current_user
from app.core.services.provider_service import ProviderError, ProviderService
from app.db.session import get_db
from app.schemas.provider import (
    ProviderModelResponse,
    ProviderCredentialResponse,
    ProviderCompatibilityResponse,
    ProviderSettingsResponse,
    ProviderSettingsUpdate,
    ProviderTestResponse,
    AgentProviderAssignmentResponse,
    AgentProviderAssignmentUpdate,
)
from app.models import Agent

router = APIRouter(prefix="/provider-settings", tags=["provider-settings"])

OPENROUTER_MODELS = [
    ProviderModelResponse(id="anthropic/claude-haiku-4.5", label="Claude Haiku 4.5"),
    ProviderModelResponse(id="openai/gpt-4o-mini", label="GPT-4o mini"),
]
OPENAI_MODELS = [
    ProviderModelResponse(id="gpt-4o-mini", label="GPT-4o mini"),
    ProviderModelResponse(id="gpt-4.1-nano", label="GPT-4.1 nano"),
    ProviderModelResponse(id="gpt-4.1-mini", label="GPT-4.1 mini"),
    ProviderModelResponse(id="gpt-4.1", label="GPT-4.1"),
]


def _response(current: CurrentUser, service: ProviderService) -> ProviderSettingsResponse:
    credentials = service.resolve(current.user)
    personal = credentials.uses_personal_key
    return ProviderSettingsResponse(
        provider=credentials.provider,
        source="personal" if personal else "platform",
        has_personal_key=personal,
        masked_key="••••••••" if personal else None,
    )


@router.get("", response_model=ProviderSettingsResponse)
def get_provider_settings(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> ProviderSettingsResponse:
    try:
        return _response(current, ProviderService(db))
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("", response_model=ProviderSettingsResponse)
def update_provider_settings(
    payload: ProviderSettingsUpdate,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> ProviderSettingsResponse:
    service = ProviderService(db)
    try:
        service.save(current.user, payload.provider, payload.api_key, payload.name)
        return _response(current, service)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_provider_settings(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> None:
    ProviderService(db).clear(current.user)


@router.get("/credentials", response_model=list[ProviderCredentialResponse])
def list_provider_credentials(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> list[ProviderCredentialResponse]:
    return [ProviderCredentialResponse(
        id=item.id, name=item.name, provider=item.provider,
        is_active=item.is_active, created_at=item.created_at,
    ) for item in ProviderService(db).list_profiles(current.user)]


@router.post("/credentials/{credential_id}/activate", response_model=ProviderSettingsResponse)
def activate_provider_credential(
    credential_id: UUID, db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> ProviderSettingsResponse:
    service = ProviderService(db)
    try:
        service.activate(current.user, credential_id)
        return _response(current, service)
    except ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_credential(
    credential_id: UUID, db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        ProviderService(db).delete_profile(current.user, credential_id)
    except ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/test", response_model=ProviderTestResponse)
def test_provider_settings(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> ProviderTestResponse:
    try:
        credentials = ProviderService(db).resolve(current.user)
        response = httpx.get(
            f"{credentials.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {credentials.api_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail="The provider rejected this API key") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The provider could not be reached") from exc
    return ProviderTestResponse(provider=credentials.provider)


@router.get("/models", response_model=list[ProviderModelResponse])
def list_provider_models(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> list[ProviderModelResponse]:
    try:
        provider = ProviderService(db).resolve(current.user).provider
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OPENAI_MODELS if provider == "openai" else OPENROUTER_MODELS


def _openai_compatible(model: str) -> bool:
    return model.startswith(("gpt-", "o1", "o3", "o4", "openai/"))


@router.get("/compatibility", response_model=ProviderCompatibilityResponse)
def provider_compatibility(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> ProviderCompatibilityResponse:
    provider = ProviderService(db).resolve(current.user).provider
    agents = list(db.scalars(select(Agent).where(Agent.tenant_id == current.tenant_id)).all())
    incompatible = [item.name for item in agents if provider == "openai" and not _openai_compatible(item.model)]
    return ProviderCompatibilityResponse(
        provider=provider, incompatible_agents=incompatible,
        recommended_model="gpt-4.1-mini" if incompatible else None,
    )


@router.post("/compatibility/migrate", response_model=ProviderCompatibilityResponse)
def migrate_provider_models(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> ProviderCompatibilityResponse:
    provider = ProviderService(db).resolve(current.user).provider
    if provider != "openai":
        return ProviderCompatibilityResponse(provider=provider, incompatible_agents=[])
    agents = list(db.scalars(select(Agent).where(Agent.tenant_id == current.tenant_id)).all())
    for agent in agents:
        if not _openai_compatible(agent.model):
            agent.model = "gpt-4.1-mini"
    db.commit()
    return ProviderCompatibilityResponse(provider="openai", incompatible_agents=[])


@router.get("/agent-assignments", response_model=list[AgentProviderAssignmentResponse])
def list_agent_provider_assignments(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> list[AgentProviderAssignmentResponse]:
    return [AgentProviderAssignmentResponse(
        agent_id=item.agent_id, credential_id=item.provider_credential_id
    ) for item in ProviderService(db).list_agent_assignments(current.user)]


@router.put("/agent-assignments/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def set_agent_provider_assignment(
    agent_id: UUID, payload: AgentProviderAssignmentUpdate,
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        ProviderService(db).assign_agent_profile(
            current.user, current.tenant_id, agent_id, payload.credential_id
        )
    except ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
