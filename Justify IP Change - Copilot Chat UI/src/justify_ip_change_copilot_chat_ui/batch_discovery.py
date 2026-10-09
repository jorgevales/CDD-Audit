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
