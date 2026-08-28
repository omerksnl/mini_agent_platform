from __future__ import annotations

import logging
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import VisualDatasetImage, VisualModel, VisualTrainingRun
from app.schemas.visual_model import VisualPredictionResponse, VisualTrainingRunCreate

logger = logging.getLogger(__name__)


def available_training_devices(tf) -> list[dict[str, object]]:
    """Return stable UI metadata without claiming that an unavailable GPU can run."""
    gpus = tf.config.list_physical_devices("GPU")
    gpu_name = _device_name(gpus[0]) if gpus else "No compatible GPU detected"
    return [
        {
            "value": "cpu",
            "label": "CPU",
            "available": True,
            "description": "Always available; slower but uses system memory.",
        },
        {
            "value": "gpu",
            "label": gpu_name if gpus else "GPU",
            "available": bool(gpus),
            "description": (
                "CUDA acceleration is available; TensorFlow memory growth is enabled."
                if gpus
                else "Start the GPU Docker configuration on an NVIDIA-compatible host."
            ),
        },
    ]


def select_training_device(tf, requested: str) -> tuple[str, str, str]:
    """Resolve auto/cpu/gpu to a TensorFlow device and avoid preallocating all VRAM."""
    gpus = tf.config.list_physical_devices("GPU")
    if requested == "gpu" and not gpus:
        raise RuntimeError(
            "GPU training was requested, but TensorFlow cannot see a compatible GPU. "
            "Use Auto/CPU or start Docker with docker-compose.gpu.yml."
        )
    if requested == "cpu" or not gpus:
        return "/CPU:0", "cpu", "CPU"

    gpu = gpus[0]
    try:
        tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError:
        # TensorFlow raises after device initialization; the already configured GPU remains usable.
        logger.debug("GPU memory growth could not be changed after initialization", exc_info=True)
    return "/GPU:0", "gpu", _device_name(gpu)


def _device_name(device) -> str:
    details = getattr(device, "name", "GPU")
    try:
        import tensorflow as tf

        details = tf.config.experimental.get_device_details(device).get(
            "device_name", details
        )
    except (ImportError, RuntimeError, ValueError):
        pass
    return str(details).split("physical_device:")[-1].strip() or "GPU"


