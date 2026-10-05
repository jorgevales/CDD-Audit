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
                           ("batch_count", ""), ("model_policy", "invalid")):
            self.assertTrue(validate_run(dict(values, **{key: value})), key)


class GuidedInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        try:
            self.app = App(self.root / "settings.json")
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
        self.assertEqual(self.app.step, 1)
        self.app._navigate(0)
        self.assertEqual(self.app.vars["working_csv"].get(), original)
        self.assertTrue((self.root / "settings.json").is_file())

    def test_missing_required_input_blocks_continue_and_direct_navigation(self):
        self.app.vars["working_csv"].set("")
        self.app._continue()
        self.assertEqual(self.app.step, 0)
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
        from workflow.design import COLORS
        self.assertEqual(str(self.app.stage_labels["copilot"]["foreground"]), COLORS["blue"])

    def test_master_stage_remains_accessible_without_browser_readiness(self):
        self.app.vars["source_data_root"].set("")
        self.app._open_master()
        self.assertEqual(self.app.step, 5)
        self.assertEqual(str(self.app.master_button["state"]), "normal")
        self.assertEqual(str(self.app.start_button["state"]), "disabled")

    def test_keyboard_focus_reveals_fields_below_the_visible_area(self):
        self.app.geometry("980x700")
        self.app._show_step(1)
        self.app.update()
        form, canvas = self.app.forms[1]
        last_field = form.winfo_children()[-1]
        self.app._reveal_field(canvas, last_field)
        self.assertGreater(canvas.yview()[0], 0)

    def test_corrupt_saved_configuration_loads_with_clear_feedback(self):
        self.app.destroy()
        path = self.root / "settings.json"
        path.write_text("invalid json", encoding="utf-8")
        self.app = App(path)
        self.assertIn("could not be read", self.app.feedback_var.get())

    def test_controls_remain_inside_the_workspace_at_common_sizes(self):
        for width, height in ((1180, 820), (1024, 768), (980, 700)):
            self.app.geometry(f"{width}x{height}")
            for index in range(6):
                self.app._show_step(index)
                self.app.update()
                for widget in (self.app.next_button, self.app.title_label,
                               self.app.pages[index], self.app.save_button):
                    self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                         self.app.winfo_rootx() + self.app.winfo_width())
                    self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                         self.app.winfo_rooty() + self.app.winfo_height())


if __name__ == "__main__":
    unittest.main()
