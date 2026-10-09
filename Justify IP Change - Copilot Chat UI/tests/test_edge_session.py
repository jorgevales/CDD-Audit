from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from justify_ip_change_copilot_chat_ui.edge_session import EdgeSession


class EdgeSessionTests(unittest.TestCase):
    def test_failed_requested_port_retries_alternate_port_and_reports_method(self):
        with tempfile.TemporaryDirectory() as directory:
            session = EdgeSession(Path(directory) / "EdgeProfile", port=9445)
            output = io.StringIO()
            with patch.object(session, "_launch_attempt", side_effect=[False, True]) as launch, contextlib.redirect_stdout(output):
                session.ensure_started(timeout=90)
            self.assertEqual(launch.call_count, 2)
            self.assertIn("Edge startup method: dedicated profile and alternate port", output.getvalue())

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
