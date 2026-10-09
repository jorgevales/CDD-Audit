from __future__ import annotations

import ntpath
import os
from pathlib import Path
from typing import Protocol

from .errors import WorkspaceError


WINDOWS_SLASH = "\\"


def normalise_windows_path_text(value: str | Path) -> str:
    text = str(value).strip().strip('"')
    if not text:
        raise WorkspaceError("No workspace path was supplied.")
    return ntpath.normpath(text.replace("/", WINDOWS_SLASH))


def strip_extended_prefix(value: str) -> str:
    extended = "\\\\?\\"
    unc = "\\\\?\\UNC\\"
    if value.casefold().startswith(unc.casefold()):
        return "\\\\" + value[len(unc):]
    if value.startswith(extended):
        return value[len(extended):]
    return value


class SharedPathResolver(Protocol):
    def resolve_and_validate(self, value: str | Path) -> Path: ...


class WindowsSDriveResolver:
    """Accept S: or the live UNC identity currently mapped to S:, never a guessed share."""

    def __init__(self, drive: str = "S:") -> None:
        self.drive = drive.rstrip("\\/")

    def _final(self, value: str) -> str:
        try:
            resolved = os.path.realpath(value, strict=True)
        except (OSError, ValueError) as exc:
            raise WorkspaceError(f"The selected path does not exist or cannot be resolved: {value}") from exc
        return ntpath.normcase(ntpath.normpath(strip_extended_prefix(resolved))).rstrip(WINDOWS_SLASH)

    def mapped_root(self) -> str:
        root = self._final(self.drive + WINDOWS_SLASH)
        if not root.startswith("\\\\"):
            raise WorkspaceError(
                f"{self.drive} is not currently mapped to a redirected UNC share. Connect the shared drive and try again."
            )
        return root

    def resolve_and_validate(self, value: str | Path) -> Path:
        text = normalise_windows_path_text(value)
        drive = ntpath.splitdrive(text)[0].casefold()
        root = self.mapped_root()
        resolved = self._final(text)
        if drive == self.drive.casefold():
            return Path(resolved)
        if not text.startswith("\\\\"):
            raise WorkspaceError(f"Select a folder on {self.drive} or its currently mapped UNC share.")
        if resolved != root and not resolved.startswith(root + WINDOWS_SLASH):
            raise WorkspaceError(f"The UNC path is not part of the share currently mapped to {self.drive}.")
        return Path(resolved)


class LocalSimulationResolver:
    """Test-only resolver proving path logic without a real mapped drive."""

    def __init__(self, allowed_root: Path) -> None:
        self.allowed_root = allowed_root.resolve()

    def resolve_and_validate(self, value: str | Path) -> Path:
        path = Path(value).expanduser().resolve()
        try:
            path.relative_to(self.allowed_root)
        except ValueError as exc:
            raise WorkspaceError("The simulated workspace is outside its allowed root.") from exc
        if not path.exists():
            raise WorkspaceError(f"The selected path does not exist: {path}")
        return path
