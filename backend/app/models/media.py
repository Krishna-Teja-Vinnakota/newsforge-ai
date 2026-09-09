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
