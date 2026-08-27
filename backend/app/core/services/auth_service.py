from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models import Tenant, User
from app.schemas.auth import LoginRequest, ProfileUpdateRequest, RegisterRequest


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

    def update_profile(self, user: User, tenant: Tenant, payload: ProfileUpdateRequest) -> None:
        new_email = payload.email.lower() if payload.email else user.email
        protected_change = new_email != user.email or payload.new_password is not None
        if protected_change and (
            not payload.current_password
            or not verify_password(payload.current_password, user.hashed_password)
        ):
            raise AuthError("Current password is incorrect", status_code=401)

        if new_email != user.email:
            existing = self.db.scalar(select(User).where(User.email == new_email, User.id != user.id))
            if existing:
                raise AuthError("Email already registered", status_code=409)
            user.email = new_email
        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()
        if payload.tenant_name is not None:
            tenant.name = payload.tenant_name.strip()
        if payload.new_password is not None:
            user.hashed_password = hash_password(payload.new_password)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AuthError("Email already registered", status_code=409) from exc
        self.db.refresh(user)
        self.db.refresh(tenant)
