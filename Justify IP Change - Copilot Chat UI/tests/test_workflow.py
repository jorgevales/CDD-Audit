from __future__ import annotations

import asyncio
import csv
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import csv
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from justify_ip_change_copilot_chat_ui.application import execute_queue
from justify_ip_change_copilot_chat_ui.attachments import build_attachment_plan, merged_pdf_parts
from justify_ip_change_copilot_chat_ui.batch_discovery import batch_range_groups, completed_output_file, describe_batch_ranges, discover_batches
from justify_ip_change_copilot_chat_ui.case_discovery import discover_case_folders, match_batch_cases
from justify_ip_change_copilot_chat_ui.copilot_ui import CaseOutcome, SimulationAdapter
from justify_ip_change_copilot_chat_ui.cli import _eligible_batches, _select_workspace, main, parse_args, run_cli
from justify_ip_change_copilot_chat_ui.errors import BatchLockedError, ResourceError, WorkspaceError
from justify_ip_change_copilot_chat_ui.error_reporting import sanitize_message, write_error_report
from justify_ip_change_copilot_chat_ui.errors import PostSendCancelledError
from justify_ip_change_copilot_chat_ui.identity import windows_account_name
from justify_ip_change_copilot_chat_ui.logs import BatchLockSet, CaseLog, LOG_FILENAME
from justify_ip_change_copilot_chat_ui.models import BatchInfo, CaseRecord
from justify_ip_change_copilot_chat_ui.paths import LocalSimulationResolver, normalise_windows_path_text, strip_extended_prefix
from justify_ip_change_copilot_chat_ui.queue_builder import build_preflight
from justify_ip_change_copilot_chat_ui.resources import REQUIRED_CASE_COLUMNS, load_case_workbook
from justify_ip_change_copilot_chat_ui.workspace import validate_runtime_resources, validate_workspace


def row_for(change_id: int, party_id: int) -> dict[str, str]:
    row = {name: f"synthetic-{name}" for name in REQUIRED_CASE_COLUMNS}
    row["change_id"] = f"{change_id:05d}"
    row["InterestedPartyId"] = str(party_id)
    row["ChangedFields"] = "[SyntheticField]"
    row["PreviousValues"] = "SyntheticField: before"
    row["NewValues"] = "SyntheticField: after"
    row["FieldChangeCount"] = "1"
    return row


