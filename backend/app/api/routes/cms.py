from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_database
from app.models.article import ArticleCreateRequest, ArticleListResponse, ArticleResponse, ArticleStatus, ArticleUpdateRequest, PublishRequest, WorkflowTransitionRequest
from app.models.user import UserRole
from app.services.articles import add_workflow_event, article_response, get_article_or_404, unique_slug
from app.services.content import sanitize_html
from app.services.retrieval import index_published_article

router = APIRouter(prefix="/cms/articles")
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)
AUTHORING_ROLES = (UserRole.ADMIN, UserRole.EDITOR, UserRole.REPORTER)


def can_edit(article: dict, user: dict) -> bool:
    return user["role"] in {UserRole.ADMIN, UserRole.EDITOR} or article["creator_id"] == user["_id"]


@router.post("", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(payload: ArticleCreateRequest, current_user: dict = Depends(require_roles(*AUTHORING_ROLES))) -> ArticleResponse:
    now = datetime.now(UTC)
    document = {
        "slug": await unique_slug(payload.title), "status": ArticleStatus.DRAFT, "title": payload.title.strip(), "dek": payload.dek.strip(),
        "content_json": payload.content_json, "content_html": sanitize_html(payload.content_html), "topic": payload.topic.strip().lower(),
        "tags": [tag.strip().lower() for tag in payload.tags if tag.strip()], "hero_media_id": ObjectId(payload.hero_media_id) if payload.hero_media_id and ObjectId.is_valid(payload.hero_media_id) else None, "hero_url": payload.hero_url,
        "creator_id": current_user["_id"], "editor_id": None, "created_at": now, "updated_at": now, "published_at": None, "scheduled_for": None,
        "metrics": {"views": 0, "likes": 0, "dislikes": 0, "engagement_ratio": 0, "popularity_score": 0, "seo_score": None},
    }
    result = await get_database().articles.insert_one(document)
    document["_id"] = result.inserted_id
    await add_workflow_event(result.inserted_id, current_user["_id"], None, ArticleStatus.DRAFT, "Article created")
    return await article_response(document)


@router.get("/mine", response_model=ArticleListResponse)
async def list_my_articles(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50), current_user: dict = Depends(get_current_user)
) -> ArticleListResponse:
    criteria = {} if current_user["role"] in {UserRole.ADMIN, UserRole.EDITOR} else {"creator_id": current_user["_id"]}
    total = await get_database().articles.count_documents(criteria)
    cursor = get_database().articles.find(criteria).sort("updated_at", -1).skip((page - 1) * page_size).limit(page_size)
    return ArticleListResponse(items=[await article_response(item) async for item in cursor], page=page, page_size=page_size, total=total)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: str, current_user: dict = Depends(get_current_user)) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if not can_edit(article, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this article")
    return await article_response(article)


@router.patch("/{article_id}", response_model=ArticleResponse)
@router.put("/{article_id}", response_model=ArticleResponse)
async def update_article(article_id: str, payload: ArticleUpdateRequest, current_user: dict = Depends(get_current_user)) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if not can_edit(article, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot edit this article")
    if article["status"] == ArticleStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Create a new revision before editing this article")
    changes = payload.model_dump(exclude_unset=True)
    if "content_html" in changes:
        changes["content_html"] = sanitize_html(changes["content_html"])
    if "title" in changes:
        changes["title"] = changes["title"].strip()
        changes["slug"] = await unique_slug(changes["title"], article["_id"])
    if "topic" in changes:
        changes["topic"] = changes["topic"].strip().lower()
    if "tags" in changes and changes["tags"] is not None:
        changes["tags"] = [tag.strip().lower() for tag in changes["tags"] if tag.strip()]
    if "hero_media_id" in changes:
        media_id = changes["hero_media_id"]
        changes["hero_media_id"] = ObjectId(media_id) if media_id and ObjectId.is_valid(media_id) else None
    changes["updated_at"] = datetime.now(UTC)
    await get_database().articles.update_one({"_id": article["_id"]}, {"$set": changes})
    article.update(changes)
    return await article_response(article)


@router.post("/{article_id}/submit-review", response_model=ArticleResponse)
async def submit_for_review(article_id: str, payload: WorkflowTransitionRequest, current_user: dict = Depends(require_roles(*EDITOR_ROLES))) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if not can_edit(article, current_user) or article["status"] not in {ArticleStatus.DRAFT, ArticleStatus.UNPUBLISHED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a draft or unpublished story can move to under_review")
    now = datetime.now(UTC)
    await get_database().articles.update_one({"_id": article["_id"]}, {"$set": {"status": ArticleStatus.UNDER_REVIEW, "updated_at": now}})
    await add_workflow_event(article["_id"], current_user["_id"], article["status"], ArticleStatus.UNDER_REVIEW, payload.note)
    article.update({"status": ArticleStatus.UNDER_REVIEW, "updated_at": now})
    return await article_response(article)


@router.post("/{article_id}/publish", response_model=ArticleResponse)
async def publish_article(article_id: str, payload: PublishRequest, current_user: dict = Depends(require_roles(*EDITOR_ROLES))) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if article["status"] != ArticleStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only an approved article can be published")
    now = datetime.now(UTC)
    # The CMS review contract deliberately permits only approved -> published.
    next_status = ArticleStatus.PUBLISHED
    changes = {"status": next_status, "editor_id": current_user["_id"], "updated_at": now, "scheduled_for": None, "published_at": now}
    await get_database().articles.update_one({"_id": article["_id"]}, {"$set": changes})
    if article.get("source_lead_id"):
        await get_database().lead_inbox.update_one(
            {"lead_id": article["source_lead_id"]},
            {"$set": {"status": "published", "updated_at": now}},
        )
    await add_workflow_event(article["_id"], current_user["_id"], article["status"], next_status, payload.note)
    article.update(changes)
    if next_status == ArticleStatus.PUBLISHED:
        await index_published_article(article)
    return await article_response(article)


@router.post("/{article_id}/approve", response_model=ArticleResponse)
async def approve_article(article_id: str, payload: WorkflowTransitionRequest, current_user: dict = Depends(require_roles(*EDITOR_ROLES))) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if article["status"] != ArticleStatus.UNDER_REVIEW:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only stories under review can be approved")
    now = datetime.now(UTC)
    changes = {"status": ArticleStatus.APPROVED, "editor_id": current_user["_id"], "updated_at": now}
    await get_database().articles.update_one({"_id": article["_id"]}, {"$set": changes})
    await add_workflow_event(article["_id"], current_user["_id"], ArticleStatus.UNDER_REVIEW, ArticleStatus.APPROVED, payload.note)
    article.update(changes)
    return await article_response(article)


@router.post("/{article_id}/reject", response_model=ArticleResponse)
async def reject_article(article_id: str, payload: WorkflowTransitionRequest, current_user: dict = Depends(require_roles(*EDITOR_ROLES))) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if article["status"] != ArticleStatus.UNDER_REVIEW:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only stories in review can be rejected")
    now = datetime.now(UTC)
    changes = {"status": ArticleStatus.REJECTED, "editor_id": current_user["_id"], "updated_at": now}
    await get_database().articles.update_one({"_id": article["_id"]}, {"$set": changes})
    await add_workflow_event(article["_id"], current_user["_id"], ArticleStatus.UNDER_REVIEW, ArticleStatus.REJECTED, payload.note)
    article.update(changes)
    return await article_response(article)


@router.post("/{article_id}/unpublish", response_model=ArticleResponse)
async def unpublish_article(article_id: str, payload: WorkflowTransitionRequest, current_user: dict = Depends(require_roles(*EDITOR_ROLES))) -> ArticleResponse:
    article = await get_article_or_404(article_id)
    if article["status"] != ArticleStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a published article can be unpublished")
    now = datetime.now(UTC)
    changes = {"status": ArticleStatus.UNPUBLISHED, "updated_at": now, "published_at": None, "scheduled_for": None}
    await get_database().articles.update_one({"_id": article["_id"]}, {"$set": changes})
    await get_database().editorial_index.delete_one({"article_id": article["_id"]})
    await add_workflow_event(article["_id"], current_user["_id"], ArticleStatus.PUBLISHED, ArticleStatus.UNPUBLISHED, payload.note)
    article.update(changes)
    return await article_response(article)
