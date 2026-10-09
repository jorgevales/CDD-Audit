from __future__ import annotations

import json
import os
from pathlib import Path


def config_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CDD Audit" / "JustifyIPChangeCopilotChatUI" / "config.json"


def load_last_workspace() -> str:
    path = config_path()
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    value = payload.get("last_workspace", "") if isinstance(payload, dict) else ""
    return value if isinstance(value, str) else ""


def save_last_workspace(value: Path) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"last_workspace": str(value)}, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
