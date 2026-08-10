from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.services.collection_service import CollectionError, CollectionService
from app.db.session import get_db
from app.schemas.collection import CollectionCreate, CollectionDocumentResponse, CollectionResponse

router = APIRouter(prefix="/collections", tags=["collections"])

def fail(exc: CollectionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)

@router.get("", response_model=list[CollectionResponse])
def list_collections(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    return [CollectionResponse.model_validate(item) for item in CollectionService(db).list_collections(current.tenant_id)]

@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
def create_collection(payload: CollectionCreate, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        return CollectionResponse.model_validate(CollectionService(db).create(current.tenant_id, payload))
    except CollectionError as exc:
        raise fail(exc) from exc

@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        CollectionService(db).delete(collection_id, current.tenant_id)
    except CollectionError as exc:
        raise fail(exc) from exc

@router.post("/{collection_id}/documents", response_model=CollectionDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(collection_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        document = CollectionService(db).add_document(collection_id, current.tenant_id, file.filename or "document", file.content_type or "application/octet-stream", await file.read())
        return CollectionDocumentResponse.model_validate(document)
    except CollectionError as exc:
        raise fail(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Document indexing failed: {exc}") from exc

@router.delete("/{collection_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(collection_id: UUID, document_id: UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    try:
        CollectionService(db).get(collection_id, current.tenant_id)
        CollectionService(db).delete_document(document_id, current.tenant_id)
    except CollectionError as exc:
        raise fail(exc) from exc
