"""Real HTTP boundary and workflow safety tests without starting Office/Copilot."""
import http.client
import json
import tempfile
import threading
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from workflow.config import WorkflowConfig
from workflow.preflight import Check
from workflow.web_server import ApiError, LocalServer, WorkflowService, run_model_check


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = WorkflowService(Path(self.temp.name) / "config.json")
        self.server = LocalServer(("127.0.0.1", 0), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        default = {"X-Workflow-Token": self.server.token}
        if data is not None:
            default["Content-Type"] = "application/json"
        default.update(headers or {})
        connection.request(method, path, json.dumps(data) if data is not None else None, default)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, json.loads(body)

    def test_api_rejects_missing_token_cross_origin_and_host_rebinding(self):
        for headers in ({"X-Workflow-Token": ""}, {"Origin": "https://example.com"}, {"Host": "evil.example"}):
            status, _ = self.request("GET", "/api/state", headers=headers)
            self.assertEqual(status, 403)
        self.assertEqual(self.request("GET", "/api/state")[0], 200)

    def test_config_change_invalidates_preflight_and_busy_blocks_mutation(self):
        self.service.ready_config = asdict(self.service.config)
        values = {"browser_tabs": 2}
        self.assertEqual(self.request("POST", "/api/config", {"config": values})[0], 200)
        self.assertIsNone(self.service.ready_config)
        self.service.busy = True
        self.assertEqual(self.request("POST", "/api/config", {"config": values})[0], 409)
        self.assertEqual(self.request("POST", "/api/shutdown", {})[0], 409)

    def test_run_requires_same_checked_config_and_acknowledgements(self):
        config = self.service.config
        with self.assertRaises(ApiError):
            self.service.start(config, {"office_acknowledged": True})
        self.service.ready_config = asdict(config)
        with self.assertRaises(ApiError):
            self.service.start(config, {})
        with self.assertRaises(ApiError):
            self.service.start(config, {"office_acknowledged": True, "cleanup": True})
        changed = self.service.collect({"browser_tabs": 2})
        with self.assertRaises(ApiError):
            self.service.start(changed, {"office_acknowledged": True})

    def test_preflight_runs_off_http_thread_and_publishes_readiness(self):
        gate = threading.Event()
        with patch("workflow.web_server.validate_field", return_value=(True, "Ready")), patch(
            "workflow.web_server.run_preflight", side_effect=lambda _: (gate.wait(3), [Check("ok", "test", "Ready")])[1]
        ):
            self.service.preflight(self.service.config)
            self.assertTrue(self.service.state()["checking"])
            self.assertEqual(self.request("GET", "/api/state")[0], 200)
            gate.set()
            self.service.worker.join(3)
            self.assertTrue(self.service.state()["ready"])
            self.assertFalse(self.service.state()["busy"])

    def test_cleanup_preview_limits_targets_to_recognised_out_of_range(self):
        root = Path(self.temp.name)
        temporary = root / "temporary"
        merged = root / "merged"
        temporary.mkdir(); merged.mkdir()
        for name in ("Change_1_active", "Change_101_old", "unrelated"):
            (temporary / name).mkdir()
        for name in ("Change_1_active.pdf", "Change_101_old.pdf", "other.pdf", "Change_101.txt"):
            (merged / name).write_text("test")
        config = self.service.collect({"temporary_batch_dir": str(temporary), "merged_pdf_dir": str(merged)})
        preview = self.service.cleanup_preview(config)
        self.assertEqual(preview["count"], 2)
        self.assertTrue(all("Change_101" in path for path in preview["targets"]))

    def test_events_are_bounded_and_cursor_returns_only_new_messages(self):
        for index in range(1000):
            self.service.emit("progress", str(index))
        state = self.service.state(995)
        self.assertEqual(len(self.service.events), 300)
        self.assertEqual(len(state["events"]), 5)
        self.assertEqual(state["cursor"], 1000)

    def test_stop_uses_orchestrator_safe_stage_request(self):
        from unittest.mock import Mock
        self.service.orchestrator = Mock()
        self.service.orchestrator.state.status = "running"
        self.service.busy = True
        self.service.mode = "primary"
        self.assertEqual(self.request("POST", "/api/stop", {})[0], 200)
        self.service.orchestrator.request_stop.assert_called_once()

    def test_invalid_config_types_and_fractional_numbers_are_rejected(self):
        for config in ({"browser_tabs": True}, {"browser_tabs": 2.5}, {"diagnostic_mode": "false"}, {"edge_debug_port": 70000}, {"unknown": 1}):
            self.assertEqual(self.request("POST", "/api/config", {"config": config})[0], 400)

    def test_stale_client_lease_preserves_active_run_then_closes_idle_server(self):
        import time
        expired = threading.Event()
        self.server.last_contact = time.monotonic() - 10
        self.service.busy = True
        with patch.object(self.server, "shutdown", side_effect=expired.set):
            watcher = threading.Thread(target=self.server.watch_lease, kwargs={"timeout": 1, "interval": .01})
            watcher.start()
            self.assertFalse(expired.wait(.06), "An active workflow must survive a closed browser")
            with self.service.lock:
                self.service.busy = False
            self.assertTrue(expired.wait(1))
            watcher.join(1)

    def test_model_check_is_on_demand_async_and_excludes_other_operations(self):
        gate = threading.Event()
        report = {"status": "verified", "models": [{"value": "GPT-6 Sol", "selected": True, "selection_ms": 230}]}
        def check(_):
            gate.wait(3)
            return report
        with patch("workflow.web_server.run_model_check", side_effect=check):
            self.assertIsNone(self.service.model_checks)
            status, body = self.request("POST", "/api/check-models", {"config": {}})
            self.assertEqual(status, 200)
            self.assertTrue(body["state"]["checking"])
            self.assertEqual(self.request("POST", "/api/preflight", {"config": {}})[0], 409)
            self.assertEqual(self.request("POST", "/api/check-models", {"config": {}})[0], 409)
            gate.set()
            self.service.worker.join(3)
            self.assertEqual(self.service.state()["model_checks"], report)
            self.assertFalse(self.service.state()["busy"])

    def test_model_check_subprocess_returns_partial_report_and_removes_temporary_files(self):
        import subprocess
        report = {"status": "partial", "models": [{"value": "GPT-6 Sol", "selected": False}]}
        output_path = None
        def execute(command, **options):
            nonlocal output_path
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(options["timeout"], 120)
            self.assertEqual(options["stdout"], subprocess.DEVNULL)
            self.assertEqual(options["stderr"], subprocess.DEVNULL)
            return subprocess.CompletedProcess(command, 1)
        with patch("workflow.web_server.subprocess.run", side_effect=execute):
            self.assertEqual(run_model_check(self.service.config_path), report)
        self.assertFalse(output_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
