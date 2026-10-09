from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket

from .errors import CopilotUIError


def default_edge_profile() -> Path:
    """Use personal synced storage, matching the proven Copilot Local Agent layout."""
    candidates = [os.environ.get(name, "") for name in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer")]
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive\Accounts") as accounts:
                for index in range(32):
                    try:
                        name = winreg.EnumKey(accounts, index)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(accounts, name) as account:
                            value, _ = winreg.QueryValueEx(account, "UserFolder")
                            if isinstance(value, str):
                                candidates.append(value)
                    except OSError:
                        continue
        except OSError:
            pass
    roots = []
    for value in candidates:
        if value:
            root = Path(value).expanduser().resolve()
            if root.is_dir() and root not in roots:
                roots.append(root)
    if not roots:
        raise CopilotUIError("No available OneDrive folder was found for the dedicated Edge profile. Use --profile-dir to select a writable personal folder.")
    machine_key = "vdi-" + hashlib.sha256(socket.gethostname().casefold().encode("utf-8")).hexdigest()[:16]
    return roots[0] / "CDD Audit" / "JustifyIPChangeCopilotChatUI" / "runtime" / "edge-profiles" / machine_key
