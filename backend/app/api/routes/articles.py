from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import get_database
from app.models.article import ArticleListResponse, ArticleResponse, ArticleStatus
from app.services.articles import article_response

router = APIRouter(prefix="/articles")


@router.get("", response_model=ArticleListResponse)
async def list_published_articles(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50)) -> ArticleListResponse:
    criteria = {"status": ArticleStatus.PUBLISHED}
    total = await get_database().articles.count_documents(criteria)
    cursor = get_database().articles.find(criteria).sort("published_at", -1).skip((page - 1) * page_size).limit(page_size)
    return ArticleListResponse(items=[await article_response(item) async for item in cursor], page=page, page_size=page_size, total=total)


@router.get("/trending", response_model=ArticleListResponse)
async def trending_articles(limit: int = Query(default=5, ge=1, le=10)) -> ArticleListResponse:
    criteria = {"status": ArticleStatus.PUBLISHED}
    cursor = get_database().articles.find(criteria).sort([("metrics.popularity_score", -1), ("published_at", -1)]).limit(limit)
    items = [await article_response(item) async for item in cursor]
    return ArticleListResponse(items=items, page=1, page_size=limit, total=len(items))


@router.get("/{slug}", response_model=ArticleResponse)
async def get_published_article(slug: str) -> ArticleResponse:
    article = await get_database().articles.find_one({"slug": slug, "status": ArticleStatus.PUBLISHED})
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return await article_response(article)
