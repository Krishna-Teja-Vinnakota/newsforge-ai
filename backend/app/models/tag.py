from datetime import datetime
from pydantic import BaseModel, Field

class TagCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=40)

class TagResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
