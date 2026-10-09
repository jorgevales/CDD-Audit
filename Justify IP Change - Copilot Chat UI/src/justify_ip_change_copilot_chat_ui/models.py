from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class WorkspacePaths:
    selected: Path
    data_root: Path
    working_space: Path
    copilot_resources: Path
    users: Path
    merged_pdfs: Path


@dataclass(frozen=True)
class CaseRecord:
    change_id: str
    interested_party_id: str
    values: Mapping[str, str]

    @property
    def canonical_key(self) -> tuple[str, str]:
        return canonical_identifier(self.change_id), self.interested_party_id.strip().casefold()

    @property
    def folder_name(self) -> str:
        return f"Change_{self.change_id}_Interested_Party_{self.interested_party_id}"


@dataclass(frozen=True)
class BatchInfo:
    path: Path
    range_from: int
    range_to: int
    completed_by: Path | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def sort_key(self) -> tuple[int, int, str]:
        return self.range_from, self.range_to, self.name.casefold()


@dataclass(frozen=True)
class AttachmentPlan:
    paths: tuple[Path, ...]
    source_document_names: tuple[str, ...]
    merged_pdf_names: tuple[str, ...]


@dataclass(frozen=True)
class QueueItem:
    batch: BatchInfo
    case: CaseRecord
    case_folder: Path
    attachments: AttachmentPlan
    prompt: str

    @property
    def key(self) -> tuple[str, str]:
        return self.case.canonical_key


@dataclass
class BatchSummary:
    batch: BatchInfo
    total_cases: int = 0
    successful_cases: int = 0
    review_required_cases: int = 0
    remaining_cases: int = 0
    blocked_cases: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreflightReport:
    selected_batches: tuple[BatchInfo, ...]
    summaries: tuple[BatchSummary, ...]
    queue: tuple[QueueItem, ...]
    blocked: tuple[str, ...]

    @property
    def total_discovered(self) -> int:
        return sum(item.total_cases for item in self.summaries)

    @property
    def successful(self) -> int:
        return sum(item.successful_cases for item in self.summaries)

    @property
    def remaining(self) -> int:
        return len(self.queue)

    @property
    def attachment_count(self) -> int:
        return sum(len(item.attachments.paths) for item in self.queue)


def canonical_identifier(value: str) -> str:
    text = str(value or "").strip()
    if text and text.lstrip("+-").isdigit():
        return str(int(text))
    return text.casefold()


def numeric_identifier(value: str) -> int:
    text = canonical_identifier(value)
    if not text.isdigit() or int(text) < 1:
        raise ValueError(f"Expected a positive numeric change_id, received {value!r}.")
    return int(text)
