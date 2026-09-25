from operator import add
from typing import Annotated, Literal, TypedDict


class NewsroomState(TypedDict, total=False):
    thread_id: str
    lead_id: str
    actor_id: str
    lead_candidate: dict
    selection_result: dict
    approval_status: Literal["pending", "approved", "rejected"]
    retrieved_sources: list[dict]
    generated_draft: dict
    article_id: str
    editorial_status: Literal["draft", "under_review", "approved", "published"]
    telemetry_delta: float
    current_step: str
    errors: Annotated[list[str], add]
    execution_history: Annotated[list[dict], add]
