"""Create a repeatable set of published NewsForge stories for local UI development.

Run inside the backend container:
    python scripts/seed_dummy_stories.py
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.services.bootstrap import ensure_bootstrap_admin


STORIES = [
    ("Cities are learning to breathe again", "A new generation of public spaces is returning quiet, shade and surprise to dense urban life.", "cities", "cities-are-learning-to-breathe-again", "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?auto=format&fit=crop&w=1400&q=85"),
    ("The libraries quietly becoming a city’s best third place", "Inside the civic rooms where work, warmth and community are sharing the same table.", "culture", "libraries-becoming-best-third-place", "https://images.unsplash.com/photo-1521587760476-6c12a4b040da?auto=format&fit=crop&w=1200&q=85"),
    ("A practical guide to building cooler neighbourhoods", "Small interventions are changing how streets feel during the longest weeks of summer.", "climate", "building-cooler-neighbourhoods", "https://images.unsplash.com/photo-1444723121867-7a241cacace9?auto=format&fit=crop&w=1200&q=85"),
    ("The patient craft behind a truly useful local app", "Designers are trading novelty for tools that make daily life feel less complicated.", "technology", "craft-behind-useful-local-app", "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1200&q=85"),
    ("Why the most interesting food stories start before dinner", "Farmers, cooks and neighbours are reshaping the way a city eats together.", "food", "food-stories-before-dinner", "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=1200&q=85"),
    ("A night train, a notebook and a slower kind of travel", "The case for letting the route be part of the story.", "travel", "night-train-slower-travel", "https://images.unsplash.com/photo-1473445361085-b9a07f55608b?auto=format&fit=crop&w=1200&q=85"),
    ("The small studios making repair feel aspirational", "Mending is becoming a social ritual, not a compromise.", "design", "studios-making-repair-aspirational", "https://images.unsplash.com/photo-1489278353717-f64c6ee8a4d2?auto=format&fit=crop&w=1200&q=85"),
    ("Inside the volunteer networks keeping rivers visible", "Citizen science is giving local waterways a louder voice.", "environment", "volunteer-networks-rivers-visible", "https://images.unsplash.com/photo-1437482078695-73f5ca6c96e2?auto=format&fit=crop&w=1200&q=85"),
    ("What a good neighbourhood market actually gives back", "Beyond groceries, the best markets offer a living map of the people around us.", "community", "what-neighbourhood-markets-give-back", "https://images.unsplash.com/photo-1488459716781-31db52582fe9?auto=format&fit=crop&w=1200&q=85"),
    ("The makers designing for five useful years, not five minutes", "A quieter product culture is putting durability back at the center.", "design", "makers-designing-for-five-years", "https://images.unsplash.com/photo-1494438639946-1ebd1d20bf85?auto=format&fit=crop&w=1200&q=85"),
    ("A field guide to finding the calmest corner of a busy city", "A writer walks the overlooked pockets that make a metropolis feel human-sized.", "culture", "field-guide-calmest-city-corner", "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&w=1200&q=85"),
]


async def main() -> None:
    if not await connect_to_mongo():
        raise RuntimeError("MongoDB is unavailable. Start the Compose stack first.")
    try:
        await ensure_bootstrap_admin()
        database = get_database()
        author = await database.users.find_one({"is_active": True, "role": "admin"})
        if author is None:
            raise RuntimeError("No administrator account is available for seeded stories.")
        now = datetime.now(UTC)
        for index, (title, dek, topic, slug, image) in enumerate(STORIES):
            published_at = now - timedelta(hours=index * 3)
            document = {
                "slug": slug,
                "status": "published",
                "title": title,
                "dek": dek,
                "content_json": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"{dek} NewsForge demo coverage gives this story a complete reading experience for local development."}]}]},
                "content_html": f"<p>{dek}</p><p>NewsForge demo coverage gives this story a complete reading experience for local development.</p>",
                "topic": topic,
                "tags": [topic, "newsforge", "demo"],
                "hero_media_id": None,
                "hero_url": image,
                "creator_id": author["_id"],
                "editor_id": author["_id"],
                "created_at": published_at,
                "updated_at": published_at,
                "published_at": published_at,
                "scheduled_for": None,
                "is_demo": True,
                "metrics": {"views": 1000 - index * 47, "likes": 100 - index * 5, "dislikes": index, "engagement_ratio": 0.1, "popularity_score": 1000 - index * 40, "seo_score": 90},
            }
            await database.articles.update_one({"slug": slug}, {"$set": document}, upsert=True)
        print(f"Seeded {len(STORIES)} published demo stories. Re-running this script safely refreshes only these slugs.")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
