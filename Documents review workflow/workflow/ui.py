from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from dataclasses import asdict, fields
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .config import CONFIG_PATH, WorkflowConfig
from .orchestrator import WorkflowOrchestrator
from .preflight import Check, has_errors, run_preflight
from .design import COLORS, apply_theme
from .setup_form import GROUPS, FIELD_SPECS, validate_field, validate_run


class App(tk.Tk):
    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        super().__init__()
        self.title(f"CDD Audit | Document Review {__version__}")
        self.geometry("1180x820")
        self.minsize(980, 700)
        apply_theme(self)
        self.config_path = config_path
        load_warning = ""
        try:
            self.config_data = WorkflowConfig.load(config_path)
        except (OSError, ValueError, TypeError, AttributeError):
            self.config_data = WorkflowConfig.defaults()
            load_warning = "Saved settings could not be read. Review the defaults before continuing."
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
        self.feedback_var = tk.StringVar(value=load_warning or "Settings are saved for this Windows user.")
        self._build()
        for key, variable in self.vars.items():
            variable.trace_add("write", lambda *args, k=key: self._changed(k))
        self.diagnostic_var.trace_add("write", self._changed)
        self._refresh_fields()
        self._show_step(0)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain_events)

    def _build(self) -> None:
        rail = tk.Frame(self, bg=COLORS["rail"], width=224)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Label(rail, text="CDD Audit", bg=COLORS["rail"], fg="white",
                 font=("Segoe UI", 24, "bold"), anchor="w").pack(fill="x", padx=24, pady=(30, 2))
        tk.Label(rail, text="DOCUMENT REVIEW", bg=COLORS["rail"], fg=COLORS["rail_text"],
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=24)
        tk.Frame(rail, height=1, bg="#365991").pack(fill="x", padx=24, pady=28)
        self.step_names = [group[0] for group in GROUPS] + ["Check setup", "Run workflow"]
        self.nav_buttons = []
        for index, name in enumerate(self.step_names):
            button = tk.Button(rail, text=f"{index + 1:02d}   {name}", anchor="w",
                               font=("Segoe UI", 10),
                               bg=COLORS["rail"], fg=COLORS["rail_text"], relief="flat", bd=0,
                               activebackground=COLORS["rail_active"], activeforeground="white",
                               padx=16, pady=14, cursor="hand2", highlightthickness=2,
                               highlightbackground=COLORS["rail"], highlightcolor="white",
                               command=lambda i=index: self._navigate(i))
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons.append(button)
        tk.Label(rail, text=f"WINDOWS WORKSPACE\nVersion {__version__}", justify="left",
                 anchor="w", bg=COLORS["rail"], fg=COLORS["rail_text"],
                 font=("Segoe UI", 9)).pack(side="bottom", fill="x", padx=24, pady=24)
        self.master_nav = tk.Button(rail, text="Master workbooks", anchor="w", font=("Segoe UI", 10),
                                    bg=COLORS["rail"], fg=COLORS["rail_text"], relief="flat", bd=0,
                                    activebackground=COLORS["rail_active"], activeforeground="white",
                                    padx=16, pady=12, cursor="hand2", command=self._open_master)
        self.master_nav.pack(side="bottom", fill="x", padx=10)
        workspace = ttk.Frame(self)
        workspace.pack(side="left", fill="both", expand=True)
        header = ttk.Frame(workspace, padding=(30, 24, 30, 20))
        header.pack(fill="x")
        self.step_label = ttk.Label(header, style="Small.TLabel")
        self.step_label.pack(anchor="w", pady=(0, 7))
        self.title_label = ttk.Label(header, style="Title.TLabel")
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(header, style="Muted.TLabel", wraplength=650)
        self.subtitle_label.pack(anchor="w", pady=(7, 0))
        ttk.Separator(workspace).pack(fill="x")
        self.body = ttk.Frame(workspace, padding=(30, 16, 30, 12))
        self.body.pack(fill="both", expand=True)
        self.pages = [ttk.Frame(self.body) for _ in range(6)]
        self.preflight_tab, self.run_tab = self.pages[4:]
        self._build_setup()
        self._build_preflight()
        self._build_run()
        ttk.Separator(workspace).pack(fill="x")
        footer = ttk.Frame(workspace, padding=(30, 14, 30, 18))
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, textvariable=self.feedback_var, style="Small.TLabel", wraplength=650).pack(anchor="w", pady=(0, 12))
        self.back_button = ttk.Button(footer, text="Back", command=lambda: self._navigate(self.step - 1))
        self.back_button.pack(side="left")
        self.save_button = ttk.Button(footer, text="Save progress", command=self._save)
        self.save_button.pack(side="left", padx=8)
        self.next_button = ttk.Button(footer, text="Continue", style="Primary.TButton", command=self._continue)
        self.next_button.pack(side="right")
        # Reserve header and footer space before allowing the page body to expand.
        self.body.pack_forget()
        self.body.pack(fill="both", expand=True)

    def _build_setup(self) -> None:
        self.forms = []
        for index, (_, _, group) in enumerate(GROUPS):
            page = self.pages[index]
            canvas = tk.Canvas(page, bg=COLORS["paper"], highlightthickness=0)
            scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            form = ttk.Frame(canvas, padding=(0, 0, 12, 12))
            window = canvas.create_window((0, 0), window=form, anchor="nw")
            form.bind("<Configure>", lambda _, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>", lambda e, c=canvas, w=window: c.itemconfigure(w, width=e.width))
            canvas.configure(yscrollcommand=scrollbar.set)
            self.forms.append((form, canvas))
            form.columnconfigure(0, weight=1)
            for row, (key, label, kind, guidance) in enumerate(group):
                block = ttk.Frame(form)
                block.grid(row=row, column=0, sticky="ew", pady=(0, 18))
                block.columnconfigure(0, weight=1)
                ttk.Label(block, text=label, style="Field.TLabel").grid(row=0, column=0, sticky="w")
                ttk.Label(block, text="Optional" if key == "edge_executable" else "Required",
                          style="Small.TLabel").grid(row=0, column=1, sticky="e")
                entry = ttk.Entry(block, textvariable=self.vars[key])
                entry.grid(row=1, column=0, sticky="ew", pady=(7, 4))
                button = ttk.Button(block, text="Choose folder" if "dir" in kind else "Choose file",
                                    command=lambda k=key, t=kind: self._browse(k, t))
                button.grid(row=1, column=1, padx=(10, 0), pady=(7, 4))
                self.edit_controls.extend([entry, button])
                for control in (entry, button):
                    control.bind("<FocusIn>", lambda _, c=canvas, b=block: self._reveal_field(c, b))
                helper = ttk.Label(block, text=guidance, style="Small.TLabel", wraplength=620)
                helper.grid(row=2, column=0, columnspan=2, sticky="w")
                block.bind("<Configure>", lambda e, h=helper: h.configure(wraplength=max(200, e.width - 12)))
                status = ttk.Label(block, style="Small.TLabel", wraplength=600)
                status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(3, 0))
                self.field_labels[key] = status
        self.bind("<MouseWheel>", self._scroll_form, add=True)

    def _build_preflight(self) -> None:
        self.readiness_label = ttk.Label(self.preflight_tab, text="Not checked", style="Section.TLabel")
        self.readiness_label.pack(anchor="w")
        self.summary_label = ttk.Label(self.preflight_tab, style="Muted.TLabel", wraplength=650)
        self.summary_label.pack(anchor="w", pady=(7, 16))
        self.check_progress = ttk.Progressbar(self.preflight_tab, mode="determinate", value=0)
        self.check_progress.pack(fill="x", pady=(0, 12))
        table = ttk.Frame(self.preflight_tab)
        table.pack(fill="both", expand=True)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.checks = ttk.Treeview(table, columns=("status", "check", "detail"), show="headings")
        self.checks.heading("status", text="Status")
        self.checks.heading("check", text="Requirement")
        self.checks.heading("detail", text="Result")
        self.checks.column("status", width=130, minwidth=130, stretch=False)
        self.checks.column("check", width=180, minwidth=130, stretch=False)
        self.checks.column("detail", width=400, minwidth=250)
        self.checks.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.checks.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.checks.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.checks.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for level, color in (("ok", "success"), ("warning", "warning"), ("error", "error")):
            self.checks.tag_configure(level, foreground=COLORS[color])
        self.check_detail = ttk.Label(self.preflight_tab, text="Select a requirement to see its full result.",
                                      style="Small.TLabel", wraplength=650)
        self.check_detail.pack(fill="x", pady=(12, 8))
        self.checks.bind("<<TreeviewSelect>>", self._show_check_detail)
        actions = ttk.Frame(self.preflight_tab)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Edit locations", command=lambda: self._navigate(0)).pack(side="left")
        self.check_button = ttk.Button(actions, text="Check setup", style="Primary.TButton", command=self._preflight)
        self.check_button.pack(side="right")

    def _build_run(self) -> None:
        controls = ttk.Frame(self.forms[3][0])
        controls.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Separator(controls).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 16))
        ttk.Label(controls, text="Run size", style="Section.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))
        specs = [
            ("start_batch", "First case ID", 1, 999999999, 100),
            ("batch_count", "100-case batches", 1, 10, 1),
            ("cases_to_process", "Cases to review", 1, 1000, 1),
            ("browser_tabs", "Browser tabs", 1, 6, 1),
        ]
        for col, (key, label, low, high, increment) in enumerate(specs):
            controls.columnconfigure(col, weight=1, uniform="numbers")
            ttk.Label(controls, text=label, style="Small.TLabel").grid(row=2, column=col, padx=(0, 12), sticky="w")
            widget = ttk.Spinbox(controls, textvariable=self.vars[key], from_=low, to=high, increment=increment, width=9)
            widget.grid(row=3, column=col, sticky="ew", padx=(0, 12), pady=(6, 8))
            self.edit_controls.append(widget)
        self.range_var = tk.StringVar()
        ttk.Label(controls, textvariable=self.range_var, style="Small.TLabel", wraplength=600).grid(row=4, column=0, columnspan=4, sticky="w", pady=(0, 12))
        self.model_names = {"1": "GPT 5.6 / Opus by case size", "2": "GPT 6.0 Sol for all cases",
                            "3": "GPT 5.6 / Sol by case size", "N": "GPT 5.6 for all cases"}
        self.flow_names = {"1": "Sequential tabs", "2": "Parallel tabs (legacy)"}
        for row, (key, label, choices) in enumerate((("model_policy", "Review models", self.model_names),
                                                    ("processing_flow", "Processing flow", self.flow_names)), 5):
            ttk.Label(controls, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            display = tk.StringVar(value=choices.get(self.vars[key].get(), ""))
            combo = ttk.Combobox(controls, textvariable=display, values=tuple(choices.values()), state="readonly")
            combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=6)
            combo.bind("<<ComboboxSelected>>", lambda _, k=key, d=display, c=choices:
                       self.vars[k].set(next(code for code, name in c.items() if name == d.get())))
            self.vars[key].trace_add("write", lambda *_, k=key, d=display, c=choices: d.set(c.get(self.vars[k].get(), "")))
            self.edit_controls.append(combo)
        self.cleanup_var = tk.BooleanVar(value=True)
        self.diagnostic_var = tk.BooleanVar(value=self.config_data.diagnostic_mode)
        cleanup = ttk.Checkbutton(controls, text="Clean up recognised temporary files outside the selected batch", variable=self.cleanup_var)
        cleanup.grid(row=7, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Label(controls, text="You will review the files and confirm before anything is removed.", style="Small.TLabel").grid(row=8, column=0, columnspan=4, sticky="w")
        diagnostic = ttk.Checkbutton(controls, text="Show detailed diagnostic activity", variable=self.diagnostic_var)
        diagnostic.grid(row=9, column=0, columnspan=4, sticky="w", pady=6)
        defaults = ttk.Button(controls, text="Restore defaults", command=self._defaults)
        defaults.grid(row=10, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.edit_controls.extend([cleanup, diagnostic, defaults])

        self.run_summary = ttk.Label(self.run_tab, style="Muted.TLabel", wraplength=650)
        self.run_summary.pack(anchor="w", pady=(0, 16))
        self.status_var = tk.StringVar(value="Not checked")
        ttk.Label(self.run_tab, textvariable=self.status_var, style="Section.TLabel", wraplength=650).pack(anchor="w")
        self.run_progress = ttk.Progressbar(self.run_tab, mode="determinate", value=0)
        self.run_progress.pack(fill="x", pady=(12, 18))
        timeline = ttk.Frame(self.run_tab)
        timeline.pack(fill="x", pady=(0, 18))
        self.stage_labels = {}
        for index, (key, name) in enumerate((("prepare", "Prepare cases"), ("merge", "Create PDFs"), ("copilot", "Review in Copilot"))):
            timeline.columnconfigure(index, weight=1, uniform="stages")
            label = ttk.Label(timeline, text=f"{index + 1:02d}  {name}", style="Small.TLabel")
            label.grid(row=0, column=index, sticky="w")
            self.stage_labels[key] = label
        self.start_button = ttk.Button(self.run_tab, text="Run document review", style="Primary.TButton", command=self._start_primary, state="disabled")
        self.start_button.pack(anchor="w", pady=(0, 10))
        self.stop_button = ttk.Button(self.run_tab, text="Stop after current stage", command=self._stop, state="disabled")
        self.stop_button.pack(anchor="w", pady=(0, 16))
        ttk.Separator(self.run_tab).pack(fill="x", pady=(0, 14))
        ttk.Label(self.run_tab, text="Activity", style="Field.TLabel").pack(anchor="w", pady=(0, 8))
        journal = ttk.Frame(self.run_tab)
        journal.pack(fill="both", expand=True)
        self.log = tk.Text(journal, wrap="word", height=7, state="disabled", font=("Segoe UI", 10),
                           bg=COLORS["background"], fg=COLORS["ink"], relief="flat", padx=14, pady=12,
                           highlightthickness=1, highlightbackground=COLORS["border"])
        scroll = ttk.Scrollbar(journal, orient="vertical", command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(fill="both", expand=True)
        action = ttk.Frame(self.run_tab)
        action.pack(fill="x", pady=(16, 0))
        self.master_button = ttk.Button(action, text="Build master workbooks", command=self._start_master)
        self.master_button.pack(side="left")
        ttk.Button(action, text="Open results", command=lambda: self._open("analysis_output_dir")).pack(side="right")
        ttk.Button(action, text="Open logs", command=lambda: self._open("diagnostics_dir")).pack(side="right", padx=8)

    def _show_step(self, index: int) -> None:
        self.step = index
        for page in self.pages:
            page.pack_forget()
        self.pages[index].pack(fill="both", expand=True)
        self.step_label.configure(text=f"STEP {index + 1} OF 6")
        self.title_label.configure(text=self.step_names[index])
        self.subtitle_label.configure(text=GROUPS[index][1] if index < 4 else
                                      "Review your choices and check everything before starting." if index == 4 else
                                      "Prepare, convert and review your selected cases.")
        for number, button in enumerate(self.nav_buttons):
            button.configure(bg=COLORS["rail_active"] if number == index else COLORS["rail"],
                             fg="white" if number == index else COLORS["rail_text"])
        busy = self.running or self.checking
        self.back_button.configure(state="disabled" if busy or index == 0 else "normal")
        self.next_button.configure(text="Continue" if index < 4 else "Go to run" if index == 4 else "Check setup again",
                                   style="TButton" if index == 5 else "Primary.TButton",
                                   state="disabled" if busy or (index == 4 and self.ready_config is None) else "normal")
        self.summary_label.configure(text=self._summary())
        self.run_summary.configure(text=self._summary())
        if index < 4:
            self.forms[index][1].yview_moveto(0)

    def _summary(self) -> str:
        try:
            start = int(self.vars["start_batch"].get())
            end = start + int(self.vars["batch_count"].get()) * 100 - 1
            return (f"Case IDs {start:,} - {end:,}  |  {self.vars['cases_to_process'].get()} cases to review  |  "
                    f"{self.vars['browser_tabs'].get()} browser tabs\n"
                    f"{self.model_names.get(self.vars['model_policy'].get(), 'Choose review models')}")
        except ValueError:
            return "Complete run preferences to see the summary."

    def _scroll_form(self, event) -> None:
        if self.step >= 4:
            return
        widget = event.widget
        while widget is not None:
            if widget == self.pages[self.step]:
                self.forms[self.step][1].yview_scroll(-int(event.delta / 120), "units")
                return
            widget = getattr(widget, "master", None)

    def _reveal_field(self, canvas, block) -> None:
        canvas.update_idletasks()
        top = canvas.canvasy(0)
        start, end = block.winfo_y(), block.winfo_y() + block.winfo_height()
        bounds = canvas.bbox("all")
        total = bounds[3] if bounds else 1
        if start < top:
            canvas.yview_moveto(start / max(1, total))
        elif end > top + canvas.winfo_height():
            canvas.yview_moveto((end - canvas.winfo_height()) / max(1, total))

    def _show_check_detail(self, _) -> None:
        selected = self.checks.selection()
        if selected:
            self.check_detail.configure(text=self.checks.item(selected[0], "values")[2])

    def _navigate(self, index: int) -> None:
        if self.running or self.checking or not 0 <= index < 6:
            return
        if index > self.step:
            for group in range(min(index, 4)):
                if not self._validate_group(group):
                    self._show_step(group)
                    return
            if index == 5 and self.ready_config is None:
                self.feedback_var.set("Check setup successfully before starting a document review.")
                self._show_step(4)
                return
        self._show_step(index)

    def _continue(self) -> None:
        if self.step == 5:
            self._navigate(4)
        elif self.step < 4:
            if self._validate_group(self.step) and self._save():
                self._navigate(self.step + 1)
        else:
            self._navigate(5)

    def _open_master(self) -> None:
        if self.running or self.checking:
            return
        self._show_step(5)
        self.feedback_var.set("Build master workbooks after completed analyses have arrived. This stage runs separately from document review.")

    def _changed(self, *_) -> None:
        if _ and _[0] in FIELD_SPECS:
            self.touched_fields.add(_[0])
        self.ready_config = None
        self.start_button.configure(state="disabled")
        self.readiness_label.configure(text="Not checked", foreground=COLORS["muted"])
        self.check_button.configure(style="Primary.TButton")
        if self.step == 4:
            self.next_button.configure(state="disabled")
        self.feedback_var.set("Changes have not been checked. Save your progress or continue.")
        if self.validation_job:
            self.after_cancel(self.validation_job)
        self.validation_job = self.after(250, self._refresh_fields)

    def _refresh_fields(self) -> None:
        self.validation_job = None
        for key, label in self.field_labels.items():
            ok, detail = validate_field(key, self.vars[key].get())
            if not ok and key not in self.touched_fields:
                label.configure(text="Not selected or not yet available", foreground=COLORS["muted"])
            else:
                label.configure(text=detail, foreground=COLORS["success"] if ok else COLORS["error"])
        message = validate_run({key: var.get() for key, var in self.vars.items()})
        self.range_var.set(message or self._summary().split("\n")[0])

    def _validate_group(self, index: int) -> bool:
        self.touched_fields.update(field[0] for field in GROUPS[index][2])
        self._refresh_fields()
        for key, label, _, _ in GROUPS[index][2]:
            ok, detail = validate_field(key, self.vars[key].get())
            if not ok:
                self.feedback_var.set(f"{label}: {detail}")
                return False
        if index == 3:
            message = validate_run({key: var.get() for key, var in self.vars.items()})
            if message:
                self.feedback_var.set(message)
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
            self.feedback_var.set("Progress saved for this Windows user.")
            return True
        except (ValueError, OSError, tk.TclError):
            self.feedback_var.set("Settings could not be saved. Check the numeric values and access to your settings folder.")
            return False

    def _defaults(self) -> None:
        if self.running or self.checking:
            return
        if not messagebox.askyesno("Restore defaults", "Replace the current locations and run preferences with defaults?", parent=self):
            return
        defaults = WorkflowConfig.defaults()
        for key, var in self.vars.items():
            if hasattr(defaults, key):
                var.set(getattr(defaults, key))
        self.diagnostic_var.set(defaults.diagnostic_mode)

    def _preflight(self) -> None:
        if self.running or self.checking:
            return
        for index in range(4):
            if not self._validate_group(index):
                self._show_step(index)
                return
        if not self._save():
            return
        self._show_step(4)
        self.checks.delete(*self.checks.get_children())
        self.ready_config = None
        self.checking = True
        self._set_busy(True)
        self.readiness_label.configure(text="Checking your setup...", foreground=COLORS["blue"])
        self.feedback_var.set("Checking files, write access, packages and Microsoft Edge.")
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
        self.feedback_var.set(f"Setup checked. {warnings} warnings to review." if ready else
                              "Review the results below, edit the relevant locations, then check again.")
        self.status_var.set("Ready to run" if ready else "Setup needs attention")
        self.start_button.configure(state="normal" if ready else "disabled")
        self.check_button.configure(style="TButton" if ready else "Primary.TButton")
        self._show_step(4)

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
        if self.running or self.checking:
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
        if self.running or self.checking or not self._save():
            return
        ok, detail = validate_field("analysis_output_dir", self.vars["analysis_output_dir"].get())
        if not ok:
            self.feedback_var.set(f"Completed analysis: {detail}")
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
        for control in self.nav_buttons + [self.master_nav, self.back_button, self.next_button, self.save_button, self.check_button, self.master_button]:
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
                    for key, label in self.stage_labels.items():
                        label.configure(foreground=COLORS["blue"] if key == message else COLORS["muted"])
                elif kind == "error":
                    self.ready_config = None
                    self.status_var.set("The run needs attention. Open logs for details, then check setup before retrying.")
                elif kind in {"progress", "complete", "warning"}:
                    self.status_var.set(message)
                if kind != "log" or self.diagnostic_var.get():
                    self.log.configure(state="normal")
                    self.log.insert("end", (self.status_var.get() if kind in {"error", "stage"} else message) + "\n")
                    if int(self.log.index("end-1c").split(".")[0]) > 500:
                        self.log.delete("1.0", "100.0")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                if kind == "complete":
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
                messagebox.showinfo("Folder not available", "This folder has not been created yet. Check setup or complete a run first.", parent=self)
                return
            os.startfile(path)
        except (OSError, ValueError):
            messagebox.showerror("Could not open folder", "This location is unavailable. Check the shared drive and your folder access.", parent=self)

    def _close(self) -> None:
        if self.running:
            messagebox.showinfo("Review in progress", "Use Stop after current stage and wait for the workflow to stop before closing.", parent=self)
        elif self.checking:
            messagebox.showinfo("Setup check in progress", "Wait for the setup check to finish before closing.", parent=self)
        else:
            self.destroy()

    def destroy(self) -> None:
        for callback in self.tk.call("after", "info"):
            self.after_cancel(callback)
        super().destroy()


def run_app(config_path: Path = CONFIG_PATH) -> None:
    App(config_path).mainloop()
