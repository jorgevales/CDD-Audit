from __future__ import annotations

import getpass
import re

from .errors import ApplicationError


def windows_account_name() -> str:
    """Return a filesystem-safe Windows account name without parsing paths."""
    raw = (getpass.getuser() or "").strip()
    if not raw:
        raise ApplicationError("The Windows account name could not be determined.")
    name = raw.rsplit("\\", 1)[-1].rsplit("/", 1)[-1].strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    if not cleaned or cleaned in {".", ".."}:
        raise ApplicationError("The Windows account name is not safe for a user folder.")
    return cleaned
