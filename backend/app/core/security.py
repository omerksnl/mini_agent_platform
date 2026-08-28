from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(*, subject: str, tenant_id: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "tenant_id": tenant_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def create_a2a_billing_token(*, user_id: str, credential_id: str, agent_id: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": user_id,
        "credential_id": credential_id,
        "agent_id": agent_id,
        "purpose": "a2a-caller-billing",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_a2a_billing_token(token: str, *, agent_id: str) -> dict[str, Any]:
    payload = decode_access_token(token)
    if payload.get("purpose") != "a2a-caller-billing" or payload.get("agent_id") != agent_id:
        raise ValueError("Invalid A2A billing token")
    if not payload.get("sub") or not payload.get("credential_id"):
        raise ValueError("Invalid A2A billing token")
    return payload


def parse_uuid(value: str) -> UUID:
    return UUID(value)
