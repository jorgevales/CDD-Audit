"""Centered, focused views for the existing document review workflow."""

import tkinter as tk
from collections import deque
from tkinter import font as tkfont, ttk

from .design import COLORS, GLYPHS, ContentFade, Stepper, Surface, Tooltip, detected_user, icon_button
from .setup_form import FIELD_SPECS, GROUPS


class WizardView:
    def _build(self):
        self.part = 0
        self.master_mode = False
        self.completed_steps = set()
        self.animations_enabled = True
        self.transitioning = False
        self.fade = ContentFade(self)
        self.user_name = detected_user()
        self.model_names = {"1": "GPT 5.6 / Opus by case size", "2": "GPT 6.0 Sol for all cases",
                            "3": "GPT 5.6 / Sol by case size", "N": "GPT 5.6 for all cases"}
        self.flow_names = {"1": "Sequential tabs", "2": "Parallel tabs (legacy)"}
        self.step_names = [group[0] for group in GROUPS] + ["Check setup", "Run workflow"]
        self.step_parts = [[field[0] for field in group[2]] for group in GROUPS] + [["checks"], ["run"]]
        self.step_parts[3] += ["scope", "models", "options"]

        header = tk.Frame(self, bg=COLORS["blue"], height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.brand_label = tk.Label(header, text="CDD Audit Remediation", font=(self.ui_font, 26, "bold"),
                                    bg=COLORS["blue"], fg="white")
        self.brand_label.place(relx=0.5, rely=0.5, anchor="center")
        self.step_label = tk.Label(header, font=(self.ui_font, 10), bg=COLORS["blue"], fg=COLORS["header_text"])
        self.step_label.place(x=28, rely=0.5, anchor="w")
        user = tk.Frame(header, bg=COLORS["blue"])
        user.place(relx=1, x=-28, rely=0.5, anchor="e")
        tk.Label(user, text=GLYPHS["user"], font=(self.icon_font, 15), bg=COLORS["blue"], fg=COLORS["header_text"]).pack(side="left", padx=(0, 7))
        user_font = tkfont.Font(root=self, family=self.ui_font, size=10)
        display_name = self.user_name
        while user_font.measure(display_name) > 140 and len(display_name) > 4:
            display_name = display_name[:-4] + "..." if display_name.endswith("...") else display_name[:-1] + "..."
        self.user_label = tk.Label(user, text=display_name, font=(self.ui_font, 10), bg=COLORS["blue"], fg="white")
        self.user_label.pack(side="left")
        Tooltip(self.user_label, self.user_name)
        progress_line = ttk.Frame(self, height=4)
        progress_line.pack(fill="x")
        progress_line.pack_propagate(False)
        self.top_progress = ttk.Progressbar(progress_line, mode="determinate", value=0)
        self.top_progress.pack(fill="both", expand=True)
        self.check_progress = self.run_progress = self.top_progress

        progress_host = ttk.Frame(self, height=66)
        progress_host.pack(fill="x", pady=(12, 0))
        progress_host.pack_propagate(False)
        self.stepper = Stepper(progress_host, self, self._navigate)
        self.stepper.place(relx=0.5, rely=0.5, anchor="center", width=740)
        progress_host.bind("<Configure>", lambda event: self.stepper.configure(width=min(740, event.width - 48)))

        footer = ttk.Frame(self, height=104)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        footer_inner = ttk.Frame(footer)
        footer_inner.place(relx=0.5, rely=0.5, anchor="center", width=740)
        footer.bind("<Configure>", lambda event: footer_inner.configure(width=min(740, event.width - 48)))
        self.feedback_label = ttk.Label(footer_inner, textvariable=self.feedback_var,
                                        style="Small.TLabel", anchor="center", justify="center", wraplength=680)
        self.feedback_label.pack(fill="x", pady=(0, 12))
        row = ttk.Frame(footer_inner)
        row.pack(fill="x")
        self.back_button = ttk.Button(row, text="\u2190  Back", command=self._back)
        self.back_button.pack(side="left")
        self.save_button = icon_button(row, self, "save", self._save, "Save settings", COLORS["background"])
        self.save_button.pack(side="left", padx=8)
        self.master_nav = icon_button(row, self, "master", self._open_master, "Master workbooks", COLORS["background"])
        self.master_nav.pack(side="left")
        self.next_button = ttk.Button(row, text="Continue  \u2192", style="Primary.TButton", command=self._continue)
        self.next_button.pack(side="right")

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        self.hero = ttk.Frame(self.body)
        self.hero.pack(fill="x", pady=(8, 12))
        self.hero_icon = tk.Canvas(self.hero, width=64, height=64, bg=COLORS["background"], highlightthickness=0)
        self.hero_icon.pack()
        self.hero_icon.create_oval(2, 2, 62, 62, fill=COLORS["soft_blue"], outline=COLORS["soft_blue"])
        self.hero_symbol = self.hero_icon.create_text(32, 32, font=(self.icon_font, 26), fill=COLORS["blue"])
        self.title_label = ttk.Label(self.hero, style="Title.TLabel", anchor="center")
        self.title_label.pack(fill="x", pady=(11, 0))
        self.part_label = ttk.Label(self.hero, style="Small.TLabel", anchor="center")
        self.part_label.pack(fill="x", pady=(5, 0))
        page_region = ttk.Frame(self.body)
        page_region.pack(fill="both", expand=True)
        self.page_host = ttk.Frame(page_region)
        self.page_host.place(relx=0.5, rely=0.5, anchor="center", width=740, relheight=1)
        page_region.bind("<Configure>", lambda event: self.page_host.configure(width=min(740, event.width - 48)))
        self.pages = [ttk.Frame(self.page_host) for _ in range(6)]
        self.parts = {}
        self.preflight_tab, self.run_tab = self.pages[4:]
        self._build_setup()
        self._build_preferences()
        self._build_preflight()
        self._build_run()

    def _part_frame(self, step, key):
        frame = ttk.Frame(self.pages[step])
        self.parts[key] = frame
        return frame

    def _build_setup(self):
        for step, (_, _, group) in enumerate(GROUPS):
            for key, label, kind, guidance in group:
                frame = self._part_frame(step, key)
                surface = Surface(frame)
                surface.pack(fill="x")
                inner = surface.inner
                inner.columnconfigure(1, weight=1)
                ttk.Label(inner, text=label, style="Field.TLabel", anchor="center").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
                help_button = icon_button(inner, self, "help", lambda text=guidance: self._show_help(text), guidance)
                help_button.grid(row=0, column=2, sticky="e", pady=(0, 6))
                symbol = "folder" if "dir" in kind else "file"
                tk.Label(inner, text=GLYPHS[symbol], font=(self.icon_font, 19), bg=COLORS["paper"], fg=COLORS["blue"]).grid(row=1, column=0, padx=(0, 10))
                entry = ttk.Entry(inner, textvariable=self.vars[key])
                entry.grid(row=1, column=1, sticky="ew")
                browse = icon_button(inner, self, "folder" if "dir" in kind else "search",
                                     lambda k=key, t=kind: self._browse(k, t),
                                     "Choose folder" if "dir" in kind else "Choose file")
                browse.grid(row=1, column=2, padx=(12, 0))
                self.edit_controls.extend([entry, browse, help_button])
                status = ttk.Label(inner, style="CardSmall.TLabel", anchor="center", justify="center", wraplength=610)
                status.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
                self.field_labels[key] = status
                if key == "edge_executable":
                    automatic = ttk.Button(frame, text="Detect automatically", command=lambda: self.vars["edge_executable"].set(""))
                    automatic.pack(pady=(14, 0))
                    self.edit_controls.append(automatic)

    def _build_preferences(self):
        self.cleanup_var = tk.BooleanVar(value=True)
        self.diagnostic_var = tk.BooleanVar(value=self.config_data.diagnostic_mode)
        scope = self._part_frame(3, "scope")
        surface = Surface(scope)
        surface.pack(fill="x")
        grid = surface.inner
        for column in (0, 1):
            grid.columnconfigure(column, weight=1, uniform="scope")
        specs = (("start_batch", "First case ID", 1, 999999999, 100),
                 ("batch_count", "100-case batches", 1, 10, 1),
                 ("cases_to_process", "Cases to review", 1, 1000, 1),
                 ("browser_tabs", "Browser tabs", 1, 6, 1))
        for number, (key, label, low, high, increment) in enumerate(specs):
            row, column = divmod(number, 2)
            ttk.Label(grid, text=label, style="Field.TLabel", anchor="center").grid(row=row*2, column=column, sticky="ew", padx=8, pady=(0, 8))
            widget = ttk.Spinbox(grid, textvariable=self.vars[key], from_=low, to=high, increment=increment, width=15)
            widget.grid(row=row*2+1, column=column, sticky="ew", padx=8, pady=(0, 16 if row == 0 else 0))
            self.edit_controls.append(widget)
        self.range_var = tk.StringVar()
        ttk.Label(scope, textvariable=self.range_var, style="Small.TLabel", anchor="center", justify="center", wraplength=700).pack(fill="x", pady=(14, 0))
        models = self._part_frame(3, "models")
        surface = Surface(models)
        surface.pack(fill="x")
        for key, label, choices in (("model_policy", "Review models", self.model_names),
                                     ("processing_flow", "Processing flow", self.flow_names)):
            ttk.Label(surface.inner, text=label, style="Field.TLabel", anchor="center").pack(fill="x", pady=(0, 8))
            display = tk.StringVar(value=choices.get(self.vars[key].get(), ""))
            combo = ttk.Combobox(surface.inner, textvariable=display, values=tuple(choices.values()), state="readonly")
            combo.pack(fill="x", pady=(0, 14))
            combo.bind("<<ComboboxSelected>>", lambda _, k=key, d=display, c=choices:
                       self.vars[k].set(next(code for code, name in c.items() if name == d.get())))
            self.vars[key].trace_add("write", lambda *_, k=key, d=display, c=choices: d.set(c.get(self.vars[k].get(), "")))
            self.edit_controls.append(combo)
        options = self._part_frame(3, "options")
        surface = Surface(options)
        surface.pack(fill="x")
        for label, variable in (("Temporary-file cleanup", self.cleanup_var), ("Detailed activity", self.diagnostic_var)):
            widget = ttk.Checkbutton(surface.inner, text=label, variable=variable)
            widget.pack(anchor="w", pady=7)
            self.edit_controls.append(widget)
        ttk.Label(surface.inner, text="Cleanup always asks for confirmation.", style="CardSmall.TLabel").pack(anchor="w", pady=(8, 0))
        defaults = icon_button(options, self, "settings", self._defaults, "Restore defaults", COLORS["background"])
        defaults.pack(pady=(16, 0))
        self.edit_controls.append(defaults)

    def _build_preflight(self):
        frame = self._part_frame(4, "checks")
        surface = Surface(frame, padding=14)
        surface.pack(fill="x")
        self.check_rows = {}
        for index, name in enumerate(("Source files", "Output folders", "Review & browser", "Dependencies")):
            row = ttk.Frame(surface.inner, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            icon = tk.Label(row, text=GLYPHS["check"], font=(self.icon_font, 17), bg=COLORS["paper"], fg=COLORS["muted"])
            icon.pack(side="left", padx=(0, 14))
            ttk.Label(row, text=name, style="Card.TLabel").pack(side="left")
            status = ttk.Label(row, text="Not checked", style="CardSmall.TLabel")
            status.pack(side="right")
            self.check_rows[name] = (icon, status)
        self.readiness_label = ttk.Label(frame, text="Not checked", style="Small.TLabel", anchor="center")
        self.readiness_label.pack(fill="x", pady=(8, 6))
        actions = ttk.Frame(frame)
        actions.pack()
        self.check_button = ttk.Button(actions, text="Check setup", style="Primary.TButton", command=self._preflight)
        self.check_button.pack(side="left", padx=6)
        self.details_button = icon_button(actions, self, "logs", self._show_check_details, "Check details", COLORS["background"])
        self.details_button.pack(side="left", padx=6)
        self.edit_controls.append(self.details_button)
        # The complete results remain available in a dialog without crowding the page.
        self.check_window = tk.Toplevel(self)
        self.check_window.title("Setup details")
        self.check_window.withdraw()
        self.check_window.protocol("WM_DELETE_WINDOW", self.check_window.withdraw)
        detail_host = ttk.Frame(self.check_window, padding=20)
        detail_host.pack(fill="both", expand=True)
        table = ttk.Frame(detail_host)
        table.pack(fill="both", expand=True)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.checks = ttk.Treeview(table, columns=("status", "check", "detail"), show="headings", height=8)
        for column, title, width in (("status", "Status", 130), ("check", "Requirement", 180), ("detail", "Result", 390)):
            self.checks.heading(column, text=title)
            self.checks.column(column, width=width, minwidth=100)
        self.checks.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.checks.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.checks.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.checks.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.check_detail = ttk.Label(detail_host, style="Small.TLabel", wraplength=680)
        self.check_detail.pack(fill="x", pady=12)
        self.checks.bind("<<TreeviewSelect>>", self._show_check_detail)
        ttk.Button(detail_host, text="Close", command=self.check_window.withdraw).pack()

    def _show_check_details(self):
        self.check_window.transient(self)
        x = self.winfo_rootx() + (self.winfo_width() - 820) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 500) // 2
        self.check_window.geometry(f"820x500+{max(0, x)}+{max(0, y)}")
        self.check_window.deiconify()
        self.check_window.lift()

    def _set_check_rows(self, checks):
        groups = {name: [] for name in self.check_rows}
        for check in checks:
            name = check.name.lower()
            group = ("Output folders" if any(word in name for word in ("workspace", "output", "diagnostics")) else
                     "Review & browser" if any(word in name for word in ("edge", "instructions", "browser", "base message")) else
                     "Dependencies" if any(word in name for word in ("pymupdf", "pillow", "reportlab", "docx", "openpyxl", "playwright", "conversion", "engine", "setup check", "dependency", "dependencies")) else "Source files")
            groups[group].append(check)
        for name, (icon, label) in self.check_rows.items():
            results = groups[name]
            level = "error" if any(check.level == "error" for check in results) else "warning" if any(check.level == "warning" for check in results) else "ok" if results else None
            color = COLORS[{"error": "error", "warning": "warning", "ok": "success"}.get(level, "muted")]
            label.configure(text={"error": "Needs attention", "warning": "Review", "ok": "Ready"}.get(level, "Not checked"), foreground=color)
            icon.configure(text=GLYPHS["check"] if level == "ok" else GLYPHS["warning"] if level else GLYPHS["help"], foreground=color)

    def _build_run(self):
        frame = self._part_frame(5, "run")
        surface = Surface(frame, padding=28)
        surface.pack(fill="x")
        self.metrics = {}
        for column, (key, label) in enumerate((("cases", "Cases"), ("tabs", "Browser tabs"), ("models", "Models"))):
            surface.inner.columnconfigure(column, weight=1, uniform="metrics")
            ttk.Label(surface.inner, text=label, style="CardSmall.TLabel", anchor="center").grid(row=0, column=column, sticky="ew", padx=12, pady=(4, 0))
            value = ttk.Label(surface.inner, style="Metric.TLabel" if key != "models" else "Field.TLabel",
                              anchor="center", justify="center", wraplength=210)
            value.grid(row=1, column=column, sticky="ew", padx=12, pady=(10, 4))
            self.metrics[key] = value
        self.status_var = tk.StringVar(value="Not checked")
        self.status_label = ttk.Label(frame, textvariable=self.status_var, style="Small.TLabel", anchor="center", justify="center", wraplength=680)
        self.status_label.pack(fill="x", pady=(12, 14))
        self.start_button = ttk.Button(frame, text="\u25b6  Run document review", style="Primary.TButton", command=self._start_primary, state="disabled")
        self.start_button.pack(pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.pack()
        self.stop_button = icon_button(actions, self, "stop", self._stop, "Stop after current stage", COLORS["background"])
        self.stop_button.configure(state="disabled")
        self.stop_button.pack(side="left", padx=8)
        icon_button(actions, self, "folder", lambda: self._open("analysis_output_dir"), "Open results", COLORS["background"]).pack(side="left", padx=8)
        icon_button(actions, self, "logs", lambda: self._open("diagnostics_dir"), "Open logs", COLORS["background"]).pack(side="left", padx=8)
        self.master_button = ttk.Button(frame, text="Build master workbooks", command=self._start_master)
        self.activity_lines = deque(maxlen=500)
        # Activity is kept in memory and exposed on request; engine logs remain on disk.
        self.activity_button = icon_button(actions, self, "help", self._show_activity, "Recent activity", COLORS["background"])
        self.activity_button.pack(side="left", padx=8)

    def _show_activity(self):
        window = tk.Toplevel(self)
        window.title("Recent activity")
        window.transient(self)
        width, height = 620, 420
        window.geometry(f"{width}x{height}+{max(0, self.winfo_rootx() + (self.winfo_width()-width)//2)}+{max(0, self.winfo_rooty() + (self.winfo_height()-height)//2)}")
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Button(frame, text="Close", command=window.destroy).pack(side="bottom", pady=(12, 0))
        scroll = ttk.Scrollbar(frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        text = tk.Text(frame, font=(self.ui_font, 10), wrap="word", bg=COLORS["paper"],
                       fg=COLORS["ink"], relief="flat", padx=12, pady=12, yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        scroll.configure(command=text.yview)
        text.insert("1.0", "\n".join(self.activity_lines) or "No activity yet.")
        text.configure(state="disabled")
        text.see("end")
        window.bind("<Escape>", lambda _: window.destroy())

    def _show_help(self, text):
        window = tk.Toplevel(self)
        window.title("Details")
        window.transient(self)
        window.configure(bg=COLORS["background"])
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=text, wraplength=450, justify="center").pack(pady=(0, 18))
        ttk.Button(frame, text="Close", command=window.destroy).pack()
        window.bind("<Escape>", lambda _: window.destroy())
        window.update_idletasks()
        width, height = window.winfo_reqwidth(), min(window.winfo_reqheight(), self.winfo_height() - 80)
        window.geometry(f"{width}x{height}+{max(0, self.winfo_rootx() + (self.winfo_width()-width)//2)}+{max(0, self.winfo_rooty() + (self.winfo_height()-height)//2)}")

    def _visible_part(self):
        return self.parts[self.step_parts[self.step][self.part]]

    def _show_step(self, index, part=0, animate=False):
        part = min(part, len(self.step_parts[index]) - 1)
        self.fade.cancel()
        self.transitioning = False
        def display():
            self.step, self.part = index, part
            if index != 5:
                self.master_mode = False
            for page in self.pages:
                page.pack_forget()
            for frame in self.parts.values():
                frame.place_forget()
            self.pages[index].pack(fill="both", expand=True)
            self._visible_part().place(relx=0.5, rely=0.5, anchor="center", relwidth=1)
            self.step_label.configure(text=f"{index + 1} / 6")
            self.title_label.configure(text="Master workbooks" if index == 5 and self.master_mode else self.step_names[index])
            self.part_label.configure(text=f"{part + 1} / {len(self.step_parts[index])}" if index < 4 else "")
            if index < 4:
                self.part_label.pack(fill="x", pady=(5, 0))
            else:
                self.part_label.pack_forget()
            self.hero_icon.itemconfigure(self.hero_symbol, text=GLYPHS[("folder", "folder", "file", "settings", "check", "play")[index]])
            if index == 5:
                if self.master_mode:
                    self.start_button.pack_forget()
                    self.master_button.configure(style="Primary.TButton")
                    self.master_button.pack(after=self.status_label, pady=(0, 12))
                    self.hero_icon.itemconfigure(self.hero_symbol, text=GLYPHS["master"])
                else:
                    self.master_button.pack_forget()
                    self.start_button.pack(after=self.status_label, pady=(0, 12))
            self.stepper.step = self.stepper.selected = index
            self.stepper.complete = self.completed_steps.copy()
            self.stepper.draw()
            busy = self.running or self.checking
            self.back_button.configure(state="disabled" if busy or (index == 0 and part == 0) else "normal")
            self.next_button.configure(text="Continue  \u2192" if index < 4 else "Go to run  \u2192" if index == 4 else "Check setup",
                                       style="TButton" if index == 5 else "Primary.TButton",
                                       state="disabled" if busy or (index == 4 and self.ready_config is None) else "normal")
            self.metrics["cases"].configure(text=self.vars["cases_to_process"].get())
            self.metrics["tabs"].configure(text=self.vars["browser_tabs"].get())
            self.metrics["models"].configure(text=self.model_names.get(self.vars["model_policy"].get(), "Choose models").replace(" by case size", "").replace(" for all cases", ""))
        if animate and self.animations_enabled:
            self.transitioning = True
            self.fade.play([self.hero, self._visible_part()], display,
                           lambda: [self.hero, self._visible_part()], lambda: setattr(self, "transitioning", False))
        else:
            display()

    def _back(self):
        if self.running or self.checking or self.transitioning:
            return
        if self.part:
            self._show_step(self.step, self.part - 1, animate=True)
        elif self.step:
            self._show_step(self.step - 1, len(self.step_parts[self.step - 1]) - 1, animate=True)