class VisualTrainingError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class VisualTrainingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def start(self, model_id: UUID, tenant_id: UUID, payload: VisualTrainingRunCreate) -> VisualTrainingRun:
        model = self._model(model_id, tenant_id)
        active = self.db.scalar(select(VisualTrainingRun.id).where(
            VisualTrainingRun.visual_model_id == model.id,
            VisualTrainingRun.status.in_(["queued", "running"]),
        ).limit(1))
        if active:
            raise VisualTrainingError("This visual model is already training", 409)
        class_counts = dict(self.db.execute(
            select(VisualDatasetImage.class_name, func.count(VisualDatasetImage.id))
            .where(VisualDatasetImage.visual_model_id == model.id)
            .group_by(VisualDatasetImage.class_name)
        ).all())
        missing = [name for name in model.class_names if class_counts.get(name, 0) < 2]
        if missing:
            raise VisualTrainingError(
                "Each class needs at least two images before training: " + ", ".join(missing)
            )
        run = VisualTrainingRun(
            tenant_id=tenant_id,
            visual_model_id=model.id,
            **payload.model_dump(),
        )
        model.status = "training"
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def latest(self, model_id: UUID, tenant_id: UUID) -> VisualTrainingRun | None:
        self._model(model_id, tenant_id)
        return self.db.scalar(
            select(VisualTrainingRun)
            .where(
                VisualTrainingRun.visual_model_id == model_id,
                VisualTrainingRun.tenant_id == tenant_id,
            )
            .order_by(VisualTrainingRun.created_at.desc())
            .limit(1)
        )

    def get(self, run_id: UUID, tenant_id: UUID) -> VisualTrainingRun:
        run = self.db.scalar(select(VisualTrainingRun).where(
            VisualTrainingRun.id == run_id, VisualTrainingRun.tenant_id == tenant_id
        ))
        if not run:
            raise VisualTrainingError("Training run not found", 404)
        return run

    def versions(self, model_id: UUID, tenant_id: UUID) -> list[VisualTrainingRun]:
        self._model(model_id, tenant_id)
        _trim_visual_versions(self.db, model_id)
        return list(self.db.scalars(
            select(VisualTrainingRun)
            .where(
                VisualTrainingRun.visual_model_id == model_id,
                VisualTrainingRun.tenant_id == tenant_id,
                VisualTrainingRun.status == "completed",
                VisualTrainingRun.artifact_path.is_not(None),
                VisualTrainingRun.version_number.is_not(None),
            )
            .order_by(VisualTrainingRun.version_number.desc())
            .limit(3)
        ))

    def activate_version(
        self, model_id: UUID, run_id: UUID, tenant_id: UUID
    ) -> VisualTrainingRun:
        self._model(model_id, tenant_id)
        run = self.db.scalar(select(VisualTrainingRun).where(
            VisualTrainingRun.id == run_id,
            VisualTrainingRun.visual_model_id == model_id,
            VisualTrainingRun.tenant_id == tenant_id,
            VisualTrainingRun.status == "completed",
            VisualTrainingRun.artifact_path.is_not(None),
        ))
        if not run:
            raise VisualTrainingError("Visual model version not found", 404)
        artifact = Path(get_settings().upload_directory).resolve() / str(run.artifact_path)
        if not artifact.is_file():
            raise VisualTrainingError("The selected model artifact is missing", 409)
        self.db.execute(
            update(VisualTrainingRun)
            .where(
                VisualTrainingRun.visual_model_id == model_id,
                VisualTrainingRun.tenant_id == tenant_id,
            )
            .values(is_active=False)
        )
        run.is_active = True
        self.db.commit()
        self.db.refresh(run)
        return run

    def evaluate_version(
        self, model_id: UUID, run_id: UUID, tenant_id: UUID
    ) -> VisualTrainingRun:
        model_config = self._model(model_id, tenant_id)
        run = self.db.scalar(select(VisualTrainingRun).where(
            VisualTrainingRun.id == run_id,
            VisualTrainingRun.visual_model_id == model_id,
            VisualTrainingRun.tenant_id == tenant_id,
            VisualTrainingRun.status == "completed",
            VisualTrainingRun.artifact_path.is_not(None),
        ))
        if not run or not run.artifact_path:
            raise VisualTrainingError("Visual model version not found", 404)
        artifact = Path(get_settings().upload_directory).resolve() / run.artifact_path
        if not artifact.is_file():
            raise VisualTrainingError("The selected model artifact is missing", 409)
        try:
            import tensorflow as tf

            val_ds = _validation_dataset(tf, model_config, run, tenant_id)
            keras_model = tf.keras.models.load_model(artifact)
            run.evaluation = _evaluate_model(
                keras_model, val_ds, list(model_config.class_names)
            )
            self.db.commit()
            self.db.refresh(run)
            return run
        except VisualTrainingError:
            raise
        except Exception as exc:
            logger.exception("Visual version evaluation failed for run %s", run_id)
            raise VisualTrainingError("This model version could not be evaluated") from exc

    def predict(self, model_id: UUID, tenant_id: UUID, image_bytes: bytes) -> VisualPredictionResponse:
        model_config = self._model(model_id, tenant_id)
        run = self.db.scalar(
            select(VisualTrainingRun)
            .where(
                VisualTrainingRun.visual_model_id == model_id,
                VisualTrainingRun.tenant_id == tenant_id,
                VisualTrainingRun.status == "completed",
                VisualTrainingRun.artifact_path.is_not(None),
                VisualTrainingRun.is_active.is_(True),
            )
            .limit(1)
        )
        if not run:
            run = self.db.scalar(
                select(VisualTrainingRun)
                .where(
                    VisualTrainingRun.visual_model_id == model_id,
                    VisualTrainingRun.tenant_id == tenant_id,
                    VisualTrainingRun.status == "completed",
                    VisualTrainingRun.artifact_path.is_not(None),
                )
                .order_by(VisualTrainingRun.completed_at.desc())
                .limit(1)
            )
        if not run or not run.artifact_path:
            raise VisualTrainingError("Train this visual model before running a prediction", 409)
        if not image_bytes:
            raise VisualTrainingError("Prediction image is empty")

        artifact = Path(get_settings().upload_directory).resolve() / run.artifact_path
        if not artifact.is_file():
            raise VisualTrainingError("The trained model artifact is missing", 409)

        try:
            import tensorflow as tf

            image = tf.convert_to_tensor(_normalized_image_array(image_bytes, model_config.channels))
            image = tf.image.resize(image, (model_config.image_height, model_config.image_width))
            image = tf.expand_dims(tf.cast(image, tf.float32), axis=0)
            keras_model = tf.keras.models.load_model(artifact)
            probabilities = keras_model.predict(image, verbose=0)[0].tolist()
        except Exception as exc:
            logger.exception("Visual prediction failed for model %s", model_id)
            raise VisualTrainingError("The image could not be processed by this model") from exc

        scores = sorted(
            (
                {"class_name": class_name, "probability": round(float(probability), 6)}
                for class_name, probability in zip(model_config.class_names, probabilities, strict=True)
            ),
            key=lambda item: item["probability"],
            reverse=True,
        )
        return VisualPredictionResponse(
            predicted_class=scores[0]["class_name"],
            confidence=scores[0]["probability"],
            scores=scores,
            training_run_id=run.id,
        )

    def _model(self, model_id: UUID, tenant_id: UUID) -> VisualModel:
        model = self.db.scalar(select(VisualModel).where(
            VisualModel.id == model_id, VisualModel.tenant_id == tenant_id
        ))
        if not model:
            raise VisualTrainingError("Visual model not found", 404)
        return model


