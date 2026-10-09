from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .attachments import build_attachment_plan
from .case_discovery import match_batch_cases
from .errors import ResourceError
from .logs import LogRecord, REVIEW_REQUIRED, SUCCESS
from .models import BatchInfo, BatchSummary, CaseRecord, PreflightReport, QueueItem
from .prompting import build_case_prompt


def build_preflight(
    batches: Iterable[BatchInfo],
    records: Iterable[CaseRecord],
    latest_log: dict[tuple[str, str], LogRecord],
    *,
    merged_root: Path,
    instructions_path: Path,
    base_message: str,
    retry_review_required: bool = False,
) -> PreflightReport:
    selected = tuple(sorted(dict.fromkeys(batches), key=lambda item: item.sort_key))
    record_list = list(records)
    queue: list[QueueItem] = []
    blocked: list[str] = []
    summaries: list[BatchSummary] = []
    queued_keys: set[tuple[str, str]] = set()
    for batch in selected:
        matched_cases, discovery_errors = match_batch_cases(batch, record_list)
        summary = BatchSummary(batch=batch, total_cases=len(matched_cases) + len(discovery_errors))
        summary.blocked_cases += len(discovery_errors)
        blocked.extend(discovery_errors)
        if batch.completed_by is not None:
            summary.warnings.append(f"Completed output present: {batch.completed_by.name}")
            summaries.append(summary)
            continue
        for record, folder in matched_cases:
            prior = latest_log.get(record.canonical_key)
            if prior and prior.status == SUCCESS:
                summary.successful_cases += 1
                continue
            # Every latest status other than successful remains eligible.  The
            # retry flag is retained for callers from older releases, but no
            # longer gates uncertain/sent outcomes: a later run must include
            # every case that did not finish successfully.
            if prior and prior.status in REVIEW_REQUIRED:
                summary.review_required_cases += 1
            if record.canonical_key in queued_keys:
                summary.warnings.append(f"Duplicate case {record.change_id} was omitted from the continuous queue.")
                continue
            try:
                attachments = build_attachment_plan(record, folder, merged_root, instructions_path)
                prompt = build_case_prompt(base_message, record, attachments)
            except (OSError, ResourceError, ValueError) as exc:
                summary.blocked_cases += 1
                blocked.append(f"{batch.name} / change_id {record.change_id}: {exc}")
                continue
            queued_keys.add(record.canonical_key)
            queue.append(QueueItem(batch, record, folder, attachments, prompt))
            summary.remaining_cases += 1
        if matched_cases and not discovery_errors and summary.successful_cases == len(matched_cases):
            summary.warnings.append(
                "REQUIRES REVIEW: every case is successful in the user log, but the batch-root IPs workbook is absent."
            )
            # Nothing was queued because successes were removed; retain explicit review state.
        summaries.append(summary)
    queue.sort(key=lambda item: (item.batch.sort_key, int(item.case.change_id), item.case.interested_party_id.casefold()))
    return PreflightReport(selected, tuple(summaries), tuple(queue), tuple(blocked))
