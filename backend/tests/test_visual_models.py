from fastapi.testclient import TestClient


def register(client: TestClient, email: str, tenant_name: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "test-password",
        "full_name": "Vision Tester",
        "tenant_name": tenant_name,
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def payload(name: str = "Waste Classifier") -> dict:
    return {
        "name": name,
        "description": "Classifies recyclable waste images.",
        "task_type": "image_classification",
        "architecture": "mobilenet_v2",
        "class_names": ["paper", "plastic", "glass"],
        "image_width": 224,
        "image_height": 224,
        "channels": 3,
        "use_pretrained_weights": True,
    }


def test_visual_model_crud_and_validation(client: TestClient) -> None:
    token = register(client, "vision@example.com", "Vision Tenant")
    auth = headers(token)

    created = client.post("/api/visual-models", headers=auth, json=payload())
    assert created.status_code == 201
    item = created.json()
    assert item["status"] == "draft"
    assert item["class_names"] == ["paper", "plastic", "glass"]

    listed = client.get("/api/visual-models", headers=auth)
    assert listed.status_code == 200
    assert [model["id"] for model in listed.json()] == [item["id"]]

    updated_payload = payload("Waste Classifier V2")
    updated_payload.update({
        "architecture": "resnet50",
        "image_width": 256,
        "image_height": 256,
    })
    updated = client.put(
        f"/api/visual-models/{item['id']}", headers=auth, json=updated_payload
    )
    assert updated.status_code == 200
    assert updated.json()["architecture"] == "resnet50"
    assert updated.json()["image_width"] == 256

    duplicate_classes = payload("Invalid classes")
    duplicate_classes["class_names"] = ["cat", "CAT"]
    assert client.post(
        "/api/visual-models", headers=auth, json=duplicate_classes
    ).status_code == 422

    invalid_simple_cnn = payload("Invalid CNN")
    invalid_simple_cnn["architecture"] = "simple_cnn"
    assert client.post(
        "/api/visual-models", headers=auth, json=invalid_simple_cnn
    ).status_code == 422

    deleted = client.delete(f"/api/visual-models/{item['id']}", headers=auth)
    assert deleted.status_code == 204
    assert client.get("/api/visual-models", headers=auth).json() == []


def test_visual_models_are_tenant_isolated(client: TestClient) -> None:
    first = register(client, "vision-a@example.com", "Vision A")
    second = register(client, "vision-b@example.com", "Vision B")
    created = client.post(
        "/api/visual-models", headers=headers(first), json=payload()
    ).json()

    assert client.get("/api/visual-models", headers=headers(second)).json() == []
    assert client.put(
        f"/api/visual-models/{created['id']}",
        headers=headers(second),
        json=payload("Stolen model"),
    ).status_code == 404
    assert client.delete(
        f"/api/visual-models/{created['id']}", headers=headers(second)
    ).status_code == 404
