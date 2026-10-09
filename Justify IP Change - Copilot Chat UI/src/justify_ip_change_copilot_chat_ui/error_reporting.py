from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import time
import traceback
import uuid

from .models import WorkspacePaths


ERROR_LOG_FOLDER = "Error logs"
_WINDOWS_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n\"']+")
_UNC_OR_LOCAL = re.compile(r"(?i)\b(?:[a-z]:\\|\\\\)[^\s,;]+")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s,;:/]+/)+[^\s,;]+")
_SAFE_FUNCTION = re.compile(r"^_?[A-Za-z][A-Za-z0-9_]{0,79}$")
_DIAGNOSTIC_LISTS = {"attempts", "edge_attempts", "readiness_attempts"}
_DIAGNOSTIC_OBJECTS = {"copilot", "case", "edge", "editor_selector_counts", "_attempt"}
_EDITOR_COUNT_KEYS = {"primary_editor", "testid_editor", "role_textbox", "message_textarea"}
_DIAGNOSTIC_FLAGS = {
    "tab_reused", "editor_visible", "model_picker_visible", "editor_in_frame",
    "login_indicator", "access_denied_indicator", "send_attempted",
    "upload_active",
}
_DIAGNOSTIC_COUNTS = {
    "cdp_connect_attempts", "cdp_context_count", "attachment_count", "elapsed_ms",
    "readiness_elapsed_ms", "readiness_checks", "frame_count", *_EDITOR_COUNT_KEYS,
    "attachment_chips", "attachment_matched", "upload_retry_count",
}
_DIAGNOSTIC_PORTS = {"requested_port", "selected_port", "port"}
_ERROR_TYPES = {
    "AttributeError", "ConnectionError", "CopilotUIError", "Error", "Exception",
    "OSError", "RuntimeError", "TargetClosedError", "TimeoutError", "ValueError",
}
_EDGE_FAILURES = {
    "none", "endpoint_unavailable", "local endpoint rejected its Edge identity or address",
    "Edge process exited without a local debugging endpoint",
    "Edge did not open a local debugging endpoint within the attempt limit",
    "dedicated profile already in use", "requested local port already in use",
}
_DIAGNOSTIC_ENUMS = {
    "phase": {
        "not_started", "edge_startup", "playwright_start", "cdp_connect", "profile_ownership",
        "copilot_navigation", "copilot_readiness", "model_selection", "ready", "fresh_chat",
        "attachment_upload", "composer_fill", "send_confirmation", "response_capture",
    },
    "method": {
        "existing_endpoint", "dedicated profile and requested port", "dedicated profile and alternate port",
        "fresh run profile and alternate port", "retained_tab", "new_tab", "new_tab_navigation_retry",
        "sign_in_completed",
    },
    "readiness_method": {"retained_tab", "new_tab", "new_tab_navigation_retry", "sign_in_completed"},
    "result": {
        "ready", "validated", "rejected", "absent", "policy_blocked", "failed", "exception",
        "composer_visible", "not_ready", "draft_present", "navigation_timeout", "navigation_error", "auth_required",
    },
    "reason": _EDGE_FAILURES | _ERROR_TYPES,
    "last_failure": _EDGE_FAILURES,
    "last_cdp_error_type": _ERROR_TYPES,
    "last_navigation_error_type": _ERROR_TYPES,
    "last_readiness_error_type": _ERROR_TYPES,
    "page_category": {"copilot", "login", "other"},
    "document_state": {"loading", "interactive", "complete", "unknown"},
    "navigation_outcome": {"success", "auth", "forbidden", "timeout", "error", "no_response"},
}
_DIAGNOSTIC_KEYS = (
    _DIAGNOSTIC_LISTS | _DIAGNOSTIC_OBJECTS | _DIAGNOSTIC_FLAGS | _DIAGNOSTIC_COUNTS
    | _DIAGNOSTIC_PORTS | set(_DIAGNOSTIC_ENUMS)
)
_APP_SOURCE_FILES = {
    "application.py", "attachments.py", "batch_discovery.py", "case_discovery.py", "cli.py",
    "config.py", "copilot_ui.py", "edge_session.py", "error_reporting.py", "errors.py",
    "identity.py", "logs.py", "models.py", "paths.py", "profile_storage.py",
    "progress.py", "prompting.py", "queue_builder.py", "resources.py", "workspace.py",
}
_STAGES = {"edge_startup", "copilot_startup", "copilot_shutdown", "case_processing", "workspace_remember", "batch_lock", "cli_failure", "operator_interrupt"}


def pseudonym(value: str, *, namespace: str) -> str:
    digest = hashlib.sha256((namespace + "\0" + value).encode("utf-8", "replace")).hexdigest()
    return f"{namespace}-{digest[:16]}"


def sanitize_message(value: object) -> str:
    text = str(value or "")
    text = _WINDOWS_PATH.sub("<path>", text)
    text = _UNC_OR_LOCAL.sub("<path>", text)
    text = _POSIX_PATH.sub("<path>", text)
    text = re.sub(r"(?i)\b(?:https?|file)://[^\s]+", "<url>", text)
    text = re.sub(r"\b[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+\b", "<account>", text)
    return text[:2000]


