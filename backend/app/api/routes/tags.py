from datetime import UTC, datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError
from app.api.dependencies import require_roles
from app.core.database import get_database
from app.models.tag import TagCreateRequest, TagResponse
from app.models.user import EDITORIAL_ROLES
router = APIRouter(prefix="/tags")
def response(tag: dict) -> TagResponse: return TagResponse(id=str(tag["_id"]), name=tag["name"], created_at=tag["created_at"])
@router.get("", response_model=list[TagResponse])
async def list_tags() -> list[TagResponse]:
    database = get_database()
    existing = [tag async for tag in database.tags.find({}).sort("name", 1)]
    names = {tag["name"] for tag in existing}
    # Existing stories are also a source of controlled suggestions during the
    # migration to the tags collection.
    for name in await database.articles.distinct("tags"):
        normalised = str(name).strip().lower()
        if normalised and normalised not in names:
            document = {"name": normalised, "created_at": datetime.now(UTC)}
            try:
                result = await database.tags.insert_one(document)
                document["_id"] = result.inserted_id
                existing.append(document)
                names.add(normalised)
            except DuplicateKeyError:
                pass
    return [response(tag) for tag in sorted(existing, key=lambda item: item["name"])]
@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreateRequest, _: dict = Depends(require_roles(*EDITORIAL_ROLES))) -> TagResponse:
    document = {"name": payload.name.strip().lower(), "created_at": datetime.now(UTC)}
    try: result = await get_database().tags.insert_one(document)
    except DuplicateKeyError as exc: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This tag already exists") from exc
    document["_id"] = result.inserted_id
    return response(document)
@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: str, _: dict = Depends(require_roles(*EDITORIAL_ROLES))):
    if not ObjectId.is_valid(tag_id): raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if not (await get_database().tags.delete_one({"_id": ObjectId(tag_id)})).deleted_count: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
