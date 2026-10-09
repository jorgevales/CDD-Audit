from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import time
import uuid

from .errors import ApplicationError, BatchLockedError
from .error_reporting import sanitize_message
from .models import CaseRecord, canonical_identifier


LOG_FILENAME = "07_Copilot_Fully_Sent_Change_IDs_Log_15576.csv"
LOG_FIELDS = (
    "change_id",
    "InterestedPartyId",
    "fully_sent_at_local",
    "run_number",
    "change_id_status",
    "source_batch",
    "attachment_count",
    "run_id",
    "detail",
)
SUCCESS = "successful"
REVIEW_REQUIRED = {"requires_review", "inconclusive_review_needed"}
SUPPORTED = {SUCCESS, "failed", "interrupted", "skipped", "sent", *REVIEW_REQUIRED}


@dataclass(frozen=True)
class LogRecord:
    change_id: str
    interested_party_id: str
    status: str
    batch: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return canonical_identifier(self.change_id), self.interested_party_id.casefold()


class ExclusiveFile:
    """Portable create-exclusive lock carrying non-sensitive holder metadata."""

    def __init__(self, path: Path, payload: dict[str, object]) -> None:
        self.path = path
        self.payload = payload
        self.held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(self.path, flags)
        except FileExistsError as exc:
            try:
                holder = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                holder = {"message": "holder metadata is unreadable"}
            raise BatchLockedError(json.dumps(holder, ensure_ascii=False, sort_keys=True)) from exc
        try:
            os.write(descriptor, (json.dumps(self.payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.held = True

    def release(self) -> None:
        if self.held:
            try:
                self.path.unlink(missing_ok=True)
            finally:
                self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


class BatchLockSet:
    def __init__(self, working_space: Path, batch_names: list[str], user: str, run_id: str) -> None:
        lock_root = working_space / ".justify-ip-change-locks"
        self.locks = [
            ExclusiveFile(
                lock_root / f"{name}.lock",
                {
                    "batch": name,
                    "user": user,
                    "computer": socket.gethostname(),
                    "pid": os.getpid(),
                    "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "run_id": run_id,
                },
            )
            for name in sorted(set(batch_names), key=str.casefold)
        ]

    def acquire(self) -> None:
        existing = [lock for lock in self.locks if lock.path.exists()]
        if existing:
            holder = {"message": "holder metadata is unreadable"}
            try:
                holder = json.loads(existing[0].path.read_text(encoding="utf-8"))
            except Exception:
                pass
            raise BatchLockedError(
                json.dumps(
                    {"batches": [lock.payload["batch"] for lock in existing], "holder": holder},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        acquired: list[ExclusiveFile] = []
        try:
            for lock in self.locks:
                lock.acquire()
                acquired.append(lock)
        except BatchLockedError as exc:
            for lock in reversed(acquired):
                lock.release()
            details = exc.args[0]
            raise BatchLockedError(
                "A selected batch is already being processed. No batch locks were retained by this run. "
                f"Current holder: {details}"
            ) from exc

    def release(self) -> None:
        for lock in reversed(self.locks):
            lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


class CaseLog:
    def __init__(self, path: Path, user: str) -> None:
        self.path = path
        self.lock = ExclusiveFile(
            path.with_name(path.name + ".lock"),
            {"user": user, "computer": socket.gethostname(), "pid": os.getpid()},
        )

    def records(self) -> list[LogRecord]:
        if not self.path.exists() or not self.path.stat().st_size:
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            if "change_id" not in fields:
                raise ApplicationError(f"User log has no change_id column: {self.path}")
            output = []
            for row in reader:
                change_id = (row.get("change_id") or "").strip()
                if not change_id:
                    continue
                status = (row.get("change_id_status") or row.get("status") or "sent").strip().casefold().replace(" ", "_")
                if status not in SUPPORTED:
                    status = "requires_review"
                output.append(LogRecord(change_id, (row.get("InterestedPartyId") or "").strip(), status, (row.get("source_batch") or "").strip()))
            return output

    def latest(self) -> dict[tuple[str, str], LogRecord]:
        result = {}
        for record in self.records():
            result[record.key] = record
        return result

    def append(
        self,
        case: CaseRecord,
        status: str,
        *,
        batch: str,
        attachment_count: int,
        run_id: str,
        run_number: int | None = None,
        detail: str = "",
    ) -> None:
        status = status.strip().casefold().replace(" ", "_")
        if status not in SUPPORTED:
            raise ValueError(f"Unsupported log status: {status}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep diagnostics concise and content-free.
        safe_detail = sanitize_message(" ".join(detail.split()))[:500]
        with self.lock:
            exists = self.path.exists() and self.path.stat().st_size > 0
            fields = list(LOG_FIELDS)
            if exists:
                with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                    old_fields = list(csv.DictReader(handle).fieldnames or [])
                fields = old_fields + [field for field in LOG_FIELDS if field not in old_fields]
                if fields != old_fields:
                    self._upgrade_schema(old_fields, fields)
            with self.path.open("a", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
                if not exists:
                    writer.writeheader()
                entry = {field: "" for field in fields}
                entry.update(
                    {
                        "change_id": case.change_id,
                        "InterestedPartyId": case.interested_party_id,
                        "fully_sent_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "run_number": str(run_number if run_number is not None else self.next_run_number()),
                        "change_id_status": status,
                        "source_batch": batch,
                        "attachment_count": str(attachment_count),
                        "run_id": run_id,
                        "detail": safe_detail,
                    }
                )
                writer.writerow(entry)
                handle.flush()
                os.fsync(handle.fileno())

    def _upgrade_schema(self, old_fields: list[str], fields: list[str]) -> None:
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        temporary = self.path.with_name(self.path.name + f".{os.getpid()}.{time.time_ns()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def next_run_number(self) -> int:
        # Append-only history remains authoritative; run numbers are best-effort metadata.
        if not self.path.exists():
            return 1
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            values = [int(row.get("run_number", "")) for row in csv.DictReader(handle) if (row.get("run_number") or "").isdigit()]
        return max(values, default=0) + 1


def new_run_id() -> str:
    return uuid.uuid4().hex
