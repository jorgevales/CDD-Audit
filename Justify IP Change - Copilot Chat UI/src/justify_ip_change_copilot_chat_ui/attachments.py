from __future__ import annotations

import re
from pathlib import Path

from .errors import ResourceError
from .models import AttachmentPlan, CaseRecord


COPILOT_ATTACHMENT_LIMIT = 20


def _direct_case_files(case_folder: Path) -> list[Path]:
    return sorted(
        (item for item in case_folder.iterdir() if item.is_file() and not item.name.startswith("~$")),
        key=lambda item: (item.name.casefold(), item.name),
    )


def merged_pdf_parts(record: CaseRecord, root: Path) -> list[Path]:
    stem = re.escape(record.folder_name)
    pattern = re.compile(rf"^{stem}_part_(\d+)\.pdf$", re.IGNORECASE)
    matches: list[tuple[int, Path]] = []
    for item in root.iterdir():
        if not item.is_file():
            continue
        match = pattern.fullmatch(item.name)
        if match:
            matches.append((int(match.group(1)), item))
    if not matches:
        exact = [item for item in root.iterdir() if item.is_file() and item.name.casefold() == f"{record.folder_name}.pdf".casefold()]
        if len(exact) == 1:
            return exact
        raise ResourceError(f"No merged PDF matches case {record.change_id}/{record.interested_party_id}.")
    by_number: dict[int, Path] = {}
    for number, path in matches:
        if number in by_number:
            raise ResourceError(f"Ambiguous merged PDF part {number} for case {record.change_id}.")
        by_number[number] = path
    expected = list(range(1, max(by_number) + 1))
    if sorted(by_number) != expected:
        raise ResourceError(
            f"Merged PDF parts for case {record.change_id} must be continuous from part 1; found {sorted(by_number)}."
        )
    return [by_number[number] for number in expected]


def build_attachment_plan(record: CaseRecord, case_folder: Path, merged_root: Path, instructions: Path) -> AttachmentPlan:
    if not case_folder.is_dir():
        raise ResourceError(f"Case folder was not found: {case_folder}")
    sources = _direct_case_files(case_folder)
    if not sources:
        raise ResourceError(f"Case folder contains no direct documents: {case_folder}")
    merged = merged_pdf_parts(record, merged_root)
    mandatory = [instructions, *merged]
    if len(mandatory) > COPILOT_ATTACHMENT_LIMIT:
        raise ResourceError(f"Case {record.change_id} has too many mandatory merged-PDF parts for Copilot's 20-file limit.")
    # The merged PDFs are primary evidence. Direct originals fill remaining slots
    # deterministically as fallback context, matching the sanitized Step 08 policy.
    remaining = COPILOT_ATTACHMENT_LIMIT - len(mandatory)
    chosen_sources = sources[:remaining]
    return AttachmentPlan(
        tuple([*mandatory, *chosen_sources]),
        tuple(path.name for path in sources),
        tuple(path.name for path in merged),
    )
