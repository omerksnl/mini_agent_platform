from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Agent, AgentProviderAssignment, ProviderCredential, User


SUPPORTED_PROVIDERS = {"openrouter", "openai"}


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class ProviderCredentials:
    provider: str
    api_key: str
    base_url: str
    uses_personal_key: bool = False


class ProviderService:
    def __init__(self, db: Session | None = None, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        digest = hashlib.sha256(self.settings.secret_key.encode("utf-8")).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(digest))

    def _platform_credentials(self) -> ProviderCredentials:
        provider = self.settings.llm_provider.strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ProviderError("LLM_PROVIDER must be openrouter or openai")
        if provider == "openai":
            if not self.settings.openai_api_key:
                raise ProviderError("OpenAI API key is not configured")
            return ProviderCredentials(provider, self.settings.openai_api_key, self.settings.openai_base_url)
        if not self.settings.openrouter_api_key:
            raise ProviderError("OpenRouter API key is not configured")
        return ProviderCredentials(provider, self.settings.openrouter_api_key, self.settings.openrouter_base_url)

    def resolve(self, user: User | None = None) -> ProviderCredentials:
        if user and self.db is not None:
            profile = self.db.scalar(select(ProviderCredential).where(
                ProviderCredential.user_id == user.id, ProviderCredential.is_active.is_(True)
            ))
            if profile:
                return self._decrypt(profile.provider, profile.encrypted_api_key)
        if user and user.llm_provider and user.encrypted_llm_api_key:
            return self._decrypt(user.llm_provider, user.encrypted_llm_api_key)
        return self._platform_credentials()

    def resolve_for_agent(self, user_id, agent_id) -> ProviderCredentials:
        if self.db is None:
            return self._platform_credentials()
        assignment = self.db.scalar(select(AgentProviderAssignment).where(
            AgentProviderAssignment.user_id == user_id,
            AgentProviderAssignment.agent_id == agent_id,
        ))
        if assignment:
            profile = self.db.scalar(select(ProviderCredential).where(
                ProviderCredential.id == assignment.provider_credential_id,
                ProviderCredential.user_id == user_id,
            ))
            if profile:
                return self._decrypt(profile.provider, profile.encrypted_api_key)
        user = self.db.get(User, user_id)
        return self.resolve(user)

    def resolve_profile(self, user_id, profile_id) -> ProviderCredentials:
        if self.db is None:
            raise ProviderError("Provider database context is unavailable")
        profile = self.db.scalar(select(ProviderCredential).where(
            ProviderCredential.id == profile_id,
            ProviderCredential.user_id == user_id,
        ))
        if not profile:
            raise ProviderError("Saved API key not found")
        return self._decrypt(profile.provider, profile.encrypted_api_key)

    def list_agent_assignments(self, user: User) -> list[AgentProviderAssignment]:
        if self.db is None:
            return []
        return list(self.db.scalars(select(AgentProviderAssignment).where(
            AgentProviderAssignment.user_id == user.id
        )).all())

    def assign_agent_profile(self, user: User, tenant_id, agent_id, profile_id):
        if self.db is None:
            raise ProviderError("Provider database context is unavailable")
        agent = self.db.scalar(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
        if not agent:
            raise ProviderError("Agent not found")
        existing = self.db.scalar(select(AgentProviderAssignment).where(
            AgentProviderAssignment.user_id == user.id,
            AgentProviderAssignment.agent_id == agent_id,
        ))
        if profile_id is None:
            if existing:
                self.db.delete(existing)
                self.db.commit()
            return None
        profile = self.db.scalar(select(ProviderCredential).where(
            ProviderCredential.id == profile_id, ProviderCredential.user_id == user.id
        ))
        if not profile:
            raise ProviderError("Saved API key not found")
        if existing:
            existing.provider_credential_id = profile.id
        else:
            existing = AgentProviderAssignment(
                user_id=user.id, agent_id=agent_id, provider_credential_id=profile.id
            )
            self.db.add(existing)
        self.db.commit()
        return existing

    def _decrypt(self, provider: str, encrypted_key: str) -> ProviderCredentials:
        try:
            key = self.cipher.decrypt(encrypted_key.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise ProviderError("Stored API key could not be decrypted") from exc
        provider = provider.lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ProviderError("Stored LLM provider is unsupported")
        base_url = self.settings.openai_base_url if provider == "openai" else self.settings.openrouter_base_url
        return ProviderCredentials(provider, key, base_url, True)

    def list_profiles(self, user: User) -> list[ProviderCredential]:
        if self.db is None:
            return []
        return list(self.db.scalars(select(ProviderCredential).where(
            ProviderCredential.user_id == user.id
        ).order_by(ProviderCredential.created_at.desc())).all())

    def save(self, user: User, provider: str, api_key: str, name: str = "Personal key") -> ProviderCredential:
        provider = provider.strip().lower()
        api_key = api_key.strip()
        if provider not in SUPPORTED_PROVIDERS:
            raise ProviderError("Provider must be openrouter or openai")
        if len(api_key) < 16:
            raise ProviderError("API key is too short")
        if self.db is None:
            raise ProviderError("Provider database context is unavailable")
        name = name.strip()
        if not name:
            raise ProviderError("Credential name is required")
        self.db.execute(update(ProviderCredential).where(
            ProviderCredential.user_id == user.id
        ).values(is_active=False))
        profile = ProviderCredential(
            user_id=user.id, name=name, provider=provider,
            encrypted_api_key=self.cipher.encrypt(api_key.encode("utf-8")).decode("ascii"),
            is_active=True,
        )
        self.db.add(profile)
        user.llm_provider = None
        user.encrypted_llm_api_key = None
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ProviderError("A saved key with this name already exists") from exc
        self.db.refresh(profile)
        return profile

    def activate(self, user: User, profile_id) -> ProviderCredential:
        if self.db is None:
            raise ProviderError("Provider database context is unavailable")
        profile = self.db.scalar(select(ProviderCredential).where(
            ProviderCredential.id == profile_id, ProviderCredential.user_id == user.id
        ))
        if not profile:
            raise ProviderError("Saved API key not found")
        self.db.execute(update(ProviderCredential).where(
            ProviderCredential.user_id == user.id
        ).values(is_active=False))
        profile.is_active = True
        self.db.commit(); self.db.refresh(profile)
        return profile

    def delete_profile(self, user: User, profile_id) -> None:
        if self.db is None:
            raise ProviderError("Provider database context is unavailable")
        profile = self.db.scalar(select(ProviderCredential).where(
            ProviderCredential.id == profile_id, ProviderCredential.user_id == user.id
        ))
        if not profile:
            raise ProviderError("Saved API key not found")
        self.db.delete(profile); self.db.commit()

    def clear(self, user: User) -> None:
        if self.db is not None:
            self.db.execute(update(ProviderCredential).where(
                ProviderCredential.user_id == user.id
            ).values(is_active=False))
        user.llm_provider = None
        user.encrypted_llm_api_key = None
        if self.db is not None:
            self.db.commit()
            self.db.refresh(user)
