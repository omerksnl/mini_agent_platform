from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Agent, Conversation, Message, User
from tests.test_phase1 import auth_headers, register


def test_assistant_feedback_is_tenant_scoped_and_sent_to_conversation_session(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    token = register(client, email="feedback@example.com", tenant_name="Feedback")
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == "feedback@example.com"))
        assert user is not None
        agent = Agent(
            tenant_id=user.tenant_id,
            name="feedback_agent",
            system_prompt="Answer briefly.",
            model="anthropic/claude-haiku-4.5",
        )
        db.add(agent); db.flush()
        conversation = Conversation(tenant_id=user.tenant_id, agent_id=agent.id, title="Feedback")
        db.add(conversation); db.flush()
        message = Message(
            tenant_id=user.tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content="An answer",
        )
        db.add(message); db.commit()
        message_id, conversation_id = message.id, conversation.id

    captured: dict = {}
    monkeypatch.setattr(
        "app.core.services.feedback_service.submit_human_feedback",
        lambda settings, **kwargs: captured.update(kwargs),
    )
    response = client.post(
        "/api/feedback",
        headers=auth_headers(token),
        json={"target_type": "message", "target_id": str(message_id), "score": 4, "comment": "Useful"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "submitted"}
    assert captured["session_id"] == str(conversation_id)
    assert captured["score"] == 4
    assert captured["comment"] == "Useful"

    other_token = register(client, email="feedback-other@example.com", tenant_name="Other")
    denied = client.post(
        "/api/feedback",
        headers=auth_headers(other_token),
        json={"target_type": "message", "target_id": str(message_id), "score": 1, "comment": ""},
    )
    assert denied.status_code == 404


def test_feedback_validation_rejects_out_of_range_score(client: TestClient) -> None:
    token = register(client, email="feedback-score@example.com")
    response = client.post(
        "/api/feedback",
        headers=auth_headers(token),
        json={"target_type": "message", "target_id": str(uuid4()), "score": 6, "comment": ""},
    )
    assert response.status_code == 422
