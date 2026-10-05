from __future__ import annotations

import os
from pathlib import Path

BASE_MESSAGE_ENV = "COPILOT_BASE_MESSAGE_PATH"
DEFAULT_BASE_MESSAGE_PATH = Path(__file__).resolve().parent / "base_message.md"


def configured_base_message_path() -> Path:
    override = os.environ.get(BASE_MESSAGE_ENV, "").strip()
    return Path(override).expanduser().resolve() if override else DEFAULT_BASE_MESSAGE_PATH


def load_base_message(path: Path | None = None) -> str:
    resolved = (path or configured_base_message_path()).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Required base-message resource was not found: {resolved}")
    try:
        value = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Could not read base-message resource {resolved}: {exc}") from exc
    if not value:
        raise RuntimeError(f"Base-message resource is empty: {resolved}")
    return value
