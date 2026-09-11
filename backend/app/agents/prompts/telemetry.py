PROMPT_VERSION = "telemetry_v1.1"


def build_telemetry_prompt(metrics: dict, maximum_weight_delta: float) -> str:
    return (
        "You are NewsForge's audience telemetry agent. Analyze only these aggregate "
        f"metrics: {metrics!r}. Propose a bounded ranking change no greater than "
        f"{maximum_weight_delta}. Return only the required JSON schema."
    )
