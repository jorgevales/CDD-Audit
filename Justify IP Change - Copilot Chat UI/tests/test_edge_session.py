from __future__ import annotations

import contextlib
import asyncio
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from justify_ip_change_copilot_chat_ui.edge_session import EdgeSession, _profile_argument, get_cdp_version
from justify_ip_change_copilot_chat_ui.errors import CopilotUIError
from justify_ip_change_copilot_chat_ui.profile_storage import default_edge_profile
from justify_ip_change_copilot_chat_ui.copilot_ui import PlaywrightCopilotAdapter


class EdgeSessionTests(unittest.TestCase):
    def test_default_profile_uses_personal_onedrive_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"OneDriveCommercial": directory}):
                profile = default_edge_profile()
            self.assertTrue(profile.is_relative_to(Path(directory).resolve()))
            self.assertEqual(profile.parent.name, "edge-profiles")

    def test_windows_quoted_profile_argument_with_spaces(self):
        profile = Path(r"C:\Users\Example Person\AppData\Local\CDD Audit\EdgeProfile")
        self.assertEqual(_profile_argument(f'msedge.exe "--user-data-dir={profile}"'), profile)
        self.assertEqual(_profile_argument(f'msedge.exe --user-data-dir="{profile}"'), profile)

    def test_real_edge_cdp_identity_is_accepted(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return json.dumps({
                    "Browser": "Edg/132.0.2957.127",
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9445/devtools/browser/test",
                }).encode("utf-8")

        with patch("justify_ip_change_copilot_chat_ui.edge_session.urllib.request.OpenerDirector.open", return_value=Response()):
            self.assertEqual(get_cdp_version("http://127.0.0.1:9445")["Browser"], "Edg/132.0.2957.127")

    def test_non_edge_cdp_identity_is_rejected(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return b'{"Browser":"Chrome/132.0","webSocketDebuggerUrl":"ws://127.0.0.1:9445/devtools/browser/test"}'

        with patch("justify_ip_change_copilot_chat_ui.edge_session.urllib.request.OpenerDirector.open", return_value=Response()):
            with self.assertRaisesRegex(CopilotUIError, "does not advertise Microsoft Edge"):
                get_cdp_version("http://127.0.0.1:9445")

    def test_launch_uses_detached_machine_safe_edge_options(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            process = type("Process", (), {
                "poll": lambda self: None,
                "terminate": lambda self: None,
                "wait": lambda self, timeout=None: 0,
            })()
            with patch("justify_ip_change_copilot_chat_ui.edge_session.find_edge", return_value=Path("msedge.exe")), patch(
                "justify_ip_change_copilot_chat_ui.edge_session.subprocess.Popen", return_value=process
            ) as popen, patch.object(session, "_port_in_use", return_value=False):
                self.assertFalse(session._launch_attempt(session.profile, session.port, timeout=0))
            command = popen.call_args.args[0]
            self.assertIn("--new-window", command)
            self.assertEqual(command[-1], "about:blank")
            self.assertIn("--remote-debugging-address=127.0.0.1", command)
            self.assertNotIn("--remote-allow-origins=*", command)

    def test_edge_handoff_keeps_polling_after_launcher_process_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            process = type("Process", (), {
                "poll": lambda self: 0,
                "terminate": lambda self: None,
                "wait": lambda self, timeout=None: 0,
            })()
            payload = {"Browser": "Edg/fixture", "webSocketDebuggerUrl": "ws://127.0.0.1:9445/devtools/browser/x"}
            with patch("justify_ip_change_copilot_chat_ui.edge_session.find_edge", return_value=Path("msedge.exe")), patch(
                "justify_ip_change_copilot_chat_ui.edge_session.subprocess.Popen", return_value=process
            ), patch.object(session, "_port_in_use", return_value=False), patch(
                "justify_ip_change_copilot_chat_ui.edge_session.get_cdp_version", side_effect=[None, payload]
            ) as probe, patch("justify_ip_change_copilot_chat_ui.edge_session.time.sleep"):
                self.assertTrue(session._launch_attempt(session.profile, session.port, timeout=1))
            self.assertEqual(probe.call_count, 2)

    def test_failed_requested_port_retries_alternate_port_and_reports_method(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            output = io.StringIO()
            with patch.object(session, "_launch_attempt", side_effect=[False, True]) as launch, contextlib.redirect_stdout(output):
                session.ensure_started(timeout=90)
            self.assertEqual(launch.call_count, 2)
            self.assertLessEqual(launch.call_args_list[0].args[2], 6)
            self.assertIn("Edge startup method: dedicated profile and alternate port", output.getvalue())

    def test_requested_port_success_uses_no_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            output = io.StringIO()
            with patch.object(session, "_launch_attempt", return_value=True) as launch, contextlib.redirect_stdout(output):
                session.ensure_started(timeout=90)
            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[1], 9445)
            self.assertIn("Edge startup method: dedicated profile and requested port", output.getvalue())

    def test_completed_adapter_disconnects_without_closing_edge(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            class Manager:
                async def stop(self):
                    return None
            adapter.manager = Manager()
            with patch.object(session, "close_owned") as retain:
                asyncio.run(adapter.close())
            retain.assert_called_once_with()

    def test_unselected_model_does_not_delay_ready_composer(self):
        ready = PlaywrightCopilotAdapter._ready_for_queue
        self.assertTrue(ready(True, None, False))
        self.assertFalse(ready(True, None, True))
        self.assertTrue(ready(True, True, True))

    def test_connected_edge_reuses_tab_and_immediately_starts_without_model_picker(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            page = SimpleNamespace(url="https://m365.cloud.microsoft/chat", bring_to_front=AsyncMock())
            context = SimpleNamespace(pages=[page], new_page=AsyncMock())
            adapter.browser = SimpleNamespace(contexts=[context])
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_first_visible", new=AsyncMock(return_value=object())
            ) as visible:
                asyncio.run(adapter._activate_copilot())
            context.new_page.assert_not_awaited()
            page.bring_to_front.assert_awaited_once()
            visible.assert_awaited_once()
            self.assertEqual(adapter.startup_diagnostics["phase"], "ready")
            self.assertTrue(adapter.startup_diagnostics["tab_reused"])

    def test_explicit_edge_policy_block_stops_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            with patch("justify_ip_change_copilot_chat_ui.edge_session.remote_debugging_blocked", return_value=True), patch.object(
                session, "_launch_attempt"
            ) as launch:
                with self.assertRaisesRegex(CopilotUIError, "policy disables remote debugging"):
                    session.ensure_started(timeout=15)
            launch.assert_not_called()

    def test_existing_validated_endpoint_reports_method(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.edge_session.get_cdp_version", return_value={"Browser": "Edg/1"}), patch(
                "justify_ip_change_copilot_chat_ui.edge_session.validate_existing_profile"
            ), contextlib.redirect_stdout(output):
                session.ensure_started(timeout=15)
            self.assertIn("Edge startup method: existing validated endpoint", output.getvalue())


if __name__ == "__main__":
    unittest.main()
