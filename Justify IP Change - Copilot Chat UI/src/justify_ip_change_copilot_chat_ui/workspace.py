from __future__ import annotations

from pathlib import Path

from .errors import ResourceError, WorkspaceError
from .models import WorkspacePaths
from .paths import SharedPathResolver


REQUIRED_RESOURCE_NAMES = (
    "IP_Review_LLM_Instructions.md",
    "base_message.md",
    "07_Interested_Parties_Changes_15576.xlsx",
)


def validate_workspace(value: str | Path, resolver: SharedPathResolver) -> WorkspacePaths:
    selected = resolver.resolve_and_validate(value)
    if selected.name.casefold() != "copilot resources":
        raise WorkspaceError("Select the folder whose final name is exactly 'Copilot resources'.")
    working = selected.parent
    if working.name.casefold() != "working space":
        raise WorkspaceError("'Copilot resources' must be directly inside a folder named 'Working Space'.")
    users = working / "Users"
    if not users.is_dir():
        raise WorkspaceError(f"The required sibling folder 'Users' was not found under {working}.")
    data_root = working.parent
    merged = selected / "Temporary merged pdfs"
    return WorkspacePaths(selected, data_root, working, selected, users, merged)


def validate_runtime_resources(workspace: WorkspacePaths) -> dict[str, Path]:
    missing: list[str] = []
    found: dict[str, Path] = {}
    for name in REQUIRED_RESOURCE_NAMES:
        path = workspace.copilot_resources / name
        if not path.is_file():
            missing.append(str(path))
        else:
            found[name] = path
    if not workspace.merged_pdfs.is_dir():
        missing.append(str(workspace.merged_pdfs))
    if missing:
        raise ResourceError("Required runtime resources are missing:\n- " + "\n- ".join(missing))
    return found
