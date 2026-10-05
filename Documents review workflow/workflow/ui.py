from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from dataclasses import fields
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .config import CONFIG_PATH, WorkflowConfig
from .orchestrator import WorkflowOrchestrator
from .preflight import Check, has_errors, run_preflight


PATH_FIELDS = [
    ("project_root", "Project root", "dir"),
    ("source_data_root", "Batch source root", "dir"),
    ("temporary_batch_dir", "Temporary case workspace", "dir"),
    ("merged_pdf_dir", "Merged PDF folder", "dir"),
    ("working_csv", "Working/source-cases CSV", "file"),
    ("source_copy_csv", "Source-copy CSV", "file"),
    ("completed_csv", "Completed-ID CSV", "file"),
    ("sent_log_csv", "Sent/result log", "file"),
    ("instructions_md", "Review instructions", "file"),
    ("analysis_output_dir", "Completed analysis folder", "dir"),
    ("case_size_output_dir", "Case-size output folder", "dir"),
    ("diagnostics_dir", "Diagnostics folder", "dir"),
    ("edge_executable", "Microsoft Edge executable", "file"),
    ("edge_profile_dir", "Dedicated Edge profile", "dir"),
]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"CDD Document Review Workflow {__version__}")
        self.geometry("1120x780")
        self.minsize(900, 650)
        self.config_data = WorkflowConfig.load()
        self.vars: dict[str, tk.Variable] = {}
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.orchestrator: WorkflowOrchestrator | None = None
        self.worker: threading.Thread | None = None
        self._build()
        self.after(100, self._drain_events)

    def _build(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.setup_tab = ttk.Frame(notebook)
        self.preflight_tab = ttk.Frame(notebook)
        self.run_tab = ttk.Frame(notebook)
        notebook.add(self.setup_tab, text="1  Setup")
        notebook.add(self.preflight_tab, text="2  Preflight")
        notebook.add(self.run_tab, text="3  Run")
        self._build_setup()
        self._build_preflight()
        self._build_run()

    def _build_setup(self) -> None:
        outer = ttk.Frame(self.setup_tab)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas)
        form.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        ttk.Label(form, text="Select locations for this Windows user. No source-code editing is required.",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(5, 12))
        for row, (key, label, kind) in enumerate(PATH_FIELDS, 1):
            value = getattr(self.config_data, key)
            var = tk.StringVar(value=value)
            self.vars[key] = var
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            ttk.Entry(form, textvariable=var, width=92).grid(row=row, column=1, sticky="ew", pady=3)
            ttk.Button(form, text="Browse…", command=lambda k=key, t=kind: self._browse(k, t)).grid(row=row, column=2, padx=6)
        form.columnconfigure(1, weight=1)
        buttons = ttk.Frame(self.setup_tab)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Save setup", command=self._save).pack(side="right", padx=5)
        ttk.Button(buttons, text="Restore sensible defaults", command=self._defaults).pack(side="right", padx=5)

    def _build_preflight(self) -> None:
        ttk.Label(self.preflight_tab, text="Preflight checks required files, folders, permissions, dependencies and Edge.",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 5))
        self.checks = ttk.Treeview(self.preflight_tab, columns=("status", "check", "detail"), show="headings")
        self.checks.heading("status", text="Status")
        self.checks.heading("check", text="Check")
        self.checks.heading("detail", text="Detail")
        self.checks.column("status", width=90, anchor="center")
        self.checks.column("check", width=190)
        self.checks.column("detail", width=720)
        self.checks.pack(fill="both", expand=True, pady=5)
        ttk.Button(self.preflight_tab, text="Run preflight", command=self._preflight).pack(anchor="e", pady=8)

    def _build_run(self) -> None:
        controls = ttk.LabelFrame(self.run_tab, text="Run selection")
        controls.pack(fill="x", pady=5)
        specs = [
            ("start_batch", "First batch ID", tk.IntVar, 12),
            ("batch_count", "100-ID batches", tk.IntVar, 8),
            ("cases_to_process", "Cases this run", tk.IntVar, 8),
            ("browser_tabs", "Browser tabs", tk.IntVar, 8),
        ]
        for col, (key, label, var_type, width) in enumerate(specs):
            var = var_type(value=getattr(self.config_data, key))
            self.vars[key] = var
            ttk.Label(controls, text=label).grid(row=0, column=col, padx=6, pady=(6, 1), sticky="w")
            ttk.Entry(controls, textvariable=var, width=width).grid(row=1, column=col, padx=6, pady=(1, 8), sticky="w")
        self.vars["model_policy"] = tk.StringVar(value=self.config_data.model_policy)
        self.vars["processing_flow"] = tk.StringVar(value=self.config_data.processing_flow)
        ttk.Label(controls, text="Model policy").grid(row=0, column=4, padx=6, pady=(6, 1), sticky="w")
        ttk.Combobox(controls, textvariable=self.vars["model_policy"], state="readonly", width=31,
                     values=("1", "2", "3", "N")).grid(row=1, column=4, padx=6, pady=(1, 8))
        ttk.Label(controls, text="Processing flow").grid(row=0, column=5, padx=6, pady=(6, 1), sticky="w")
        ttk.Combobox(controls, textvariable=self.vars["processing_flow"], state="readonly", width=16,
                     values=("1", "2")).grid(row=1, column=5, padx=6, pady=(1, 8))
        self.cleanup_var = tk.BooleanVar(value=True)
        self.diagnostic_var = tk.BooleanVar(value=self.config_data.diagnostic_mode)
        ttk.Checkbutton(controls, text="Remove out-of-range temporary cases/PDFs", variable=self.cleanup_var).grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=5)
        ttk.Checkbutton(controls, text="Diagnostic output", variable=self.diagnostic_var).grid(row=2, column=3, columnspan=2, sticky="w", padx=6, pady=5)

        action = ttk.Frame(self.run_tab)
        action.pack(fill="x", pady=5)
        self.start_button = ttk.Button(action, text="Start primary workflow", command=self._start_primary)
        self.start_button.pack(side="left", padx=4)
        self.master_button = ttk.Button(action, text="Run separate master stage", command=self._start_master)
        self.master_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(action, text="Stop after safe stage", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(action, text="Open output folder", command=lambda: self._open("analysis_output_dir")).pack(side="right", padx=4)
        ttk.Button(action, text="Open diagnostics", command=lambda: self._open("diagnostics_dir")).pack(side="right", padx=4)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.run_tab, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=4)
        self.log = tk.Text(self.run_tab, wrap="word", height=27, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _browse(self, key: str, kind: str) -> None:
        current = self.vars[key].get()
        selected = filedialog.askdirectory(initialdir=current or None) if kind == "dir" else filedialog.askopenfilename(initialdir=str(Path(current).parent) if current else None)
        if selected:
            self.vars[key].set(selected)

    def _collect(self) -> WorkflowConfig:
        data = WorkflowConfig.load().__dict__
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
            config.save()
            self.config_data = config
            self.status_var.set(f"Setup saved to {CONFIG_PATH}")
            return True
        except (ValueError, OSError) as exc:
            messagebox.showerror("Setup could not be saved", str(exc), parent=self)
            return False

    def _defaults(self) -> None:
        defaults = WorkflowConfig.defaults()
        for key, var in self.vars.items():
            if hasattr(defaults, key):
                var.set(getattr(defaults, key))

    def _preflight(self) -> list[Check]:
        if not self._save():
            return []
        self.checks.delete(*self.checks.get_children())
        try:
            checks = run_preflight(self.config_data)
        except Exception as exc:
            checks = [Check("error", "Preflight", str(exc))]
        for check in checks:
            self.checks.insert("", "end", values=(check.level.upper(), check.name, check.detail))
        errors = sum(item.level == "error" for item in checks)
        warnings = sum(item.level == "warning" for item in checks)
        self.status_var.set(f"Preflight: {errors} error(s), {warnings} warning(s)")
        return checks

    def _office_acknowledgement(self) -> bool:
        return messagebox.askokcancel(
            "Automated Office conversion",
            "The PDF stage may open isolated Word, Excel or PowerPoint processes and may encounter files already open or locked.\n\n"
            "Save your work before continuing and avoid editing source documents while conversion runs.\n\n"
            "Press Enter or select OK to continue.", parent=self, default=messagebox.OK,
        )

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
        value = simpledialog.askstring(
            "Confirm temporary cleanup",
            f"Recognised cleanup targets: {len(targets)}\n\n{preview}\n\n"
            "The active batch range and unrelated files remain protected.\n\nType DELETE to allow this cleanup:",
            parent=self,
        )
        return value == "DELETE"

    def _start_primary(self) -> None:
        checks = self._preflight()
        if not checks or has_errors(checks):
            messagebox.showerror("Preflight failed", "Resolve the ERROR items before starting.", parent=self)
            return
        if (self.config_data.start_batch < 1 or (self.config_data.start_batch - 1) % 100 or
                not 1 <= self.config_data.batch_count <= 10 or not 1 <= self.config_data.browser_tabs <= 6):
            messagebox.showerror("Invalid run selection", "First batch ID must start a 100-ID batch; batches must be 1–10 and tabs 1–6.", parent=self)
            return
        if not self._office_acknowledgement() or not self._confirm_cleanup():
            self.status_var.set("Cancelled before any processing")
            return
        self._launch("primary")

    def _start_master(self) -> None:
        if not self._save():
            return
        output = self.config_data.path("analysis_output_dir")
        existing = sorted(output.glob("IPs_Completed_Analysis_Master_*.xlsx")) if output.is_dir() else []
        note = "Only complete, readable 100-ID batches will be created. Missing workbooks will be listed."
        if existing:
            note += f"\n\n{len(existing)} existing batch master file(s) may be atomically replaced after revalidation."
        if not messagebox.askokcancel("Run master stage", note, parent=self):
            return
        self._launch("master")

    def _launch(self, mode: str) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.orchestrator = WorkflowOrchestrator(self.config_data, self._emit)
        target = (lambda: self.orchestrator.run_primary(self.cleanup_var.get())) if mode == "primary" else self.orchestrator.run_master
        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.master_button.configure(state="disabled")
        self.stop_button.configure(state="normal" if mode == "primary" else "disabled")

    def _stop(self) -> None:
        if self.orchestrator:
            self.orchestrator.request_stop()

    def _emit(self, kind: str, message: str) -> None:
        self.events.put((kind, message))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind in {"stage", "progress", "complete", "error", "warning"}:
                    self.status_var.set(message)
                self.log.configure(state="normal")
                self.log.insert("end", message + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
                if kind in {"complete", "error"}:
                    self.start_button.configure(state="normal")
                    self.master_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _open(self, key: str) -> None:
        try:
            path = self._collect().path(key)
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror("Could not open folder", str(exc), parent=self)


def run_app() -> None:
    App().mainloop()