def _normalized_image_array(image_bytes: bytes, channels: int) -> np.ndarray:
    """Decode browser uploads consistently, including CMYK JPEGs and transparent images."""
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGB" if channels == 3 else "L")
            array = np.asarray(image, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise VisualTrainingError("The uploaded file is not a supported image") from exc
    if channels == 1:
        array = np.expand_dims(array, axis=-1)
    return array


def execute_visual_training(run_id: UUID, tenant_id: UUID) -> None:
    """Train one model in a worker thread; status remains queryable through the API."""
    db = SessionLocal()
    try:
        run = db.scalar(select(VisualTrainingRun).where(
            VisualTrainingRun.id == run_id, VisualTrainingRun.tenant_id == tenant_id
        ))
        if not run:
            return
        model_config = db.scalar(select(VisualModel).where(VisualModel.id == run.visual_model_id))
        if not model_config:
            raise RuntimeError("Visual model no longer exists")
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        import tensorflow as tf

        device_path, used_device, device_name = select_training_device(
            tf, run.requested_device
        )
        run.used_device = used_device
        run.device_name = device_name
        db.commit()

        dataset_root = (
            Path(get_settings().upload_directory).resolve()
            / "visual-datasets" / str(tenant_id) / str(model_config.id)
        )
        color_mode = "rgb" if model_config.channels == 3 else "grayscale"
        common = dict(
            directory=str(dataset_root),
            labels="inferred",
            label_mode="int",
            class_names=list(model_config.class_names),
            validation_split=run.validation_split,
            seed=42,
            image_size=(model_config.image_height, model_config.image_width),
            batch_size=run.batch_size,
            color_mode=color_mode,
        )
        with tf.device(device_path):
            train_ds = tf.keras.utils.image_dataset_from_directory(subset="training", **common)
            val_ds = tf.keras.utils.image_dataset_from_directory(subset="validation", **common)
            train_ds = train_ds.prefetch(tf.data.AUTOTUNE)
            val_ds = val_ds.prefetch(tf.data.AUTOTUNE)
            keras_model = _build_model(
                tf, model_config, len(model_config.class_names), run.learning_rate
            )

        class ProgressCallback(tf.keras.callbacks.Callback):
            def on_epoch_end(self, epoch, logs=None):
                callback_db = SessionLocal()
                try:
                    current = callback_db.get(VisualTrainingRun, run_id)
                    if current:
                        current.current_epoch = epoch + 1
                        current.progress = round(((epoch + 1) / current.epochs) * 100)
                        current.metrics = {
                            key: round(float(value), 6)
                            for key, value in (logs or {}).items()
                            if value is not None
                        }
                        history = dict(current.training_history or {})
                        for key, value in (logs or {}).items():
                            if value is None:
                                continue
                            history.setdefault(key, []).append(round(float(value), 6))
                        current.training_history = history
                        callback_db.commit()
                finally:
                    callback_db.close()

        with tf.device(device_path):
            fit_history = keras_model.fit(
                train_ds,
                validation_data=val_ds,
                epochs=run.epochs,
                callbacks=[ProgressCallback()],
                verbose=0,
            )
            evaluation = _evaluate_model(
                keras_model, val_ds, list(model_config.class_names)
            )
        artifact_directory = (
            Path(get_settings().upload_directory).resolve()
            / "visual-model-artifacts" / str(tenant_id) / str(model_config.id)
        )
        artifact_directory.mkdir(parents=True, exist_ok=True)
        artifact = artifact_directory / f"{run.id}.keras"
        keras_model.save(artifact)

        db.expire_all()
        completed = db.get(VisualTrainingRun, run_id)
        trained_model = db.get(VisualModel, model_config.id)
        if completed and trained_model:
            latest_version = db.scalar(
                select(func.max(VisualTrainingRun.version_number)).where(
                    VisualTrainingRun.visual_model_id == model_config.id
                )
            ) or 0
            db.execute(
                update(VisualTrainingRun)
                .where(VisualTrainingRun.visual_model_id == model_config.id)
                .values(is_active=False)
            )
            completed.status = "completed"
            completed.progress = 100
            # Keras owns the authoritative full epoch history. Persist it once at
            # completion as well as emitting live callback progress; this avoids
            # losing intermediate JSON updates across callback DB sessions.
            completed.training_history = {
                key: [round(float(value), 6) for value in values]
                for key, values in fit_history.history.items()
            }
            completed.artifact_path = artifact.relative_to(Path(get_settings().upload_directory).resolve()).as_posix()
            completed.evaluation = evaluation
            completed.version_number = latest_version + 1
            completed.is_active = True
            completed.completed_at = datetime.now(timezone.utc)
            trained_model.status = "trained"
            db.commit()
            _trim_visual_versions(db, model_config.id)
    except Exception as exc:
        logger.exception("Visual training failed for run %s", run_id)
        db.rollback()
        failed = db.get(VisualTrainingRun, run_id)
        if failed:
            failed.status = "failed"
            failed.error = str(exc)[:2000]
            failed.completed_at = datetime.now(timezone.utc)
            failed_model = db.get(VisualModel, failed.visual_model_id)
            if failed_model:
                failed_model.status = "training_failed"
            db.commit()
    finally:
        db.close()


def _trim_visual_versions(db: Session, model_id: UUID) -> None:
    versions = list(db.scalars(
        select(VisualTrainingRun)
        .where(
            VisualTrainingRun.visual_model_id == model_id,
            VisualTrainingRun.status == "completed",
            VisualTrainingRun.version_number.is_not(None),
        )
        .order_by(VisualTrainingRun.version_number.desc())
    ))
    upload_root = Path(get_settings().upload_directory).resolve()
    for obsolete in versions[3:]:
        if obsolete.artifact_path:
            artifact = upload_root / obsolete.artifact_path
            if artifact.is_file():
                artifact.unlink()
        db.delete(obsolete)
    db.commit()


def _validation_dataset(tf, config: VisualModel, run: VisualTrainingRun, tenant_id: UUID):
    dataset_root = (
        Path(get_settings().upload_directory).resolve()
        / "visual-datasets" / str(tenant_id) / str(config.id)
    )
    return tf.keras.utils.image_dataset_from_directory(
        directory=str(dataset_root),
        labels="inferred",
        label_mode="int",
        class_names=list(config.class_names),
        validation_split=run.validation_split,
        subset="validation",
        seed=42,
        image_size=(config.image_height, config.image_width),
        batch_size=run.batch_size,
        color_mode="rgb" if config.channels == 3 else "grayscale",
        shuffle=False,
    ).prefetch(tf.data.AUTOTUNE)


def _evaluate_model(keras_model, validation_dataset, class_names: list[str]) -> dict:
    labels: list[int] = []
    probabilities: list[list[float]] = []
    for images, batch_labels in validation_dataset:
        batch_probabilities = keras_model.predict_on_batch(images)
        labels.extend(np.asarray(batch_labels).astype(int).tolist())
        probabilities.extend(np.asarray(batch_probabilities).astype(float).tolist())
    return _evaluation_payload(class_names, np.asarray(labels), np.asarray(probabilities))


def _evaluation_payload(
    class_names: list[str], labels: np.ndarray, probabilities: np.ndarray
) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    if not labels.size or probabilities.ndim != 2:
        raise VisualTrainingError("The validation set contains no evaluable images")
    predictions = probabilities.argmax(axis=1)
    indexes = list(range(len(class_names)))
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=indexes, zero_division=0
    )
    macro = precision_recall_fscore_support(
        labels, predictions, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        labels, predictions, average="weighted", zero_division=0
    )
    confidence = probabilities.max(axis=1)
    histogram, boundaries = np.histogram(confidence, bins=np.linspace(0, 1, 6))
    return {
        "sample_count": int(labels.size),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "accuracy": round(float(accuracy_score(labels, predictions)), 6),
            "balanced_accuracy": round(float(balanced_accuracy_score(labels, predictions)), 6),
            "macro_precision": round(float(macro[0]), 6),
            "macro_recall": round(float(macro[1]), 6),
            "macro_f1": round(float(macro[2]), 6),
            "weighted_precision": round(float(weighted[0]), 6),
            "weighted_recall": round(float(weighted[1]), 6),
            "weighted_f1": round(float(weighted[2]), 6),
        },
        "classes": [
            {
                "class_name": name,
                "precision": round(float(precision[index]), 6),
                "recall": round(float(recall[index]), 6),
                "f1": round(float(f1[index]), 6),
                "support": int(support[index]),
            }
            for index, name in enumerate(class_names)
        ],
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=indexes
        ).astype(int).tolist(),
        "confidence_histogram": {
            "labels": [
                f"{boundaries[index]:.1f}–{boundaries[index + 1]:.1f}"
                for index in range(len(boundaries) - 1)
            ],
            "counts": histogram.astype(int).tolist(),
        },
    }


