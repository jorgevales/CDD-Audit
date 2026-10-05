"""Small synthetic fixtures for the portable workflow tests.

The generated records contain identifiers only.  They are deliberately unrelated
to production data and are always written beneath a caller-provided directory.
"""
from __future__ import annotations

import csv
from pathlib import Path


CSV_FIELDS = (
    "change_id", "InterestedPartyId", "InterestedPartyCurrentName", "Date_of_birth",
    "Status", "ActionDateTime", "ActionUserId", "ActionUserName", "ActionUserTeam",
    "ChangedSections", "ChangedFields", "PreviousValues", "NewValues", "FieldChangeCount",
)


def write_case_csv(path: Path, start: int, count: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for change_id in range(start, start + count):
            writer.writerow({
                "change_id": f"{change_id:05d}",
                "InterestedPartyId": f"IP{change_id:05d}",
                "InterestedPartyCurrentName": f"Synthetic Case {change_id:05d}",
                "Date_of_birth": "2000-01-01", "Status": "Synthetic",
                "ActionDateTime": "2026-01-01T00:00:00", "ActionUserId": "SYNTHETIC",
                "ActionUserName": "Synthetic User", "ActionUserTeam": "Test Team",
                "ChangedSections": "[Contact Details]", "ChangedFields": "Telephone",
                "PreviousValues": "0000000000", "NewValues": "0000000001", "FieldChangeCount": "1",
            })
    return path


def write_completed_csv(path: Path, start: int, count: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["change_id"])
        writer.writerows([[f"{change_id:05d}"] for change_id in range(start, start + count)])
    return path


def write_batch_folders(source_root: Path, start: int, count: int = 100) -> Path:
    """Create one compact source batch with a tiny text file per Change ID."""
    end = start + count - 1
    batch = source_root / f"Batch_{start:05d}_to_{end:05d}"
    for change_id in range(start, start + count):
        case = batch / f"Change_{change_id:05d}_Interested_Party_IP{change_id:05d}"
        case.mkdir(parents=True, exist_ok=True)
        (case / "evidence.txt").write_text(
            f"Synthetic evidence for Change {change_id:05d}\n", encoding="utf-8"
        )
    return batch


def write_analysis_workbooks(folder: Path, start: int, count: int) -> list[Path]:
    """Create minimal, readable Copilot-result workbooks."""
    from openpyxl import Workbook

    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for change_id in range(start, start + count):
        path = folder / (
            f"Change_{change_id:05d}_IP_IP{change_id:05d}_documents_analysed.xlsx"
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["change_id", "InterestedPartyId", "potential_error"])
        sheet.append([f"{change_id:05d}", f"IP{change_id:05d}", ""])
        workbook.save(path)
        workbook.close()
        paths.append(path)
    return paths

