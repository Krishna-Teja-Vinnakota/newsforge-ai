from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from app.api.dependencies import require_roles
from app.core.database import get_database
from app.models.topic import TopicCreateRequest, TopicResponse, TopicUpdateRequest
from app.models.user import UserRole

router = APIRouter(prefix="/topics")


def response(document: dict) -> TopicResponse:
    return TopicResponse(id=str(document["_id"]), name=document["name"], slug=document["slug"], is_active=document.get("is_active", True), created_at=document["created_at"])


@router.get("", response_model=list[TopicResponse])
async def list_topics() -> list[TopicResponse]:
    cursor = get_database().topics.find({"is_active": True}).sort("name", 1)
    return [response(topic) async for topic in cursor]


@router.get("/tags", response_model=list[str])
async def list_tags() -> list[str]:
    return await get_database().articles.distinct("tags")


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(payload: TopicCreateRequest, _: dict = Depends(require_roles(UserRole.ADMIN))) -> TopicResponse:
    document = {"name": payload.name.strip(), "slug": payload.slug.strip().lower(), "is_active": True, "created_at": datetime.now(UTC)}
    try:
        result = await get_database().topics.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A topic with this slug already exists") from exc
    document["_id"] = result.inserted_id
    return response(document)


@router.patch("/{topic_id}", response_model=TopicResponse)
async def update_topic(topic_id: str, payload: TopicUpdateRequest, _: dict = Depends(require_roles(UserRole.ADMIN))) -> TopicResponse:
    if not ObjectId.is_valid(topic_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    result = await get_database().topics.find_one_and_update({"_id": ObjectId(topic_id)}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return response(result)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: str, _: dict = Depends(require_roles(UserRole.ADMIN))):
    if not ObjectId.is_valid(topic_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    result = await get_database().topics.delete_one({"_id": ObjectId(topic_id)})
    if not result.deleted_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