def _build_model(tf, config: VisualModel, class_count: int, learning_rate: float):
    input_shape = (config.image_height, config.image_width, config.channels)
    augmentation = tf.keras.Sequential([
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.05),
        tf.keras.layers.RandomZoom(0.1),
    ], name="augmentation")
    inputs = tf.keras.Input(shape=input_shape)
    x = augmentation(inputs)
    if config.architecture == "simple_cnn":
        x = tf.keras.layers.Rescaling(1.0 / 255)(x)
        for filters in (32, 64, 128):
            x = tf.keras.layers.Conv2D(filters, 3, activation="relu", padding="same")(x)
            x = tf.keras.layers.MaxPooling2D()(x)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
    else:
        if config.channels != 3:
            raise RuntimeError("Transfer-learning architectures require RGB images")
        application = tf.keras.applications.MobileNetV2 if config.architecture == "mobilenet_v2" else tf.keras.applications.ResNet50
        preprocess = tf.keras.applications.mobilenet_v2.preprocess_input if config.architecture == "mobilenet_v2" else tf.keras.applications.resnet50.preprocess_input
        x = preprocess(x)
        base = application(
            include_top=False,
            weights="imagenet" if config.use_pretrained_weights else None,
            input_shape=input_shape,
        )
        base.trainable = not config.use_pretrained_weights
        x = base(x, training=False)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.2)(x)
    outputs = tf.keras.layers.Dense(class_count, activation="softmax")(x)
    model = tf.keras.Model(inputs, outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model
