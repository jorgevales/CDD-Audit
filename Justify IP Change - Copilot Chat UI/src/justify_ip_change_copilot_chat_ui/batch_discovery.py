from __future__ import annotations

import re
from pathlib import Path

from .models import BatchInfo


BATCH_PATTERN = re.compile(r"^Batch_(\d+)_to_(\d+)$", re.IGNORECASE)
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".xlsb"}


def completed_output_file(batch_root: Path) -> Path | None:
    """Return the first direct IPs Excel output; never inspect case subfolders."""
    candidates = []
    for item in batch_root.iterdir():
        if not item.is_file() or item.name.startswith("~$"):
            continue
        if item.stem.casefold().startswith("ips") and item.suffix.casefold() in EXCEL_EXTENSIONS:
            candidates.append(item)
    return sorted(candidates, key=lambda item: (item.name.casefold(), item.name))[0] if candidates else None


def discover_batches(data_root: Path) -> list[BatchInfo]:
    batches: list[BatchInfo] = []
    for item in data_root.iterdir():
        if not item.is_dir():
            continue
        match = BATCH_PATTERN.fullmatch(item.name)
        if not match:
            continue
        low, high = int(match.group(1)), int(match.group(2))
        if low < 1 or high < low:
            continue
        batches.append(BatchInfo(item, low, high, completed_output_file(item)))
    return sorted(batches, key=lambda batch: batch.sort_key)


def batch_range_groups(batches: list[BatchInfo] | tuple[BatchInfo, ...] | list[str] | tuple[str, ...]) -> list[tuple[int, int]]:
    """Collapse adjacent Batch_* folders into numeric inclusive ranges.

    Adjacent means the next folder starts exactly one number after the
    previous folder ends.  The function accepts BatchInfo objects or batch
    folder names so lock/error reporting can use it without filesystem reads.
    """
    ranges: list[tuple[int, int]] = []
    for item in batches:
        if isinstance(item, BatchInfo):
            low, high = item.range_from, item.range_to
        else:
            match = BATCH_PATTERN.fullmatch(str(item).strip())
            if not match:
                continue
            low, high = int(match.group(1)), int(match.group(2))
        if low < 1 or high < low:
            continue
        if ranges and low <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], high))
        else:
            ranges.append((low, high))
    return ranges


def describe_batch_ranges(
    batches: list[BatchInfo] | tuple[BatchInfo, ...] | list[str] | tuple[str, ...],
    *,
    verb: str,
    reason: str | None = None,
) -> str:
    """Return one compact operator-facing message for one or more batches."""
    groups = batch_range_groups(batches)
    if not groups:
        return ""
    ranges = ", ".join(f"{low} to {high}" for low, high in groups)
    prefix = "Batch" if len(groups) == 1 and groups[0][0] == groups[0][1] else "Batches"
    suffix = f" {reason}" if reason else ""
    return f"{prefix} {ranges} {verb}{suffix}."
