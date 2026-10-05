from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceSettings:
    """Immutable resource locations supplied by the lightweight orchestrator."""

    resources_dir: Path
    base_message_path: Path

    @classmethod
    def from_orchestrator(cls, orchestrator_file: Path) -> "ResourceSettings":
        root = (Path(os.environ["CDD_PROJECT_ROOT"]).expanduser().resolve()
                if os.environ.get("CDD_PROJECT_ROOT") else orchestrator_file.resolve().parent.parent)
        resources_dir = root / "resources"
        production_name = resources_dir / "base_message.md"
        sanitized_name = resources_dir / "base_message_sanitized.md"
        return cls(resources_dir, production_name if production_name.is_file() else sanitized_name)

    def validate(self) -> None:
        if not self.resources_dir.is_dir():
            raise FileNotFoundError(f"Resources directory was not found: {self.resources_dir}")
        if not self.base_message_path.is_file():
            raise FileNotFoundError(f"Base-message resource was not found: {self.base_message_path}")
