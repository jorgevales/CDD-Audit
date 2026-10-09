from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
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

    @staticmethod
    def _free_port(preferred: int, excluded: set[int]) -> int:
        candidates = [preferred, preferred + 1, preferred + 2]
        for candidate in candidates:
            if not 1024 <= candidate <= 65535 or candidate in excluded:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind(("127.0.0.1", candidate))
                except OSError:
                    continue
            return candidate
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            candidate = int(probe.getsockname()[1])
        if candidate in excluded:
            raise CopilotUIError("Could not find an unused loopback debugging port for Edge.")
        return candidate

    def _stop_failed_process(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return
        # This process was created by this EdgeSession, so it is safe to stop
        # during recovery. Existing operator-owned Edge processes are never touched.
        try:
            process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _launch_attempt(self, profile: Path, port: int, timeout: float) -> bool:
        self.profile = profile.expanduser().resolve()
        self.port = port
        self.endpoint = cdp_endpoint(port)
        self.profile.mkdir(parents=True, exist_ok=True)
        command = [
            str(find_edge(self.edge_path)),
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://m365.cloud.microsoft/chat",
        ]
        self.process = subprocess.Popen(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                payload = get_cdp_version(self.endpoint, timeout=0.25)
            except CopilotUIError:
                payload = None
            if payload:
                return True
            if self.process.poll() is not None:
                break
            time.sleep(0.15)
        self._stop_failed_process()
        return False

    def ensure_started(self, timeout: float = 90.0) -> None:
        started_at = time.monotonic()
        attempted_ports: set[int] = set()
        try:
            payload = get_cdp_version(self.endpoint)
            if payload:
                validate_existing_profile(self.port, self.profile)
                print("\033[92mEdge startup method: existing validated endpoint\033[0m")
                return
        except CopilotUIError:
            pass

        edge_timeout = max(5.0, timeout / 3.0)
        requested_profile = self.profile
        methods = (
            ("dedicated profile and requested port", requested_profile, self.port),
            ("dedicated profile and alternate port", requested_profile, None),
            ("fresh run profile and alternate port", requested_profile.parent / (requested_profile.name + "-run-" + os.urandom(4).hex()), None),
        )
        for method, profile, requested_port in methods:
            if time.monotonic() - started_at >= timeout:
                break
            port = requested_port if requested_port is not None else self._free_port(self.port, attempted_ports)
            attempted_ports.add(port)
            remaining = max(5.0, min(edge_timeout, timeout - (time.monotonic() - started_at)))
            if self._launch_attempt(profile, port, remaining):
                print(f"\033[92mEdge startup method: {method}\033[0m")
                return
        raise CopilotUIError(
            "Edge did not expose its local debugging endpoint after three bounded startup methods "
            "(existing endpoint, alternate port, and fresh profile)."
        )

    def close_owned(self) -> None:
        # Keep the visible, signed-in Edge session available for operator inspection.
        # Playwright disconnects without closing an attached browser.
        return