def _safe_diagnostics(value: object, depth: int = 0, key: str | None = None) -> object:
    """Retain only bounded, fixed-schema telemetry, never page or exception content."""
    if depth > 5:
        return None
    if isinstance(value, dict):
        if key is not None and key not in _DIAGNOSTIC_OBJECTS:
            return None
        allowed = _EDITOR_COUNT_KEYS if key == "editor_selector_counts" else _DIAGNOSTIC_KEYS
        return {
            item_key: _safe_diagnostics(item, depth + 1, item_key)
            for item_key, item in list(value.items())[:24]
            if isinstance(item_key, str) and item_key in allowed
        }
    if isinstance(value, (list, tuple)):
        if key not in _DIAGNOSTIC_LISTS:
            return None
        return [
            _safe_diagnostics(item, depth + 1, "_attempt")
            for item in value[:12]
            if isinstance(item, dict)
        ]
    if value is None:
        return value
    if isinstance(value, bool):
        return value if key in _DIAGNOSTIC_FLAGS else None
    if isinstance(value, int):
        if key in _DIAGNOSTIC_PORTS and 1 <= value <= 65535:
            return value
        if key in _DIAGNOSTIC_COUNTS and 0 <= value <= 1_000_000:
            return value
        return None
    if isinstance(value, str):
        return value if value in _DIAGNOSTIC_ENUMS.get(key, ()) else "<redacted>"
    return None


def _safe_frames(exc: BaseException) -> list[dict[str, object]]:
    frames = traceback.extract_tb(exc.__traceback__)
    safe = []
    for frame in frames[-12:]:
        is_app = "justify_ip_change_copilot_chat_ui" in frame.filename
        source = Path(frame.filename).name
        safe.append({
            "module": "app" if is_app else "dependency",
            "source_file": source if is_app and source in _APP_SOURCE_FILES else "<redacted>",
            "function": frame.name if is_app and _SAFE_FUNCTION.fullmatch(frame.name) else "<redacted>",
            "line": frame.lineno,
        })
    return safe


def write_error_report(
    workspace: WorkspacePaths | None,
    exc: BaseException,
    *,
    stage: str,
    action: str = "Start",
    batch: str | None = None,
    case_key: tuple[str, str] | None = None,
    run_id: str | None = None,
) -> Path | None:
    if workspace is None:
        return None
    target = workspace.working_space / ERROR_LOG_FOLDER
    try:
        target.mkdir(parents=True, exist_ok=True)
        account = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown-user"
        device = os.environ.get("COMPUTERNAME") or socket.gethostname() or "unknown-device"
        safe_message = "Failure details are in the structured stage, diagnostics, and error type; raw exception text is omitted."
        diagnostic_stage = getattr(exc, "diagnostic_stage", stage)
        if diagnostic_stage not in _STAGES:
            diagnostic_stage = stage
        safe_frames = _safe_frames(exc)
        error_signature = json.dumps(
            {"stage": diagnostic_stage, "type": type(exc).__name__, "frames": safe_frames[-3:]},
            sort_keys=True,
        )
        report = {
            "schema": "cdd-audit-error-report-v1",
            "report_id": str(uuid.uuid4()),
            "occurred_at_utc": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "stage": diagnostic_stage,
            "error_type": type(exc).__name__,
            "error_ref": pseudonym(error_signature, namespace="error"),
            "message": safe_message,
            "user_ref": pseudonym(account, namespace="user"),
            "device_ref": pseudonym(device, namespace="device"),
            "workspace_ref": pseudonym(str(workspace.selected), namespace="workspace"),
            "batch_ref": pseudonym(batch, namespace="batch") if batch else None,
            "case_ref": pseudonym("/".join(case_key), namespace="case") if case_key else None,
            "run_ref": pseudonym(run_id, namespace="run") if run_id else None,
            "python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
            "process_id": os.getpid(),
            "free_space_bytes": _free_space_snapshot(workspace),
            "diagnostics": _safe_diagnostics(getattr(exc, "diagnostics", {})),
            "frames": safe_frames,
            "cause_types": [type(item).__name__ for item in (exc.__cause__, exc.__context__) if item is not None],
            "os_error": {"errno": getattr(exc, "errno", None), "winerror": getattr(exc, "winerror", None)},
            "support_note": "Correlate occurred_at_utc with user_ref and device_ref; raw paths and identifiers are intentionally omitted.",
        }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        path = target / f"error_{stamp}_{report['report_id'][:8]}.json"
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        for attempt in range(2):
            temporary = target / f".{path.name}.{os.getpid()}.{attempt}.tmp"
            try:
                temporary.write_text(payload, encoding="utf-8")
                os.replace(temporary, path)
                saved = json.loads(path.read_text(encoding="utf-8"))
                if all(key in saved for key in ("stage", "error_type", "diagnostics", "frames", "user_ref", "device_ref")):
                    return path
                path.unlink(missing_ok=True)
            except (OSError, ValueError):
                temporary.unlink(missing_ok=True)
                if attempt == 0:
                    _prune_old_reports(target)
        return None
    except OSError:
        return None


def _free_space_snapshot(workspace: WorkspacePaths) -> dict[str, int | None]:
    values: dict[str, int | None] = {}
    for label, candidate in (
        ("workspace_volume", workspace.working_space),
        ("local_temp_volume", Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")),
        ("local_appdata_volume", Path(os.environ.get("LOCALAPPDATA") or Path.home())),
    ):
        try:
            values[label] = int(shutil.disk_usage(candidate).free)
        except OSError:
            values[label] = None
    return values


def _prune_old_reports(target: Path, *, keep_days: int = 30, keep_count: int = 200) -> None:
    cutoff = time.time() - keep_days * 86400
    candidates = []
    for entry in target.glob("error_*.json"):
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
            elif entry.is_file():
                candidates.append(entry)
        except OSError:
            continue
    for entry in sorted(candidates, key=lambda item: item.stat().st_mtime)[:-keep_count]:
        try:
            entry.unlink()
        except OSError:
            pass
