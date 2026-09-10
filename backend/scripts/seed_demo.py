"""Create the deterministic NewsForge editorial demonstration scenario."""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Support `python scripts/seed_demo.py` from the backend directory.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from bson import ObjectId

from app.core.database import close_mongo_connection, connect_to_mongo, get_database

DEMO_TIMESTAMP = datetime(2025, 9, 1, tzinfo=UTC)
PLACEHOLDER_HERO_URL = "http://localhost:9000/media/placeholder-tech.jpg"
DEMO_USER_ID = ObjectId("64a0000000000000000000ff")

LEADS = (
    ("demo-ohio-microchip-facility", "Ohio Tech Corridor Expands with Major Microchip Facility Investment", "nation-world", "Ohio", 0.65, 1),
    ("demo-nfl-season-kickoff", "National Football League Prepares for Season Kickoff Next Month", "sports", "national", 0.65, 2),
    ("demo-open-source-ai-model", "New Open-Source AI Model Outperforms Commercial Benchmarks", "technology", "global", 0.65, 3),
    ("demo-ohio-clean-energy-grid", "Ohio Clean Energy Grid Upgrade Receives Federal Approval", "nation-world", "Ohio", 0.60, 4),
    ("demo-municipal-transit-bill", "Municipal Transit Modernization Bill Passed by City Council", "local", "Seattle", 0.55, 5),
    ("demo-semiconductor-supply-chain", "Global Semiconductor Supply Chain Report Highlights Growth", "business", "global", 0.50, 6),
)

SOURCES = (
    {
        "article_id": ObjectId("64a000000000000000000001"),
        "slug": "ohio-semiconductor-tax-incentives-passed",
        "title": "Ohio Semiconductor Tax Incentives Passed",
        "topic": "nation-world",
        "geo": "Ohio",
        "summary": "Ohio lawmakers approved a package of tax incentives intended to attract semiconductor manufacturers and their suppliers.",
        "body": "Ohio lawmakers approved semiconductor tax incentives that tie public support to job creation, capital investment and workforce training. The package is designed to help local communities prepare utility, road and housing infrastructure for large advanced-manufacturing projects.",
    },
    {
        "article_id": ObjectId("64a000000000000000000002"),
        "slug": "midwest-tech-infrastructure-report-2025",
        "title": "Midwest Tech Infrastructure Report 2025",
        "topic": "nation-world",
        "geo": "Ohio",
        "summary": "A regional report identifies power capacity, skilled labor and transportation links as key factors in Midwest technology investment.",
        "body": "The 2025 Midwest Tech Infrastructure Report finds that dependable power, specialized technical training and freight connections are central to attracting technology manufacturing. Ohio is highlighted for coordinated planning among utilities, colleges and regional development agencies.",
    },
    {
        "article_id": ObjectId("64a000000000000000000003"),
        "slug": "federal-microchip-manufacturing-subsidies-overview",
        "title": "Federal Microchip Manufacturing Subsidies Overview",
        "topic": "technology",
        "geo": "national",
        "summary": "Federal manufacturing subsidies are supporting domestic semiconductor capacity, research and workforce development.",
        "body": "Federal microchip manufacturing subsidies support domestic fabrication capacity, supply-chain resilience, research partnerships and workforce development. Applicants must document project milestones and the expected economic impact of new facilities.",
    },
)


def lead_document(lead_id: str, headline: str, topic: str, geo: str, base_score: float, current_rank: int) -> dict:
    return {
        "demo": True,
        "lead_id": lead_id,
        "headline": headline,
        "topic": topic,
        "geo": geo,
        "status": "pending",
        "base_score": base_score,
        "learned_weight_delta": 0.0,
        "final_score": base_score,
        "priority_score": base_score,
        "previous_rank": None,
        "current_rank": current_rank,
        "rank_shift": 0,
        "suggested_angle": f"What {headline.lower()} means for {geo} readers.",
        "reasoning": "Curated deterministic demo lead for the editorial workflow.",
        "created_at": DEMO_TIMESTAMP,
        "updated_at": DEMO_TIMESTAMP,
    }


def source_document(source: dict) -> dict:
    body = source["body"]
    return {
        **source,
        "demo": True,
        "tags": [source["topic"], source["geo"].lower(), "semiconductors"],
        "excerpt": source["summary"],
        "content_html": f"<p>{body}</p>",
        "hero_url": PLACEHOLDER_HERO_URL,
        "status": "published",
        "published_at": DEMO_TIMESTAMP,
        "indexed_at": DEMO_TIMESTAMP,
    }


async def reset_demo_data(database=None) -> dict[str, int]:
    """Idempotently replace only NewsForge-owned demo records, never live data."""
    db = database or get_database()
    for collection_name in ("lead_inbox", "editorial_index", "ranking_signals", "telemetry_events", "articles", "users"):
        await db[collection_name].delete_many({"demo": True})

    await db.lead_inbox.insert_many([lead_document(*lead) for lead in LEADS])
    await db.editorial_index.insert_many([source_document(source) for source in SOURCES])
    await db.users.insert_one({"_id": DEMO_USER_ID, "demo": True, "email": "demo.editor@newsforge.dev", "display_name": "NewsForge Demo Editor", "role": "editor", "is_active": True, "password_hash": "demo-only-not-for-login", "created_at": DEMO_TIMESTAMP, "updated_at": DEMO_TIMESTAMP})
    await db.articles.insert_many([{
        "_id": source["article_id"], "demo": True, "slug": source["slug"], "title": source["title"], "dek": source["summary"], "content": source["body"], "content_html": f"<p>{source['body']}</p>", "content_json": {}, "topic": source["topic"], "geo": source["geo"], "tags": [source["topic"], "semiconductors"], "status": "published", "creator_id": DEMO_USER_ID, "editor_id": DEMO_USER_ID, "hero_media_id": None, "hero_url": PLACEHOLDER_HERO_URL, "created_at": DEMO_TIMESTAMP, "updated_at": DEMO_TIMESTAMP, "published_at": DEMO_TIMESTAMP, "scheduled_for": None, "metrics": {"views": 0, "likes": 0, "dislikes": 0, "engagement_ratio": 0, "popularity_score": 0, "seo_score": None},
    } for source in SOURCES])
    await db.ranking_signals.insert_one({"_id": "demo|baseline", "demo": True, "topic": "demo", "geo": "baseline", "weight_delta": 0.0, "sample_size": 0, "confidence": 0.5, "last_updated": DEMO_TIMESTAMP})
    return {"seeded_leads": len(LEADS), "indexed_sources": len(SOURCES), "seeded_articles": len(SOURCES), "seeded_users": 1}


async def main() -> None:
    if not await connect_to_mongo():
        raise RuntimeError("MongoDB is unavailable; demo data was not reset")
    try:
        result = await reset_demo_data()
        print(f"Seeded {result['seeded_leads']} leads and {result['indexed_sources']} indexed sources.")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
