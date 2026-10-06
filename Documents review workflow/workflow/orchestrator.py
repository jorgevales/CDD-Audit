from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import APP_DIR, WorkflowConfig
from .models import validate_model
from .notify import notify
from .state import RunState


REFS = APP_DIR / "Initial sanitized reference files"
PYTHON = str(Path(sys.executable).with_name("python.exe")) if Path(sys.executable).name.lower() == "pythonw.exe" else sys.executable
WAKE_DETAIL = re.compile(r"WAKE CYCLE|VISIBLY VISITED|NEXT WAKE|wake (?:round|cycle)", re.I)
PROGRESS_SIGNAL = re.compile(r"Remaining|queued|completed|successful|failed|active tabs", re.I)


class WorkflowOrchestrator:
    def __init__(self, config: WorkflowConfig, emit: Callable[[str, str], None]):
        self.config = config
        self.emit = emit
        self.stop_after_stage = threading.Event()
        self.process: subprocess.Popen[str] | None = None
        token = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = config.path("diagnostics_dir") / "runs" / token
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.run_dir / "run_config.json"
        self.config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
        self.state_path = self.run_dir / "run_state.json"
        self.state = RunState(token)
        self.state.save(self.state_path)

    def request_stop(self) -> None:
        self.stop_after_stage.set()
        self.emit("warning", "Stop requested. The workflow will stop after the current safe stage.")

    def _run(self, stage: str, command: list[str], env: dict[str, str] | None = None,
             answers: list[str] | None = None) -> int:
        self.state.stage_started(stage, self.state_path)
        self.emit("stage", stage)
        log_path = self.run_dir / f"{stage}.log"
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            self.process = subprocess.Popen(
                command, cwd=str(APP_DIR), env=merged_env,
                stdin=subprocess.PIPE if answers is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if answers is not None and self.process.stdin:
                self.process.stdin.write("\n".join(answers) + "\n")
                self.process.stdin.flush()
            assert self.process.stdout is not None
            last_progress = ""
            for line in self.process.stdout:
                clean = line.rstrip()
                log.write(line)
                log.flush()
                if self.config.diagnostic_mode or not WAKE_DETAIL.search(clean):
                    self.emit("log", clean)
                elif PROGRESS_SIGNAL.search(clean) and clean != last_progress:
                    last_progress = clean
                    self.emit("progress", clean)
            code = self.process.wait()
            self.process = None
        if code:
            message = f"{stage} failed with exit code {code}. See {log_path}"
            self.state.failed(stage, message, self.state_path)
            raise RuntimeError(message)
        self.state.stage_completed(stage, self.state_path)
        return code

    def run_primary(self, cleanup: bool) -> None:
        try:
            prepare = [PYTHON, "-u", "-m", "workflow.engine_runner", "prepare",
                       "--config", str(self.config_path)]
            if cleanup:
                prepare.append("--cleanup")
            self._run("prepare", prepare)
            if self.stop_after_stage.is_set():
                self._stopped()
                return

            start = int(self.config.start_batch)
            end = start + int(self.config.batch_count) * 100 - 1
            merge_script = REFS / "07_merge_change_folders_to_pdf_v19_delayed_file_progress_sanitized.py"
            merge_env = {
                "CDD_MASTER_FOLDER": str(self.config.path("temporary_batch_dir")),
                "CDD_MERGED_PDF_FOLDER": str(self.config.path("merged_pdf_dir")),
            }
            self._run("merge", [PYTHON, "-u", str(merge_script), "--from-id", str(start),
                                "--to-id", str(end), "--yes"], env=merge_env)
            status_file = self.config.path("merged_pdf_dir") / f"merge_status_{start}_{end}.json"
            if not status_file.is_file():
                raise RuntimeError(f"Merge completed without its required status file: {status_file}")
            if self.stop_after_stage.is_set():
                self._stopped()
                return

            browser_env = {
                "COPILOT_BASE_MESSAGE_PATH": str(REFS / "resources" / "base_message_sanitized.md"),
                "CDD_DIAGNOSTICS_DIR": str(self.config.path("diagnostics_dir")),
                "CDD_PROJECT_ROOT": str(REFS),
                "PYTHONPATH": str(REFS) + os.pathsep + os.environ.get("PYTHONPATH", ""),
            }
            browser = [
                PYTHON, str(REFS / "08_open_copilot_dynamic_case_size_batches_v25_useful_upto_V12_sanitized.py"),
                "--csv-path", str(self.config.path("working_csv")),
                "--completed-path", str(self.config.path("completed_csv")),
                "--log-path", str(self.config.path("sent_log_csv")),
                "--instructions-path", str(self.config.path("instructions_md")),
                "--case-files-root", str(self.config.path("temporary_batch_dir")),
                "--merged-pdfs-root", str(self.config.path("merged_pdf_dir")),
                "--case-size-output-root", str(self.config.path("case_size_output_dir")),
                "--profile-dir", str(self.config.path("edge_profile_dir")),
                "--port", str(self.config.edge_debug_port),
                "--tabs", str(self.config.browser_tabs),
                "--max-tabs", str(self.config.browser_tabs),
                "--cases", str(self.config.cases_to_process),
                "--default-model", validate_model(self.config.default_model),
            ]
            if self.config.edge_executable:
                browser += ["--edge-path", str(self.config.path("edge_executable"))]
            # A global model is supplied explicitly; only send/flow prompts remain.
            answers = ["", self.config.processing_flow]
            self._run("copilot", browser, env=browser_env, answers=answers)
            self.state.complete(self.state_path)
            self.emit("complete", "Primary workflow completed. Copilot results were detected and logged.")
            notify("CDD review complete", "The primary document-review workflow has finished.")
        except Exception as exc:
            if self.state.status != "failed":
                self.state.failed(self.state.current_stage or "validation", str(exc), self.state_path)
            self.emit("error", str(exc))
            notify("CDD review needs attention", str(exc)[:180])

    def run_master(self) -> None:
        try:
            command = [PYTHON, "-u", "-m", "workflow.engine_runner", "master",
                       "--config", str(self.config_path)]
            self._run("master", command)
            self.state.complete(self.state_path)
            self.emit("complete", "Master stage finished. Only complete 100-ID batches were created.")
            notify("CDD master stage complete", "Master workbook assessment and creation finished.")
        except Exception as exc:
            if self.state.status != "failed":
                self.state.failed("master", str(exc), self.state_path)
            self.emit("error", str(exc))
            notify("CDD master stage needs attention", str(exc)[:180])

    def _stopped(self) -> None:
        self.state.status = "cancelled_safe"
        self.state.last_message = "Stopped after a safe stage boundary"
        self.state.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.state.save(self.state_path)
        self.emit("warning", self.state.last_message)