class Fixture:
    def __init__(self, root: Path, counts=(3, 2)) -> None:
        self.root = root / "source elsewhere" / "deep" / "shared data"
        self.root.mkdir(parents=True)
        self.working = self.root / "Working Space"
        self.resources = self.working / "Copilot resources"
        self.users = self.working / "Users"
        self.merged = self.resources / "Temporary merged pdfs"
        self.merged.mkdir(parents=True)
        self.users.mkdir(parents=True)
        (self.resources / "IP_Review_LLM_Instructions.md").write_text("Synthetic instructions", encoding="utf-8")
        (self.resources / "base_message.md").write_text("Synthetic base message", encoding="utf-8")
        self.rows = []
        next_id = 1
        self.batches = []
        for count in counts:
            low = next_id
            high = next_id + 99
            batch = self.root / f"Batch_{low:05d}_to_{high:05d}"
            batch.mkdir()
            self.batches.append(batch)
            for offset in range(count):
                row = row_for(next_id + offset, 700000 + next_id + offset)
                self.rows.append(row)
                folder_name = f"Change_{row['change_id']}_Interested_Party_{row['InterestedPartyId']}"
                case = batch / folder_name
                case.mkdir()
                (case / f"synthetic_{row['change_id']}.txt").write_text("fictional content", encoding="utf-8")
                (self.merged / f"{folder_name}_part_1.pdf").write_bytes(b"%PDF-1.4 synthetic")
            next_id += 100
        self.write_workbook(self.rows)

    def write_workbook(self, rows) -> None:
        with (self.resources / "07_Interested_Parties_Changes_15576.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REQUIRED_CASE_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_deep_path_with_spaces_validates_and_derives(self):
        workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        self.assertTrue(os.path.samefile(workspace.data_root, self.fixture.root))
        self.assertTrue(os.path.samefile(workspace.users, self.fixture.users))
        self.assertTrue(os.path.samefile(workspace.merged_pdfs, self.fixture.merged))

    def test_wrong_final_folder_rejected(self):
        with self.assertRaisesRegex(WorkspaceError, "Copilot resources"):
            validate_workspace(self.fixture.working, LocalSimulationResolver(Path(self.temp.name)))

    def test_missing_users_rejected(self):
        self.fixture.users.rmdir()
        with self.assertRaisesRegex(WorkspaceError, "Users"):
            validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))

    def test_previously_confirmed_workspace_is_reused_without_prompt(self):
        args = parse_args(["--simulation-root", self.temp.name])
        with patch(
            "justify_ip_change_copilot_chat_ui.cli.load_last_workspace",
            return_value=str(self.fixture.resources),
        ), patch("builtins.input") as prompt, patch("justify_ip_change_copilot_chat_ui.cli.save_last_workspace") as save:
            workspace = _select_workspace(args)
        self.assertTrue(os.path.samefile(workspace.selected, self.fixture.resources))
        prompt.assert_not_called()
        save.assert_not_called()

    def test_workspace_is_available_to_error_reporting_when_remember_write_is_full(self):
        args = parse_args(["--workspace", str(self.fixture.resources)])
        with patch("justify_ip_change_copilot_chat_ui.cli.WindowsSDriveResolver", return_value=LocalSimulationResolver(Path(self.temp.name))), patch(
            "justify_ip_change_copilot_chat_ui.cli.save_last_workspace", side_effect=OSError(28, "No space left on device")
        ), patch("justify_ip_change_copilot_chat_ui.cli.write_error_report", return_value=self.fixture.working / "Error logs" / "error.json") as report:
            workspace = _select_workspace(args)
        self.assertTrue(os.path.samefile(workspace.selected, self.fixture.resources))
        report.assert_called_once()
        self.assertEqual(report.call_args.kwargs["stage"], "workspace_remember")

    def test_all_missing_resources_reported_together(self):
        workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        (self.fixture.resources / "base_message.md").unlink()
        (self.fixture.resources / "IP_Review_LLM_Instructions.md").unlink()
        with self.assertRaises(ResourceError) as caught:
            validate_runtime_resources(workspace)
        self.assertIn("base_message.md", str(caught.exception))
        self.assertIn("IP_Review_LLM_Instructions.md", str(caught.exception))

    def test_windows_normalisation_and_extended_unc(self):
        self.assertEqual(normalise_windows_path_text(r'S:/A/B'), r"S:\A\B")
        self.assertEqual(strip_extended_prefix(r"\\?\UNC\server\share\folder"), r"\\server\share\folder")

    def test_windows_account_name_is_sanitised(self):
        with patch("getpass.getuser", return_value=r"DOMAIN\synthetic.user"):
            self.assertEqual(windows_account_name(), "synthetic.user")

    def test_error_report_is_workspace_local_and_redacted(self):
        workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        raw = r"failure at C:\Users\Jane Doe\Documents\secret.txt and /tmp/private.txt"
        self.assertNotIn("C:\\Users", sanitize_message(raw))
        with patch.dict(os.environ, {"USERNAME": "Jane Doe", "COMPUTERNAME": "VDI-01"}, clear=False):
            path = write_error_report(workspace, RuntimeError(raw), stage="edge_startup", batch=self.fixture.batches[0].name)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent.name, "Error logs")
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = path.read_text(encoding="utf-8")
        self.assertEqual(payload["schema"], "cdd-audit-error-report-v1")
        self.assertEqual(payload["stage"], "edge_startup")
        self.assertEqual(set(payload["free_space_bytes"]), {"workspace_volume", "local_temp_volume", "local_appdata_volume"})
        self.assertNotIn("C:\\Users", text)
        self.assertNotIn("Jane Doe", text)
        self.assertNotIn("VDI-01", text)
        self.assertIn("diagnostics", payload)
        self.assertIn("frames", payload)
        self.assertIn("error_ref", payload)
        self.assertNotIn("traceback", payload)
        other = write_error_report(workspace, RuntimeError("different private exception text"), stage="edge_startup")
        self.assertEqual(payload["error_ref"], json.loads(other.read_text(encoding="utf-8"))["error_ref"])

    def test_error_report_keeps_safe_stage_details_and_discards_raw_values(self):
        workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        error = RuntimeError(r"private name and C:\Users\Jane Doe\secret.txt")
        error.diagnostic_stage = "copilot_startup"
        error.diagnostics = {"copilot": {"phase": "copilot_readiness", "cdp_connect_attempts": 2, "raw": r"C:\Users\Jane Doe\secret.txt"}}
        path = write_error_report(workspace, error, stage="cli_failure")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["stage"], "copilot_startup")
        self.assertEqual(payload["diagnostics"]["copilot"]["phase"], "copilot_readiness")
        self.assertEqual(payload["diagnostics"]["copilot"]["cdp_connect_attempts"], 2)
        self.assertNotIn("raw", payload["diagnostics"]["copilot"])
        self.assertNotIn("Jane Doe", path.read_text(encoding="utf-8"))

    def test_error_report_retains_bounded_readiness_evidence_without_page_content(self):
        workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        private = r"C:\Users\Jane Doe\private\case 12345.txt"
        error = RuntimeError(f"Copilot page contained {private}")
        error.diagnostic_stage = "copilot_startup"
        error.diagnostics = {
            "copilot": {
                "phase": "copilot_readiness",
                "readiness_method": "new_tab_navigation_retry",
                "readiness_attempts": [
                    {"method": "retained_tab", "result": "not_ready", "elapsed_ms": 1200},
                    {"method": "new_tab_navigation_retry", "result": "composer_visible", "elapsed_ms": 350},
                    {"method": private, "result": "not_ready", "elapsed_ms": 1},
                ] + [{"method": private} for _ in range(20)],
                "readiness_elapsed_ms": 1550,
                "readiness_checks": 7,
                "page_category": "login",
                "document_state": "interactive",
                "editor_selector_counts": {
                    "primary_editor": 0,
                    "testid_editor": 1,
                    "role_textbox": 0,
                    "message_textarea": 0,
                    "private_selector": private,
                },
                "frame_count": 1,
                "editor_in_frame": False,
                "login_indicator": True,
                "access_denied_indicator": False,
                "navigation_outcome": "auth",
                "last_navigation_error_type": "TimeoutError",
                "last_readiness_error_type": "TargetClosedError",
                "url": "https://m365.cloud.microsoft/chat?account=Jane Doe",
                "page_text": private,
            },
            "private_key": private,
        }
        path = write_error_report(workspace, error, stage="cli_failure")
        payload = json.loads(path.read_text(encoding="utf-8"))
        copilot = payload["diagnostics"]["copilot"]
        self.assertEqual(copilot["readiness_method"], "new_tab_navigation_retry")
        self.assertEqual(copilot["editor_selector_counts"]["testid_editor"], 1)
        self.assertEqual(copilot["navigation_outcome"], "auth")
        self.assertEqual(copilot["last_navigation_error_type"], "TimeoutError")
        self.assertEqual(copilot["last_readiness_error_type"], "TargetClosedError")
        self.assertEqual(copilot["readiness_attempts"][0]["result"], "not_ready")
        self.assertEqual(copilot["readiness_attempts"][2]["method"], "<redacted>")
        self.assertEqual(len(copilot["readiness_attempts"]), 12)
        self.assertNotIn("private_selector", copilot["editor_selector_counts"])
        self.assertNotIn("url", copilot)
        self.assertNotIn("page_text", copilot)
        self.assertNotIn("private_key", payload["diagnostics"])
        self.assertNotIn("Jane Doe", path.read_text(encoding="utf-8"))

    def test_unexpected_startup_failure_still_creates_complete_report(self):
        workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        with patch("justify_ip_change_copilot_chat_ui.cli.run_cli", side_effect=RuntimeError("private exception data")), patch(
            "justify_ip_change_copilot_chat_ui.cli._LAST_WORKSPACE", workspace
        ), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([]), 1)
        reports = list((self.fixture.working / "Error logs").glob("error_*.json"))
        self.assertEqual(len(reports), 1)
        payload = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["stage"], "cli_failure")
        self.assertIn("frames", payload)
        self.assertNotIn("private exception data", reports[0].read_text(encoding="utf-8"))


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_numeric_batch_order_and_unrelated_folder_ignored(self):
        (self.fixture.root / "Batch_1001_to_1100").mkdir()
        (self.fixture.root / "Batch_201_to_300").mkdir()
        (self.fixture.root / "Not_A_Batch").mkdir()
        ranges = [(item.range_from, item.range_to) for item in discover_batches(self.fixture.root)]
        self.assertEqual(ranges, [(1, 100), (101, 200), (201, 300), (1001, 1100)])

    def test_batch_range_reporting_collapses_contiguous_ranges_and_strips_padding(self):
        names = ["Batch_01001_to_01100", "Batch_01101_to_01200", "Batch_01201_to_01300", "Batch_02001_to_02100"]
        self.assertEqual(batch_range_groups(names), [(1001, 1300), (2001, 2100)])
        self.assertEqual(
            describe_batch_ranges(names, verb="are locked"),
            "Batches 1001 to 1300, 2001 to 2100 are locked.",
        )

    def test_batch_range_reporting_omits_excel_filename(self):
        message = describe_batch_ranges(["Batch_00001_to_00100"], verb="are excluded because a completed Excel output exists")
        self.assertEqual(message, "Batches 1 to 100 are excluded because a completed Excel output exists.")

    def test_discovery_errors_are_reported_as_ranges(self):
        batches = [BatchInfo(Path(f"Batch_{start:05d}_to_{start + 99:05d}"), start, start + 99) for start in (1, 101, 201)]
        with patch("justify_ip_change_copilot_chat_ui.cli.match_batch_cases", return_value=([], ["synthetic discovery error"])), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(_eligible_batches(batches, [], {}), [])
        self.assertIn("Batches 1 to 300 have cases blocked by discovery errors.", output.getvalue())

    def test_direct_ips_excel_completes_batch_case_insensitive(self):
        marker = self.fixture.batches[0] / "iPs_Completed_Analysis.XLSX"
        marker.write_bytes(b"synthetic")
        self.assertEqual(completed_output_file(self.fixture.batches[0]), marker)

    def test_nested_ips_excel_does_not_complete_batch(self):
        case = next(item for item in self.fixture.batches[0].iterdir() if item.is_dir())
        (case / "IPs_case_input.xlsx").write_bytes(b"synthetic")
        self.assertIsNone(completed_output_file(self.fixture.batches[0]))

    def test_temporary_excel_lock_file_ignored(self):
        (self.fixture.batches[0] / "~$IPs_output.xlsx").write_bytes(b"synthetic")
        self.assertIsNone(completed_output_file(self.fixture.batches[0]))

    def test_final_batch_fewer_than_100_is_valid(self):
        records = load_case_workbook(self.fixture.resources / "07_Interested_Parties_Changes_15576.csv")
        selected = [row for row in records if 101 <= int(row.change_id) <= 200]
        self.assertEqual(len(selected), 2)

    def test_case_folder_without_workbook_row_is_blocked(self):
        folder = self.fixture.batches[0] / "Change_00099_Interested_Party_799999"
        folder.mkdir()
        records = load_case_workbook(self.fixture.resources / "07_Interested_Parties_Changes_15576.csv")
        matched, blocked = match_batch_cases(discover_batches(self.fixture.root)[0], records)
        self.assertEqual(len(matched), 3)
        self.assertTrue(any("no matching runtime CSV row" in message for message in blocked))

    def test_out_of_range_case_folder_is_blocked(self):
        folder = self.fixture.batches[0] / "Change_00101_Interested_Party_700101"
        folder.mkdir()
        records = load_case_workbook(self.fixture.resources / "07_Interested_Parties_Changes_15576.csv")
        _, blocked = match_batch_cases(discover_batches(self.fixture.root)[0], records)
        self.assertTrue(any("outside the batch" in message for message in blocked))

    def test_canonical_duplicate_case_folders_are_rejected(self):
        existing = next(item for item in self.fixture.batches[0].iterdir() if item.is_dir())
        duplicate = self.fixture.batches[0] / existing.name.replace("Change_00001_", "Change_1_")
        duplicate.mkdir()
        with self.assertRaisesRegex(ResourceError, "duplicate case folders"):
            discover_case_folders(discover_batches(self.fixture.root)[0])


class AttachmentAndWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name), counts=(1,))
        self.record = load_case_workbook(self.fixture.resources / "07_Interested_Parties_Changes_15576.csv")[0]
        self.folder = self.fixture.batches[0] / self.record.folder_name

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_part_sequence_and_plan(self):
        plan = build_attachment_plan(
            self.record,
            self.folder,
            self.fixture.merged,
            self.fixture.resources / "IP_Review_LLM_Instructions.md",
        )
        self.assertEqual(plan.merged_pdf_names, (self.record.folder_name + "_part_1.pdf",))
        self.assertEqual(len(plan.paths), 3)

    def test_missing_part_is_blocked(self):
        part1 = self.fixture.merged / (self.record.folder_name + "_part_1.pdf")
        part1.rename(self.fixture.merged / (self.record.folder_name + "_part_2.pdf"))
        with self.assertRaisesRegex(ResourceError, "continuous"):
            merged_pdf_parts(self.record, self.fixture.merged)

    def test_ambiguous_part_is_blocked_case_insensitively(self):
        duplicate = self.fixture.merged / (self.record.folder_name + "_part_01.pdf")
        duplicate.write_bytes(b"%PDF duplicate")
        with self.assertRaisesRegex(ResourceError, "Ambiguous"):
            merged_pdf_parts(self.record, self.fixture.merged)

    def test_duplicate_workbook_case_rejected(self):
        self.fixture.write_workbook([self.fixture.rows[0], self.fixture.rows[0]])
        with self.assertRaisesRegex(ResourceError, "duplicate"):
            load_case_workbook(self.fixture.resources / "07_Interested_Parties_Changes_15576.csv")


class QueueLogAndLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name))
        self.workspace = validate_workspace(self.fixture.resources, LocalSimulationResolver(Path(self.temp.name)))
        self.records = load_case_workbook(self.fixture.resources / "07_Interested_Parties_Changes_15576.csv")
        self.batches = discover_batches(self.fixture.root)
        self.log_path = self.fixture.users / "synthetic.user" / LOG_FILENAME
        self.log = CaseLog(self.log_path, "synthetic.user")

    def tearDown(self):
        self.temp.cleanup()

    def preflight(self, batches=None, retry_review=False):
        return build_preflight(
            batches or self.batches,
            self.records,
            self.log.latest(),
            merged_root=self.fixture.merged,
            instructions_path=self.fixture.resources / "IP_Review_LLM_Instructions.md",
            base_message="Synthetic base",
            retry_review_required=retry_review,
        )

    def test_multiple_batches_form_one_deterministic_continuous_queue(self):
        report = self.preflight(list(reversed(self.batches)))
        self.assertEqual([int(item.case.change_id) for item in report.queue], [1, 2, 3, 101, 102])

    def test_success_is_excluded_failed_and_interrupted_retry(self):
        for record, status in zip(self.records[:3], ("successful", "failed", "interrupted")):
            self.log.append(record, status, batch=self.batches[0].name, attachment_count=2, run_id="run")
        report = self.preflight()
        ids = {int(item.case.change_id) for item in report.queue}
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)
        self.assertIn(3, ids)

    def test_uncertain_latest_status_is_automatically_retried(self):
        self.log.append(self.records[0], "requires_review", batch=self.batches[0].name, attachment_count=2, run_id="run")
        self.assertIn(1, {int(item.case.change_id) for item in self.preflight().queue})

    def test_sent_latest_status_is_automatically_retried(self):
        self.log.append(self.records[0], "sent", batch=self.batches[0].name, attachment_count=2, run_id="run")
        self.assertIn(1, {int(item.case.change_id) for item in self.preflight().queue})

    def test_all_success_without_output_warns_and_queues_nothing(self):
        first_batch_records = self.records[:3]
        for record in first_batch_records:
            self.log.append(record, "successful", batch=self.batches[0].name, attachment_count=2, run_id="run")
        report = self.preflight([self.batches[0]])
        self.assertFalse(report.queue)
        self.assertTrue(any("REQUIRES REVIEW" in value for value in report.summaries[0].warnings))

    def test_log_is_append_only_and_latest_status_controls_resume(self):
        record = self.records[0]
        self.log.append(record, "failed", batch=self.batches[0].name, attachment_count=2, run_id="one")
        self.log.append(record, "successful", batch=self.batches[0].name, attachment_count=2, run_id="two")
        with self.log_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.log.latest()[record.canonical_key].status, "successful")

    def test_existing_sanitized_five_column_log_is_supported(self):
        self.log_path.parent.mkdir(parents=True)
        with self.log_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["change_id", "InterestedPartyId", "fully_sent_at_local", "run_number", "change_id_status"])
            writer.writeheader()
            writer.writerow({"change_id": self.records[0].change_id, "InterestedPartyId": self.records[0].interested_party_id, "fully_sent_at_local": "synthetic", "run_number": "1", "change_id_status": "successful"})
        self.assertEqual(len(self.log.latest()), 1)
        self.log.append(self.records[1], "failed", batch=self.batches[0].name, attachment_count=2, run_id="new")
        with self.log_path.open("r", encoding="utf-8-sig", newline="") as handle:
            fields = csv.DictReader(handle).fieldnames
        self.assertIn("source_batch", fields)

    def test_batch_lock_identifies_current_holder_and_releases(self):
        first = BatchLockSet(self.workspace.working_space, [self.batches[0].name], "first.user", "one")
        second = BatchLockSet(self.workspace.working_space, [self.batches[0].name], "second.user", "two")
        first.acquire()
        try:
            with self.assertRaises(BatchLockedError) as caught:
                second.acquire()
            self.assertIn("first.user", str(caught.exception))
            self.assertIn(self.batches[0].name, str(caught.exception))
        finally:
            first.release()
        second.acquire()
        second.release()

    def test_contested_multi_batch_lock_is_all_or_nothing(self):
        occupied = BatchLockSet(self.workspace.working_space, [self.batches[1].name], "holder", "one")
        contender = BatchLockSet(self.workspace.working_space, [b.name for b in self.batches], "other", "two")
        occupied.acquire()
        try:
            with self.assertRaises(BatchLockedError):
                contender.acquire()
            first_lock = self.workspace.working_space / ".justify-ip-change-locks" / f"{self.batches[0].name}.lock"
            self.assertFalse(first_lock.exists())
        finally:
            occupied.release()

    def test_simulated_end_to_end_and_resume(self):
        report = self.preflight()
        outcomes = {report.queue[1].key: "failed"}
        adapter = SimulationAdapter(outcomes)
        result = asyncio.run(execute_queue(report, self.workspace, self.log, adapter, user="synthetic.user", run_id="run-one"))
        self.assertEqual(result.processed, 5)
        self.assertEqual(result.successful, 4)
        resumed = self.preflight()
        self.assertEqual([item.key for item in resumed.queue], [report.queue[1].key])

    def test_interruption_is_durably_logged_and_resumable(self):
        report = self.preflight([self.batches[0]])

        class InterruptingAdapter(SimulationAdapter):
            async def process(self, item):
                raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(execute_queue(report, self.workspace, self.log, InterruptingAdapter(), user="synthetic.user", run_id="interrupt"))
        latest = self.log.latest()
        self.assertEqual(latest[report.queue[0].key].status, "interrupted")
        self.assertIn(report.queue[0].key, [item.key for item in self.preflight([self.batches[0]]).queue])

    def test_post_send_interruption_is_review_logged_and_auto_resumed(self):
        report = self.preflight([self.batches[0]])

        class PostSendInterruptingAdapter(SimulationAdapter):
            async def process(self, item):
                raise PostSendCancelledError()

        with self.assertRaises(PostSendCancelledError):
            asyncio.run(
                execute_queue(
                    report,
                    self.workspace,
                    self.log,
                    PostSendInterruptingAdapter(),
                    user="synthetic.user",
                    run_id="post-send-interrupt",
                )
            )
        latest = self.log.latest()
        self.assertEqual(latest[report.queue[0].key].status, "requires_review")
        self.assertIn(report.queue[0].key, [item.key for item in self.preflight([self.batches[0]]).queue])


