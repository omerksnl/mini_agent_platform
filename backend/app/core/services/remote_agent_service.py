from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from langchain_core.tools import ToolException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.tools.http_tools import HttpToolExecutor
from app.core.services.attachment_service import AttachmentError, AttachmentService
from app.core.security import create_a2a_billing_token
from app.models import A2ACallUsage, Attachment, ProviderCredential, RemoteAgent


class RemoteAgentError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RemoteAgentService:
    MAX_CARD_BYTES = 1_000_000

    def __init__(self, db: Session) -> None:
        self.db = db
        digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(digest))

    def list(self, tenant_id: UUID, user_id: UUID) -> list[RemoteAgent]:
        return list(self.db.scalars(
            select(RemoteAgent).where(
                RemoteAgent.tenant_id == tenant_id,
                RemoteAgent.owner_user_id == user_id,
            ).order_by(RemoteAgent.created_at.desc())
        ).all())

    def get(self, remote_id: UUID, tenant_id: UUID, user_id: UUID) -> RemoteAgent:
        item = self.db.scalar(select(RemoteAgent).where(
            RemoteAgent.id == remote_id,
            RemoteAgent.tenant_id == tenant_id,
            RemoteAgent.owner_user_id == user_id,
        ))
        if not item:
            raise RemoteAgentError("Remote agent not found", 404)
        return item

    @staticmethod
    def _request_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise RemoteAgentError("Invalid Agent Card URL")
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            return urlunparse(("http", "127.0.0.1:8000", parsed.path, "", parsed.query, ""))
        try:
            HttpToolExecutor.validate_public_url(value)
        except ToolException as exc:
            raise RemoteAgentError(str(exc)) from exc
        return value

    def _fetch_card(self, card_url: str) -> dict:
        try:
            response = httpx.get(self._request_url(card_url), timeout=10.0, follow_redirects=False)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            raise RemoteAgentError("Agent Card could not be reached", 502) from exc
        if len(response.content) > self.MAX_CARD_BYTES:
            raise RemoteAgentError("Agent Card response is too large")
        try:
            card = response.json()
        except ValueError as exc:
            raise RemoteAgentError("Agent Card did not return valid JSON") from exc
        if not isinstance(card, dict):
            raise RemoteAgentError("Invalid Agent Card")
        return card

    @staticmethod
    def _interface(card: dict) -> tuple[str, str]:
        interfaces = card.get("supportedInterfaces")
        if not isinstance(interfaces, list):
            raise RemoteAgentError("Agent Card has no supported interfaces")
        interface = next((item for item in interfaces if isinstance(item, dict) and item.get("protocolBinding") == "JSONRPC"), None)
        if not interface or not isinstance(interface.get("url"), str):
            raise RemoteAgentError("Agent does not expose a JSONRPC interface")
        return interface["url"], str(interface.get("protocolVersion", "1.0"))

    def create(
        self,
        tenant_id: UUID,
        user_id: UUID,
        card_url: str,
        api_key: str,
        billing_mode: str = "owner",
        provider_credential_id: UUID | None = None,
    ) -> RemoteAgent:
        if billing_mode not in {"owner", "caller"}:
            raise RemoteAgentError("Invalid A2A billing mode")
        if billing_mode == "caller":
            profile = self.db.scalar(select(ProviderCredential).where(
                ProviderCredential.id == provider_credential_id,
                ProviderCredential.user_id == user_id,
            ))
            if profile is None:
                raise RemoteAgentError("Saved API key not found")
        else:
            provider_credential_id = None
        card = self._fetch_card(card_url)
        endpoint, protocol_version = self._interface(card)
        item = RemoteAgent(
            tenant_id=tenant_id,
            owner_user_id=user_id,
            name=str(card.get("name") or "Remote agent")[:255],
            description=str(card.get("description") or ""),
            agent_card_url=card_url,
            endpoint_url=endpoint,
            encrypted_api_key=self.cipher.encrypt(api_key.encode("utf-8")).decode("ascii"),
            billing_mode=billing_mode,
            provider_credential_id=provider_credential_id,
            protocol_version=protocol_version[:20],
            skills=card.get("skills") if isinstance(card.get("skills"), list) else [],
        )
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise RemoteAgentError("This remote agent is already connected") from exc
        self.db.refresh(item)
        return item

    def delete(self, remote_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        item = self.get(remote_id, tenant_id, user_id)
        self.db.delete(item)
        self.db.commit()

    def _attachments(self, ids: list[UUID], tenant_id: UUID, user_id: UUID) -> list[Attachment]:
        if not ids:
            return []
        unique_ids = list(dict.fromkeys(ids))
        attachments = list(self.db.scalars(select(Attachment).where(
            Attachment.id.in_(unique_ids),
            Attachment.tenant_id == tenant_id,
            Attachment.uploaded_by_id == user_id,
        )).all())
        if len(attachments) != len(unique_ids):
            raise RemoteAgentError("One or more PDF attachments are unavailable", 404)
        return attachments

    def send(
        self,
        remote_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        content: str,
        attachment_ids: list[UUID],
    ) -> tuple[str, str | None, float, str, str, str | None]:
        item = self.get(remote_id, tenant_id, user_id)
        try:
            api_key = self.cipher.decrypt(item.encrypted_api_key.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RemoteAgentError("Stored A2A credential cannot be decrypted", 500) from exc
        parts: list[dict] = []
        if content.strip():
            parts.append({"kind": "text", "text": content.strip()})
        for attachment in self._attachments(attachment_ids, tenant_id, user_id):
            try:
                data = AttachmentService(self.db).path_for(attachment).read_bytes()
            except AttachmentError as exc:
                raise RemoteAgentError(exc.message, exc.status_code) from exc
            parts.append({"kind": "file", "file": {
                "name": attachment.original_name,
                "mimeType": "application/pdf",
                "bytes": base64.b64encode(data).decode("ascii"),
            }})
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "SendMessage",
            "params": {"message": {
                "kind": "message", "role": "user", "messageId": str(uuid4()),
                "parts": parts,
            }},
        }
        headers = {"Authorization": f"Bearer {api_key}", "A2A-Version": item.protocol_version}
        if item.billing_mode == "caller":
            if item.provider_credential_id is None:
                raise RemoteAgentError("Select a provider profile for caller-paid A2A requests")
            try:
                target_agent_id = UUID(urlparse(item.endpoint_url).path.rstrip("/").split("/")[-1])
            except (ValueError, IndexError) as exc:
                raise RemoteAgentError("Remote endpoint cannot accept caller billing") from exc
            headers["X-A2A-Billing-Token"] = create_a2a_billing_token(
                user_id=str(user_id),
                credential_id=str(item.provider_credential_id),
                agent_id=str(target_agent_id),
            )
        try:
            response = httpx.post(
                self._request_url(item.endpoint_url),
                headers=headers,
                json=payload,
                timeout=300.0,
                follow_redirects=False,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RemoteAgentError("Remote agent request failed", 502) from exc
        if not isinstance(body, dict) or not isinstance(body.get("result"), dict):
            message = body.get("error", {}).get("message") if isinstance(body, dict) else None
            raise RemoteAgentError(str(message or "Remote agent returned an invalid response"), 502)
        result = body["result"]
        parts = result.get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)).strip()
        if not text:
            raise RemoteAgentError("Remote agent returned no text", 502)
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        raw_cost = metadata.get("apiCostUsd", 0.0)
        try:
            api_cost = max(0.0, float(raw_cost))
        except (TypeError, ValueError):
            api_cost = 0.0
        billing_mode = str(metadata.get("billingMode") or "owner")
        billed_to = str(metadata.get("billedTo") or "agent_owner")
        provider = metadata.get("provider") if metadata.get("provider") in {"openrouter", "openai"} else None
        if item.billing_mode == "caller" and (billing_mode != "caller" or billed_to != "caller"):
            raise RemoteAgentError(
                "The remote platform does not support secure caller-paid A2A billing", 400
            )
        self.db.add(A2ACallUsage(
            tenant_id=tenant_id,
            user_id=user_id,
            remote_agent_id=item.id,
            billing_mode=billing_mode,
            billed_to=billed_to,
            provider=provider,
            api_cost_usd=api_cost,
        ))
        self.db.commit()
        return (
            text,
            result.get("contextId") if isinstance(result.get("contextId"), str) else None,
            api_cost,
            billing_mode,
            billed_to,
            provider,
        )
