from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any
from .files import replace_with_retry
from .models import DEFAULT_MODEL, MODEL_OPTIONS


APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CDDReviewWorkflow"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class WorkflowConfig:
    project_root: str = ""
    source_data_root: str = ""
    temporary_batch_dir: str = ""
    merged_pdf_dir: str = ""
    working_csv: str = ""
    source_copy_csv: str = ""
    completed_csv: str = ""
    sent_log_csv: str = ""
    instructions_md: str = ""
    analysis_output_dir: str = ""
    case_size_output_dir: str = ""
    diagnostics_dir: str = ""
    edge_executable: str = ""
    edge_profile_dir: str = ""
    edge_debug_port: int = 9223
    start_batch: int = 1
    batch_count: int = 1
    cases_to_process: int = 100
    browser_tabs: int = 6
    model_policy: str = "1"
    default_model: str = DEFAULT_MODEL
    processing_flow: str = "1"
    diagnostic_mode: bool = False

    @classmethod
    def defaults(cls) -> "WorkflowConfig":
        home_root = Path.home() / "CopilotCaseAutomation"
        temp = home_root / "IPs_Documents_Analysis" / "Temporary_100_batch_IP_files"
        ready = home_root / "Copilot outputs" / "ready_for_AI"
        data = home_root / "data"
        refs = APP_DIR / "Initial sanitized reference files"
        return cls(
            project_root=str(home_root),
            source_data_root=str(home_root / "source_data" / "data"),
            temporary_batch_dir=str(temp),
            merged_pdf_dir=str(temp / "Merged_PDFs"),
            working_csv=str(ready / "07_Interested_Parties_Last_Changes_name_and_birth_15576.csv"),
            source_copy_csv=str(ready / "07_Interested_Parties_Last_Changes_name_and_birth_15576 copy.csv"),
            completed_csv=str(data / "completed_change_ids.csv"),
            sent_log_csv=str(data / "fully_sent_change_ids_log.csv"),
            instructions_md=str(refs / "IP_Review_LLM_Instructions_3_Changes_Merged.md"),
            analysis_output_dir=str(home_root / "IPs_Documents_Analysis" / "IPs_Completed_Analysis"),
            case_size_output_dir=str(data / "outputs"),
            diagnostics_dir=str(APP_DIR / "diagnostics"),
            edge_profile_dir=str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CopilotTabAutomation" / "EdgeProfile"),
        )

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "WorkflowConfig":
        defaults = asdict(cls.defaults())
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            allowed = {item.name for item in fields(cls)}
            defaults.update({key: value for key, value in loaded.items() if key in allowed})
        return cls(**defaults)

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        replace_with_retry(temporary, path)

    def path(self, name: str) -> Path:
        value = getattr(self, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name.replace('_', ' ').title()} has not been configured.")
        return Path(value).expanduser().resolve()

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        profile = result.get("edge_profile_dir", "")
        if profile:
            result["edge_profile_dir"] = "<current-user Edge profile>"
        return result
