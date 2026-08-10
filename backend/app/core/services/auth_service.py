from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models import Tenant, User
from app.schemas.auth import LoginRequest, RegisterRequest


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class AuthResult:
    access_token: str
    user: User
    tenant: Tenant


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: RegisterRequest) -> AuthResult:
        existing = self.db.scalar(select(User).where(User.email == payload.email.lower()))
        if existing:
            raise AuthError("Email already registered", status_code=409)

        tenant = Tenant(name=payload.tenant_name)
        user = User(
            email=payload.email.lower(),
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            tenant=tenant,
        )
        self.db.add(tenant)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AuthError("Email already registered", status_code=409) from exc
        self.db.refresh(user)
        self.db.refresh(tenant)

        token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
        return AuthResult(access_token=token, user=user, tenant=tenant)

    def login(self, payload: LoginRequest) -> AuthResult:
        user = self.db.scalar(select(User).where(User.email == payload.email.lower()))
        if not user or not verify_password(payload.password, user.hashed_password):
            raise AuthError("Invalid email or password", status_code=401)

        tenant = self.db.get(Tenant, user.tenant_id)
        if not tenant:
            raise AuthError("Tenant not found", status_code=500)

        token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
        return AuthResult(access_token=token, user=user, tenant=tenant)

    def get_user(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        return self.db.get(Tenant, tenant_id)
