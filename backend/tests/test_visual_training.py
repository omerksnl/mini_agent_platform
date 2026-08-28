from io import BytesIO
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
import numpy as np

from app.api.routes import visual_models as routes
from app.core.services import visual_training_service as training_module
from app.core.services.visual_training_service import (
    _normalized_image_array,
    _evaluation_payload,
    _trim_visual_versions,
    available_training_devices,
    select_training_device,
)
from app.models import VisualModel, VisualTrainingRun


class _FakeExperimental:
    def __init__(self) -> None:
        self.growth_device = None

    def set_memory_growth(self, device, enabled: bool) -> None:
        if enabled:
            self.growth_device = device

    def get_device_details(self, device) -> dict[str, str]:
        return {"device_name": "Test GPU"}


def test_evaluation_payload_contains_dashboard_metrics() -> None:
    payload = _evaluation_payload(
        ["cat", "dog"],
        np.asarray([0, 0, 1, 1]),
        np.asarray([[.9, .1], [.4, .6], [.2, .8], [.1, .9]]),
    )

    assert payload["sample_count"] == 4
    assert payload["confusion_matrix"] == [[1, 1], [0, 2]]
    assert payload["summary"]["accuracy"] == .75
    assert payload["classes"][1]["recall"] == 1.0
    assert sum(payload["confidence_histogram"]["counts"]) == 4


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


def test_visual_versions_keep_order_and_can_activate(
    client: TestClient, db_session_factory, tmp_path, monkeypatch
) -> None:
    auth = _register(client)
    model_payload = client.post("/api/visual-models", headers=auth, json={
        "name": "Versioned classifier",
        "description": "version test",
        "task_type": "image_classification",
        "architecture": "simple_cnn",
        "class_names": ["cat", "dog"],
        "image_width": 64,
        "image_height": 64,
        "channels": 3,
        "use_pretrained_weights": False,
    }).json()
    monkeypatch.setattr(
        training_module, "get_settings", lambda: SimpleNamespace(upload_directory=str(tmp_path))
    )
    with db_session_factory() as db:
        model = db.get(VisualModel, UUID(model_payload["id"]))
        assert model is not None
        for number in range(1, 5):
            relative = f"versions/v{number}.keras"
            artifact = tmp_path / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"model")
            db.add(VisualTrainingRun(
                id=uuid4(),
                tenant_id=model.tenant_id,
                visual_model_id=model.id,
                status="completed",
                progress=100,
                epochs=number,
                batch_size=8,
                validation_split=0.2,
                learning_rate=0.001,
                current_epoch=number,
                metrics={"accuracy": number / 10},
                artifact_path=relative,
                version_number=number,
                is_active=number == 4,
                completed_at=datetime.now(timezone.utc),
            ))
        db.commit()
        _trim_visual_versions(db, model.id)
        assert db.query(VisualTrainingRun).filter_by(visual_model_id=model.id).count() == 3
        assert not (tmp_path / "versions/v1.keras").exists()

    versions = client.get(
        f"/api/visual-models/{model_payload['id']}/versions", headers=auth
    )
    assert versions.status_code == 200
    assert [item["version_number"] for item in versions.json()] == [4, 3, 2]
    target = versions.json()[-1]

    activated = client.post(
        f"/api/visual-models/{model_payload['id']}/versions/{target['id']}/activate",
        headers=auth,
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    refreshed = client.get(
        f"/api/visual-models/{model_payload['id']}/versions", headers=auth
    ).json()
    assert [item["version_number"] for item in refreshed if item["is_active"]] == [2]
