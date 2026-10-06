from __future__ import annotations

import csv
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCES_ROOT = PROJECT_ROOT / "Initial sanitized reference files"


class WakeOutputContractTests(unittest.TestCase):
    def test_detailed_wake_lines_are_classified_for_terminal_suppression(self) -> None:
        from workflow.orchestrator import WAKE_DETAIL

        detailed = (
            "WAKE CYCLE 4: starting visibly from tab 1",
            "WAKE CYCLE 4: VISIBLY VISITED physical tab 2/6",
            "WAKE CYCLE 4 COMPLETE: visibly visited 6/6 active snapshot tab(s)",
            "NEXT WAKE CYCLE: will restart visibly from tab 1",
            "Wake round 10: 3 tab(s) still pending",
        )
        for line in detailed:
            with self.subTest(line=line):
                self.assertRegex(line, WAKE_DETAIL)

    def test_non_wake_results_remain_visible(self) -> None:
        from workflow.orchestrator import WAKE_DETAIL

        visible = (
            "CASE RESULT: tab 2 | change_id 42 | successful",
            "ADAPTIVE PROGRESS: 73/100 successful; 27 remain retryable.",
            "RUN COMPLETE",
        )
        for line in visible:
            with self.subTest(line=line):
                self.assertIsNone(WAKE_DETAIL.search(line))


class BrowserCommandContractTests(unittest.TestCase):
    def test_primary_flow_passes_every_required_browser_path_and_cli_value(self) -> None:
        from workflow.config import WorkflowConfig
        from workflow.orchestrator import WorkflowOrchestrator

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = {
                "project_root": root / "project",
                "source_data_root": root / "source",
                "temporary_batch_dir": root / "temporary",
                "merged_pdf_dir": root / "merged",
                "working_csv": root / "working.csv",
                "source_copy_csv": root / "source-copy.csv",
                "completed_csv": root / "completed.csv",
                "sent_log_csv": root / "sent.csv",
                "instructions_md": root / "instructions.md",
                "analysis_output_dir": root / "analysis",
                "case_size_output_dir": root / "case-sizes",
                "diagnostics_dir": root / "diagnostics",
                "edge_executable": root / "msedge.exe",
                "edge_profile_dir": root / "edge-profile",
            }
            config = WorkflowConfig(
                **{name: str(path) for name, path in paths.items()},
                edge_debug_port=9333,
                start_batch=201,
                batch_count=1,
                cases_to_process=87,
                browser_tabs=4,
                model_policy="3",
                processing_flow="1",
            )
            paths["merged_pdf_dir"].mkdir(parents=True)
            (paths["merged_pdf_dir"] / "merge_status_201_300.json").write_text(
                '{"range_from": 201, "range_to": 300, "results": []}',
                encoding="utf-8",
            )

            calls: list[tuple[str, list[str], dict[str, str] | None, list[str] | None]] = []
            orchestrator = WorkflowOrchestrator(config, lambda *_: None)

            def capture(stage, command, env=None, answers=None):
                calls.append((stage, command, env, answers))
                return 0

            with patch.object(orchestrator, "_run", side_effect=capture), patch(
                "workflow.orchestrator.notify"
            ):
                orchestrator.run_primary(cleanup=False)

            stage, command, env, answers = next(call for call in calls if call[0] == "copilot")
            self.assertEqual(stage, "copilot")
            self.assertEqual(command[:2], [sys.executable, str(REFERENCES_ROOT / "08_open_copilot_dynamic_case_size_batches_v25_useful_upto_V12_sanitized.py")])
            expected_options = {
                "--csv-path": paths["working_csv"],
                "--completed-path": paths["completed_csv"],
                "--log-path": paths["sent_log_csv"],
                "--instructions-path": paths["instructions_md"],
                "--case-files-root": paths["temporary_batch_dir"],
                "--merged-pdfs-root": paths["merged_pdf_dir"],
                "--case-size-output-root": paths["case_size_output_dir"],
                "--profile-dir": paths["edge_profile_dir"],
                "--edge-path": paths["edge_executable"],
            }
            for option, expected in expected_options.items():
                with self.subTest(option=option):
                    index = command.index(option)
                    self.assertEqual(Path(command[index + 1]), expected.resolve())
            for option, expected in {
                "--port": "9333",
                "--tabs": "4",
                "--max-tabs": "4",
                "--cases": "87",
                "--default-model": "GPT-6 Sol",
            }.items():
                index = command.index(option)
                self.assertEqual(command[index + 1], expected)

            self.assertEqual(answers, ["", "1"])
            self.assertEqual(
                env["COPILOT_BASE_MESSAGE_PATH"],
                str(REFERENCES_ROOT / "resources" / "base_message_sanitized.md"),
            )
            self.assertEqual(env["CDD_DIAGNOSTICS_DIR"], str(paths["diagnostics_dir"].resolve()))
            self.assertEqual(env["CDD_PROJECT_ROOT"], str(REFERENCES_ROOT))
            self.assertEqual(env["PYTHONPATH"].split(os.pathsep)[0], str(REFERENCES_ROOT))


class BrowserPersistenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base_message = REFERENCES_ROOT / "resources" / "base_message_sanitized.md"
        cls._old_base_message = os.environ.get("COPILOT_BASE_MESSAGE_PATH")
        os.environ["COPILOT_BASE_MESSAGE_PATH"] = str(base_message)
        sys.path.insert(0, str(REFERENCES_ROOT))
        try:
            cls.implementation = importlib.import_module("resources.implementation_sanitized")
        except Exception as exc:  # pragma: no cover - reports optional dependency/import issues clearly
            raise unittest.SkipTest(f"Browser implementation could not be imported offline: {exc}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            sys.path.remove(str(REFERENCES_ROOT))
        except ValueError:
            pass
        if cls._old_base_message is None:
            os.environ.pop("COPILOT_BASE_MESSAGE_PATH", None)
        else:
            os.environ["COPILOT_BASE_MESSAGE_PATH"] = cls._old_base_message

    def test_log_schema_and_pending_journal_contract(self) -> None:
        implementation = self.implementation
        self.assertEqual(
            implementation.LOG_FIELDS,
            ["change_id", "InterestedPartyId", "fully_sent_at_local", "run_number", "change_id_status"],
        )
        self.assertEqual(
            implementation.FINAL_STATUSES,
            {"successful", "failed", "inconclusive_review_needed", "Failed_to_add_attachments"},
        )

        with tempfile.TemporaryDirectory() as folder:
            log_path = Path(folder) / "results.csv"
            store = implementation.CaseLogStore(log_path)
            self.assertEqual(store.journal_path.name, "results.csv.pending-transitions.csv")

            row = {"change_id": "00042", "InterestedPartyId": "IP-7"}
            store.upsert(row, "sent", 1)
            store.upsert(row, "failed", 1)
            store.upsert(row, "inconclusive_review_needed", 2)
            key = ("42", "ip-7")
            self.assertEqual(store.load()[key].status, "failed")

            store.upsert(row, "successful", 3)
            record = store.load()[key]
            self.assertEqual(record.status, "successful")
            self.assertEqual(record.run_number, "3")
            with log_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, implementation.LOG_FIELDS)
                self.assertEqual(len(list(reader)), 1)

    def test_journal_is_merged_as_authoritative_recovery_input(self) -> None:
        implementation = self.implementation
        with tempfile.TemporaryDirectory() as folder:
            log_path = Path(folder) / "results.csv"
            store = implementation.CaseLogStore(log_path)
            store.upsert({"change_id": "8", "InterestedPartyId": "A"}, "sent", 1)
            journal_record = implementation.CaseLogRecord(
                "8", "A", "2026-01-01T00:00:00+00:00", "2", "successful"
            )
            store._write_csv(store.journal_path, [journal_record])

            loaded = store.load(compact=False)
            self.assertEqual(loaded[("8", "a")].status, "successful")
            self.assertEqual(loaded[("8", "a")].run_number, "2")


if __name__ == "__main__":
    unittest.main()
