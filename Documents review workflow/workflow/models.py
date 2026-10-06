"""The review model catalogue; availability is verified in the user's Copilot UI."""

DEFAULT_MODEL = "GPT-6 Sol"
MODEL_OPTIONS = [
    {"value": label, "label": label, "group": group}
    for group, label in (
        ("GPT", "GPT 5.6 Sol Quick response"),
        ("GPT", "GPT 5.6 Sol Think deeper"),
        ("GPT", DEFAULT_MODEL),
        ("Claude", "Sonnet 5.5"),
        ("Claude", "Opus 5.5"),
        ("Claude", "Sonnet 5"),
    )
]
MODEL_VALUES = frozenset(item["value"] for item in MODEL_OPTIONS)


def validate_model(value: str) -> str:
    if value not in MODEL_VALUES:
        raise ValueError("Choose one of the six supported review models.")
    return value
