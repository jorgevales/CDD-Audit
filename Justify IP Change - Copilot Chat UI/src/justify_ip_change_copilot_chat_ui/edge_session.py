from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
from urllib.parse import urlparse

from .errors import CopilotUIError


def cdp_endpoint(port: int) -> str:
    if not 1024 <= port <= 65535:
        raise ValueError("The Edge debugging port must be between 1024 and 65535.")
    return f"http://127.0.0.1:{port}"


def get_cdp_version(endpoint: str, timeout: float = 0.75) -> dict | None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise CopilotUIError("CDP must use an explicit loopback endpoint.")
    try:
        with urllib.request.urlopen(endpoint + "/json/version", timeout=timeout) as response:
            payload = json.loads(response.read(65536))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    websocket = str(payload.get("webSocketDebuggerUrl", ""))
    browser = str(payload.get("Browser", ""))
    parsed_ws = urlparse(websocket)
    if parsed_ws.scheme != "ws" or parsed_ws.hostname not in {"127.0.0.1", "localhost"} or parsed_ws.port != parsed.port:
        raise CopilotUIError("Edge advertised a debugging address outside the requested loopback port.")
    if "edge" not in browser.casefold():
        raise CopilotUIError("The debugging endpoint does not advertise Microsoft Edge.")
    return payload


def find_edge(explicit: Path | None = None) -> Path:
    if explicit:
        path = explicit.expanduser().resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(f"Configured Microsoft Edge executable was not found: {path}")
    candidates = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("Microsoft Edge was not found. Use --edge-path with the approved msedge.exe path.")


def _profile_argument(command_line: str) -> Path | None:
    match = re.search(r'--user-data-dir(?:=|\s+)(?:"([^"]+)"|(\S+))', command_line, re.IGNORECASE)
    return Path(match.group(1) or match.group(2)) if match else None


def validate_existing_profile(port: int, profile: Path) -> None:
    if os.name != "nt":
        raise CopilotUIError("Existing Edge profile ownership validation is supported on Windows only.")
    script = (
        f"$owner=(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction Stop | "
        "Where-Object {$_.LocalAddress -in @('127.0.0.1','::1','0.0.0.0','::')} | Select-Object -First 1).OwningProcess; "
        "Get-CimInstance Win32_Process -Filter (\"ProcessId = $owner\") | Select-Object Name,CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        info = json.loads(completed.stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CopilotUIError("Cannot prove ownership of the existing Edge debugging profile.") from exc
    line = str(info.get("CommandLine") or "")
    actual = _profile_argument(line)
    if "msedge" not in str(info.get("Name", "")).casefold() or actual is None:
        raise CopilotUIError("The debugging port is not owned by an identifiable Microsoft Edge profile.")
    if os.path.normcase(str(actual.expanduser().resolve())) != os.path.normcase(str(profile.expanduser().resolve())):
        raise CopilotUIError("The debugging port belongs to a different Edge profile.")


class EdgeSession:
    def __init__(self, profile: Path, port: int = 9445, edge_path: Path | None = None) -> None:
        self.profile = profile.expanduser().resolve()
        self.port = port
        self.edge_path = edge_path
        self.endpoint = cdp_endpoint(port)
        self.process: subprocess.Popen | None = None

    def ensure_started(self, timeout: float = 90.0) -> None:
        payload = get_cdp_version(self.endpoint)
        if payload:
            validate_existing_profile(self.port, self.profile)
            return
        self.profile.mkdir(parents=True, exist_ok=True)
        command = [
            str(find_edge(self.edge_path)),
            f"--remote-debugging-port={self.port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://m365.cloud.microsoft/chat",
        ]
        self.process = subprocess.Popen(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = get_cdp_version(self.endpoint, timeout=0.25)
            if payload:
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.15)
        raise CopilotUIError("Edge did not expose its local debugging endpoint before the startup timeout.")

    def close_owned(self) -> None:
        # Keep the visible, signed-in Edge session available for operator inspection.
        # Playwright disconnects without closing an attached browser.
        return
