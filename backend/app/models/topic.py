from datetime import datetime

from pydantic import BaseModel, Field


class TopicCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")


class TopicUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=50)
    is_active: bool | None = None


class TopicResponse(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime
