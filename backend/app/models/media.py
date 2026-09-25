from datetime import datetime

from pydantic import BaseModel


class MediaResponse(BaseModel):
    id: str
    url: str
    object_key: str
    content_type: str
    size_bytes: int
    uploader_id: str
    created_at: datetime
    ai_generated: bool = False
    ai_model: str | None = None
    alt_text: str | None = None
    disclosure: str | None = None
