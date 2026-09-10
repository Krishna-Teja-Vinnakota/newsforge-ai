import random
import uuid
from datetime import datetime, timedelta
from pymongo import MongoClient

# MongoDB Connection
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "newsforge"

topics = ["nation-world", "sports", "local-government", "technology", "health", "money"]
geos = ["Ohio", "Seattle", "San Antonio", "Chicago", "New York", "Austin"]
stations = ["ABB-TV", "ABCD", "WKRCCW", "WLOS", "PQR"]
platforms = ["web", "ios", "android"]
event_types = ["view", "like", "save", "share"]

def generate_bulk_dataset(num_leads=100, num_events=2500):
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # 1. Generate Candidate Leads (100 stories)
    print(f"Generating {num_leads} candidate leads...")
    leads = []
    now = datetime(2026, 9, 9, 20, 0, 0)
    
    for i in range(num_leads):
        topic = random.choice(topics)
        geo = random.choice(geos)
        lead_id = f"lead_{uuid.uuid4().hex[:10]}"
        pub_time = now - timedelta(hours=random.randint(1, 72))
        
        leads.append({
            "_id": lead_id,
            "headline": f"Dynamic {topic.replace('-', ' ').title()} Alert for {geo} Area #{i+1}",
            "topic": topic,
            "geo": geo,
            "station": random.choice(stations),
            "source": random.choice(["rss", "wire", "community_feed"]),
            "word_count": random.randint(120, 850),
            "tags": [topic, geo, "Automated"],
            "summary": f"Comprehensive report covering key developments in {geo} regarding {topic}.",
            "status": "lead",
            "published_at": pub_time,
            "created_at": pub_time
        })
    
    # 2. Generate Granular Telemetry Events (2,500 events)
    print(f"Generating {num_events} telemetry events...")
    events = []
    for _ in range(num_events):
        topic = random.choice(topics)
        geo = random.choice(geos)
        evt_time = now - timedelta(hours=random.randint(0, 48))
        
        events.append({
            "content_id": f"art_{uuid.uuid4().hex[:8]}",
            "topic": topic,
            "geo": geo,
            "event_type": random.choices(event_types, weights=[0.7, 0.15, 0.1, 0.05])[0],
            "platform": random.choice(platforms),
            "visitor_key": f"anon_{uuid.uuid4().hex[:8]}",
            "duration_sec": random.randint(10, 300),
            "timestamp": evt_time
        })

    # 3. Generate Ranking Signals (36 topic|geo key pairs)
    print("Generating baseline ranking signals...")
    signals = []
    for topic in topics:
        for geo in geos:
            key = f"{topic}|{geo}"
            signals.append({
                "_id": key,
                "key": key,  # <--- ADD THIS LINE
                "topic": topic,
                "geo": geo,
                "weight_delta": round(random.uniform(-0.10, 0.25), 2),
                "sample_size": random.randint(50, 300),
                "confidence": round(random.uniform(0.75, 0.98), 2),
                "last_updated": now
            })
            
    # Bulk Insert to MongoDB
    print("Clearing existing collections and inserting new data...")
    db.leads.delete_many({})
    db.telemetry_events.delete_many({})
    db.ranking_signals.delete_many({})

    db.leads.insert_many(leads)
    db.telemetry_events.insert_many(events)
    db.ranking_signals.insert_many(signals)

    print(f"Successfully loaded into MongoDB database '{DB_NAME}'!")
    print(f" - leads: {db.leads.count_documents({})}")
    print(f" - telemetry_events: {db.telemetry_events.count_documents({})}")
    print(f" - ranking_signals: {db.ranking_signals.count_documents({})}")

if __name__ == "__main__":
    generate_bulk_dataset()