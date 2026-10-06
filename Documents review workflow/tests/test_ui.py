from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from workflow.config import WorkflowConfig
from workflow.preflight import Check
from workflow.setup_form import FIELD_SPECS, validate_field, validate_run
from workflow.ui import App


class SetupValidationTests(unittest.TestCase):
    def test_required_and_optional_locations(self):
        self.assertFalse(validate_field("working_csv", "")[0])
        self.assertEqual(validate_field("edge_executable", ""), (True, "Automatic detection"))

    def test_file_type_and_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrong = root / "cases.xlsx"
            wrong.touch()
            self.assertFalse(validate_field("working_csv", str(wrong))[0])
            self.assertFalse(validate_field("working_csv", str(root / "missing.csv"))[0])
            self.assertFalse(validate_field("source_data_root", str(wrong))[0])

    def test_output_validation_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new" / "results"
            self.assertTrue(validate_field("analysis_output_dir", str(path))[0])
            self.assertFalse(path.exists())
            with patch("workflow.setup_form.os.access", return_value=False):
                self.assertFalse(validate_field("analysis_output_dir", str(path))[0])

    def test_run_scope_and_numeric_errors(self):
        values = asdict(WorkflowConfig())
        self.assertEqual(validate_run(values), "")
        for key, value in (("start_batch", 2), ("browser_tabs", 7),
                           ("batch_count", 11), ("cases_to_process", 101),
                           ("batch_count", ""), ("default_model", "invalid"),
                           ("processing_flow", "invalid")):
            self.assertTrue(validate_run(dict(values, **{key: value})), key)


class GuidedInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        try:
            self.app = App(self.root / "settings.json")
            self.app.animations_enabled = False
        except tk.TclError as exc:
            self.directory.cleanup()
            self.skipTest(f"A desktop display is required: {exc}")
        for key, (_, _, kind, _) in FIELD_SPECS.items():
            if key == "edge_executable":
                self.app.vars[key].set("")
                continue
            suffix = ".md" if kind == "markdown" else ".csv" if "csv" in kind else ""
            path = self.root / (key + suffix)
            if "dir" in kind:
                path.mkdir()
            else:
                path.write_text("change_id\n1\n", encoding="utf-8")
            self.app.vars[key].set(str(path))
        self.app.update()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.destroy()
        self.directory.cleanup()

    def test_values_persist_when_moving_back_and_forward(self):
        original = self.app.vars["working_csv"].get()
        self.app._continue()
        self.assertEqual((self.app.step, self.app.part), (0, 1))
        self.app._back()
        self.assertEqual(self.app.vars["working_csv"].get(), original)
        self.assertTrue((self.root / "settings.json").is_file())
        for _ in range(len(self.app.step_parts[0])):
            self.app._continue()
        self.assertEqual(self.app.step, 1)

    def test_missing_required_input_blocks_continue_and_direct_navigation(self):
        self.app.vars["working_csv"].set("")
        self.app._show_step(0, 2)
        self.app._continue()
        self.assertEqual(self.app.step, 0)
        self.assertEqual(self.app.part, 2)
        self.app._navigate(4)
        self.assertEqual(self.app.step, 0)
        self.assertIn("Working case list", self.app.feedback_var.get())

    def test_readiness_requires_real_check_results_and_invalidates_on_change(self):
        self.app._navigate(5)
        self.assertEqual(self.app.step, 4)
        self.app._finish_checks(self.app._collect(), [Check("error", "Dependency", "Missing")])
        self.assertIsNone(self.app.ready_config)
        self.assertEqual(str(self.app.start_button["state"]), "disabled")
        self.app._finish_checks(self.app._collect(), [Check("ok", "Dependency", "Available")])
        self.app._navigate(5)
        self.assertEqual(self.app.step, 5)
        self.app.vars["browser_tabs"].set("2")
        self.assertIsNone(self.app.ready_config)
        self.assertEqual(str(self.app.start_button["state"]), "disabled")

    def test_checks_run_in_background_and_do_not_allow_duplicate_checks(self):
        import threading
        gate = threading.Event()
        def check(config):
            gate.wait(2)
            return [Check("ok", "Files", "Available")]
        try:
            with patch("workflow.ui.run_preflight", side_effect=check) as preflight:
                self.app._preflight()
                self.assertTrue(self.app.checking)
                self.app._preflight()
                self.assertEqual(str(self.app.save_button["state"]), "disabled")
                gate.set()
                import time
                deadline = time.monotonic() + 3
                while self.app.checking and time.monotonic() < deadline:
                    self.app.update()
                    time.sleep(0.01)
                self.assertFalse(self.app.checking)
                self.assertEqual(preflight.call_count, 1)
        finally:
            gate.set()

    def test_safe_stop_restores_controls_after_worker_exits(self):
        from types import SimpleNamespace
        self.app.ready_config = asdict(self.app._collect())
        self.app.running = True
        self.app._set_busy(True)
        self.app.worker = SimpleNamespace(is_alive=lambda: False)
        self.app.orchestrator = SimpleNamespace(state=SimpleNamespace(status="cancelled_safe"))
        self.app.events.put(("warning", "Stopped after a safe stage boundary"))
        self.app._drain_events()
        self.assertFalse(self.app.running)
        self.assertEqual(str(self.app.save_button["state"]), "normal")
        self.assertEqual(str(self.app.stop_button["state"]), "disabled")
        self.assertIn("Stopped safely", self.app.feedback_var.get())

    def test_copilot_stage_uses_the_actual_engine_event_name(self):
        self.app.events.put(("stage", "copilot"))
        self.app._drain_events()
        self.assertEqual(self.app.status_var.get(), "Reviewing in Copilot")
        self.assertIn("Reviewing in Copilot", self.app.activity_lines)

    def test_successful_master_does_not_report_failure_without_browser_readiness(self):
        from types import SimpleNamespace
        self.app.ready_config = None
        self.app.running = True
        self.app.worker = SimpleNamespace(is_alive=lambda: False)
        self.app.orchestrator = SimpleNamespace(state=SimpleNamespace(status="complete"))
        self.app.events.put(("complete", "Master stage finished."))
        self.app._drain_events()
        self.assertIn("Finished", self.app.feedback_var.get())
        self.assertFalse(self.app.running)

    def test_master_stage_remains_accessible_without_browser_readiness(self):
        self.app.vars["source_data_root"].set("")
        self.app._open_master()
        self.assertEqual(self.app.step, 5)
        self.assertEqual(str(self.app.master_button["state"]), "normal")
        self.assertEqual(str(self.app.start_button["state"]), "disabled")

    def test_only_one_field_page_is_visible_at_a_time(self):
        self.app.geometry("900x700")
        self.app._show_step(1, 4)
        self.app.update()
        visible = [key for key, frame in self.app.parts.items() if frame.winfo_ismapped()]
        self.assertEqual(visible, ["diagnostics_dir"])
        self.app._back()
        self.assertEqual(self.app.part, 3)

    def test_brand_user_font_and_top_progress(self):
        self.assertEqual(self.app.brand_label["text"], "CDD Audit Remediation")
        self.assertTrue(self.app.user_name)
        self.assertTrue(self.app.ui_font)
        self.assertLessEqual(self.app.top_progress.winfo_height(), 6)

    def test_aptos_is_real_or_fallback_is_explained(self):
        from tkinter import font
        if self.app.ui_font == "Aptos":
            for weight in ("normal", "bold"):
                actual = font.Font(root=self.app, family=self.app.ui_font, size=11, weight=weight).actual()
                self.assertEqual(actual["family"], "Aptos")
                self.assertEqual(actual["weight"], weight)
            self.assertEqual(self.app.font_warning, "")
        else:
            self.assertIn("Install Aptos.cmd", self.app.font_warning)

    def test_run_summary_has_clear_top_and_bottom_insets(self):
        from workflow.design import Surface
        self.app._show_step(5)
        self.app.update()
        surface = next(widget for widget in self.app.parts["run"].winfo_children() if isinstance(widget, Surface))
        for label in surface.inner.winfo_children():
            self.assertGreaterEqual(label.winfo_rooty() - surface.winfo_rooty(), 28)
            self.assertGreaterEqual(surface.winfo_rooty() + surface.winfo_height() -
                                    label.winfo_rooty() - label.winfo_height(), 28)

    def test_rounded_controls_keep_native_states_and_field_layouts(self):
        from tkinter import ttk
        style = ttk.Style(self.app)
        for name in ("TButton", "Primary.TButton", "TEntry", "TSpinbox", "TCombobox"):
            self.assertIn("Rounded.", str(style.layout(name)))
        self.assertIsInstance(self.app.save_button, ttk.Button)
        from tkinter import font
        from workflow.design import GLYPHS
        icon_width = font.Font(root=self.app, family=self.app.icon_font, size=19).measure(GLYPHS["save"])
        self.assertGreaterEqual(self.app.save_button.winfo_width(), icon_width + 24)
        primary_image = next(image for image in self.app.rounded_images
                             if image.get(10, 10) == (16, 45, 89))
        # Opaque parent-colour corners remain rounded with remote software rendering.
        self.assertEqual(primary_image.get(0, 0), (245, 247, 251))
        self.app.save_button.configure(state="disabled")
        with patch.object(self.app.config_data, "save") as save:
            self.app.save_button.invoke()
            save.assert_not_called()

    def test_detected_user_fallback_uses_current_session(self):
        from workflow.design import detected_user
        with patch("workflow.design.os.name", "posix"), patch("workflow.design.getpass.getuser", return_value="current-analyst"):
            self.assertEqual(detected_user(), "current-analyst")

    def test_cleanup_dialog_requires_exact_confirmation(self):
        from tkinter import ttk
        from workflow.design import compact_confirm
        observed = []
        def answer():
            dialog = next(window for window in self.app.winfo_children()
                          if isinstance(window, tk.Toplevel) and window.title() == "Confirm cleanup")
            controls = []
            def visit(widget):
                controls.append(widget)
                for child in widget.winfo_children():
                    visit(child)
            visit(dialog)
            primary = next(widget for widget in controls if isinstance(widget, ttk.Button) and widget["text"] == "Allow cleanup")
            entry = next(widget for widget in controls if isinstance(widget, ttk.Entry))
            details = next(widget for widget in controls if isinstance(widget, ttk.Button) and widget["text"] == "View files")
            details.invoke()
            dialog.update_idletasks()
            self.assertLessEqual(primary.winfo_rooty() + primary.winfo_height(), dialog.winfo_rooty() + dialog.winfo_height())
            observed.append(str(primary["state"]))
            entry.insert(0, "delete")
            observed.append(str(primary["state"]))
            entry.delete(0, "end")
            entry.insert(0, "DELETE")
            observed.append(str(primary["state"]))
            primary.invoke()
        self.app.after(100, answer)
        self.assertTrue(compact_confirm(self.app, "Confirm cleanup", "One temporary item.", action="Allow cleanup", details="Fictional temporary case folder", required_text="DELETE"))
        self.assertEqual(observed, ["disabled", "disabled", "normal"])

    def test_page_fades_finish_and_preserve_input_values(self):
        import time
        self.app.animations_enabled = True
        original = self.app.vars["working_csv"].get()
        self.app._show_step(0, 1, animate=True)
        self.assertTrue(self.app.transitioning)
        self.app._continue()
        deadline = time.monotonic() + 2
        while self.app.transitioning and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.01)
        self.assertFalse(self.app.transitioning)
        self.assertEqual((self.app.step, self.app.part), (0, 1))
        self.assertEqual(self.app.vars["working_csv"].get(), original)
        self.assertEqual(self.app.title_label["style"], "Title.TLabel")
        from workflow.design import COLORS
        self.assertEqual(self.app.hero_icon.itemcget(self.app.hero_symbol, "fill"), COLORS["blue"])

    def test_stepper_supports_keyboard_navigation(self):
        self.app.stepper.move(1)
        self.app.stepper.activate()
        self.assertEqual(self.app.step, 1)
        self.app.stepper.enabled = False
        self.app.stepper.move(1)
        self.app.stepper.activate()
        self.assertEqual(self.app.step, 1)

    def test_corrupt_saved_configuration_loads_with_clear_feedback(self):
        self.app.destroy()
        path = self.root / "settings.json"
        path.write_text("invalid json", encoding="utf-8")
        self.app = App(path)
        self.assertIn("could not be read", self.app.feedback_var.get())

    def test_controls_remain_inside_the_workspace_at_common_sizes(self):
        for width, height in ((1080, 820), (1024, 768), (900, 700)):
            self.app.geometry(f"{width}x{height}")
            for index in range(6):
                for part in range(len(self.app.step_parts[index])):
                    self.app._show_step(index, part)
                    self.app.update()
                    for widget in (self.app.next_button, self.app.title_label,
                                   self.app._visible_part(), self.app.save_button):
                        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                             self.app.winfo_rootx() + self.app.winfo_width())
                        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                             self.app.winfo_rooty() + self.app.winfo_height())
                    content = self.app._visible_part()
                    self.assertGreaterEqual(content.winfo_rooty(),
                                            self.app.hero.winfo_rooty() + self.app.hero.winfo_height(),
                                            (width, height, index, part, content.winfo_height()))
                    self.assertLessEqual(content.winfo_rooty() + content.winfo_height(),
                                         self.app.feedback_label.winfo_rooty(),
                                         (width, height, index, part, content.winfo_height()))


if __name__ == "__main__":
    unittest.main()
