from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import VisualDatasetImage, VisualModel
from app.schemas.visual_model import (
    VisualDatasetClassSummary,
    VisualDatasetSummary,
    VisualDatasetUploadResponse,
)


class VisualDatasetError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class VisualDatasetService:
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    content_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def get_model(self, model_id: UUID, tenant_id: UUID) -> VisualModel:
        model = self.db.scalar(select(VisualModel).where(
            VisualModel.id == model_id, VisualModel.tenant_id == tenant_id
        ))
        if not model:
            raise VisualDatasetError("Visual model not found", 404)
        return model

    def summary(self, model_id: UUID, tenant_id: UUID) -> VisualDatasetSummary:
        model = self.get_model(model_id, tenant_id)
        rows = self.db.execute(
            select(
                VisualDatasetImage.class_name,
                func.count(VisualDatasetImage.id),
                func.coalesce(func.sum(VisualDatasetImage.size_bytes), 0),
            )
            .where(
                VisualDatasetImage.visual_model_id == model.id,
                VisualDatasetImage.tenant_id == tenant_id,
            )
            .group_by(VisualDatasetImage.class_name)
        ).all()
        counts = {name: (int(count), int(size)) for name, count, size in rows}
        classes = [
            VisualDatasetClassSummary(
                class_name=name,
                image_count=counts.get(name, (0, 0))[0],
                total_bytes=counts.get(name, (0, 0))[1],
            )
            for name in model.class_names
        ]
        return VisualDatasetSummary(
            visual_model_id=model.id,
            total_images=sum(item.image_count for item in classes),
            total_bytes=sum(item.total_bytes for item in classes),
            ready_for_training=bool(classes) and all(item.image_count > 0 for item in classes),
            classes=classes,
        )

    def upload(self, model_id: UUID, tenant_id: UUID, files: list, class_name: str | None) -> VisualDatasetUploadResponse:
        model = self.get_model(model_id, tenant_id)
        if not files:
            raise VisualDatasetError("Select at least one image or ZIP file")
        if len(files) > self.settings.visual_dataset_max_files_per_upload:
            raise VisualDatasetError("Too many files in one upload", 413)

        zip_files = [item for item in files if Path(item.filename or "").suffix.lower() == ".zip"]
        if zip_files and (len(files) != 1 or len(zip_files) != 1):
            raise VisualDatasetError("Upload one ZIP file or multiple image files, not both")

        class_lookup = {name.casefold(): name for name in model.class_names}
        canonical_class = self._canonical_class(class_name, class_lookup) if not zip_files else None
        if not zip_files and canonical_class is None:
            raise VisualDatasetError("Choose a class for the uploaded images")

        existing_hashes = set(self.db.scalars(select(VisualDatasetImage.sha256).where(
            VisualDatasetImage.visual_model_id == model.id
        )).all())
        seen_hashes: set[str] = set()
        written_paths: list[Path] = []
        added = 0
        skipped = 0
        total_bytes = 0

        try:
            if zip_files:
                archive = zip_files[0]
                archive.file.seek(0)
                try:
                    with zipfile.ZipFile(archive.file) as bundle:
                        members = [member for member in bundle.infolist() if not member.is_dir() and not member.filename.startswith("__MACOSX/")]
                        image_members = [member for member in members if PurePosixPath(member.filename).suffix.lower() in self.allowed_extensions]
                        if not image_members:
                            raise VisualDatasetError("ZIP contains no supported images")
                        if len(image_members) > self.settings.visual_dataset_max_files_per_upload:
                            raise VisualDatasetError("ZIP contains too many images", 413)
                        if sum(member.file_size for member in image_members) > self.settings.visual_dataset_upload_max_bytes:
                            raise VisualDatasetError("ZIP uncompressed size exceeds the upload limit", 413)
                        for member in image_members:
                            parts = PurePosixPath(member.filename).parts
                            if len(parts) < 2:
                                raise VisualDatasetError("ZIP images must be stored under class folders")
                            member_class = self._canonical_class(parts[0], class_lookup)
                            if member_class is None:
                                raise VisualDatasetError(f"Unknown class folder: {parts[0]}")
                            with bundle.open(member) as source:
                                result = self._store_image(model, tenant_id, member_class, PurePosixPath(member.filename).name, source, member.file_size, existing_hashes, seen_hashes)
                            if result is None:
                                skipped += 1
                            else:
                                path, record = result
                                written_paths.append(path)
                                self.db.add(record)
                                added += 1
                                total_bytes += record.size_bytes
                                if total_bytes > self.settings.visual_dataset_upload_max_bytes:
                                    raise VisualDatasetError("Upload exceeds the total size limit", 413)
                except zipfile.BadZipFile as exc:
                    raise VisualDatasetError("The uploaded ZIP is invalid") from exc
            else:
                for uploaded in files:
                    uploaded.file.seek(0)
                    result = self._store_image(model, tenant_id, canonical_class, uploaded.filename or "image", uploaded.file, None, existing_hashes, seen_hashes)
                    if result is None:
                        skipped += 1
                    else:
                        path, record = result
                        written_paths.append(path)
                        self.db.add(record)
                        added += 1
                        total_bytes += record.size_bytes
                    if total_bytes > self.settings.visual_dataset_upload_max_bytes:
                        raise VisualDatasetError("Upload exceeds the total size limit", 413)

            self.db.flush()
            provisional = self.summary(model.id, tenant_id)
            model.status = "dataset_ready" if provisional.ready_for_training else "draft"
            self.db.commit()
        except (VisualDatasetError, IntegrityError) as exc:
            self.db.rollback()
            for path in written_paths:
                path.unlink(missing_ok=True)
            if isinstance(exc, IntegrityError):
                raise VisualDatasetError("One or more images already exist in this dataset") from exc
            raise

        return VisualDatasetUploadResponse(
            added_images=added,
            skipped_duplicates=skipped,
            summary=self.summary(model.id, tenant_id),
        )

    def clear(self, model_id: UUID, tenant_id: UUID) -> None:
        model = self.get_model(model_id, tenant_id)
        self.db.execute(delete(VisualDatasetImage).where(
            VisualDatasetImage.visual_model_id == model.id,
            VisualDatasetImage.tenant_id == tenant_id,
        ))
        model.status = "draft"
        self.db.commit()
        shutil.rmtree(self._model_root(tenant_id, model.id), ignore_errors=True)

    def _store_image(self, model: VisualModel, tenant_id: UUID, class_name: str, original_name: str, source: BinaryIO, declared_size: int | None, existing_hashes: set[str], seen_hashes: set[str]) -> tuple[Path, VisualDatasetImage] | None:
        extension = Path(original_name).suffix.lower()
        if extension not in self.allowed_extensions:
            raise VisualDatasetError(f"Unsupported image type: {extension or 'unknown'}")
        if declared_size is not None and declared_size > self.settings.visual_dataset_image_max_bytes:
            raise VisualDatasetError(f"Image exceeds the {self.settings.visual_dataset_image_max_bytes // 1_000_000} MB limit", 413)

        image_id = uuid4()
        class_directory = (self._model_root(tenant_id, model.id) / class_name).resolve()
        model_root = self._model_root(tenant_id, model.id)
        if model_root not in class_directory.parents:
            raise VisualDatasetError("Invalid dataset path")
        class_directory.mkdir(parents=True, exist_ok=True)
        destination = class_directory / f"{image_id}{extension}"
        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.visual_dataset_image_max_bytes:
                        raise VisualDatasetError(f"Image exceeds the {self.settings.visual_dataset_image_max_bytes // 1_000_000} MB limit", 413)
                    digest.update(chunk)
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        if size == 0:
            destination.unlink(missing_ok=True)
            raise VisualDatasetError("Empty images are not allowed")

        sha256 = digest.hexdigest()
        if sha256 in existing_hashes or sha256 in seen_hashes:
            destination.unlink(missing_ok=True)
            return None
        try:
            with Image.open(destination) as image:
                image.verify()
            with Image.open(destination) as image:
                width, height = image.size
        except (UnidentifiedImageError, OSError) as exc:
            destination.unlink(missing_ok=True)
            raise VisualDatasetError(f"Invalid or corrupted image: {Path(original_name).name}") from exc
        seen_hashes.add(sha256)
        storage_key = destination.relative_to(Path(self.settings.upload_directory).resolve()).as_posix()
        return destination, VisualDatasetImage(
            id=image_id,
            tenant_id=tenant_id,
            visual_model_id=model.id,
            class_name=class_name,
            original_name=Path(original_name).name[:255],
            content_type=self.content_types[extension],
            size_bytes=size,
            width=width,
            height=height,
            sha256=sha256,
            storage_key=storage_key,
        )

    def _model_root(self, tenant_id: UUID, model_id: UUID) -> Path:
        root = Path(self.settings.upload_directory).resolve() / "visual-datasets" / str(tenant_id) / str(model_id)
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    @staticmethod
    def _canonical_class(value: str | None, lookup: dict[str, str]) -> str | None:
        return lookup.get((value or "").strip().casefold())
