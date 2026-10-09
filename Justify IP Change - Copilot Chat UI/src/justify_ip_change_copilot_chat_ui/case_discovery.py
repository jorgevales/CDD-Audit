from __future__ import annotations

import re
from pathlib import Path

from .errors import ResourceError
from .models import BatchInfo, CaseRecord, canonical_identifier


CASE_FOLDER_PATTERN = re.compile(r"^Change_(\d+)_Interested_Party_(\d+)$", re.IGNORECASE)


def discover_case_folders(batch: BatchInfo) -> dict[tuple[str, str], Path]:
    """Discover only exact direct case subfolders and reject canonical duplicates."""
    discovered: dict[tuple[str, str], Path] = {}
    for item in batch.path.iterdir():
        if not item.is_dir():
            continue
        match = CASE_FOLDER_PATTERN.fullmatch(item.name)
        if not match:
            continue
        key = canonical_identifier(match.group(1)), match.group(2).casefold()
        if key in discovered:
            raise ResourceError(
                f"Batch {batch.name} contains duplicate case folders for {match.group(1)}/{match.group(2)}."
            )
        discovered[key] = item
    return discovered


def match_batch_cases(
    batch: BatchInfo,
    records: list[CaseRecord],
) -> tuple[list[tuple[CaseRecord, Path]], list[str]]:
    folders = discover_case_folders(batch)
    by_key = {record.canonical_key: record for record in records}
    matched: list[tuple[CaseRecord, Path]] = []
    blocked: list[str] = []
    for key, folder in folders.items():
        change_number = int(key[0])
        if not batch.range_from <= change_number <= batch.range_to:
            blocked.append(
                f"{batch.name} / {folder.name}: change_id is outside the batch's declared numeric range."
            )
            continue
        record = by_key.get(key)
        if record is None:
            blocked.append(f"{batch.name} / {folder.name}: no matching runtime CSV row exists.")
            continue
        matched.append((record, folder))
    matched.sort(key=lambda pair: (int(pair[0].change_id), pair[0].interested_party_id.casefold()))
    return matched, blocked
