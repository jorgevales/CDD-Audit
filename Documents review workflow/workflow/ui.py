from __future__ import annotations

import os
import queue
import re
import threading
import tkinter as tk
from dataclasses import asdict, fields
from pathlib import Path
from tkinter import filedialog, ttk

from . import __version__
from .config import CONFIG_PATH, WorkflowConfig
from .orchestrator import WorkflowOrchestrator
from .preflight import Check, has_errors, run_preflight
from .design import COLORS, apply_theme, compact_confirm
from .fonts import release_ui_fonts
from .setup_form import GROUPS, FIELD_SPECS, validate_field, validate_run
from .wizard_view import WizardView


class App(WizardView, tk.Tk):
    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        super().__init__()
        self.title(f"CDD Audit Remediation {__version__}")
        self.geometry("1080x820")
        self.minsize(900, 700)
        apply_theme(self)
        self.config_path = config_path
        load_warning = self.font_warning
        try:
            self.config_data = WorkflowConfig.load(config_path)
        except (OSError, ValueError, TypeError, AttributeError):
            self.config_data = WorkflowConfig.defaults()
            load_warning = "Saved settings could not be read. Review the defaults before continuing. " + self.font_warning
        self.vars: dict[str, tk.Variable] = {
            field.name: tk.StringVar(value=getattr(self.config_data, field.name))
            for field in fields(WorkflowConfig) if field.name != "diagnostic_mode"
        }
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.orchestrator: WorkflowOrchestrator | None = None
        self.worker: threading.Thread | None = None
        self.step = 0
        self.ready_config = None
        self.checking = False
        self.running = False
        self.field_labels = {}
        self.touched_fields = set()
        self.edit_controls = []
        self.validation_job = None
        self.feedback_var = tk.StringVar(value=load_warning)
        self._build()
        for key, variable in self.vars.items():
            variable.trace_add("write", lambda *args, k=key: self._changed(k))
        self.diagnostic_var.trace_add("write", self._changed)
        self._refresh_fields()
        self._show_step(0)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain_events)

    def _summary(self) -> str:
        try:
            start = int(self.vars["start_batch"].get())
            end = start + int(self.vars["batch_count"].get()) * 100 - 1
            return (f"Case IDs {start:,} - {end:,}  |  {self.vars['cases_to_process'].get()} cases to review  |  "
                    f"{self.vars['browser_tabs'].get()} browser tabs\n"
                    f"{self.model_names.get(self.vars['model_policy'].get(), 'Choose review models')}")
        except ValueError:
            return "Complete run preferences to see the summary."

    def _show_check_detail(self, _) -> None:
        selected = self.checks.selection()
        if selected:
            self.check_detail.configure(text=self.checks.item(selected[0], "values")[2])

    def _navigate(self, index: int) -> None:
        if self.running or self.checking or self.transitioning or not 0 <= index < 6:
            return
        if index > self.step:
            for group in range(min(index, 4)):
                if not self._validate_group(group):
                    self._show_step(group, self.problem_part, animate=True)
                    return
                self.completed_steps.add(group)
            if index == 5 and self.ready_config is None:
                self.feedback_var.set("Check setup before running.")
                self._show_step(4, animate=True)
                return
        if index == 5:
            self.master_mode = False
        self._show_step(index, animate=True)

    def _continue(self) -> None:
        if self.running or self.checking or self.transitioning:
            return
        if self.step == 5:
            self._navigate(4)
        elif self.step < 4:
            key = self.step_parts[self.step][self.part]
            if key in FIELD_SPECS:
                self.touched_fields.add(key)
                self._refresh_fields()
                valid, detail = validate_field(key, self.vars[key].get())
                if not valid:
                    self.feedback_var.set(f"{FIELD_SPECS[key][1]}: {detail}")
                    return
            elif key in {"scope", "models", "options"}:
                detail = validate_run({name: variable.get() for name, variable in self.vars.items()})
                if detail:
                    self.feedback_var.set(detail)
                    return
            if self._save():
                if self.part + 1 < len(self.step_parts[self.step]):
                    self._show_step(self.step, self.part + 1, animate=True)
                elif self._validate_group(self.step):
                    self.completed_steps.add(self.step)
                    self._navigate(self.step + 1)
        else:
            self._navigate(5)

    def _open_master(self) -> None:
        if self.running or self.checking or self.transitioning:
            return
        self.master_mode = True
        self._show_step(5, animate=True)
        self.status_var.set("Completed analyses")
        self.feedback_var.set("Master workbooks use your completed analyses.")

    def _changed(self, *_) -> None:
        if _ and _[0] in FIELD_SPECS:
            self.touched_fields.add(_[0])
        self.ready_config = None
        self.start_button.configure(state="disabled")
        self.readiness_label.configure(text="Not checked", foreground=COLORS["muted"])
        self._set_check_rows([])
        self.check_button.configure(style="Primary.TButton")
        if self.step == 4:
            self.next_button.configure(state="disabled")
        self.completed_steps.discard(4)
        if _ and _[0] in FIELD_SPECS:
            for index, (_, _, group) in enumerate(GROUPS):
                if any(field[0] == _[0] for field in group):
                    self.completed_steps.discard(index)
        elif _ and _[0] in {"start_batch", "batch_count", "cases_to_process", "browser_tabs", "model_policy", "processing_flow"}:
            self.completed_steps.discard(3)
        self.stepper.complete = self.completed_steps.copy()
        self.stepper.draw()
        self.feedback_var.set("")
        if self.validation_job:
            self.after_cancel(self.validation_job)
        self.validation_job = self.after(250, self._refresh_fields)

    def _refresh_fields(self) -> None:
        self.validation_job = None
        for key, label in self.field_labels.items():
            ok, detail = validate_field(key, self.vars[key].get())
            if not ok and key not in self.touched_fields:
                label.configure(text="Optional" if key == "edge_executable" else "Required", foreground=COLORS["muted"])
            else:
                label.configure(text="Ready" if ok and detail in {"Selected", "Available"} else detail,
                                foreground=COLORS["success"] if ok else COLORS["error"])
        message = validate_run({key: var.get() for key, var in self.vars.items()})
        self.range_var.set(message or self._summary().split("\n")[0])

    def _validate_group(self, index: int) -> bool:
        self.touched_fields.update(field[0] for field in GROUPS[index][2])
        self._refresh_fields()
        for part, (key, label, _, _) in enumerate(GROUPS[index][2]):
            ok, detail = validate_field(key, self.vars[key].get())
            if not ok:
                self.feedback_var.set(f"{label}: {detail}")
                self.problem_part = part
                return False
        if index == 3:
            message = validate_run({key: var.get() for key, var in self.vars.items()})
            if message:
                self.feedback_var.set(message)
                self.problem_part = len(GROUPS[3][2])
                return False
        return True

    def _browse(self, key: str, kind: str) -> None:
        current = self.vars[key].get()
        path = Path(current).expanduser() if current else None
        initial = path if path and path.is_dir() else path.parent if path else None
        options = {"parent": self, "title": FIELD_SPECS[key][1]}
        if initial and initial.is_dir():
            options["initialdir"] = str(initial)
        if "dir" in kind:
            selected = filedialog.askdirectory(**options, mustexist=kind == "input_dir")
        else:
            extension = ".csv" if "csv" in kind else ".md" if kind == "markdown" else ".exe"
            options["filetypes"] = [(extension.upper() + " files", "*" + extension)]
            selected = (filedialog.asksaveasfilename(**options, defaultextension=extension) if kind == "output_csv"
                        else filedialog.askopenfilename(**options))
        if selected:
            self.vars[key].set(selected)

    def _collect(self) -> WorkflowConfig:
        data = asdict(self.config_data)
        for field in fields(WorkflowConfig):
            if field.name in self.vars:
                data[field.name] = self.vars[field.name].get()
        data["diagnostic_mode"] = bool(self.diagnostic_var.get()) if hasattr(self, "diagnostic_var") else False
        for key in ("edge_debug_port", "start_batch", "batch_count", "cases_to_process", "browser_tabs"):
            data[key] = int(data[key])
        return WorkflowConfig(**data)

    def _save(self) -> bool:
        try:
            config = self._collect()
            config.save(self.config_path)
            self.config_data = config
            self.feedback_var.set("Saved")
            return True
        except (ValueError, OSError, tk.TclError):
            self.feedback_var.set("Settings could not be saved. Check the numeric values and access to your settings folder.")
            return False

    def _defaults(self) -> None:
        if self.running or self.checking:
            return
        if not compact_confirm(self, "Restore defaults?", "Your current selections will be replaced.", action="Restore"):
            return
        defaults = WorkflowConfig.defaults()
        for key, var in self.vars.items():
            if hasattr(defaults, key):
                var.set(getattr(defaults, key))
        self.diagnostic_var.set(defaults.diagnostic_mode)

    def _preflight(self) -> None:
        if self.running or self.checking or self.transitioning:
            return
        for index in range(4):
            if not self._validate_group(index):
                self._show_step(index, self.problem_part)
                return
        if not self._save():
            return
        self._show_step(4)
        self.checks.delete(*self.checks.get_children())
        self.ready_config = None
        self.checking = True
        self._set_busy(True)
        self.readiness_label.configure(text="Checking...", foreground=COLORS["blue"])
        self.feedback_var.set("")
        self.check_progress.configure(mode="indeterminate")
        self.check_progress.start(12)
        config = self._collect()
        def check():
            try:
                result = run_preflight(config)
            except Exception:
                self._log_exception("Setup check failed")
                result = [Check("error", "Setup check", "The check could not finish. Review your locations or ask support to check access.")]
            self.events.put(("checks", (config, result)))
        threading.Thread(target=check, daemon=True).start()

    def _finish_checks(self, config, checks) -> None:
        self.checking = False
        self.check_progress.stop()
        self.check_progress.configure(mode="determinate", value=0)
        self._set_busy(False)
        labels = {"ok": "Ready", "warning": "Review", "error": "Needs attention"}
        for check in checks:
            self.checks.insert("", "end", values=(labels.get(check.level, "Not checked"), check.name, check.detail), tags=(check.level,))
        errors = sum(item.level == "error" for item in checks)
        warnings = sum(item.level == "warning" for item in checks)
        ready = bool(checks) and not has_errors(checks) and asdict(config) == asdict(self._collect())
        self.ready_config = asdict(config) if ready else None
        self.readiness_label.configure(text="Ready to run" if ready else f"{errors} requirements need attention",
                                       foreground=COLORS["success"] if ready else COLORS["error"])
        self.feedback_var.set(f"{warnings} warnings to review" if ready and warnings else "" if ready else "Open check details to resolve issues.")
        self.status_var.set("Ready to run" if ready else "Setup needs attention")
        self.start_button.configure(state="normal" if ready else "disabled")
        self.check_button.configure(style="TButton" if ready else "Primary.TButton")
        self._set_check_rows(checks)
        if ready:
            self.completed_steps.update(range(5))
        self._show_step(4)

    def _office_acknowledgement(self) -> bool:
        return compact_confirm(self, "Save your Office work", "Conversion may open Office apps. Avoid editing source documents during the run.")

    def _confirm_cleanup(self) -> bool:
        if not self.cleanup_var.get():
            return True
        start = int(self.config_data.start_batch)
        end = start + int(self.config_data.batch_count) * 100 - 1
        temp = self.config_data.path("temporary_batch_dir")
        merged = self.config_data.path("merged_pdf_dir")
        targets: list[Path] = []
        change_re = re.compile(r"^Change_(\d+)(?:_|$)", re.I)
        pdf_re = re.compile(r"^Change_(\d+)(?:_|$).*\.pdf$", re.I)
        if temp.is_dir():
            for path in temp.iterdir():
                match = change_re.match(path.name) if path.is_dir() else None
                if match and not start <= int(match.group(1)) <= end:
                    targets.append(path)
        if merged.is_dir():
            for path in merged.iterdir():
                match = pdf_re.match(path.name) if path.is_file() else None
                if match and not start <= int(match.group(1)) <= end:
                    targets.append(path)
        preview = "\n".join(str(path) for path in targets[:15]) or "No recognised out-of-range targets currently found."
        if len(targets) > 15:
            preview += f"\n… and {len(targets) - 15} more"
        return compact_confirm(self, "Confirm cleanup", f"{len(targets)} recognised temporary items outside your batch. Active cases and unrelated files stay protected.",
                               action="Allow cleanup", details=preview, required_text="DELETE")

    def _start_primary(self) -> None:
        if self.running or self.checking or self.transitioning:
            return
        if self.ready_config is None or self.ready_config != asdict(self._collect()):
            self.feedback_var.set("Check setup successfully before starting a document review.")
            self._show_step(4)
            return
        if not self._save():
            return
        if not self._office_acknowledgement() or not self._confirm_cleanup():
            self.status_var.set("Cancelled before any processing")
            return
        self._launch("primary")

    def _start_master(self) -> None:
        if self.running or self.checking or self.transitioning or not self._save():
            return
        ok, detail = validate_field("analysis_output_dir", self.vars["analysis_output_dir"].get())
        if not ok:
            self.feedback_var.set(f"Completed analysis: {detail}")
            return
        output = self.config_data.path("analysis_output_dir")
        existing = sorted(output.glob("IPs_Completed_Analysis_Master_*.xlsx")) if output.is_dir() else []
        note = "Only complete, readable 100-case batches are built. Missing files are listed."
        if existing:
            note += f"\n\n{len(existing)} existing masters may be replaced after checking."
        if not compact_confirm(self, "Build master workbooks?", note, action="Build"):
            return
        self._launch("master")

    def _launch(self, mode: str) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            self.orchestrator = WorkflowOrchestrator(self.config_data, self._emit)
        except Exception:
            self._log_exception("Run could not start")
            self.status_var.set("The run could not start. Check access to the diagnostic folder.")
            return
        cleanup = self.cleanup_var.get()
        target = (lambda: self.orchestrator.run_primary(cleanup)) if mode == "primary" else self.orchestrator.run_master
        self.worker = threading.Thread(target=target, daemon=True)
        self.running = True
        self._set_busy(True)
        self.run_progress.configure(mode="indeterminate")
        self.run_progress.start(12)
        self.status_var.set("Starting document review..." if mode == "primary" else "Building master workbooks...")
        self.feedback_var.set("Run in progress. Keep this window and the dedicated browser session open.")
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.master_button.configure(state="disabled")
        self.stop_button.configure(state="normal" if mode == "primary" else "disabled")

    def _stop(self) -> None:
        if self.orchestrator:
            self.orchestrator.request_stop()
            self.stop_button.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        for control in self.edit_controls:
            control.configure(state="disabled" if busy else "readonly" if isinstance(control, ttk.Combobox) else "normal")
        self.stepper.enabled = not busy
        for control in [self.master_nav, self.back_button, self.next_button, self.save_button, self.check_button, self.master_button]:
            control.configure(state="disabled" if busy else "normal")
        if not busy:
            self._show_step(self.step)

    def _emit(self, kind: str, message: str) -> None:
        self.events.put((kind, message))

    def _drain_events(self) -> None:
        try:
            for _ in range(150):
                kind, message = self.events.get_nowait()
                if kind == "checks":
                    self._finish_checks(*message)
                    continue
                if kind == "stage":
                    names = {"prepare": "Preparing cases", "merge": "Creating PDFs", "copilot": "Reviewing in Copilot", "master": "Building master workbooks"}
                    self.status_var.set(names.get(message, message))
                elif kind == "error":
                    self.ready_config = None
                    self.completed_steps.discard(4)
                    self.status_var.set("The run needs attention. Open logs for details, then check setup before retrying.")
                elif kind in {"progress", "complete", "warning"}:
                    self.status_var.set(message if len(message) <= 140 else message[:137] + "...")
                if kind != "log" or self.diagnostic_var.get():
                    self.activity_lines.append(self.status_var.get() if kind in {"error", "stage"} else message)
                if kind == "complete":
                    self.completed_steps.add(5)
                    self.feedback_var.set("Finished. Open results to view the completed output.")
        except queue.Empty:
            pass
        if self.running and self.worker and not self.worker.is_alive() and self.events.empty():
            self.running = False
            self.run_progress.stop()
            self.run_progress.configure(mode="determinate", value=0)
            self._set_busy(False)
            self.start_button.configure(state="normal" if self.ready_config is not None else "disabled")
            self.stop_button.configure(state="disabled")
            if self.orchestrator and self.orchestrator.state.status == "cancelled_safe":
                self.feedback_var.set("Stopped safely. Adjust settings or start another run.")
            elif self.orchestrator and self.orchestrator.state.status == "complete":
                self.feedback_var.set("Finished. Open results to view the completed output.")
            elif self.ready_config is None:
                self.feedback_var.set("The run did not finish. Open logs and check setup before retrying.")
        self.after(100, self._drain_events)

    def _log_exception(self, message: str) -> None:
        import traceback
        try:
            folder = self.config_path.parent / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "interface.log").open("a", encoding="utf-8") as handle:
                handle.write(message + "\n" + traceback.format_exc() + "\n")
        except OSError:
            pass

    def _open(self, key: str) -> None:
        try:
            path = self._collect().path(key)
            if not path.is_dir():
                compact_confirm(self, "Folder not available", "Check setup or complete a run first.", action="Close", cancel_label=None)
                return
            os.startfile(path)
        except (OSError, ValueError):
            compact_confirm(self, "Folder unavailable", "Check the shared drive and your folder access.", action="Close", cancel_label=None)

    def _close(self) -> None:
        if self.running:
            compact_confirm(self, "Review in progress", "Request a stop, then wait for the current stage to finish.", action="Close", cancel_label=None)
        elif self.checking:
            compact_confirm(self, "Checking setup", "Wait for the check to finish before closing.", action="Close", cancel_label=None)
        else:
            self.destroy()

    def destroy(self) -> None:
        self.fade.cancel()
        for callback in self.tk.call("after", "info"):
            self.after_cancel(callback)
        super().destroy()
        release_ui_fonts(self)


def run_app(config_path: Path = CONFIG_PATH) -> None:
    App(config_path).mainloop()
