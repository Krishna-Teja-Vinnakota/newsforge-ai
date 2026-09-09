from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_current_user
from app.core.database import get_database
from app.core.storage import upload_public_object
from app.core.features import require_storage_feature
from app.models.media import MediaResponse

router = APIRouter(prefix="/media")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def media_response(media: dict) -> MediaResponse:
    return MediaResponse(
        id=str(media["_id"]),
        url=media["url"],
        object_key=media["object_key"],
        content_type=media["content_type"],
        size_bytes=media["size_bytes"],
        uploader_id=str(media["uploader_id"]),
        created_at=media["created_at"],
    )


@router.post("/upload", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    purpose: str = Form("inline"),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_storage_feature),
) -> MediaResponse:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only JPEG, PNG, WebP, and GIF images are allowed")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image must be smaller than 10 MB")
    object_key, url = await upload_public_object(content, file.content_type, file.filename or "image")
    document = {
        "object_key": object_key,
        "url": url,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "purpose": purpose if purpose in {"avatar", "inline", "hero"} else "inline",
        "uploader_id": current_user["_id"],
        "created_at": datetime.now(UTC),
    }
    result = await get_database().media.insert_one(document)
    document["_id"] = result.inserted_id
    if document["purpose"] == "avatar":
        await get_database().users.update_one({"_id": current_user["_id"]}, {"$set": {"avatar_media_id": result.inserted_id, "updated_at": datetime.now(UTC)}})
    return media_response(document)
