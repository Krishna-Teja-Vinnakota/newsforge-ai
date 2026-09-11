import json

PROMPT_VERSION = "production_v1.1"


def build_production_prompt(headline: str, topic: str, context: str, sources: list[dict], target_platforms: list[str]) -> str:
    return (
        "You are NewsForge's production agent. Create a fact-grounded draft using only "
        "the supplied context and retrieved sources. Do not invent facts. Return only "
        "the required JSON schema. "
        f"headline={headline!r}; topic={topic!r}; context={context!r}; "
        f"retrieved_sources={json.dumps(sources, default=str)}; platforms={target_platforms!r}."
    )
