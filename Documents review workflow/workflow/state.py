from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from .files import replace_with_retry


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class RunState:
    run_id: str
    status: str = "created"
    current_stage: str = ""
    completed_stages: list[str] = field(default_factory=list)
    failed_stage: str = ""
    last_message: str = ""
    started_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    finished_at: str = ""

    @classmethod
    def load(cls, path: Path) -> "RunState":
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        self.updated_at = now()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        replace_with_retry(temporary, path)

    def stage_started(self, stage: str, path: Path) -> None:
        self.status = "running"
        self.current_stage = stage
        self.last_message = f"Started {stage}"
        self.save(path)

    def stage_completed(self, stage: str, path: Path) -> None:
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.current_stage = ""
        self.last_message = f"Completed {stage}"
        self.save(path)

    def failed(self, stage: str, message: str, path: Path) -> None:
        self.status = "failed"
        self.failed_stage = stage
        self.current_stage = ""
        self.last_message = message
        self.finished_at = now()
        self.save(path)

    def complete(self, path: Path) -> None:
        self.status = "complete"
        self.current_stage = ""
        self.last_message = "Workflow completed"
        self.finished_at = now()
        self.save(path)
