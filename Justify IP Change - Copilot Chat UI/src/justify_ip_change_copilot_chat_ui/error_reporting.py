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
        safe_message = sanitize_message(exc).replace(account, "<user>").replace(device, "<device>")
        safe_traceback = sanitize_message("".join(traceback.format_exception(exc))).replace(account, "<user>").replace(device, "<device>")
        report = {
            "schema": "cdd-audit-error-report-v1",
            "report_id": str(uuid.uuid4()),
            "occurred_at_utc": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "stage": stage,
            "error_type": type(exc).__name__,
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
            "traceback": safe_traceback[:4000],
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
                return path
            except OSError:
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
