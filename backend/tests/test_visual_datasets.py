from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_dataset_storage(tmp_path):
    settings = get_settings()
    previous = settings.upload_directory
    settings.upload_directory = str(tmp_path)
    try:
        yield
    finally:
        settings.upload_directory = previous


def register(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "strong-password",
        "full_name": "Visual User",
        "tenant_name": email.split("@")[0],
    })
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_model(client: TestClient, token: str) -> dict:
    response = client.post("/api/visual-models", headers=headers(token), json={
        "name": "Animal classifier",
        "description": "Cats and dogs",
        "task_type": "image_classification",
        "architecture": "mobilenet_v2",
        "class_names": ["cat", "dog"],
        "image_width": 224,
        "image_height": 224,
        "channels": 3,
        "use_pretrained_weights": True,
    })
    assert response.status_code == 201
    return response.json()


def png(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 10), color).save(output, format="PNG")
    return output.getvalue()


def dataset_zip() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("cat/cat-one.png", png((255, 0, 0)))
        archive.writestr("dog/dog-one.png", png((0, 0, 255)))
    return output.getvalue()


def test_upload_images_and_zip_dataset(client: TestClient) -> None:
    token = register(client, "visual-dataset@example.com")
    model = create_model(client, token)

    first = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(token),
        data={"class_name": "cat"},
        files=[("files", ("cat.png", png((0, 255, 0)), "image/png"))],
    )
    assert first.status_code == 200
    assert first.json()["added_images"] == 1
    assert first.json()["summary"]["ready_for_training"] is False

    duplicate = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(token),
        data={"class_name": "cat"},
        files=[("files", ("same.png", png((0, 255, 0)), "image/png"))],
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["skipped_duplicates"] == 1

    zipped = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(token),
        files=[("files", ("dataset.zip", dataset_zip(), "application/zip"))],
    )
    assert zipped.status_code == 200
    summary = zipped.json()["summary"]
    assert summary["total_images"] == 3
    assert summary["ready_for_training"] is True
    assert {item["class_name"]: item["image_count"] for item in summary["classes"]} == {
        "cat": 2,
        "dog": 1,
    }
    refreshed = client.get("/api/visual-models", headers=headers(token)).json()[0]
    assert refreshed["status"] == "dataset_ready"

    cleared = client.delete(
        f"/api/visual-models/{model['id']}/dataset", headers=headers(token)
    )
    assert cleared.status_code == 204
    empty = client.get(
        f"/api/visual-models/{model['id']}/dataset", headers=headers(token)
    ).json()
    assert empty["total_images"] == 0
    assert empty["ready_for_training"] is False


def test_dataset_validation_and_tenant_isolation(client: TestClient) -> None:
    owner = register(client, "visual-owner@example.com")
    outsider = register(client, "visual-outsider@example.com")
    model = create_model(client, owner)

    unknown_class = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(owner),
        data={"class_name": "bird"},
        files=[("files", ("bird.png", png((1, 2, 3)), "image/png"))],
    )
    assert unknown_class.status_code == 400

    corrupt = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(owner),
        data={"class_name": "cat"},
        files=[("files", ("broken.png", b"not-an-image", "image/png"))],
    )
    assert corrupt.status_code == 400
    assert "corrupted" in corrupt.json()["detail"].lower()

    hidden = client.get(
        f"/api/visual-models/{model['id']}/dataset", headers=headers(outsider)
    )
    assert hidden.status_code == 404
    forbidden_upload = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(outsider),
        data={"class_name": "cat"},
        files=[("files", ("cat.png", png((4, 5, 6)), "image/png"))],
    )
    assert forbidden_upload.status_code == 404


def test_cannot_remove_populated_class(client: TestClient) -> None:
    token = register(client, "visual-classes@example.com")
    model = create_model(client, token)
    uploaded = client.post(
        f"/api/visual-models/{model['id']}/dataset",
        headers=headers(token),
        data={"class_name": "cat"},
        files=[("files", ("cat.png", png((9, 9, 9)), "image/png"))],
    )
    assert uploaded.status_code == 200
    update = client.put(f"/api/visual-models/{model['id']}", headers=headers(token), json={
        "name": "Animal classifier",
        "description": "Dogs and birds",
        "task_type": "image_classification",
        "architecture": "mobilenet_v2",
        "class_names": ["dog", "bird"],
        "image_width": 224,
        "image_height": 224,
        "channels": 3,
        "use_pretrained_weights": True,
    })
    assert update.status_code == 400
    assert "clear the dataset" in update.json()["detail"].lower()
