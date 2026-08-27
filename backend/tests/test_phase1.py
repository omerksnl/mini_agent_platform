from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_access_token, hash_password
from app.models import User


def register(
    client: TestClient,
    *,
    email: str = "user@example.com",
    tenant_name: str = "Tenant A",
) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "test-password",
            "full_name": "Test User",
            "tenant_name": tenant_name,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_agent(client: TestClient, token: str, name: str = "Test Agent") -> dict:
    response = client.post(
        "/api/agents",
        headers=auth_headers(token),
        json={
            "name": name,
            "system_prompt": "You are a test assistant.",
            "model": "anthropic/claude-haiku-4.5",
            "temperature": 0.7,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "redis": "disabled",
    }


def test_register_login_and_me(client: TestClient) -> None:
    token = register(client, email="USER@example.com")

    me_response = client.get("/api/auth/me", headers=auth_headers(token))
    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "user@example.com"
    assert me_response.json()["tenant_name"] == "Tenant A"

    login_response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["token_type"] == "bearer"
    assert login_response.json()["access_token"]


def test_authentication_errors(client: TestClient) -> None:
    register(client)

    duplicate = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "test-password",
            "full_name": "Another User",
            "tenant_name": "Another Tenant",
        },
    )
    assert duplicate.status_code == 409

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401

    short_password = client.post(
        "/api/auth/register",
        json={
            "email": "short@example.com",
            "password": "short",
            "full_name": "Short Password",
            "tenant_name": "Tenant",
        },
    )
    assert short_password.status_code == 422

    assert client.get("/api/auth/me").status_code == 401
    assert client.get(
        "/api/auth/me",
        headers=auth_headers("not-a-valid-token"),
    ).status_code == 401


def test_profile_identity_update(client: TestClient) -> None:
    token = register(client)

    response = client.patch(
        "/api/auth/profile",
        headers=auth_headers(token),
        json={
            "full_name": "Updated User",
            "email": "updated@example.com",
            "tenant_name": "Updated Tenant",
            "current_password": "test-password",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["full_name"] == "Updated User"
    assert response.json()["user"]["email"] == "updated@example.com"
    assert response.json()["tenant_name"] == "Updated Tenant"

    assert client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "updated@example.com", "password": "test-password"},
    ).status_code == 200


def test_profile_protected_changes_require_current_password(client: TestClient) -> None:
    token = register(client)
    headers = auth_headers(token)

    missing_password = client.patch(
        "/api/auth/profile",
        headers=headers,
        json={"email": "protected@example.com"},
    )
    assert missing_password.status_code == 401

    wrong_password = client.patch(
        "/api/auth/profile",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "new-password"},
    )
    assert wrong_password.status_code == 401

    changed = client.patch(
        "/api/auth/profile",
        headers=headers,
        json={"current_password": "test-password", "new_password": "new-password"},
    )
    assert changed.status_code == 200

    assert client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "new-password"},
    ).status_code == 200


def test_agent_crud_and_validation(client: TestClient) -> None:
    token = register(client)
    agent = create_agent(client, token)
    agent_id = agent["id"]

    listed = client.get("/api/agents", headers=auth_headers(token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [agent_id]

    fetched = client.get(f"/api/agents/{agent_id}", headers=auth_headers(token))
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Test Agent"
    assert fetched.json()["collection_search_limit"] == 5

    updated = client.patch(
        f"/api/agents/{agent_id}",
        headers=auth_headers(token),
        json={
            "name": "Updated Agent",
            "temperature": 1.2,
            "collection_search_limit": 3,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Agent"
    assert updated.json()["temperature"] == 1.2
    assert updated.json()["collection_search_limit"] == 3

    invalid_collection_limit = client.patch(
        f"/api/agents/{agent_id}",
        headers=auth_headers(token),
        json={"collection_search_limit": 0},
    )
    assert invalid_collection_limit.status_code == 422

    null_update = client.patch(
        f"/api/agents/{agent_id}",
        headers=auth_headers(token),
        json={"name": None},
    )
    assert null_update.status_code == 422

    deleted = client.delete(f"/api/agents/{agent_id}", headers=auth_headers(token))
    assert deleted.status_code == 204
    assert client.get(
        f"/api/agents/{agent_id}",
        headers=auth_headers(token),
    ).status_code == 404


def test_tenant_isolation(client: TestClient) -> None:
    tenant_a_token = register(
        client,
        email="tenant-a@example.com",
        tenant_name="Tenant A",
    )
    tenant_a_agent = create_agent(client, tenant_a_token, "Tenant A Agent")

    tenant_b_token = register(
        client,
        email="tenant-b@example.com",
        tenant_name="Tenant B",
    )
    tenant_b_headers = auth_headers(tenant_b_token)
    agent_id = tenant_a_agent["id"]

    listed = client.get("/api/agents", headers=tenant_b_headers)
    assert listed.status_code == 200
    assert listed.json() == []

    assert client.get(f"/api/agents/{agent_id}", headers=tenant_b_headers).status_code == 404
    assert client.patch(
        f"/api/agents/{agent_id}",
        headers=tenant_b_headers,
        json={"name": "Stolen Agent"},
    ).status_code == 404
    assert client.delete(
        f"/api/agents/{agent_id}",
        headers=tenant_b_headers,
    ).status_code == 404

    owner_view = client.get(
        f"/api/agents/{agent_id}",
        headers=auth_headers(tenant_a_token),
    )
    assert owner_view.status_code == 200
    assert owner_view.json()["name"] == "Tenant A Agent"


def test_users_in_same_tenant_share_agents(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    first_user_token = register(client, email="owner@example.com", tenant_name="Shared Tenant")
    shared_agent = create_agent(client, first_user_token, "Shared Agent")

    with db_session_factory() as db:
        first_user = db.scalar(select(User).where(User.email == "owner@example.com"))
        assert first_user is not None

        second_user = User(
            id=uuid4(),
            tenant_id=first_user.tenant_id,
            email="colleague@example.com",
            hashed_password=hash_password("test-password"),
            full_name="Tenant Colleague",
        )
        db.add(second_user)
        db.commit()

        second_user_token = create_access_token(
            subject=str(second_user.id),
            tenant_id=str(second_user.tenant_id),
        )

    response = client.get("/api/agents", headers=auth_headers(second_user_token))

    assert response.status_code == 200
    assert [agent["id"] for agent in response.json()] == [shared_agent["id"]]
