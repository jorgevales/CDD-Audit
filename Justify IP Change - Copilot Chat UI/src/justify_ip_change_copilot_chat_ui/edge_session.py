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
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(endpoint + "/json/version", timeout=max(0.05, min(timeout, 0.75))) as response:
            payload = json.loads(response.read(65536))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    websocket = str(payload.get("webSocketDebuggerUrl", ""))
    browser = str(payload.get("Browser", ""))
    parsed_ws = urlparse(websocket)
    if parsed_ws.scheme != "ws" or parsed_ws.hostname not in {"127.0.0.1", "localhost"} or parsed_ws.port != parsed.port:
        raise CopilotUIError("Edge advertised a debugging address outside the requested loopback port.")
    # Edge identifies itself as Edg/<version> in /json/version. The previous
    # "edge" check rejected every valid Edge response and exhausted all retries.
    if "edg/" not in browser.casefold():
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


def remote_debugging_blocked() -> bool:
    if os.name != "nt":
        return False
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Policies\Microsoft\Edge") as key:
                value, _ = winreg.QueryValueEx(key, "RemoteDebuggingAllowed")
                if value == 0:
                    return True
        except OSError:
            continue
    return False


def _profile_argument(command_line: str) -> Path | None:
    # Windows quotes the entire argument when the profile path contains spaces.
    match = re.search(
        r'"--user-data-dir=([^"]+)"|--user-data-dir(?:=|\s+)(?:"([^"]+)"|(\S+))',
        command_line,
        re.IGNORECASE,
    )
    return Path(next(value for value in match.groups() if value)) if match else None


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
        self.last_failure = ""

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

    @staticmethod
    def _profile_in_use(profile: Path) -> bool:
        if os.name != "nt" or not profile.is_dir():
            return False
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
            "Where-Object { $_.CommandLine -match '--user-data-dir' } | "
            "Select-Object CommandLine | ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=8, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            records = json.loads(completed.stdout) if completed.stdout.strip() else []
        except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
            return False
        values = records if isinstance(records, list) else [records]
        for record in values:
            command_line = str(record.get("CommandLine", "")) if isinstance(record, dict) else ""
            actual = _profile_argument(command_line)
            if actual is not None and os.path.normcase(str(actual.expanduser().resolve())) == os.path.normcase(str(profile.resolve())):
                return True
        return False

    @staticmethod
    def _port_in_use(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            return False

    def _launch_attempt(self, profile: Path, port: int, timeout: float) -> bool:
        self.profile = profile.expanduser().resolve()
        self.port = port
        self.endpoint = cdp_endpoint(port)
        if self._profile_in_use(self.profile):
            self.last_failure = "dedicated profile already in use"
            self._stop_failed_process()
            return False
        if self._port_in_use(port):
            self.last_failure = "requested local port already in use"
            self._stop_failed_process()
            return False
        self.profile.mkdir(parents=True, exist_ok=True)
        probe = self.profile / (".write-check-" + os.urandom(4).hex())
        try:
            with probe.open("xb") as handle:
                handle.write(b"ok")
        except OSError as exc:
            raise CopilotUIError("The dedicated Edge profile is not writable. Choose a writable personal OneDrive folder with --profile-dir.") from exc
        finally:
            probe.unlink(missing_ok=True)
        command = [
            str(find_edge(self.edge_path)),
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            "about:blank",
        ]
        options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            options["start_new_session"] = True
        try:
            self.process = subprocess.Popen(command, **options)
        except OSError as exc:
            raise CopilotUIError("Microsoft Edge could not be started. Check the Edge installation and local execution policy.") from exc
        deadline = time.monotonic() + timeout
        launched_process_exited = False
        endpoint_rejected = False
        while time.monotonic() < deadline:
            try:
                payload = get_cdp_version(self.endpoint, timeout=0.25)
            except CopilotUIError:
                endpoint_rejected = True
                payload = None
            if payload:
                return True
            if self.process.poll() is not None:
                # Edge commonly hands the visible window to a child process;
                # keep the full bounded handshake window for that child.
                launched_process_exited = True
            time.sleep(0.10 if not launched_process_exited else 0.15)
        self.last_failure = (
            "local endpoint rejected its Edge identity or address" if endpoint_rejected
            else "Edge process exited without a local debugging endpoint" if launched_process_exited
            else "Edge did not open a local debugging endpoint within the attempt limit"
        )
        self._stop_failed_process()
        return False

    def ensure_started(self, timeout: float = 90.0) -> None:
        started_at = time.monotonic()
        attempted_ports: set[int] = set()
        if remote_debugging_blocked():
            raise CopilotUIError("Microsoft Edge policy disables remote debugging. Ask IT to enable it for this application.")
        try:
            payload = get_cdp_version(self.endpoint)
            if payload:
                validate_existing_profile(self.port, self.profile)
                print("\033[92mEdge startup method: existing validated endpoint\033[0m")
                return
        except CopilotUIError:
            pass

        requested_profile = self.profile
        methods = (
            ("dedicated profile and requested port", requested_profile, self.port, 12.0),
            ("dedicated profile and alternate port", requested_profile, None, 8.0),
            ("fresh run profile and alternate port", requested_profile.parent / (requested_profile.name + "-run-" + os.urandom(4).hex()), None, 30.0),
        )
        failures = []
        for method, profile, requested_port, budget in methods:
            if time.monotonic() - started_at >= timeout:
                break
            port = requested_port if requested_port is not None else self._free_port(self.port, attempted_ports)
            attempted_ports.add(port)
            remaining = max(0.1, min(budget, timeout - (time.monotonic() - started_at)))
            if self._launch_attempt(profile, port, remaining):
                print(f"\033[92mEdge startup method: {method}\033[0m")
                return
            failures.append(f"{method}: {self.last_failure or 'endpoint unavailable'}")
        raise CopilotUIError(
            "Edge did not expose its local debugging endpoint. " + "; ".join(failures)
        )

    def close_owned(self) -> None:
        # Keep the visible, signed-in Edge session available for operator inspection.
        # Playwright disconnects without closing an attached browser.
        return