class HundredCaseFixtureTest(unittest.TestCase):
    def test_exactly_100_cases_and_final_partial_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), counts=(100, 7))
            records = load_case_workbook(fixture.resources / "07_Interested_Parties_Changes_15576.csv")
            batches = discover_batches(fixture.root)
            report = build_preflight(
                batches,
                records,
                {},
                merged_root=fixture.merged,
                instructions_path=fixture.resources / "IP_Review_LLM_Instructions.md",
                base_message="Synthetic base",
            )
            self.assertEqual(len(report.queue), 107)
            self.assertEqual(report.summaries[0].total_cases, 100)
            self.assertEqual(report.summaries[1].total_cases, 7)


class CLIDryRunTest(unittest.TestCase):
    def test_top_level_dry_run_has_no_operational_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            args = parse_args(
                [
                    "--workspace",
                    str(fixture.resources),
                    "--simulation-root",
                    directory,
                    "--batches",
                    fixture.batches[0].name,
                    fixture.batches[1].name,
                    "--dry-run",
                ]
            )
            output = io.StringIO()
            with patch(
                "justify_ip_change_copilot_chat_ui.cli.windows_account_name",
                return_value="synthetic.user",
            ), contextlib.redirect_stdout(output):
                result = run_cli(args)
            self.assertEqual(result, 0)
            text = output.getvalue()
            self.assertIn("Remaining eligible cases: 5", text)
            self.assertIn("Dry run complete", text)
            for hidden_line in (
                "Selected workspace:",
                "Copilot resources:",
                "Users folder:",
                "Windows account:",
                "User log:",
                "Expected attachment operations:",
            ):
                self.assertNotIn(hidden_line, text)
            self.assertFalse((fixture.users / "synthetic.user" / LOG_FILENAME).exists())
            self.assertFalse((fixture.working / ".justify-ip-change-locks").exists())


if __name__ == "__main__":
    unittest.main()
