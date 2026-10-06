"""Setup field descriptions and non-destructive input validation."""

import os
from pathlib import Path
from .models import DEFAULT_MODEL, MODEL_VALUES

# key, label, kind, guidance
GROUPS = (
    ("Source files", "Select the case folders and the two source lists.", (
        ("project_root", "Working folder", "output_dir", "Folder for the existing case automation workspace."),
        ("source_data_root", "Case source folder", "input_dir", "Existing folder containing the original case documents."),
        ("working_csv", "Working case list", "csv", "Existing CSV with the case details used for review."),
        ("source_copy_csv", "Source-copy list", "csv", "Existing CSV used to prepare each batch of cases."),
    )),
    ("Output folders", "Choose where temporary files and completed results belong.", (
        ("temporary_batch_dir", "Temporary case workspace", "output_dir", "Folder for the selected batch's working copies."),
        ("merged_pdf_dir", "Merged PDFs", "output_dir", "Folder for case PDFs submitted for review."),
        ("analysis_output_dir", "Completed analysis", "output_dir", "Destination used by your completed-analysis file movement process."),
        ("case_size_output_dir", "Case-size reports", "output_dir", "Folder for case-size reports."),
        ("diagnostics_dir", "Diagnostic logs", "output_dir", "Folder for detailed run logs and recovery records."),
    )),
    ("Review & browser", "Select the review instructions and a dedicated Edge profile.", (
        ("instructions_md", "Review instructions", "markdown", "Existing Markdown (.md) file containing the review methodology."),
        ("edge_executable", "Microsoft Edge", "exe", "Optional: choose msedge.exe if Edge cannot be found automatically."),
        ("edge_profile_dir", "Dedicated browser profile", "output_dir", "Separate folder for this user's review session; avoid your everyday Edge profile."),
    )),
    ("Run preferences", "Select the tracking files and the scope of your next run.", (
        ("completed_csv", "Completed-case list", "csv", "Existing CSV of completed IDs used to avoid repeat processing."),
        ("sent_log_csv", "Result log", "output_csv", "CSV file for submission and result tracking; a new file is allowed."),
    )),
)

FIELD_SPECS = {field[0]: field for _, _, group in GROUPS for field in group}


def validate_field(key: str, value: str) -> tuple[bool, str]:
    kind = FIELD_SPECS[key][2]
    if not value.strip():
        return (True, "Automatic detection") if key == "edge_executable" else (False, "Choose a location to continue.")
    path = Path(value.strip()).expanduser()
    try:
        if kind in {"csv", "output_csv", "markdown", "exe"}:
            extension = {"csv": ".csv", "output_csv": ".csv", "markdown": ".md", "exe": ".exe"}[kind]
            if path.suffix.lower() != extension:
                return False, f"Select a {extension} file."
            if key == "edge_executable" and path.name.lower() != "msedge.exe":
                return False, "Select Microsoft Edge's msedge.exe."
            if path.exists() and not path.is_file():
                return False, "This location is a folder. Select a file."
        if kind == "input_dir" and not path.is_dir():
            return False, "This folder is unavailable. Check the shared drive or choose another folder."
        if kind in {"csv", "markdown", "exe"} and not path.is_file():
            return False, "This file is unavailable. Check the shared drive or choose another file."
        if kind in {"output_dir", "output_csv"}:
            if kind == "output_dir" and path.exists() and not path.is_dir():
                return False, "Select a folder, rather than a file."
            parent = path if path.is_dir() else path.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            if not parent.is_dir() or not os.access(parent, os.W_OK):
                return False, "This location is not writable. Choose a folder you can use."
            if path.is_file() and not os.access(path, os.W_OK):
                return False, "This file is not writable. Choose a file you can update."
            return True, "Selected" if path.exists() else "Will be created when needed"
        if not os.access(path, os.R_OK):
            return False, "This location is not readable. Ask support to check access."
    except (OSError, ValueError):
        return False, "This path is invalid or unavailable. Choose another location."
    return True, "Available"


def validate_run(values: dict) -> str:
    try:
        start, batches, cases, tabs = (int(values[key]) for key in
                                      ("start_batch", "batch_count", "cases_to_process", "browser_tabs"))
    except (ValueError, TypeError):
        return "Enter whole numbers for the run size and browser tabs."
    if start < 1 or (start - 1) % 100:
        return "First case ID must start a batch: 1, 101, 201, and so on."
    if not 1 <= batches <= 10:
        return "Choose between 1 and 10 batches."
    if not 1 <= cases <= batches * 100:
        return "Cases to review must be between 1 and the number of selected case IDs."
    if not 1 <= tabs <= 6:
        return "Choose between 1 and 6 browser tabs."
    if values.get("default_model", DEFAULT_MODEL) not in MODEL_VALUES:
        return "Choose an available default model."
    if values["processing_flow"] not in {"1", "2"}:
        return "Choose an available processing flow."
    return ""
