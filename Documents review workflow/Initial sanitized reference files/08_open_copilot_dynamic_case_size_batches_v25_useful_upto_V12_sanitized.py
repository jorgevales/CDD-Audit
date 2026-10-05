#!/usr/bin/env python3
"""Target-driven launcher for resilient Copilot case orchestration."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_MESSAGE_PATH_OVERRIDE: Path | None = None


def _project_root() -> Path:
    override = os.environ.get("CDD_PROJECT_ROOT", "").strip()
    return Path(override).expanduser().resolve() if override else Path(__file__).resolve().parent.parent


def main() -> int:
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from resources.configuration import ResourceSettings

    settings = ResourceSettings.from_orchestrator(Path(__file__))
    if BASE_MESSAGE_PATH_OVERRIDE is not None:
        settings = ResourceSettings(
            settings.resources_dir,
            BASE_MESSAGE_PATH_OVERRIDE.expanduser().resolve(),
        )
    settings.validate()
    os.environ["COPILOT_BASE_MESSAGE_PATH"] = str(settings.base_message_path)

    from resources import implementation

    implementation.self_test_v24()
    implementation.self_test_target_orchestration()
    return implementation.main()


if __name__ == "__main__":
    raise SystemExit(main())
