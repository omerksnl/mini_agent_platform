from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, parse_uuid
from app.core.services.auth_service import AuthService
from app.core.services.llm_service import LLMClient, LLMError, OpenRouterLLMClient
from app.core.services.provider_service import ProviderError, ProviderService
from app.db.session import get_db
from app.models import Tenant, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_platform_llm_client() -> LLMClient:
    try:
        return OpenRouterLLMClient()
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@dataclass
class CurrentUser:
    user: User
    tenant: Tenant

    @property
    def id(self) -> UUID:
        return self.user.id

    @property
    def tenant_id(self) -> UUID:
        return self.tenant.id


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = parse_uuid(payload["sub"])
        tenant_id = parse_uuid(payload["tenant_id"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    auth_service = AuthService(db)
    user = auth_service.get_user(user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    tenant = auth_service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return CurrentUser(user=user, tenant=tenant)


def get_llm_client(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> LLMClient:
    try:
        credentials = ProviderService(db).resolve(current.user)
        return OpenRouterLLMClient(credentials, user_id=current.user.id)
    except (ProviderError, LLMError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
