from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import visual_models as routes
from app.core.services.visual_training_service import (
    _normalized_image_array,
    available_training_devices,
    select_training_device,
)


class _FakeExperimental:
    def __init__(self) -> None:
        self.growth_device = None

    def set_memory_growth(self, device, enabled: bool) -> None:
        if enabled:
            self.growth_device = device

    def get_device_details(self, device) -> dict[str, str]:
        return {"device_name": "Test GPU"}


class _FakeConfig:
    def __init__(self, gpus: list[object]) -> None:
        self.gpus = gpus
        self.experimental = _FakeExperimental()

    def list_physical_devices(self, kind: str) -> list[object]:
        return self.gpus if kind == "GPU" else []


class _FakeTensorFlow:
    def __init__(self, gpus: list[object]) -> None:
        self.config = _FakeConfig(gpus)


def test_training_device_auto_prefers_gpu_and_enables_memory_growth(monkeypatch) -> None:
    gpu = type("Device", (), {"name": "physical_device:GPU:0"})()
    tf = _FakeTensorFlow([gpu])
    monkeypatch.setitem(__import__("sys").modules, "tensorflow", tf)

    path, used, name = select_training_device(tf, "auto")

    assert (path, used, name) == ("/GPU:0", "gpu", "Test GPU")
    assert tf.config.experimental.growth_device is gpu


def test_training_device_gpu_request_fails_when_unavailable() -> None:
    tf = _FakeTensorFlow([])

    devices = available_training_devices(tf)

    assert devices[1]["available"] is False
    try:
        select_training_device(tf, "gpu")
    except RuntimeError as exc:
        assert "cannot see a compatible GPU" in str(exc)
    else:
        raise AssertionError("GPU selection should fail without a visible GPU")


def _png(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color).save(output, format="PNG")
    return output.getvalue()


def test_prediction_image_normalization_accepts_cmyk_jpeg() -> None:
    output = BytesIO()
    Image.new("CMYK", (12, 8), (0, 128, 255, 0)).save(output, format="JPEG")

    normalized = _normalized_image_array(output.getvalue(), channels=3)

    assert normalized.shape == (8, 12, 3)
    assert normalized.dtype.name == "uint8"


def _register(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/register", json={
        "email": "visual-training@example.com",
        "password": "strong-password",
        "full_name": "Training User",
        "tenant_name": "Training Tenant",
    })
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_training_run_is_queued_and_tenant_scoped(client: TestClient, monkeypatch) -> None:
    auth = _register(client)
    model = client.post("/api/visual-models", headers=auth, json={
        "name": "Cats and dogs",
        "description": "training test",
        "task_type": "image_classification",
        "architecture": "simple_cnn",
        "class_names": ["cat", "dog"],
        "image_width": 64,
        "image_height": 64,
        "channels": 3,
        "use_pretrained_weights": False,
    }).json()
    for class_name, colors in {
        "cat": [(255, 0, 0), (200, 0, 0)],
        "dog": [(0, 0, 255), (0, 0, 200)],
    }.items():
        response = client.post(
            f"/api/visual-models/{model['id']}/dataset",
            headers=auth,
            data={"class_name": class_name},
            files=[
                ("files", (f"{class_name}-{index}.png", _png(color), "image/png"))
                for index, color in enumerate(colors)
            ],
        )
        assert response.status_code == 200

    monkeypatch.setattr(routes.visual_training_executor, "submit", lambda *args, **kwargs: None)
    started = client.post(
        f"/api/visual-models/{model['id']}/training-runs",
        headers=auth,
        json={"epochs": 3, "batch_size": 2, "validation_split": 0.25, "learning_rate": 0.001},
    )
    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    assert started.json()["progress"] == 0

    latest = client.get(
        f"/api/visual-models/{model['id']}/training-runs/latest", headers=auth
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == started.json()["id"]

    duplicate = client.post(
        f"/api/visual-models/{model['id']}/training-runs",
        headers=auth,
        json={"epochs": 3, "batch_size": 2, "validation_split": 0.25, "learning_rate": 0.001},
    )
    assert duplicate.status_code == 409


def test_prediction_requires_a_trained_model_and_supported_image(client: TestClient) -> None:
    auth = _register(client)
    model = client.post("/api/visual-models", headers=auth, json={
        "name": "Prediction guard",
        "description": "prediction test",
        "task_type": "image_classification",
        "architecture": "simple_cnn",
        "class_names": ["cat", "dog"],
        "image_width": 64,
        "image_height": 64,
        "channels": 3,
        "use_pretrained_weights": False,
    }).json()

    unsupported = client.post(
        f"/api/visual-models/{model['id']}/predict",
        headers=auth,
        files={"image": ("sample.gif", b"not-an-image", "image/gif")},
    )
    assert unsupported.status_code == 415

    untrained = client.post(
        f"/api/visual-models/{model['id']}/predict",
        headers=auth,
        files={"image": ("sample.png", _png((120, 50, 20)), "image/png")},
    )
    assert untrained.status_code == 409
    assert "Train this visual model" in untrained.json()["detail"]
