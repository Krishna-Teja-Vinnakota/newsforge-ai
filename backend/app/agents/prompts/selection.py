import json

PROMPT_VERSION = "selection_v1.1"


def build_selection_prompt(candidates: list[dict]) -> str:
    return (
        "You are NewsForge's editorial strategy agent. Provide editorial guidance for "
        "each candidate. Return ONLY JSON with a `guidance` array. Every array item "
        "must contain ONLY `lead_id`, `suggested_angle`, and `editorial_guidance`. "
        "Do not provide, calculate, alter, or discuss scores, ranks, or numeric fields. "
        f"Candidates: {json.dumps(candidates, default=str)}"
    )
