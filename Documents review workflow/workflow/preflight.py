from __future__ import annotations

import csv
import importlib.util
import os
import shutil
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import APP_DIR, WorkflowConfig


@dataclass(frozen=True)
class Check:
    level: str
    name: str
    detail: str


REQUIRED_COLUMNS = {
    "change_id", "InterestedPartyId", "InterestedPartyCurrentName",
    "Date_of_birth", "Status", "ActionDateTime", "ActionUserId",
    "ActionUserName", "ActionUserTeam", "ChangedSections", "ChangedFields",
    "PreviousValues", "NewValues", "FieldChangeCount",
}


def _csv_columns(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return set(next(csv.reader(handle)))


def _writable_probe(folder: Path) -> tuple[bool, str]:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = Path(tempfile.mkdtemp(prefix="cdd_probe_", dir=folder))
        first = probe / "write.tmp"
        second = probe / "rename.tmp"
        first.write_text("probe", encoding="utf-8")
        os.replace(first, second)
        second.unlink()
        probe.rmdir()
        return True, "write, rename and delete probe passed"
    except OSError as exc:
        return False, str(exc)


def run_preflight(config: WorkflowConfig, browser: bool = True) -> list[Check]:
    checks: list[Check] = []
    refs = APP_DIR / "Initial sanitized reference files"
    required_files = {
        "PDF merger engine": refs / "07_merge_change_folders_to_pdf_v19_delayed_file_progress_sanitized.py",
        "batch preparation engine": refs / "10_prepare_next_ip_batches_long_path_cleanup_sanitized.py",
        "master builder engine": refs / "09_append_ip_analysis_to_master_100_case_batches_sanitized.py",
        "review instructions": config.path("instructions_md"),
        "base message": refs / "resources" / "base_message_sanitized.md",
        "browser engine": refs / "resources" / "implementation_sanitized.py",
    }
    for label, path in required_files.items():
        checks.append(Check("ok" if path.is_file() else "error", label, str(path)))

    for key, label in (("source_data_root", "Source data root"),
                       ("working_csv", "Working CSV"),
                       ("source_copy_csv", "Source-copy CSV"),
                       ("completed_csv", "Completed-ID CSV")):
        path = config.path(key)
        checks.append(Check("ok" if path.exists() else "error", label, str(path)))

    working = config.path("working_csv")
    if working.is_file():
        try:
            missing = sorted(REQUIRED_COLUMNS - _csv_columns(working))
            checks.append(Check("error" if missing else "ok", "Working CSV schema",
                                "Missing: " + ", ".join(missing) if missing else "Required browser columns found"))
        except (OSError, UnicodeError, csv.Error, StopIteration) as exc:
            checks.append(Check("error", "Working CSV schema", str(exc)))

    for key, label in (("temporary_batch_dir", "Temporary workspace"),
                       ("analysis_output_dir", "Analysis output"),
                       ("diagnostics_dir", "Diagnostics"),
                       ("case_size_output_dir", "Case-size output")):
        path = config.path(key)
        ok, detail = _writable_probe(path)
        checks.append(Check("ok" if ok else "error", label, f"{path} — {detail}"))

    for module, distribution in (("fitz", "PyMuPDF"), ("PIL", "Pillow"),
                                 ("reportlab", "ReportLab"), ("docx", "python-docx"),
                                 ("openpyxl", "openpyxl")):
        checks.append(Check("ok" if importlib.util.find_spec(module) else "error",
                            distribution, "available" if importlib.util.find_spec(module) else "not installed"))
    if browser:
        checks.append(Check("ok" if importlib.util.find_spec("playwright") else "error",
                            "Playwright", "available" if importlib.util.find_spec("playwright") else "not installed"))
        edge = Path(config.edge_executable) if config.edge_executable else None
        edge_found = edge if edge and edge.is_file() else next((Path(p) for p in (
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ) if Path(p).is_file()), None)
        checks.append(Check("ok" if edge_found else "error", "Microsoft Edge",
                            str(edge_found) if edge_found else "Executable not found; select it in Setup"))
        with socket.socket() as sock:
            in_use = sock.connect_ex(("127.0.0.1", int(config.edge_debug_port))) == 0
        checks.append(Check("warning" if in_use else "ok", "Edge debugging port",
                            "Already in use; the dedicated Edge session may already be running" if in_use else "available"))

    converter = shutil.which("soffice") or shutil.which("libreoffice")
    office_level = "ok" if os.name == "nt" or converter else "warning"
    checks.append(Check(office_level, "Document conversion",
                        "Windows Office automation and Python converters will be tried" if os.name == "nt" else
                        (str(converter) if converter else "LibreOffice not found; some formats cannot be converted")))
    return checks


def has_errors(checks: list[Check]) -> bool:
    return any(check.level == "error" for check in checks)
