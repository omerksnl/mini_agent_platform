import io
import re
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.services.embedding_service import EmbeddingService
from app.models import Collection, CollectionDocument, DocumentChunk
from app.schemas.collection import CollectionCreate


class CollectionError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message, self.status_code = message, status_code
        super().__init__(message)


class CollectionService:
    def __init__(self, db: Session, embeddings: EmbeddingService | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.embeddings = embeddings

    def list_collections(self, tenant_id: UUID) -> list[Collection]:
        return list(self.db.scalars(select(Collection).where(Collection.tenant_id == tenant_id).order_by(Collection.created_at.desc())).unique().all())

    def get(self, collection_id: UUID, tenant_id: UUID) -> Collection:
        item = self.db.scalar(select(Collection).where(Collection.id == collection_id, Collection.tenant_id == tenant_id))
        if not item:
            raise CollectionError("Collection not found", 404)
        return item

    def get_many(self, ids: list[UUID], tenant_id: UUID) -> list[Collection]:
        if not ids:
            return []
        unique = list(dict.fromkeys(ids))
        items = list(self.db.scalars(select(Collection).where(Collection.id.in_(unique), Collection.tenant_id == tenant_id)).all())
        if len(items) != len(unique):
            raise CollectionError("One or more collections were not found", 404)
        by_id = {item.id: item for item in items}
        return [by_id[item_id] for item_id in unique]

    def create(self, tenant_id: UUID, payload: CollectionCreate) -> Collection:
        item = Collection(tenant_id=tenant_id, name=payload.name.strip(), description=payload.description.strip())
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise CollectionError("A collection with this name already exists", 409) from exc
        self.db.refresh(item)
        return item

    def delete(self, collection_id: UUID, tenant_id: UUID) -> None:
        self.db.delete(self.get(collection_id, tenant_id))
        self.db.commit()

    def delete_document(self, document_id: UUID, tenant_id: UUID) -> None:
        item = self.db.scalar(select(CollectionDocument).where(CollectionDocument.id == document_id, CollectionDocument.tenant_id == tenant_id))
        if not item:
            raise CollectionError("Document not found", 404)
        self.db.delete(item)
        self.db.commit()

    def add_document(self, collection_id: UUID, tenant_id: UUID, filename: str, content_type: str, data: bytes) -> CollectionDocument:
        collection = self.get(collection_id, tenant_id)
        if not data or len(data) > self.settings.attachment_max_bytes:
            raise CollectionError("Document is empty or exceeds the upload limit", 413)
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".txt", ".md"}:
            raise CollectionError("Only PDF, TXT, and Markdown documents are supported")
        sections = self._extract_sections(suffix, data)
        chunks = self._chunk_sections(sections)
        if not chunks:
            raise CollectionError("No readable text was found; scanned PDFs require OCR")
        vectors = (self.embeddings or EmbeddingService()).embed([text for text, _ in chunks], "search_document")
        document = CollectionDocument(tenant_id=tenant_id, collection_id=collection.id, original_name=Path(filename).name[:255], content_type=content_type, size_bytes=len(data), chunk_count=len(chunks))
        self.db.add(document)
        self.db.flush()
        for position, ((text, page), vector) in enumerate(zip(chunks, vectors, strict=True)):
            self.db.add(DocumentChunk(tenant_id=tenant_id, collection_id=collection.id, document_id=document.id, position=position, page_number=page, content=text, embedding=vector))
        self.db.commit()
        self.db.refresh(document)
        return document

    def search(self, tenant_id: UUID, collection_ids: list[UUID], query: str, limit: int | None = None) -> list[tuple[DocumentChunk, float]]:
        if not collection_ids:
            return []
        vector = (self.embeddings or EmbeddingService()).embed([query], "search_query")[0]
        distance = DocumentChunk.embedding.cosine_distance(vector)
        stmt = select(DocumentChunk, distance.label("distance")).where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.collection_id.in_(collection_ids)).order_by(distance).limit(limit or self.settings.collection_search_results)
        return [(chunk, max(0.0, 1.0 - float(value))) for chunk, value in self.db.execute(stmt).all()]

    def read_all_text(
        self, tenant_id: UUID, collection_ids: list[UUID], max_characters: int = 50_000
    ) -> str:
        if not collection_ids:
            return ""
        chunks = list(self.db.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.collection_id.in_(collection_ids),
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.position)
        ).all())
        blocks: list[str] = []
        total = 0
        for chunk in chunks:
            source = chunk.document.original_name
            location = f", page {chunk.page_number}" if chunk.page_number else ""
            block = f"[Source: {source}{location}]\n{chunk.content}"
            if total + len(block) > max_characters:
                remaining = max_characters - total
                if remaining > 200:
                    blocks.append(block[:remaining])
                break
            blocks.append(block)
            total += len(block)
        return "\n\n---\n\n".join(blocks)

    def search_text(
        self,
        tenant_id: UUID,
        collection_ids: list[UUID],
        query: str,
        *,
        limit: int | None = None,
        max_characters: int = 12_000,
    ) -> str:
        """Return compact, source-labelled semantic-search context for one LLM call."""
        results = self.search(tenant_id, collection_ids, query, limit)
        # A relevant heading can land at the end of one chunk while its criteria
        # continue in the next chunk. Expand each semantic hit with its immediate
        # neighbours so the model receives complete local context instead of a
        # misleading fragment.
        expanded: list[tuple[DocumentChunk, float]] = []
        seen: set[UUID] = set()
        for hit, score in results:
            positions = [position for position in (hit.position - 1, hit.position, hit.position + 1) if position >= 0]
            neighbours = list(self.db.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.document_id == hit.document_id,
                    DocumentChunk.position.in_(positions),
                )
                .order_by(DocumentChunk.position)
            ).all())
            for neighbour in neighbours:
                if neighbour.id in seen:
                    continue
                seen.add(neighbour.id)
                distance = abs(neighbour.position - hit.position)
                expanded.append((neighbour, max(0.0, score - (0.001 * distance))))
        results = expanded
        blocks: list[str] = []
        total = 0
        for chunk, score in results:
            source = chunk.document.original_name
            location = f", page {chunk.page_number}" if chunk.page_number else ""
            block = f"[Source: {source}{location}; relevance: {score:.3f}]\n{chunk.content}"
            remaining = max_characters - total
            if remaining <= 0:
                break
            if len(block) > remaining:
                if remaining > 200:
                    blocks.append(block[:remaining])
                break
            blocks.append(block)
            total += len(block)
        return "\n\n---\n\n".join(blocks)

    def _extract_sections(self, suffix: str, data: bytes) -> list[tuple[str, int | None]]:
        if suffix == ".pdf":
            try:
                reader = PdfReader(io.BytesIO(data))
            except Exception as exc:
                raise CollectionError("The PDF could not be read") from exc
            return [(page.extract_text() or "", index + 1) for index, page in enumerate(reader.pages[:self.settings.pdf_max_pages])]
        try:
            return [(data.decode("utf-8"), None)]
        except UnicodeDecodeError as exc:
            raise CollectionError("Text documents must use UTF-8 encoding") from exc

    def _chunk_sections(self, sections: list[tuple[str, int | None]]) -> list[tuple[str, int | None]]:
        size, overlap = self.settings.collection_chunk_characters, self.settings.collection_chunk_overlap
        result: list[tuple[str, int | None]] = []
        for raw, page in sections:
            text = re.sub(r"[ \t]+", " ", raw).strip()
            start = 0
            while start < len(text):
                end = min(len(text), start + size)
                if end < len(text):
                    boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
                    if boundary > start + size // 2:
                        end = boundary + 1
                chunk = text[start:end].strip()
                if chunk:
                    result.append((chunk, page))
                if end >= len(text):
                    break
                start = max(start + 1, end - overlap)
        return result
