from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from .nodes import (
    node_approval_gate,
    node_editorial_gate,
    node_publish,
    node_retrieve_and_draft,
    node_selection,
    node_telemetry_rerank,
)
from .state import NewsroomState


def after_approval(state: NewsroomState) -> str:
    return "retrieve_and_draft" if state.get("approval_status") == "approved" else END


def after_editorial_review(state: NewsroomState) -> str:
    return "publish" if state.get("editorial_status") == "approved" else END


def build_newsroom_workflow():
    graph = StateGraph(NewsroomState)
    retry_policy = RetryPolicy(max_attempts=3, initial_interval=0.25, max_interval=2.0)
    graph.add_node("selection", node_selection, retry_policy=retry_policy)
    graph.add_node("approval_gate", node_approval_gate)
    graph.add_node("retrieve_and_draft", node_retrieve_and_draft, retry_policy=retry_policy)
    graph.add_node("editorial_gate", node_editorial_gate)
    graph.add_node("publish", node_publish)
    graph.add_node("telemetry", node_telemetry_rerank, retry_policy=retry_policy)
    graph.add_edge(START, "selection")
    graph.add_edge("selection", "approval_gate")
    graph.add_conditional_edges("approval_gate", after_approval, {"retrieve_and_draft": "retrieve_and_draft", END: END})
    graph.add_edge("retrieve_and_draft", "editorial_gate")
    graph.add_conditional_edges("editorial_gate", after_editorial_review, {"publish": "publish", END: END})
    graph.add_edge("publish", "telemetry")
    graph.add_edge("telemetry", END)
    return graph.compile(checkpointer=MemorySaver(), interrupt_before=["approval_gate", "editorial_gate"])


newsroom_workflow = build_newsroom_workflow()


def workflow_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}
