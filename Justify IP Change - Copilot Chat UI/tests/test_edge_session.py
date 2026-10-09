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
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from justify_ip_change_copilot_chat_ui.edge_session import EdgeSession, _profile_argument, get_cdp_version
from justify_ip_change_copilot_chat_ui.errors import CopilotUIError
from justify_ip_change_copilot_chat_ui.profile_storage import default_edge_profile
from justify_ip_change_copilot_chat_ui.copilot_ui import (
    ATTACH_BUTTON_SELECTORS, EDITOR_SELECTORS, SEND_SELECTORS,
    SINGLE_CASE_FILE_ASSIGN_TIMEOUT_MS, SINGLE_CASE_UPLOAD_TIMEOUT_SECONDS,
    PlaywrightCopilotAdapter,
)


class EdgeSessionTests(unittest.TestCase):
    def test_original_single_case_upload_budgets_are_preserved(self):
        self.assertEqual(SINGLE_CASE_FILE_ASSIGN_TIMEOUT_MS, 900_000)
        self.assertEqual(SINGLE_CASE_UPLOAD_TIMEOUT_SECONDS, 600)

    def test_attachment_picker_waits_for_delayed_file_input(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = PlaywrightCopilotAdapter(EdgeSession(Path(directory) / "profile"))
            inputs = SimpleNamespace(count=AsyncMock(side_effect=[0, 0, 1]))
            button = SimpleNamespace(click=AsyncMock())
            menu = SimpleNamespace(count=AsyncMock(return_value=0))
            adapter.page = SimpleNamespace(locator=Mock(return_value=inputs), get_by_role=Mock(return_value=menu))
            with patch.object(adapter, "_first_visible", new=AsyncMock(return_value=button)):
                found = asyncio.run(adapter._ensure_attachment_input())
            self.assertIs(found, inputs)
            button.click.assert_awaited_once()

    def test_attachment_chips_alone_do_not_finish_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = PlaywrightCopilotAdapter(EdgeSession(Path(directory) / "profile"))
            file_input = SimpleNamespace(set_input_files=AsyncMock())
            inputs = SimpleNamespace(count=AsyncMock(return_value=1), first=file_input)
            adapter.page = SimpleNamespace(locator=Mock(return_value=inputs))
            item = SimpleNamespace(attachments=SimpleNamespace(paths=(Path("first.pdf"), Path("second.pdf"))))
            busy = {"chip_count": 2, "matched_count": 2, "active": True, "upload_error": False, "send_enabled": True}
            ready = {**busy, "active": False}
            with patch.object(adapter, "_attachment_state", new=AsyncMock(side_effect=[busy, ready])) as snapshot, patch(
                "justify_ip_change_copilot_chat_ui.copilot_ui.TRANSFER_QUIET_SECONDS", 0
            ), patch("justify_ip_change_copilot_chat_ui.copilot_ui.asyncio.sleep", new=AsyncMock()):
                asyncio.run(adapter._attach(item))
            self.assertEqual(snapshot.await_count, 2)
            self.assertEqual(file_input.set_input_files.await_args.kwargs["timeout"], 900_000)

    def test_prompt_is_filled_before_upload_and_no_send_occurs_on_upload_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = PlaywrightCopilotAdapter(EdgeSession(Path(directory) / "profile"))
            events = []
            async def fill(_):
                events.append("fill")
            async def attach(_):
                events.append("attach")
                raise CopilotUIError("synthetic pre-send upload failure")
            editor = SimpleNamespace(fill=fill)
            item = SimpleNamespace(prompt="synthetic prompt", attachments=SimpleNamespace(paths=(Path("first.pdf"),)))
            with patch.object(adapter, "_fresh_chat", new=AsyncMock()), patch.object(
                adapter, "_first_visible", new=AsyncMock(return_value=editor)
            ), patch.object(adapter, "_editor_text", new=AsyncMock(return_value=item.prompt)), patch.object(
                adapter, "_attach", side_effect=attach
            ):
                with self.assertRaises(CopilotUIError):
                    asyncio.run(adapter.process(item))
            self.assertEqual(events, ["fill", "attach"])
            self.assertFalse(adapter.case_diagnostics["send_attempted"])

    def test_parallel_tab_pool_reuses_marked_empty_tab_then_creates_one(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = PlaywrightCopilotAdapter(EdgeSession(Path(directory) / "profile"), tab_count=3)
            main = SimpleNamespace(url="https://m365.cloud.microsoft/chat", evaluate=AsyncMock())
            existing = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat", evaluate=AsyncMock(return_value="JustifyIPChange-Worker"),
                locator=Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=0))),
            )
            fresh = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat", goto=AsyncMock(), evaluate=AsyncMock(),
            )
            context = SimpleNamespace(pages=[main, existing], new_page=AsyncMock(return_value=fresh))
            adapter.page = main
            adapter.context = context
            adapter.browser = SimpleNamespace(contexts=[context])
            with patch.object(PlaywrightCopilotAdapter, "_wait_for_ready", new=AsyncMock(return_value=True)), patch.object(
                PlaywrightCopilotAdapter, "_first_visible", new=AsyncMock(return_value=object())
            ), patch.object(PlaywrightCopilotAdapter, "_editor_text", new=AsyncMock(return_value="")):
                asyncio.run(adapter._prepare_parallel_tabs())
            self.assertEqual(adapter.parallelism, 3)
            self.assertEqual(adapter._tab_pool.qsize(), 3)
            context.new_page.assert_awaited_once()
            fresh.goto.assert_awaited_once()

    def test_working_agent_editor_attachment_and_send_variants_are_available(self):
        self.assertIn("#m365-chat-editor-target-element", EDITOR_SELECTORS)
        self.assertIn("button[data-testid='chat-input-attach-button']", ATTACH_BUTTON_SELECTORS)
        self.assertIn("button[type='submit'][aria-label*='send' i]:not([aria-label*='stop' i])", SEND_SELECTORS)

    def test_microsoft_login_frame_is_classified_without_recording_its_url(self):
        page = SimpleNamespace(
            url="https://m365.cloud.microsoft/chat",
            frames=[SimpleNamespace(url="https://m365.cloud.microsoft/chat"), SimpleNamespace(url="https://login.microsoftonline.com/common")],
        )
        self.assertEqual(PlaywrightCopilotAdapter._page_category(page), "login")

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
            adapter.manager = SimpleNamespace(stop=AsyncMock())
            adapter.playwright = SimpleNamespace(stop=AsyncMock())
            adapter.browser = SimpleNamespace(close=AsyncMock())
            adapter.page = SimpleNamespace(close=AsyncMock())
            manager = adapter.manager
            playwright = adapter.playwright
            browser = adapter.browser
            page = adapter.page
            with patch.object(session, "close_owned") as retain:
                asyncio.run(adapter.close())
            playwright.stop.assert_awaited_once_with()
            manager.stop.assert_not_awaited()
            browser.close.assert_not_awaited()
            page.close.assert_not_awaited()
            self.assertIsNone(adapter.playwright)
            retain.assert_called_once_with()

    def test_unselected_model_does_not_delay_ready_composer(self):
        ready = PlaywrightCopilotAdapter._ready_for_queue
        self.assertTrue(ready(True, None, False))
        self.assertFalse(ready(True, None, True))
        self.assertTrue(ready(True, True, True))

    def test_ready_retained_tab_starts_queue_without_navigation_or_send(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            page = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            context = SimpleNamespace(pages=[page], new_page=AsyncMock())
            adapter.browser = SimpleNamespace(contexts=[context])
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(return_value=True), create=True
            ) as ready, patch.object(adapter, "_page_is_empty", new=AsyncMock(return_value=True)), patch.object(
                adapter, "process", new=AsyncMock()
            ) as process, contextlib.redirect_stdout(output):
                asyncio.run(adapter._activate_copilot())
            context.new_page.assert_not_awaited()
            page.goto.assert_not_awaited()
            page.reload.assert_not_awaited()
            page.bring_to_front.assert_awaited_once()
            ready.assert_awaited_once()
            process.assert_not_awaited()
            self.assertEqual(adapter.startup_diagnostics["phase"], "ready")
            self.assertTrue(adapter.startup_diagnostics["tab_reused"])
            self.assertIn("\033[92m", output.getvalue())
            self.assertIn("retained tab", output.getvalue())
            self.assertEqual(output.getvalue().count("retained tab"), 1)

    def test_retained_tab_with_draft_is_preserved_and_new_tab_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = PlaywrightCopilotAdapter(EdgeSession(Path(directory) / "profile"))
            old = SimpleNamespace(url="https://m365.cloud.microsoft/chat", evaluate=AsyncMock(return_value="JustifyIPChange-Worker"), bring_to_front=AsyncMock(), goto=AsyncMock())
            fresh = SimpleNamespace(url="https://m365.cloud.microsoft/chat", bring_to_front=AsyncMock(), goto=AsyncMock())
            adapter.browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[old], new_page=AsyncMock(return_value=fresh))])
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(return_value=True)
            ), patch.object(adapter, "_page_is_empty", new=AsyncMock(return_value=False)):
                asyncio.run(adapter._activate_copilot())
            old.goto.assert_not_awaited()
            fresh.goto.assert_awaited_once()
            self.assertIs(adapter.page, fresh)

    def test_unready_retained_tab_opens_one_new_tab_without_touching_old_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            old = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            new = SimpleNamespace(
                url="about:blank", bring_to_front=AsyncMock(), goto=AsyncMock(),
                reload=AsyncMock(), is_closed=lambda: False,
            )
            context = SimpleNamespace(pages=[old], new_page=AsyncMock(return_value=new))
            adapter.browser = SimpleNamespace(contexts=[context])
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(side_effect=[False, True]), create=True
            ) as ready, contextlib.redirect_stdout(output):
                asyncio.run(adapter._activate_copilot())
            self.assertEqual(ready.await_count, 2)
            context.new_page.assert_awaited_once()
            old.goto.assert_not_awaited()
            old.reload.assert_not_awaited()
            new.goto.assert_awaited_once()
            new.reload.assert_not_awaited()
            self.assertIs(adapter.page, new)
            self.assertIn("\033[92m", output.getvalue())
            self.assertIn("new tab", output.getvalue())
            self.assertEqual(output.getvalue().count("new tab"), 1)

    def test_no_retained_tab_starts_in_one_new_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            new = SimpleNamespace(
                url="about:blank", bring_to_front=AsyncMock(), goto=AsyncMock(),
                reload=AsyncMock(), is_closed=lambda: False,
            )
            context = SimpleNamespace(pages=[], new_page=AsyncMock(return_value=new))
            adapter.browser = SimpleNamespace(contexts=[context])
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(return_value=True), create=True
            ) as ready, contextlib.redirect_stdout(output):
                asyncio.run(adapter._activate_copilot())
            ready.assert_awaited_once()
            context.new_page.assert_awaited_once()
            new.goto.assert_awaited_once()
            new.reload.assert_not_awaited()
            self.assertIs(adapter.page, new)
            self.assertIn("\033[92m", output.getvalue())
            self.assertIn("new tab", output.getvalue())
            self.assertEqual(output.getvalue().count("new tab"), 1)

    def test_new_tab_navigation_retry_is_bounded_and_does_not_touch_retained_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            old = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            new = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            context = SimpleNamespace(pages=[old], new_page=AsyncMock(return_value=new))
            adapter.browser = SimpleNamespace(contexts=[context])
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(side_effect=[False, False, True]), create=True
            ) as ready, contextlib.redirect_stdout(output):
                asyncio.run(adapter._activate_copilot())
            self.assertEqual(ready.await_count, 3)
            context.new_page.assert_awaited_once()
            old.goto.assert_not_awaited()
            old.reload.assert_not_awaited()
            self.assertEqual(new.goto.await_count, 2)
            self.assertIs(adapter.page, new)
            self.assertIn("\033[92m", output.getvalue())
            self.assertIn("new tab navigation retry", output.getvalue())
            self.assertEqual(output.getvalue().count("new tab navigation retry"), 1)

    def test_sign_in_waits_in_new_tab_without_navigation_retry_or_send(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session, startup_timeout=37)
            old = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            new = SimpleNamespace(
                url="https://login.microsoftonline.com/example",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            context = SimpleNamespace(pages=[old], new_page=AsyncMock(return_value=new))
            adapter.browser = SimpleNamespace(contexts=[context])
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(side_effect=[False, False, True]), create=True
            ) as ready, patch.object(adapter, "process", new=AsyncMock()) as process, contextlib.redirect_stdout(output):
                asyncio.run(adapter._activate_copilot())
            self.assertEqual(ready.await_count, 3)
            self.assertEqual(ready.await_args_list[-1].args[1], 37)
            context.new_page.assert_awaited_once()
            old.goto.assert_not_awaited()
            old.reload.assert_not_awaited()
            new.goto.assert_awaited_once()
            new.reload.assert_not_awaited()
            process.assert_not_awaited()
            self.assertEqual(adapter.startup_diagnostics["phase"], "ready")
            self.assertIn("\033[92m", output.getvalue())
            self.assertIn("sign-in completed", output.getvalue())
            self.assertEqual(output.getvalue().count("sign-in completed"), 1)

    def test_unready_copilot_fails_before_send_after_bounded_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            adapter = PlaywrightCopilotAdapter(session)
            old = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            new = SimpleNamespace(
                url="https://m365.cloud.microsoft/chat",
                bring_to_front=AsyncMock(), goto=AsyncMock(), reload=AsyncMock(),
                is_closed=lambda: False,
            )
            context = SimpleNamespace(pages=[old], new_page=AsyncMock(return_value=new))
            adapter.browser = SimpleNamespace(contexts=[context])
            output = io.StringIO()
            with patch("justify_ip_change_copilot_chat_ui.copilot_ui.validate_existing_profile"), patch.object(
                adapter, "_wait_for_ready", new=AsyncMock(side_effect=[False, False, False]), create=True
            ) as ready, patch.object(
                adapter, "_capture_readiness_state", new=AsyncMock(), create=True
            ) as snapshot, patch.object(adapter, "process", new=AsyncMock()) as process, contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(CopilotUIError, "No case was sent"):
                    asyncio.run(adapter._activate_copilot())
            self.assertEqual(ready.await_count, 3)
            snapshot.assert_awaited_once()
            self.assertEqual(new.goto.await_count, 2)
            old.goto.assert_not_awaited()
            old.reload.assert_not_awaited()
            process.assert_not_awaited()
            self.assertNotIn("\033[92mCopilot readiness method:", output.getvalue())

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
